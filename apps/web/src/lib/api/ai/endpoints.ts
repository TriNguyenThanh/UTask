import type { ApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import type { AiContextDto, AiRequestBody, AiResponseDto } from "@/lib/api/ai/dto";

/** Gateway chuyển nguyên đường dẫn `/api/ai/...` cho AI Service, service phục vụ dưới `/api/ai/v1`. */
export const AI_ROOT = "/api/ai/v1";

/** `Idempotency-Key` bắt buộc. Phản hồi không có envelope nên dùng `request` thô. */
export function createAiRequest(client: ApiClient, body: AiRequestBody, idempotencyKey: string, signal?: AbortSignal) {
  return client.request<AiResponseDto<unknown>>(`${AI_ROOT}/requests`, {
    method: "POST",
    body,
    idempotencyKey,
    signal,
  });
}

export function getAiRequest(client: ApiClient, requestId: string, signal?: AbortSignal) {
  return client.request<AiResponseDto<unknown>>(`${AI_ROOT}/requests/${encodeURIComponent(requestId)}`, { signal });
}

export interface RunAiOptions {
  idempotencyKey: string;
  signal?: AbortSignal;
  intervalMs?: number;
  /** Server dừng cứng ở 30 giây; thêm biên cho độ trễ mạng. */
  maxWaitMs?: number;
  sleep?: (ms: number, signal?: AbortSignal) => Promise<void>;
  now?: () => number;
}

export interface AiRunResult<R> {
  requestId: string;
  result: R;
  context: AiContextDto;
}

function abortError() {
  return new DOMException("Aborted", "AbortError");
}

export function defaultSleep(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(abortError());
      return;
    }
    const timer = setTimeout(() => {
      signal?.removeEventListener("abort", onAbort);
      resolve();
    }, ms);
    function onAbort() {
      clearTimeout(timer);
      reject(abortError());
    }
    signal?.addEventListener("abort", onAbort, { once: true });
  });
}

/** Client biến fetch bị hủy thành lỗi mạng; ở đây trả lại đúng `AbortError` để UI phân biệt với mất kết nối. */
async function unlessAborted<T>(call: Promise<T>, signal?: AbortSignal): Promise<T> {
  try {
    return await call;
  } catch (error) {
    throw signal?.aborted ? abortError() : error;
  }
}

/**
 * Gửi yêu cầu AI rồi chờ kết quả: 200 trả ngay, 202 thì hỏi lại theo chu kỳ.
 * Hủy bằng `signal` chỉ dừng phía trình duyệt; request vẫn chạy ở server.
 * `result` được ép kiểu, endpoint không kiểm schema (giống DTO Work).
 */
export async function runAiRequest<R>(client: ApiClient, body: AiRequestBody, options: RunAiOptions): Promise<AiRunResult<R>> {
  const { idempotencyKey, signal, intervalMs = 1500, maxWaitMs = 45_000, sleep = defaultSleep, now = Date.now } = options;
  const startedAt = now();
  let response = await unlessAborted(createAiRequest(client, body, idempotencyKey, signal), signal);

  for (;;) {
    if (response.status === "succeeded") {
      return { requestId: response.request_id, result: response.result as R, context: response.context };
    }
    if (response.status === "failed") {
      throw new ApiError({ status: 502, code: response.error.code, message: response.error.message });
    }
    if (signal?.aborted) {
      throw abortError();
    }
    if (now() - startedAt >= maxWaitMs) {
      throw new ApiError({ status: 504, code: "WORKFLOW_TIMEOUT", message: "AI xử lý quá lâu." });
    }
    await sleep(intervalMs, signal);
    response = await unlessAborted(getAiRequest(client, response.request_id, signal), signal);
  }
}
