import { describe, expect, it } from "vitest";

import { loginErrorMessage } from "@/features/auth/errorMessages";
import { ApiError } from "@/lib/api/errors";

function error(init: { status: number; code?: string; message?: string; retryAfterSeconds?: number }) {
  return new ApiError({ message: "Từ máy chủ", ...init });
}

describe("loginErrorMessage", () => {
  it.each([
    [{ status: 401, code: "INVALID_CREDENTIALS" }, "Email hoặc mật khẩu không đúng."],
    [{ status: 403, code: "ACCOUNT_PENDING_ACTIVATION" }, "Tài khoản chưa được kích hoạt. Hãy kiểm tra email kích hoạt."],
    [{ status: 403, code: "ACCOUNT_SUSPENDED" }, "Tài khoản đã bị khóa. Liên hệ quản trị viên."],
    [{ status: 503, code: "IDENTITY_UNAVAILABLE" }, "Dịch vụ đăng nhập tạm thời không khả dụng."],
    [{ status: 503 }, "Dịch vụ đăng nhập tạm thời không khả dụng."],
    [{ status: 418, code: "SOMETHING_ELSE" }, "Từ máy chủ"],
    [{ status: 0 }, "Từ máy chủ"],
  ])("maps %o", (init, expected) => {
    expect(loginErrorMessage(error(init))).toBe(expected);
  });

  it("maps an unverified email reported as a validation error", () => {
    const unverified = new ApiError({
      status: 400,
      message: "Từ máy chủ",
      code: "VALIDATION_ERROR",
      fieldErrors: { non_field_errors: ["E-mail is not verified."] },
    });
    expect(loginErrorMessage(unverified)).toBe("Email chưa được xác minh. Hãy kiểm tra email kích hoạt.");
  });

  it("rounds Retry-After up to minutes on rate limit", () => {
    expect(loginErrorMessage(error({ status: 429, code: "RATE_LIMIT_EXCEEDED", retryAfterSeconds: 61 }))).toBe(
      "Bạn đã đăng nhập sai quá nhiều lần. Thử lại sau 2 phút.",
    );
  });

  it("defaults to 15 minutes without Retry-After", () => {
    expect(loginErrorMessage(error({ status: 429 }))).toBe(
      "Bạn đã đăng nhập sai quá nhiều lần. Thử lại sau 15 phút.",
    );
  });
});
