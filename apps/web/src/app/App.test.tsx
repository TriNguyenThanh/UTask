import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { RequireAuth } from "@/app/router/RequireAuth";
import { AuthLayout } from "@/app/layouts/AuthLayout";
import { Component as LoginRoute } from "@/features/auth/routes/LoginRoute";
import { LoginForm } from "@/features/auth/components/LoginForm";
import { LEADER_ID } from "@/mocks/data/database";
import { renderApp } from "@/test/render";

afterEach(() => {
  sessionStorage.clear();
  vi.unstubAllEnvs();
});

describe("authentication routes", () => {
  it("shows generic invalid-credential error and restores a valid Leader session", async () => {
    vi.stubEnv("VITE_ENABLE_MOCKS", "true");
    const user = userEvent.setup();
    const first = renderApp(<LoginRoute />, {
      route: "/login",
      session: null,
      routes: [
        { path: "/login", element: <LoginRoute /> },
        { path: "/my-work", element: <h1>Trang chủ UTask</h1> },
      ],
    });

    await user.type(await screen.findByLabelText("Email trường học"), "leader@utask.test");
    await user.type(screen.getByLabelText("Mật khẩu"), "incorrect");
    await user.click(screen.getByRole("button", { name: "Đăng nhập" }));
    expect(await screen.findByText("Email hoặc mật khẩu không đúng.")).toBeInTheDocument();

    await user.clear(screen.getByLabelText("Mật khẩu"));
    await user.type(screen.getByLabelText("Mật khẩu"), "demo1234");
    await user.click(screen.getByRole("button", { name: "Đăng nhập" }));
    expect(await screen.findByRole("heading", { name: "Trang chủ UTask" })).toBeInTheDocument();
    expect(sessionStorage.getItem("utask.mock.refresh-token")).toBe(`mock-refresh:${LEADER_ID}`);
    first.unmount();

    renderApp(<div />, {
      route: "/",
      session: null,
      routes: [
        { path: "/login", element: <AuthLayout><LoginForm /></AuthLayout> },
        {
          element: <RequireAuth />,
          children: [{ path: "/", element: <h1>Phiên đã khôi phục</h1> }],
        },
      ],
    });
    expect(await screen.findByRole("heading", { name: "Phiên đã khôi phục" })).toBeInTheDocument();
  });
});

describe("deep link restore", () => {
  it("restores full protected URL after login", async () => {
    vi.stubEnv("VITE_ENABLE_MOCKS", "true");
    const user = userEvent.setup();
    const result = renderApp(
      <RequireAuth />,
      {
        route: "/settings/profile?tab=security",
        session: null,
        routes: [
          { path: "/login", element: <AuthLayout><LoginForm /></AuthLayout> },
          {
            element: <RequireAuth />,
            children: [{ path: "/settings/profile", element: <h1>Deep link</h1> }],
          },
        ],
      },
    );

    await user.type(await screen.findByLabelText("Email trường học"), "leader@utask.test");
    await user.type(screen.getByLabelText("Mật khẩu"), "demo1234");
    await user.click(screen.getByRole("button", { name: "Đăng nhập" }));

    const { router } = result;
    expect(router.state.location.pathname).toBe("/settings/profile");
    expect(router.state.location.search).toBe("?tab=security");
  });
});