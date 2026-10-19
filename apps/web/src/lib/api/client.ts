import { z } from "zod";

import { ApiError, type ApiErrorDetail, type FieldErrors } from "@/lib/api/errors";

export interface ApiClientOptions {
  baseUrl: string;
  getAccessToken: () => string | null;
  onUnauthorized: () => void;
}

export interface ApiRequestOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
  /** Gửi header `Idempotency-Key` (bắt buộc với POST/PATCH của Classroom và Work). */
  idempotencyKey?: string;
}

export interface ApiEnvelopeResult<T, M> {
  data: T;
  meta: M | null;
  message: string;
}

export interface ApiClient {
  /** Trả body thô; dùng cho API mock cũ không có envelope. */
  request<T>(path: string, options?: ApiRequestOptions): Promise<T>;
  /** Dùng cho API thật: kiểm envelope `{success, message, data, meta, error}`. */
  requestEnvelope<T, M = unknown>(path: string, options?: ApiRequestOptions): Promise<ApiEnvelopeResult<T, M>>;
}

const NETWORK_ERROR_MESSAGE = "Không thể kết nối đến máy chủ.";
const FALLBACK_ERROR_MESSAGE = "Yêu cầu không thành công.";
const MALFORMED_RESPONSE_MESSAGE = "Phản hồi máy chủ không đúng định dạng.";

const detailSchema = z.object({ field: z.string().optional(), issue: z.string() });
const errorEnvelopeSchema = z.object({
  success: z.literal(false).optional(),
  message: z.string().optional(),
  error: z.object({ code: z.string(), details: z.array(z.unknown()).optional() }),
});
const successEnvelopeSchema = z.object({
  success: z.literal(true),
  message: z.string().optional(),
  data: z.unknown(),
  meta: z.unknown().optional(),
});
/** Lỗi kiểu cũ (DRF/MSW): `{detail}`, `{non_field_errors}`, `{field: string[]}`. */
const legacyErrorSchema = z.record(z.string(), z.unknown());

function normalizeFieldErrors(payload: Record<string, unknown>): FieldErrors {
  const fieldErrors: FieldErrors = {};

  for (const [field, value] of Object.entries(payload)) {
    if (field === "detail" || field === "non_field_errors") {
      continue;
    }

    if (Array.isArray(value) && value.every((item) => typeof item === "string")) {
      fieldErrors[field] = value;
    }
  }

  return fieldErrors;
}

interface EnvelopeError {
  code: string;
  details: ApiErrorDetail[];
  fieldErrors: FieldErrors;
}

function parseEnvelopeError(payload: unknown): EnvelopeError | null {
  const parsed = errorEnvelopeSchema.safeParse(payload);
  if (!parsed.success) {
    return null;
  }

  const details: ApiErrorDetail[] = [];
  const fieldErrors: FieldErrors = {};

  for (const item of parsed.data.error.details ?? []) {
    const detail = detailSchema.safeParse(item);
    if (!detail.success) {
      continue;
    }
    const { field, issue } = detail.data;
    details.push(field ? { field, issue } : { issue });
    if (field) {
      fieldErrors[field] = [...(fieldErrors[field] ?? []), issue];
    }
  }

  return { code: parsed.data.error.code, details, fieldErrors };
}

function messageFromPayload(payload: unknown, status: number): string {
  if (typeof payload === "string" && payload.trim()) {
    return payload;
  }

  const envelope = errorEnvelopeSchema.safeParse(payload);
  if (envelope.success && envelope.data.message?.trim()) {
    return envelope.data.message;
  }

  const legacy = legacyErrorSchema.safeParse(payload);
  if (legacy.success) {
    const { detail, non_field_errors: nonFieldErrors } = legacy.data;
    if (typeof detail === "string" && detail.trim()) {
      return detail;
    }
    if (Array.isArray(nonFieldErrors)) {
      const first = nonFieldErrors.find((item) => typeof item === "string");
      if (typeof first === "string") {
        return first;
      }
    }
  }

  if (status === 403) {
    return "Bạn không có quyền thực hiện thao tác này.";
  }
  if (status === 404) {
    return "Không tìm thấy dữ liệu yêu cầu.";
  }
  return FALLBACK_ERROR_MESSAGE;
}

