import { describe, expect, it } from "vitest";

import { aiErrorMessage } from "@/features/projects/lib/aiErrors";
import { ApiError } from "@/lib/api/errors";

function api(code: string, extra: { status?: number; message?: string; retryAfterSeconds?: number } = {}) {
  return new ApiError({ status: extra.status ?? 400, code, message: extra.message ?? "msg", retryAfterSeconds: extra.retryAfterSeconds });
}

describe("aiErrorMessage", () => {
  it("is empty when the user aborted", () => {
    expect(aiErrorMessage(new DOMException("Aborted", "AbortError"))).toBe("");
  });

  it("tells how long to wait when rate limited with a delay", () => {
    expect(aiErrorMessage(api("RATE_LIMITED", { status: 429, retryAfterSeconds: 7 }))).toBe(
      "Bạn đã gửi quá nhiều yêu cầu AI. Thử lại sau 7 giây.",
    );
  });

  it("falls back to a generic wait when rate limited without a delay", () => {
    expect(aiErrorMessage(api("RATE_LIMITED", { status: 429 }))).toBe(
      "Bạn đã gửi quá nhiều yêu cầu AI. Thử lại sau ít phút.",
    );
  });

  it.each([
    ["TARGET_ACCESS_DENIED", "Bạn không có quyền dùng AI cho mục này."],
    ["PROVIDER_UNAVAILABLE", "AI tạm thời không khả dụng. Vui lòng thử lại sau."],
    ["WORKFLOW_TIMEOUT", "AI xử lý quá lâu. Vui lòng thử lại."],
  ])("maps %s", (code, message) => {
    expect(aiErrorMessage(api(code))).toBe(message);
  });

  it.each(["INVALID_INPUT", "INVALID_REQUEST"])("includes the server message for %s", (code) => {
    expect(aiErrorMessage(api(code, { message: "thiếu mô tả" }))).toBe("Dữ liệu gửi cho AI không hợp lệ: thiếu mô tả");
  });

  it("passes through the message of other API errors, including network failures", () => {
    expect(aiErrorMessage(api("OTHER", { message: "Lỗi lạ" }))).toBe("Lỗi lạ");
    expect(aiErrorMessage(api("NETWORK_ERROR", { status: 0, message: "Không thể kết nối đến máy chủ." }))).toBe(
      "Không thể kết nối đến máy chủ.",
    );
  });

  it("uses a generic message for non-API errors", () => {
    expect(aiErrorMessage(new Error("x"))).toBe("Không gọi được AI.");
  });
});
