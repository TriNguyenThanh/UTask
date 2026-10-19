import { QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import type { ReactNode } from "react";
import { afterAll, afterEach, describe, expect, it } from "vitest";

import { AuthProvider, useAuth } from "@/features/auth/AuthProvider";
import { subscribeSession, type SessionEvent } from "@/features/auth/sessionEvents";
import type { AuthSession } from "@/features/auth/types";
import { createTestQueryClient } from "@/lib/query/client";
import { LEADER_ID } from "@/mocks/data/database";
import { server } from "@/mocks/server";
import { leaderTestSession } from "@/test/render";

function setup(initialSession: AuthSession | null = null) {
  const queryClient = createTestQueryClient();
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>
      <AuthProvider initialSession={initialSession}>{children}</AuthProvider>
    </QueryClientProvider>
  );
  return renderHook(() => useAuth(), { wrapper });
}

const events: SessionEvent[] = [];
const unsubscribe = subscribeSession((event) => events.push(event));
afterEach(() => {
  events.length = 0;
});
afterAll(unsubscribe);

function envelope<T>(data: T) {
  return HttpResponse.json({ success: true, message: "OK", data, meta: null, error: null });
}

const sessionsFixture = [
  { id: "s1", token_family: "f", device_name: "x", ip_address: null, is_current: false, created_at: "", expires_at: "" },
  { id: "s2", token_family: "g", device_name: "y", ip_address: null, is_current: true, created_at: "", expires_at: "" },
];

describe("AuthProvider.login", () => {
  it("stores the user and access token and publishes the session", async () => {
    const { result } = setup();
    expect(result.current.status).toBe("anonymous");

    await act(async () => {
      await result.current.login({ email: "leader@utask.test", password: "demo1234" });
    });

    expect(result.current.status).toBe("authenticated");
    expect(result.current.user?.id).toBe(LEADER_ID);
    expect(result.current.user?.roles).toEqual(["STUDENT"]);
    expect(result.current.accessToken).toMatch(/^mock-access:/);
    expect(events.at(-1)?.accessToken).toBe(result.current.accessToken);
  });

  it("sends the device name and keeps the user anonymous on bad credentials", async () => {
    let body: { device_name?: string } = {};
    server.use(
      http.post("/api/auth/login", async ({ request }) => {
        body = await request.json() as typeof body;
        return HttpResponse.json(
          { success: false, message: "x", data: null, error: { code: "INVALID_CREDENTIALS", details: [] } },
          { status: 401 },
        );
      }),
    );
    const { result } = setup();

    await act(async () => {
      await expect(result.current.login({ email: "a@b.vn", password: "x" })).rejects.toMatchObject({
        code: "INVALID_CREDENTIALS",
      });
    });

    expect(body.device_name).toEqual(expect.any(String));
    expect(result.current.status).toBe("anonymous");
    expect(result.current.user).toBeNull();
  });
});

describe("AuthProvider.logout", () => {
  it("revokes the current session and clears local state", async () => {
    const revoked: string[] = [];
    server.use(
      http.get("/api/auth/sessions", () => envelope(sessionsFixture)),
      http.delete("/api/auth/sessions/:id", ({ params }) => {
        revoked.push(String(params.id));
        return envelope(null);
      }),
    );
    const { result } = setup(leaderTestSession);

    let outcome: { revoked: boolean } | undefined;
    await act(async () => {
      outcome = await result.current.logout();
    });

    expect(outcome).toEqual({ revoked: true });
    expect(revoked).toEqual(["s2"]);
    expect(result.current.status).toBe("anonymous");
    expect(result.current.accessToken).toBeNull();
    expect(events.at(-1)).toBeNull();
  });

  it("treats a missing current session as already revoked", async () => {
    server.use(http.get("/api/auth/sessions", () => envelope([sessionsFixture[0]])));
    const { result } = setup(leaderTestSession);

    let outcome: { revoked: boolean } | undefined;
    await act(async () => {
      outcome = await result.current.logout();
    });

    expect(outcome).toEqual({ revoked: true });
    expect(result.current.status).toBe("anonymous");
  });

  it("treats SESSION_NOT_FOUND as revoked", async () => {
    server.use(
      http.get("/api/auth/sessions", () => envelope(sessionsFixture)),
      http.delete("/api/auth/sessions/:id", () =>
        HttpResponse.json(
          { success: false, message: "x", data: null, error: { code: "SESSION_NOT_FOUND", details: [] } },
          { status: 404 },
        )),
    );
    const { result } = setup(leaderTestSession);

    let outcome: { revoked: boolean } | undefined;
    await act(async () => {
      outcome = await result.current.logout();
    });

    expect(outcome).toEqual({ revoked: true });
  });

  it("reports revoked:false on a network failure but still clears local state", async () => {
    server.use(
      http.get("/api/auth/sessions", () => envelope(sessionsFixture)),
      http.delete("/api/auth/sessions/:id", () => HttpResponse.error()),
    );
    const { result } = setup(leaderTestSession);

    let outcome: { revoked: boolean } | undefined;
    await act(async () => {
      outcome = await result.current.logout();
    });

    expect(outcome).toEqual({ revoked: false });
    expect(result.current.status).toBe("anonymous");
    expect(result.current.user).toBeNull();
  });

  it("reports revoked:false on other API errors", async () => {
    server.use(http.get("/api/auth/sessions", () => HttpResponse.json({}, { status: 500 })));
    const { result } = setup(leaderTestSession);

    let outcome: { revoked: boolean } | undefined;
    await act(async () => {
      outcome = await result.current.logout();
    });

    expect(outcome).toEqual({ revoked: false });
  });
});
