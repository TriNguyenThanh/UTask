import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { ActivateAccountForm, ACTIVATED_NOTICE } from "@/features/auth/components/ActivateAccountForm";
import { ForgotPasswordForm } from "@/features/auth/components/ForgotPasswordForm";
import { LoginForm } from "@/features/auth/components/LoginForm";
import { RegisterForm } from "@/features/auth/components/RegisterForm";
import { RESET_DONE_NOTICE, ResetPasswordForm } from "@/features/auth/components/ResetPasswordForm";
import { Component as ActivateRoute } from "@/features/auth/routes/ActivateAccountRoute";
import { Component as ResetRoute } from "@/features/auth/routes/ResetPasswordRoute";
import { MOCK_ACTIVATION_KEY, MOCK_RESET_TOKEN } from "@/mocks/handlers/auth";
import { server } from "@/mocks/server";
import { renderApp } from "@/test/render";

function failure(status: number, code: string, message: string, details: unknown[] = [], headers?: Record<string, string>) {
  return HttpResponse.json(
    { success: false, message, data: null, meta: null, error: { code, details } },
    { status, headers },
  );
}

function anonymous(element: React.ReactElement, route = "/") {
  return renderApp(element, { route, session: null });
}

describe("ForgotPasswordForm", () => {
  async function submitEmail(user: ReturnType<typeof userEvent.setup>, email = "a@st.edu.vn") {
    await user.type(screen.getByLabelText(/Email trường học/), email);
    await user.click(screen.getByRole("button", { name: /Gửi liên kết khôi phục/ }));
  }

  it("shows the same neutral message whether or not the email exists", async () => {
    const user = userEvent.setup();
    anonymous(<ForgotPasswordForm />);

    await submitEmail(user, "ghost@nowhere.vn");

    expect(await screen.findByText("Nếu email tồn tại, bạn sẽ nhận được hướng dẫn.")).toBeInTheDocument();
  });

  it("never claims the email was sent on 503", async () => {
    server.use(http.post("/api/auth/password-reset/request", () => failure(503, "IDENTITY_UNAVAILABLE", "x")));
    const user = userEvent.setup();
    anonymous(<ForgotPasswordForm />);

    await submitEmail(user);

    expect(await screen.findByText("Tính năng tạm thời không khả dụng. Hãy thử lại sau.")).toBeInTheDocument();
    expect(screen.queryByText("Nếu email tồn tại, bạn sẽ nhận được hướng dẫn.")).not.toBeInTheDocument();
  });

  it("explains throttling on 429", async () => {
    server.use(http.post("/api/auth/password-reset/request", () => failure(429, "RATE_LIMIT_EXCEEDED", "x")));
    const user = userEvent.setup();
    anonymous(<ForgotPasswordForm />);

    await submitEmail(user);

    expect(await screen.findByText(/thao tác quá nhiều lần/)).toBeInTheDocument();
  });

  it("rejects a malformed email without calling the API", async () => {
    const user = userEvent.setup();
    anonymous(<ForgotPasswordForm />);

    await submitEmail(user, "not-an-email");

    expect(await screen.findByText("Nhập địa chỉ email trường học hợp lệ.")).toBeInTheDocument();
  });
});

