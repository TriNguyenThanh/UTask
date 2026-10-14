import { delay, http, HttpResponse, type HttpHandler } from "msw";

import {
  DEMO_PASSWORD,
  MOCK_USERS,
} from "@/mocks/data/database";
import type { MockDatabase } from "@/mocks/data/database";
import type { MockRepository } from "@/mocks/data/storage";
import type { MockScenario } from "@/mocks/scenarios";
import type { AuthUser } from "@/features/auth/types";

export const SERVER_ERROR = "Lỗi hệ thống, vui lòng thử lại sau.";

function sleepFor(scenario: MockScenario): Promise<void> | undefined {
  return scenario === "slow-network" ? delay(1200) : undefined;
}

function parseTokenUserId(request: Request): string | null {
  const header = request.headers.get("Authorization") ?? "";
  const match = /^Bearer mock-access:([^:]+):/.exec(header);
  return match?.[1] ?? null;
}

function userForToken(db: MockDatabase, request: Request): AuthUser | null {
  const userId = parseTokenUserId(request);
  return userId ? db.authUsersById[userId] ?? null : null;
}

interface StoredRefreshToken {
  user_id: string;
}

export function createAuthHandlers(
  scenario: MockScenario,
  repository: MockRepository,
): HttpHandler[] {
  const { db } = repository;

  return [
    http.post("/api/auth/api/v1/auth/login", async ({ request }) => {
      await sleepFor(scenario);
      if (scenario === "server-error") {
        return HttpResponse.json({ detail: SERVER_ERROR }, { status: 500 });
      }
      const body = await request.json() as { email?: string; password?: string };
      const email = body.email?.trim().toLowerCase();
      const user = MOCK_USERS.find((candidate) => candidate.email === email);
      if (!user || body.password !== DEMO_PASSWORD) {
        return HttpResponse.json(
          { detail: "Email hoặc mật khẩu không đúng." },
          { status: 401 },
        );
      }
      return HttpResponse.json({
        access_token: `mock-access:${user.id}:default`,
        refresh_token: `mock-refresh:${user.id}`,
        expires_in: 3600,
        user,
      });
    }),

    http.post("/api/auth/api/v1/auth/refresh", async ({ request }) => {
      await sleepFor(scenario);
      if (scenario === "server-error") {
        return HttpResponse.json({ detail: SERVER_ERROR }, { status: 500 });
      }
      const body = await request.json() as { refresh_token?: string };
      const userId = /^mock-refresh:(.+)$/.exec(body.refresh_token ?? "")?.[1];
      const user = userId ? db.authUsersById[userId] : null;
      if (!user) {
        return HttpResponse.json(
          { detail: "Phiên đăng nhập đã hết hạn." },
          { status: 401 },
        );
      }
      return HttpResponse.json({
        access_token: `mock-access:${user.id}:default`,
        expires_in: 3600,
        user,
      });
    }),

    http.post("/api/auth/api/v1/auth/logout", async ({ request }) => {
      await sleepFor(scenario);
      const user = userForToken(db, request);
      let stored: StoredRefreshToken;
      try {
        stored = {
          user_id: user?.id ?? "",
        };
      } catch {
        stored = { user_id: "" };
      }
      void stored;
      return new HttpResponse(null, { status: 204 });
    }),
  ];
}