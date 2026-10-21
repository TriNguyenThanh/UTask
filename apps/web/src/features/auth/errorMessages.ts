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

  // Backend trả email chưa xác minh dưới dạng VALIDATION_ERROR, không phải ACCOUNT_PENDING_ACTIVATION.
  if (error.fieldErrors.non_field_errors?.some((message) => /not verified/i.test(message))) {
    return "Email chưa được xác minh. Hãy kiểm tra email kích hoạt.";
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

/** Thông báo cho form khôi phục/gửi lại email; không bao giờ báo "đã gửi" khi lỗi. */
export function recoveryErrorMessage(error: ApiError): string {
  if (error.status === 503 || error.code === "IDENTITY_UNAVAILABLE") {
    return "Tính năng tạm thời không khả dụng. Hãy thử lại sau.";
  }
  if (error.status === 429 || error.code === "RATE_LIMIT_EXCEEDED") {
    return "Bạn thao tác quá nhiều lần. Hãy thử lại sau ít phút.";
  }
  return error.message;
}

export const NEUTRAL_RECOVERY_MESSAGE = "Nếu email tồn tại, bạn sẽ nhận được hướng dẫn.";

/** Link kích hoạt sai/hết hạn: backend trả 404 RESOURCE_NOT_FOUND hoặc INVALID_ACTIVATION_TOKEN. */
export function activationErrorMessage(error: ApiError): string {
  switch (error.code) {
    case "ACCOUNT_ALREADY_ACTIVE":
      return "Tài khoản đã kích hoạt. Bạn có thể đăng nhập.";
    case "RESOURCE_NOT_FOUND":
    case "INVALID_ACTIVATION_TOKEN":
      return "Liên kết kích hoạt không hợp lệ hoặc đã hết hạn.";
    default:
      return recoveryErrorMessage(error);
  }
}

/** Token đặt lại mật khẩu sai/hết hạn nằm ở lỗi trường `token` hoặc `uid`. */
export function isInvalidResetLink(error: ApiError): boolean {
  return Boolean(error.fieldErrors.token?.length || error.fieldErrors.uid?.length || error.code === "INVALID_TOKEN");
}

/** Django trả lỗi mật khẩu cũ bằng tiếng Anh; các thông báo lạ giữ nguyên. */
export function oldPasswordMessages(messages: readonly string[] | undefined): string[] | undefined {
  return messages?.map((message) =>
    /old password was entered incorrectly/i.test(message) ? "Mật khẩu hiện tại không đúng." : message,
  );
}
