import { delay, http, HttpResponse, type HttpHandler } from "msw";

import { resolveMockUserId } from "@/mocks/resolveMockUserId";
import {
  DEMO_PASSWORD,
  MOCK_USERS,
} from "@/mocks/data/database";
import type { MockDatabase } from "@/mocks/data/database";
import type { MockRepository } from "@/mocks/data/storage";
import type { MockScenario } from "@/mocks/scenarios";
import type { AuthUser } from "@/features/auth/types";
import type { SessionDto } from "@/lib/api/identity/dto";

export const SERVER_ERROR = "Lỗi hệ thống, vui lòng thử lại sau.";

function sleepFor(scenario: MockScenario): Promise<void> | undefined {
  return scenario === "slow-network" ? delay(1200) : undefined;
}

function ok<T>(data: T) {
  return HttpResponse.json({ success: true, message: "OK", data, meta: null, error: null });
}

function fail(status: number, code: string, message: string) {
  return HttpResponse.json(
    { success: false, message, data: null, meta: null, error: { code, details: [] } },
    { status },
  );
}

function userForToken(db: MockDatabase, request: Request): AuthUser | null {
  const userId = resolveMockUserId(request);
  return userId ? db.authUsersById[userId] ?? null : null;
}

/** Token mock có dạng `mock-access:<userId>:<sessionId>`; `<sessionId>` xác định phiên hiện tại. */
function currentSessionId(request: Request): string | null {
  return /^Bearer mock-access:[^:]+:(.+)$/.exec(request.headers.get("Authorization") ?? "")?.[1] ?? null;
}

interface MockSession {
  userId: string;
  dto: Omit<SessionDto, "is_current">;
}

export function createAuthHandlers(
  scenario: MockScenario,
  repository: MockRepository,
): HttpHandler[] {
  const { db } = repository;
  const sessions = new Map<string, MockSession>();
  let sequence = 0;

  return [
    http.post("/api/auth/login", async ({ request }) => {
      await sleepFor(scenario);
      if (scenario === "server-error") {
        return fail(500, "INTERNAL_ERROR", SERVER_ERROR);
      }
      const body = await request.json() as { email?: string; password?: string; device_name?: string };
      const email = body.email?.trim().toLowerCase();
      const user = MOCK_USERS.find((candidate) => candidate.email === email);
      if (!user || body.password !== DEMO_PASSWORD) {
        return fail(401, "INVALID_CREDENTIALS", "Email hoặc mật khẩu không đúng.");
      }
      sequence += 1;
      const sessionId = `mock-session-${sequence}`;
      const now = new Date();
      sessions.set(sessionId, {
        userId: user.id,
        dto: {
          id: sessionId,
          token_family: `mock-family-${sequence}`,
          device_name: body.device_name ?? "Trình duyệt web",
          ip_address: "127.0.0.1",
          created_at: now.toISOString(),
          expires_at: new Date(now.getTime() + 7 * 24 * 3600 * 1000).toISOString(),
        },
      });
      return ok({ access: `mock-access:${user.id}:${sessionId}`, refresh: "", user });
    }),

    http.get("/api/auth/sessions", async ({ request }) => {
      await sleepFor(scenario);
      const user = userForToken(db, request);
      if (!user) {
        return fail(401, "AUTHENTICATION_REQUIRED", "Yêu cầu thông tin xác thực để thực hiện thao tác.");
      }
      const current = currentSessionId(request);
      const items: SessionDto[] = [...sessions.values()]
        .filter((session) => session.userId === user.id)
        .map((session) => ({ ...session.dto, is_current: session.dto.id === current }));
      return ok(items);
    }),

    http.delete("/api/auth/sessions/:sessionId", async ({ request, params }) => {
      await sleepFor(scenario);
      const user = userForToken(db, request);
      if (!user) {
        return fail(401, "AUTHENTICATION_REQUIRED", "Yêu cầu thông tin xác thực để thực hiện thao tác.");
      }
      const sessionId = String(params.sessionId);
      if (sessions.get(sessionId)?.userId !== user.id) {
        return fail(404, "SESSION_NOT_FOUND", "Không tìm thấy phiên đăng nhập.");
      }
      sessions.delete(sessionId);
      return ok(null);
    }),

    http.get("/api/auth/users/me", async ({ request }) => {
      await sleepFor(scenario);
      const user = userForToken(db, request);
      if (!user) {
        return fail(401, "AUTHENTICATION_REQUIRED", "Yêu cầu thông tin xác thực để thực hiện thao tác.");
      }
      return ok(user);
    }),
  ];
}
