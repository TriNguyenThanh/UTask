import { QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import type { ReactNode } from "react";
import { afterAll, afterEach, describe, expect, it, vi } from "vitest";

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
    await waitFor(() => expect(result.current.status).toBe("anonymous"));

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

function fakeJwt(expSeconds: number): string {
  const encode = (value: unknown) => btoa(JSON.stringify(value)).replace(/=+$/, "");
  return `${encode({ alg: "none" })}.${encode({ exp: expSeconds })}.sig`;
}

describe("AuthProvider session restore", () => {
  it("restores the session from the refresh cookie after a reload", async () => {
    const first = setup();
    await waitFor(() => expect(first.result.current.status).toBe("anonymous"));
    await act(async () => {
      await first.result.current.login({ email: "leader@utask.test", password: "demo1234" });
    });
    first.unmount();

    const second = setup();
    expect(second.result.current.status).toBe("restoring");
    await waitFor(() => expect(second.result.current.status).toBe("authenticated"));
    expect(second.result.current.user?.id).toBe(LEADER_ID);
  });

  it("falls back to anonymous when there is no valid refresh cookie", async () => {
    server.use(
      http.post("/api/auth/refresh", () =>
        HttpResponse.json(
          { success: false, message: "x", data: null, error: { code: "INVALID_TOKEN", details: [] } },
          { status: 401 },
        )),
    );
    const { result } = setup();
    expect(result.current.status).toBe("restoring");
    await waitFor(() => expect(result.current.status).toBe("anonymous"));
    expect(result.current.user).toBeNull();
  });

  it("falls back to anonymous when the server is down", async () => {
    server.use(http.post("/api/auth/refresh", () => HttpResponse.error()));
    const { result } = setup();
    await waitFor(() => expect(result.current.status).toBe("anonymous"));
  });
});

describe("AuthProvider.refreshAccessToken", () => {
  it("shares one request between concurrent callers and swaps the token", async () => {
    let calls = 0;
    server.use(
      http.post("/api/auth/refresh", async () => {
        calls += 1;
        await new Promise((resolve) => setTimeout(resolve, 20));
        return envelope({ access: "mock-access:fresh", access_expiration: "" });
      }),
    );
    const { result } = setup(leaderTestSession);

    let tokens: (string | null)[] = [];
    await act(async () => {
      tokens = await Promise.all([result.current.refreshAccessToken(), result.current.refreshAccessToken()]);
    });

    expect(calls).toBe(1);
    expect(tokens).toEqual(["mock-access:fresh", "mock-access:fresh"]);
    expect(result.current.accessToken).toBe("mock-access:fresh");
    expect(result.current.user?.id).toBe(LEADER_ID);
    expect(events.at(-1)?.accessToken).toBe("mock-access:fresh");
  });

  it("reuses the current token when another request already refreshed", async () => {
    let calls = 0;
    server.use(http.post("/api/auth/refresh", () => {
      calls += 1;
      return envelope({ access: "x", access_expiration: "" });
    }));
    const { result } = setup(leaderTestSession);

    let token: string | null = null;
    await act(async () => {
      token = await result.current.refreshAccessToken("some-older-token");
    });

    expect(token).toBe(leaderTestSession.accessToken);
    expect(calls).toBe(0);
  });

  it("returns null on 401 and throws on server errors", async () => {
    server.use(http.post("/api/auth/refresh", () =>
      HttpResponse.json({ success: false, message: "x", data: null, error: { code: "INVALID_TOKEN", details: [] } }, { status: 401 })));
    const { result } = setup(leaderTestSession);
    await act(async () => {
      expect(await result.current.refreshAccessToken()).toBeNull();
    });

    server.use(http.post("/api/auth/refresh", () => HttpResponse.json({}, { status: 503 })));
    await act(async () => {
      await expect(result.current.refreshAccessToken()).rejects.toMatchObject({ status: 503 });
    });
  });
});

describe("AuthProvider refresh timer", () => {
  it("refreshes shortly before the access token expires", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      let calls = 0;
      server.use(http.post("/api/auth/refresh", () => {
        calls += 1;
        return envelope({ access: "mock-access:renewed", access_expiration: "" });
      }));
      const nowSeconds = Math.floor(Date.now() / 1000);
      const session = { ...leaderTestSession, accessToken: fakeJwt(nowSeconds + 15 * 60) };
      const { result } = setup(session);

      await act(async () => {
        await vi.advanceTimersByTimeAsync(13 * 60 * 1000);
      });
      expect(calls).toBe(0);

      await act(async () => {
        await vi.advanceTimersByTimeAsync(2 * 60 * 1000);
      });
      await waitFor(() => expect(result.current.accessToken).toBe("mock-access:renewed"));
      expect(calls).toBe(1);
    } finally {
      vi.useRealTimers();
    }
  });

  it("signs out when the timer refresh finds the session gone", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      server.use(http.post("/api/auth/refresh", () =>
        HttpResponse.json({ success: false, message: "x", data: null, error: { code: "INVALID_TOKEN", details: [] } }, { status: 401 })));
      const session = { ...leaderTestSession, accessToken: fakeJwt(Math.floor(Date.now() / 1000) + 90) };
      const { result } = setup(session);

      await act(async () => {
        await vi.advanceTimersByTimeAsync(40_000);
      });
      await waitFor(() => expect(result.current.status).toBe("anonymous"));
    } finally {
      vi.useRealTimers();
    }
  });
});

describe("AuthProvider.logoutAll", () => {
  it("returns the revoked count and clears local state", async () => {
    server.use(http.post("/api/auth/logout-all", () => envelope({ revoked_sessions_count: 3 })));
    const { result } = setup(leaderTestSession);

    let count = 0;
    await act(async () => {
      count = await result.current.logoutAll();
    });

    expect(count).toBe(3);
    expect(result.current.status).toBe("anonymous");
    expect(events.at(-1)).toBeNull();
  });

  it("still clears local state when the server call fails", async () => {
    server.use(http.post("/api/auth/logout-all", () => HttpResponse.error()));
    const { result } = setup(leaderTestSession);

    await act(async () => {
      await expect(result.current.logoutAll()).rejects.toMatchObject({ status: 0 });
    });

    expect(result.current.status).toBe("anonymous");
  });
});