function parseRetryAfter(response: Response): number | null {
  const raw = response.headers.get("retry-after");
  if (!raw || !/^\d+$/.test(raw.trim())) {
    return null;
  }
  return Number.parseInt(raw, 10);
}

async function parseResponseBody(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!text) {
    return undefined;
  }

  try {
    return JSON.parse(text) as unknown;
  } catch {
    return text;
  }
}

export function createApiClient({ baseUrl, getAccessToken, onUnauthorized }: ApiClientOptions): ApiClient {
  const normalizedBaseUrl = baseUrl.replace(/\/$/, "");
  let lastUnauthorizedToken: string | null = null;

  async function execute(
    path: string,
    { idempotencyKey, ...options }: ApiRequestOptions,
  ): Promise<{ status: number; payload: unknown }> {
    const accessToken = getAccessToken();
    const headers = new Headers(options.headers);
    headers.set("Accept", "application/json");

    let body: BodyInit | undefined;
    if (options.body !== undefined) {
      headers.set("Content-Type", "application/json");
      body = JSON.stringify(options.body);
    }
    if (accessToken) {
      headers.set("Authorization", `Bearer ${accessToken}`);
    }
    if (idempotencyKey) {
      headers.set("Idempotency-Key", idempotencyKey);
    }

    let response: Response;
    try {
      response = await fetch(`${normalizedBaseUrl}${path.startsWith("/") ? path : `/${path}`}`, {
        ...options,
        body,
        headers,
        credentials: "include",
      });
    } catch {
      throw new ApiError({ status: 0, message: NETWORK_ERROR_MESSAGE });
    }

    if (response.ok) {
      if (accessToken && lastUnauthorizedToken !== accessToken) {
        lastUnauthorizedToken = null;
      }
      const payload = response.status === 204 ? undefined : await parseResponseBody(response);
      return { status: response.status, payload };
    }

    const payload = await parseResponseBody(response);
    const requestId = response.headers.get("x-request-id") ?? undefined;
    const envelopeError = parseEnvelopeError(payload);
    const legacy = legacyErrorSchema.safeParse(payload);
    const fieldErrors = envelopeError
      ? envelopeError.fieldErrors
      : legacy.success
        ? normalizeFieldErrors(legacy.data)
        : {};

    if (response.status === 401 && accessToken && lastUnauthorizedToken !== accessToken) {
      lastUnauthorizedToken = accessToken;
      onUnauthorized();
    }

    throw new ApiError({
      status: response.status,
      message: messageFromPayload(payload, response.status),
      fieldErrors,
      requestId,
      code: envelopeError?.code,
      details: envelopeError?.details,
      retryAfterSeconds: parseRetryAfter(response),
    });
  }

  return {
    async request<T>(path: string, options: ApiRequestOptions = {}) {
      const { status, payload } = await execute(path, options);
      return (status === 204 ? undefined : payload) as T;
    },

    async requestEnvelope<T, M = unknown>(path: string, options: ApiRequestOptions = {}) {
      const { status, payload } = await execute(path, options);

      // 204 không có body để kiểm: không phải phản hồi sai định dạng.
      if (status === 204) {
        return { data: undefined as T, meta: null, message: "" };
      }
      const envelope = successEnvelopeSchema.safeParse(payload);
      if (!envelope.success) {
        throw new ApiError({ status, message: MALFORMED_RESPONSE_MESSAGE });
      }

      return {
        data: envelope.data.data as T,
        meta: (envelope.data.meta ?? null) as M | null,
        message: envelope.data.message ?? "",
      };
    },
  };
}
