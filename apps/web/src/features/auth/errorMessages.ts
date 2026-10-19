import type { ApiError } from "@/lib/api/errors";

const DEFAULT_LOCK_MINUTES = 15;

/** Thông báo đăng nhập; không bao giờ tiết lộ email có tồn tại hay không. */
export function loginErrorMessage(error: ApiError): string {
  if (error.status === 429 || error.code === "RATE_LIMIT_EXCEEDED") {
    const minutes = error.retryAfterSeconds ? Math.ceil(error.retryAfterSeconds / 60) : DEFAULT_LOCK_MINUTES;
    return `Bạn đã đăng nhập sai quá nhiều lần. Thử lại sau ${minutes} phút.`;
  }
  if (error.status === 503 || error.code === "IDENTITY_UNAVAILABLE") {
    return "Dịch vụ đăng nhập tạm thời không khả dụng.";
  }

  switch (error.code) {
    case "INVALID_CREDENTIALS":
      return "Email hoặc mật khẩu không đúng.";
    case "ACCOUNT_PENDING_ACTIVATION":
      return "Tài khoản chưa được kích hoạt. Hãy kiểm tra email kích hoạt.";
    case "ACCOUNT_SUSPENDED":
      return "Tài khoản đã bị khóa. Liên hệ quản trị viên.";
    default:
      return error.message;
  }
}
