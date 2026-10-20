import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse, type HttpHandler } from "msw";
import { describe, expect, it, vi } from "vitest";

import { LoginForm } from "@/features/auth/components/LoginForm";
import { REVOKE_FAILED_MESSAGE } from "@/features/auth/useSignOut";
import {
  IdentitySecurityPage,
  PASSWORD_CHANGED_NOTICE,
} from "@/features/notifications/components/IdentitySecurityPage";
import { createMemoryRepository } from "@/mocks/data/storage";
import { createAuthHandlers } from "@/mocks/handlers/auth";
import { server } from "@/mocks/server";
import { leaderTestSession, renderApp } from "@/test/render";

function envelope(data: unknown) {
  return HttpResponse.json({ success: true, message: "OK", data, meta: null, error: null });
}

function failure(status: number, code: string, message: string, details: unknown[] = []) {
  return HttpResponse.json(
    { success: false, message, data: null, meta: null, error: { code, details } },
    { status },
  );
}

const sessionRows = [
  { id: "s1", device_name: "Chrome trên Windows", ip_address: "10.0.0.1", created_at: "2026-10-01T08:00:00Z", is_current: true },
  { id: "s2", device_name: "Safari trên iPhone", ip_address: null, created_at: "2026-10-02T09:00:00Z", is_current: false },
];

function setup(...overrides: HttpHandler[]) {
  vi.stubEnv("VITE_REAL_SERVICES", "auth");
  server.use(...overrides, ...createAuthHandlers("default", createMemoryRepository("default")));
  return renderApp(<div />, {
    route: "/settings/security",
    session: leaderTestSession,
    routes: [
      { path: "/settings/security", element: <IdentitySecurityPage /> },
      { path: "/login", element: <LoginForm /> },
    ],
  });
}

describe("IdentitySecurityPage — devices", () => {
  it("lists devices, marks the current one and offers revoke only for others", async () => {
    setup(http.get("/api/auth/sessions", () => envelope(sessionRows)));

    expect(await screen.findByText("Chrome trên Windows")).toBeInTheDocument();
    expect(screen.getByText("Thiết bị hiện tại")).toBeInTheDocument();
    expect(screen.getByText("Safari trên iPhone")).toBeInTheDocument();
    expect(screen.getByText(/Không rõ IP/)).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Đăng xuất thiết bị" })).toHaveLength(1);
  });

  it("shows an empty state when there are no sessions", async () => {
    setup(http.get("/api/auth/sessions", () => envelope([])));

    expect(await screen.findByText("Không có phiên đăng nhập nào.")).toBeInTheDocument();
  });

  it("revokes another device and refetches the list", async () => {
    let rows = sessionRows;
    let revoked = "";
    const user = userEvent.setup();
    setup(
      http.get("/api/auth/sessions", () => envelope(rows)),
      http.delete("/api/auth/sessions/:id", ({ params }) => {
        revoked = String(params.id);
        rows = rows.filter((row) => row.id !== revoked);
        return envelope(null);
      }),
    );

    await user.click(await screen.findByRole("button", { name: "Đăng xuất thiết bị" }));

    await waitFor(() => expect(screen.queryByText("Safari trên iPhone")).not.toBeInTheDocument());
    expect(revoked).toBe("s2");
  });

  it("keeps the list and shows a toast when revoke fails", async () => {
    const user = userEvent.setup();
    setup(
      http.get("/api/auth/sessions", () => envelope(sessionRows)),
      http.delete("/api/auth/sessions/:id", () => failure(503, "IDENTITY_UNAVAILABLE", "Dịch vụ tạm thời không khả dụng.")),
    );

    await user.click(await screen.findByRole("button", { name: "Đăng xuất thiết bị" }));

    expect(await screen.findByText("Dịch vụ tạm thời không khả dụng.")).toBeInTheDocument();
    expect(screen.getByText("Safari trên iPhone")).toBeInTheDocument();
  });
});