describe("ResetPasswordForm / route", () => {
  async function fill(user: ReturnType<typeof userEvent.setup>, p1: string, p2: string) {
    await user.type(screen.getByLabelText("Mật khẩu mới"), p1);
    await user.type(screen.getByLabelText("Xác nhận mật khẩu mới"), p2);
    await user.click(screen.getByRole("button", { name: /Cập nhật mật khẩu/ }));
  }

  it("sends uid, token and both passwords, then goes to /login with a notice", async () => {
    let body: unknown;
    server.use(
      http.post("/api/auth/password-reset/confirm", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ success: true, message: "OK", data: null, meta: null, error: null });
      }),
    );
    const user = userEvent.setup();
    const { router } = renderApp(<div />, {
      route: `/auth/reset?uid=u1&token=${MOCK_RESET_TOKEN}`,
      session: null,
      routes: [
        { path: "/auth/reset", element: <ResetRoute /> },
        { path: "/login", element: <LoginForm /> },
      ],
    });

    await fill(user, "Newpass#2026", "Newpass#2026");

    await waitFor(() => expect(router.state.location.pathname).toBe("/login"));
    expect(body).toEqual({ uid: "u1", token: MOCK_RESET_TOKEN, new_password1: "Newpass#2026", new_password2: "Newpass#2026" });
    expect(await screen.findByText(RESET_DONE_NOTICE)).toBeInTheDocument();
  });

  it("offers a new link when the token is rejected", async () => {
    const user = userEvent.setup();
    anonymous(<ResetPasswordForm uid="u1" token="stale" />);

    await fill(user, "Newpass#2026", "Newpass#2026");

    expect(await screen.findByText(/không hợp lệ hoặc đã hết hạn/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Yêu cầu liên kết mới" })).toHaveAttribute("href", "/forgot-password");
  });

  it("shows backend password-policy errors under the field", async () => {
    server.use(
      http.post("/api/auth/password-reset/confirm", () =>
        failure(400, "VALIDATION_ERROR", "x", [{ field: "new_password1", issue: "This password is too common." }])),
    );
    const user = userEvent.setup();
    anonymous(<ResetPasswordForm uid="u1" token={MOCK_RESET_TOKEN} />);

    await fill(user, "Password1!", "Password1!");

    expect(await screen.findByText("This password is too common.")).toBeInTheDocument();
  });

  it("shows a message on 503 and stays on the form", async () => {
    server.use(http.post("/api/auth/password-reset/confirm", () => failure(503, "IDENTITY_UNAVAILABLE", "x")));
    const user = userEvent.setup();
    anonymous(<ResetPasswordForm uid="u1" token={MOCK_RESET_TOKEN} />);

    await fill(user, "Newpass#2026", "Newpass#2026");

    expect(await screen.findByText("Tính năng tạm thời không khả dụng. Hãy thử lại sau.")).toBeInTheDocument();
  });

  it.each(["/auth/reset", "/auth/reset?uid=u1", "/auth/reset?token=t"])("shows an invalid-link screen for %s", (route) => {
    renderApp(<div />, { route, session: null, routes: [{ path: "/auth/reset", element: <ResetRoute /> }] });

    expect(screen.getByText("Liên kết đặt lại mật khẩu không hợp lệ")).toBeInTheDocument();
    expect(screen.queryByLabelText("Mật khẩu mới")).not.toBeInTheDocument();
  });
});

describe("RegisterForm", () => {
  async function fillAll(user: ReturnType<typeof userEvent.setup>, email = "new@st.edu.vn") {
    await user.type(screen.getByLabelText("Họ và tên đệm"), "Nguyễn Văn");
    await user.type(screen.getByLabelText("Tên"), "An");
    await user.type(screen.getByLabelText("Tên đăng nhập"), "annv");
    await user.type(screen.getByLabelText("Email"), email);
    await user.type(screen.getByLabelText("Mật khẩu"), "Newpass#2026");
    await user.type(screen.getByLabelText("Xác nhận mật khẩu"), "Newpass#2026");
    await user.click(screen.getByRole("button", { name: /^Đăng ký/ }));
  }

  it("sends the contract body and shows the check-your-email screen (no auto login)", async () => {
    let body: unknown;
    server.use(
      http.post("/api/auth/register", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(
          { success: true, message: "OK", data: { user: {}, account_status: "PENDING_ACTIVATION" }, meta: null, error: null },
          { status: 201 },
        );
      }),
    );
    const user = userEvent.setup();
    anonymous(<RegisterForm />);

    await fillAll(user);

    expect(await screen.findByText("Đăng ký thành công")).toBeInTheDocument();
    expect(screen.getByText(/Kiểm tra email để kích hoạt/)).toBeInTheDocument();
    expect(body).toEqual({
      email: "new@st.edu.vn",
      username: "annv",
      first_name: "An",
      last_name: "Nguyễn Văn",
      password1: "Newpass#2026",
      password2: "Newpass#2026",
    });
  });

  it("shows VALIDATION_ERROR under the offending field", async () => {
    const user = userEvent.setup();
    anonymous(<RegisterForm />);

    await fillAll(user, "leader@utask.test");

    expect(await screen.findByText("A user is already registered with this e-mail address.")).toBeInTheDocument();
    expect(screen.queryByText("Đăng ký thành công")).not.toBeInTheDocument();
  });

  it("shows a form-level message on 503", async () => {
    server.use(http.post("/api/auth/register", () => failure(503, "IDENTITY_UNAVAILABLE", "x")));
    const user = userEvent.setup();
    anonymous(<RegisterForm />);

    await fillAll(user);

    expect(await screen.findByText("Tính năng tạm thời không khả dụng. Hãy thử lại sau.")).toBeInTheDocument();
  });

  it("blocks mismatched passwords before calling the API", async () => {
    const user = userEvent.setup();
    anonymous(<RegisterForm />);

    await user.type(screen.getByLabelText("Mật khẩu"), "Newpass#2026");
    await user.type(screen.getByLabelText("Xác nhận mật khẩu"), "Different#1");
    await user.click(screen.getByRole("button", { name: /^Đăng ký/ }));

    expect(await screen.findByText("Mật khẩu xác nhận không trùng khớp.")).toBeInTheDocument();
  });
});

