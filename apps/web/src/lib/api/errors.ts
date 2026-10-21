/**
 * API error types shared by the HTTP client and the UI layer.
 */

export type FieldErrors = Record<string, string[]>;

export interface ApiErrorDetail {
  field?: string;
  issue: string;
}

export interface ApiErrorInit {
  status: number;
  message: string;
  fieldErrors?: FieldErrors;
  requestId?: string;
  code?: string | null;
  details?: ApiErrorDetail[];
  retryAfterSeconds?: number | null;
}

/** HTTP or network error returned by {@link "../api/client" | ApiClient}. */
export class ApiError extends Error {
  /** HTTP status; `0` for network failures. */
  readonly status: number;
  /** Per-field validation errors extracted from the response payload. */
  readonly fieldErrors: FieldErrors;
  /** Server request id from `x-request-id`, when present. */
  readonly requestId?: string;
  /** Mã lỗi nghiệp vụ trong envelope (`error.code`), `null` khi không có. */
  readonly code: string | null;
  /** Chi tiết lỗi theo envelope (`error.details`). */
  readonly details: ApiErrorDetail[];
  /** Giá trị header `Retry-After` (giây), `null` khi không có. */
  readonly retryAfterSeconds: number | null;

  constructor(init: ApiErrorInit) {
    super(init.message);
    this.name = "ApiError";
    this.status = init.status;
    this.fieldErrors = init.fieldErrors ?? {};
    this.requestId = init.requestId;
    this.code = init.code ?? null;
    this.details = init.details ?? [];
    this.retryAfterSeconds = init.retryAfterSeconds ?? null;
  }
}