import { ApiError, type FieldErrors } from "@/lib/api/errors";

export interface ApiClientOptions {
  baseUrl: string;
  getAccessToken: () => string | null;
  onUnauthorized: () => void;
}

export interface ApiRequestOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
}

export interface ApiClient {
  request<T>(path: string, options?: ApiRequestOptions): Promise<T>;
}

const NETWORK_ERROR_MESSAGE = "Không thể kết nối đến máy chủ.";
const FALLBACK_ERROR_MESSAGE = "Yêu cầu không thành công.";

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

function messageFromPayload(payload: unknown, status: number): string {
  if (typeof payload === "string" && payload.trim()) {
    return payload;
  }

  if (payload && typeof payload === "object") {
    const record = payload as Record<string, unknown>;
    if (typeof record.detail === "string" && record.detail.trim()) {
      return record.detail;
    }
    if (Array.isArray(record.non_field_errors)) {
      const first = record.non_field_errors.find((item) => typeof item === "string");
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

  return {
    async request<T>(path: string, options: ApiRequestOptions = {}) {
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

      let response: Response;
      try {
        response = await fetch(`${normalizedBaseUrl}${path.startsWith("/") ? path : `/${path}`}`, {
          ...options,
          body,
          headers,
        });
      } catch {
        throw new ApiError({ status: 0, message: NETWORK_ERROR_MESSAGE });
      }

      if (response.ok) {
        if (accessToken && lastUnauthorizedToken !== accessToken) {
          lastUnauthorizedToken = null;
        }
        if (response.status === 204) {
          return undefined as T;
        }
        return (await parseResponseBody(response)) as T;
      }

      const payload = await parseResponseBody(response);
      const requestId = response.headers.get("x-request-id") ?? undefined;
      const fieldErrors = payload && typeof payload === "object" && !Array.isArray(payload)
        ? normalizeFieldErrors(payload as Record<string, unknown>)
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
      });
    },
  };
}