describe("ActivateAccountForm / route", () => {
  it("activates with only the key and lands on /login with a notice", async () => {
    let body: unknown;
    server.use(
      http.post("/api/auth/activate", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ success: true, message: "OK", data: null, meta: null, error: null });
      }),
    );
    const user = userEvent.setup();
    const { router } = renderApp(<div />, {
      route: `/auth/activate?key=${MOCK_ACTIVATION_KEY}`,
      session: null,
      routes: [
        { path: "/auth/activate", element: <ActivateRoute /> },
        { path: "/login", element: <LoginForm /> },
      ],
    });

    await user.click(screen.getByRole("button", { name: "Kích hoạt tài khoản" }));

    await waitFor(() => expect(router.state.location.pathname).toBe("/login"));
    expect(body).toEqual({ key: MOCK_ACTIVATION_KEY });
    expect(await screen.findByText(ACTIVATED_NOTICE)).toBeInTheDocument();
  });

  it("sends new passwords only when the optional section is filled", async () => {
    let body: unknown;
    server.use(
      http.post("/api/auth/activate", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ success: true, message: "OK", data: null, meta: null, error: null });
      }),
    );
    const user = userEvent.setup();
    anonymous(<ActivateAccountForm activationKey="k1" />);

    await user.click(screen.getByText(/Tài khoản do giảng viên tạo/));
    await user.type(screen.getByLabelText("Mật khẩu mới"), "Newpass#2026");
    await user.type(screen.getByLabelText("Xác nhận mật khẩu mới"), "Newpass#2026");
    await user.click(screen.getByRole("button", { name: "Kích hoạt tài khoản" }));

    await waitFor(() => expect(body).toEqual({ key: "k1", new_password1: "Newpass#2026", new_password2: "Newpass#2026" }));
  });

  it("explains a broken link and still offers to resend", async () => {
    const user = userEvent.setup();
    anonymous(<ActivateAccountForm activationKey="stale" />);

    await user.click(screen.getByRole("button", { name: "Kích hoạt tài khoản" }));

    expect(await screen.findByText("Liên kết kích hoạt không hợp lệ hoặc đã hết hạn.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Kích hoạt tài khoản" })).not.toBeInTheDocument();
    expect(screen.getByLabelText("Gửi lại email kích hoạt")).toBeInTheDocument();
  });

  it("shows an already-active screen with a login link", async () => {
    server.use(http.post("/api/auth/activate", () => failure(400, "ACCOUNT_ALREADY_ACTIVE", "x")));
    const user = userEvent.setup();
    anonymous(<ActivateAccountForm activationKey="k1" />);

    await user.click(screen.getByRole("button", { name: "Kích hoạt tài khoản" }));

    expect(await screen.findByText("Tài khoản đã kích hoạt")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Đăng nhập" })).toHaveAttribute("href", "/login");
  });

  it("resend shows the neutral message, and an error on 503 without claiming it was sent", async () => {
    const user = userEvent.setup();
    anonymous(<ActivateAccountForm activationKey="stale" />);
    await user.type(screen.getByLabelText("Gửi lại email kích hoạt"), "a@st.edu.vn");
    await user.click(screen.getByRole("button", { name: "Gửi lại email kích hoạt" }));
    expect(await screen.findByText("Nếu email tồn tại, bạn sẽ nhận được hướng dẫn.")).toBeInTheDocument();
  });

  it("resend reports 503", async () => {
    server.use(http.post("/api/auth/activation/resend", () => failure(503, "IDENTITY_UNAVAILABLE", "x")));
    const user = userEvent.setup();
    anonymous(<ActivateAccountForm activationKey="k" />);
    await user.type(screen.getByLabelText("Gửi lại email kích hoạt"), "a@st.edu.vn");
    await user.click(screen.getByRole("button", { name: "Gửi lại email kích hoạt" }));

    expect(await screen.findByText("Tính năng tạm thời không khả dụng. Hãy thử lại sau.")).toBeInTheDocument();
    expect(screen.queryByText("Nếu email tồn tại, bạn sẽ nhận được hướng dẫn.")).not.toBeInTheDocument();
  });

  it("shows an invalid-link screen when the key is missing", () => {
    renderApp(<div />, { route: "/auth/activate", session: null, routes: [{ path: "/auth/activate", element: <ActivateRoute /> }] });

    expect(screen.getByText("Liên kết kích hoạt không hợp lệ")).toBeInTheDocument();
  });
});