describe("IdentitySecurityPage — change password", () => {
  async function fillAndSubmit(user: ReturnType<typeof userEvent.setup>, old: string, next: string, confirm: string) {
    await user.type(await screen.findByLabelText("Mật khẩu hiện tại"), old);
    await user.type(screen.getByLabelText("Mật khẩu mới"), next);
    await user.type(screen.getByLabelText("Xác nhận mật khẩu mới"), confirm);
    await user.click(screen.getByRole("button", { name: "Cập nhật mật khẩu" }));
  }

  it("signs out and lands on /login with a notice on success", async () => {
    const user = userEvent.setup();
    const { router } = setup(http.get("/api/auth/sessions", () => envelope([])));

    await fillAndSubmit(user, "demo1234", "Newpass#2026", "Newpass#2026");

    await waitFor(() => expect(router.state.location.pathname).toBe("/login"));
    expect(await screen.findByText(PASSWORD_CHANGED_NOTICE)).toBeInTheDocument();
  });

  it("shows a wrong old password under its field and stays on the page", async () => {
    const user = userEvent.setup();
    const { router } = setup(http.get("/api/auth/sessions", () => envelope([])));

    await fillAndSubmit(user, "wrong-old", "Newpass#2026", "Newpass#2026");

    expect(await screen.findByText("Mật khẩu hiện tại không đúng.")).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/settings/security");
  });

  it("blocks submit and warns when confirmation does not match", async () => {
    const user = userEvent.setup();
    setup(http.get("/api/auth/sessions", () => envelope([])));

    await user.type(await screen.findByLabelText("Mật khẩu hiện tại"), "demo1234");
    await user.type(screen.getByLabelText("Mật khẩu mới"), "Newpass#2026");
    await user.type(screen.getByLabelText("Xác nhận mật khẩu mới"), "Other");

    expect(screen.getByText("Xác nhận mật khẩu không khớp.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cập nhật mật khẩu" })).toBeDisabled();
  });

  it("shows the server message on a 503 without field errors", async () => {
    const user = userEvent.setup();
    setup(
      http.get("/api/auth/sessions", () => envelope([])),
      http.post("/api/auth/password-change", () => failure(503, "IDENTITY_UNAVAILABLE", "Dịch vụ tạm thời không khả dụng.")),
    );

    await fillAndSubmit(user, "demo1234", "Newpass#2026", "Newpass#2026");

    expect(await screen.findByRole("alert")).toHaveTextContent("Dịch vụ tạm thời không khả dụng.");
  });
});

describe("IdentitySecurityPage — logout all", () => {
  async function openDialogAndConfirm(user: ReturnType<typeof userEvent.setup>) {
    await user.click(await screen.findByRole("button", { name: "Đăng xuất mọi thiết bị" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Đăng xuất mọi thiết bị" }));
  }

  it("asks for confirmation, then lands on /login with the revoked count", async () => {
    const user = userEvent.setup();
    const { router } = setup(
      http.get("/api/auth/sessions", () => envelope([])),
      http.post("/api/auth/logout-all", () => envelope({ revoked_sessions_count: 3 })),
    );

    await openDialogAndConfirm(user);

    await waitFor(() => expect(router.state.location.pathname).toBe("/login"));
    expect(await screen.findByText("Đã đăng xuất khỏi 3 thiết bị.")).toBeInTheDocument();
  });

  it("does nothing when the dialog is cancelled", async () => {
    const user = userEvent.setup();
    const { router } = setup(http.get("/api/auth/sessions", () => envelope([])));

    await user.click(await screen.findByRole("button", { name: "Đăng xuất mọi thiết bị" }));
    await user.click(await screen.findByRole("button", { name: "Hủy" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(router.state.location.pathname).toBe("/settings/security");
  });

  it("tells the user the server did not revoke when logout-all fails", async () => {
    const user = userEvent.setup();
    const { router } = setup(
      http.get("/api/auth/sessions", () => envelope([])),
      http.post("/api/auth/logout-all", () => failure(503, "IDENTITY_UNAVAILABLE", "Dịch vụ tạm thời không khả dụng.")),
    );

    await openDialogAndConfirm(user);

    await waitFor(() => expect(router.state.location.pathname).toBe("/login"));
    expect(await screen.findByText(REVOKE_FAILED_MESSAGE)).toBeInTheDocument();
  });
});
