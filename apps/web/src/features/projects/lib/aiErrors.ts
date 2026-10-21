import { ApiError } from "@/lib/api/errors";

/** Thông báo cho lỗi gọi AI. Chuỗi rỗng = không hiện gì (người dùng tự hủy). */
export function aiErrorMessage(error: unknown): string {
  if (error instanceof DOMException && error.name === "AbortError") return "";
  if (!(error instanceof ApiError)) return "Không gọi được AI.";
  switch (error.code) {
    case "RATE_LIMITED":
      return error.retryAfterSeconds === null
        ? "Bạn đã gửi quá nhiều yêu cầu AI. Thử lại sau ít phút."
        : `Bạn đã gửi quá nhiều yêu cầu AI. Thử lại sau ${error.retryAfterSeconds} giây.`;
    case "TARGET_ACCESS_DENIED":
      return "Bạn không có quyền dùng AI cho mục này.";
    case "INVALID_INPUT":
    case "INVALID_REQUEST":
      return `Dữ liệu gửi cho AI không hợp lệ: ${error.message}`;
    case "PROVIDER_UNAVAILABLE":
      return "AI tạm thời không khả dụng. Vui lòng thử lại sau.";
    case "WORKFLOW_TIMEOUT":
      return "AI xử lý quá lâu. Vui lòng thử lại.";
    default:
      return error.message;
  }
}
