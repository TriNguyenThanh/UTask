import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { LoginForm } from "@/features/auth/components/LoginForm";
import { server } from "@/mocks/server";
import { renderApp } from "@/test/render";

function failLogin(status: number, code: string, headers: Record<string, string> = {}) {
  server.use(
    http.post("/api/auth/login", () =>
      HttpResponse.json(
        { success: false, message: "Từ máy chủ", data: null, error: { code, details: [] } },
        { status, headers },
      )),
  );
}

async function submit(password = "x") {
  const user = userEvent.setup();
  renderApp(<LoginForm />, { route: "/login", session: null });
  await user.type(await screen.findByLabelText("Email trường học"), "a@b.vn");
  await user.type(screen.getByLabelText("Mật khẩu"), password);
  await user.click(screen.getByRole("button", { name: "Đăng nhập" }));
}

describe("LoginForm errors", () => {
  it.each([
    [401, "INVALID_CREDENTIALS", {}, "Email hoặc mật khẩu không đúng."],
    [403, "ACCOUNT_PENDING_ACTIVATION", {}, "Tài khoản chưa được kích hoạt. Hãy kiểm tra email kích hoạt."],
    [403, "ACCOUNT_SUSPENDED", {}, "Tài khoản đã bị khóa. Liên hệ quản trị viên."],
    [429, "RATE_LIMIT_EXCEEDED", { "Retry-After": "300" }, "Bạn đã đăng nhập sai quá nhiều lần. Thử lại sau 5 phút."],
    [503, "IDENTITY_UNAVAILABLE", {}, "Dịch vụ đăng nhập tạm thời không khả dụng."],
  ])("shows the message for %i %s", async (status, code, headers, text) => {
    failLogin(status, code, headers);
    await submit();
    expect(await screen.findByText(text)).toBeInTheDocument();
  });

  it("accepts a short password and lets the server decide", async () => {
    failLogin(401, "INVALID_CREDENTIALS");
    await submit("a");
    expect(await screen.findByText("Email hoặc mật khẩu không đúng.")).toBeInTheDocument();
    expect(screen.queryByText(/ít nhất 8 ký tự/)).not.toBeInTheDocument();
  });
});
