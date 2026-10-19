import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { useSignOut } from "@/features/auth/useSignOut";
import { server } from "@/mocks/server";
import { leaderTestSession, renderApp } from "@/test/render";

function SignOutButton() {
  const signOut = useSignOut();
  return <button onClick={() => void signOut()}>out</button>;
}

function setup() {
  return renderApp(<SignOutButton />, {
    route: "/",
    session: leaderTestSession,
    routes: [
      { path: "/", element: <SignOutButton /> },
      { path: "/login", element: <h1>Trang đăng nhập</h1> },
    ],
  });
}

describe("useSignOut", () => {
  it("navigates to /login without a warning when the session was revoked", async () => {
    server.use(http.get("/api/auth/sessions", () =>
      HttpResponse.json({ success: true, message: "OK", data: [], meta: null, error: null })));
    setup();
    await userEvent.click(screen.getByText("out"));
    expect(await screen.findByRole("heading", { name: "Trang đăng nhập" })).toBeInTheDocument();
    expect(screen.queryByText(/Chưa thu hồi được phiên/)).not.toBeInTheDocument();
  });

  it("warns when the server could not revoke the session, still leaving", async () => {
    server.use(http.get("/api/auth/sessions", () => HttpResponse.error()));
    setup();
    await userEvent.click(screen.getByText("out"));
    expect(await screen.findByRole("heading", { name: "Trang đăng nhập" })).toBeInTheDocument();
    expect(await screen.findByText(/Chưa thu hồi được phiên trên máy chủ/)).toBeInTheDocument();
  });
});
