import { delay, http, HttpResponse, type HttpHandler } from "msw";

import { buildMockAuthUser } from "@/mocks/data/authUsers";
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

/**
 * Cookie refresh mô phỏng `refresh_token` của backend: `mock-refresh:<userId>:<sessionId>`.
 * Handler MSW chạy trong trang nên đọc/ghi thẳng `document.cookie`; MSW 3 không lưu `Set-Cookie`
 * của phản hồi mock trong môi trường test (Node) và cookie HttpOnly sẽ vô hình với handler.
 */
const REFRESH_COOKIE = "refresh_token";

function setRefreshCookie(value: string, maxAgeSeconds = 7 * 24 * 3600) {
  document.cookie = `${REFRESH_COOKIE}=${value}; Path=/; Max-Age=${maxAgeSeconds}; SameSite=Lax`;
}

function readRefreshCookie(): string {
  const entry = document.cookie.split("; ").find((item) => item.startsWith(`${REFRESH_COOKIE}=`));
  return entry ? entry.slice(REFRESH_COOKIE.length + 1) : "";
}

function fail(status: number, code: string, message: string, details: { field?: string; issue: string }[] = []) {
  return HttpResponse.json(
    { success: false, message, data: null, meta: null, error: { code, details } },
    { status },
  );
}

/** Link demo: `/auth/activate?key=mock-activation-key`, `/auth/reset?uid=mock&token=mock-reset-token`. */
export const MOCK_ACTIVATION_KEY = "mock-activation-key";
export const MOCK_RESET_TOKEN = "mock-reset-token";

const PROFILE_FIELDS = new Set([
  "first_name",
  "last_name",
  "phone_number",
  "bio",
  "academic_year",
  "faculty",
  "timezone",
  "preferences",
]);

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
    http.post("/api/auth/register", async ({ request }) => {
      await sleepFor(scenario);
      const body = await request.json() as Record<string, string>;
      const email = (body.email ?? "").trim().toLowerCase();
      if (Object.values(db.authUsersById).some((user) => user.email.toLowerCase() === email)) {
        return fail(400, "VALIDATION_ERROR", "Dữ liệu đầu vào không hợp lệ.",
          [{ field: "email", issue: "A user is already registered with this e-mail address." }]);
      }
      if (body.password1 !== body.password2) {
        return fail(400, "VALIDATION_ERROR", "Dữ liệu đầu vào không hợp lệ.",
          [{ field: "password2", issue: "The two password fields didn't match." }]);
      }
      return HttpResponse.json(
        {
          success: true,
          message: "Đăng ký thành công.",
          data: {
            user: buildMockAuthUser({ id: `mock-${email}`, email, display_name: `${body.last_name} ${body.first_name}`, roles: ["STUDENT"] }),
            account_status: "PENDING_ACTIVATION",
          },
          meta: null,
          error: null,
        },
        { status: 201 },
      );
    }),

    http.post("/api/auth/activate", async ({ request }) => {
      await sleepFor(scenario);
      const body = await request.json() as Record<string, string>;
      if (body.key !== MOCK_ACTIVATION_KEY) {
        return fail(404, "RESOURCE_NOT_FOUND", "Invalid or expired activation key.");
      }
      return ok(null);
    }),

    http.post("/api/auth/activation/resend", async () => {
      await sleepFor(scenario);
      return ok({ detail: "If eligible, verification instructions have been queued." });
    }),

    http.post("/api/auth/password-reset/request", async () => {
      await sleepFor(scenario);
      if (scenario === "server-error") {
        return fail(503, "IDENTITY_UNAVAILABLE", "Dịch vụ tạm thời không khả dụng.");
      }
      return ok({ detail: "Password reset e-mail has been sent." });
    }),

    http.post("/api/auth/password-reset/confirm", async ({ request }) => {
      await sleepFor(scenario);
      const body = await request.json() as Record<string, string>;
      if (body.token !== MOCK_RESET_TOKEN) {
        return fail(400, "VALIDATION_ERROR", "Dữ liệu đầu vào không hợp lệ.", [{ field: "token", issue: "Invalid value" }]);
      }
      if (body.new_password1 !== body.new_password2) {
        return fail(400, "VALIDATION_ERROR", "Dữ liệu đầu vào không hợp lệ.",
          [{ field: "new_password2", issue: "The two password fields didn't match." }]);
      }
      return ok(null);
    }),

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
      setRefreshCookie(`mock-refresh:${user.id}:${sessionId}`);
      return ok({ access: `mock-access:${user.id}:${sessionId}`, refresh: "", user });
    }),

    // Backend đặt cookie `csrftoken` khi mở trang docs; web dùng nó làm điểm lấy CSRF.
    http.get("/api/auth/docs/", () =>
      new HttpResponse("<html></html>", {
        headers: { "Content-Type": "text/html", "Set-Cookie": "csrftoken=mock-csrf; Path=/" },
      })),

    http.post("/api/auth/refresh", async () => {
      await sleepFor(scenario);
      const match = /^mock-refresh:([^:]+):(.+)$/.exec(readRefreshCookie());
      if (!match || !db.authUsersById[match[1]]) {
        return fail(401, "INVALID_TOKEN", "Token không hợp lệ.");
      }
      return ok({
        access: `mock-access:${match[1]}:${match[2]}`,
        access_expiration: new Date(Date.now() + 15 * 60 * 1000).toISOString(),
      });
    }),

    http.post("/api/auth/logout-all", async ({ request }) => {
      await sleepFor(scenario);
      const user = userForToken(db, request);
      if (!user) {
        return fail(401, "AUTHENTICATION_REQUIRED", "Yêu cầu thông tin xác thực để thực hiện thao tác.");
      }
      let revoked = 0;
      for (const [id, session] of sessions) {
        if (session.userId === user.id) {
          sessions.delete(id);
          revoked += 1;
        }
      }
      setRefreshCookie("", 0);
      return ok({ revoked_sessions_count: revoked });
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
      if (sessionId === currentSessionId(request)) {
        setRefreshCookie("", 0);
      }
      sessions.delete(sessionId);
      return ok(null);
    }),

    http.patch("/api/auth/users/me", async ({ request }) => {
      await sleepFor(scenario);
      const user = userForToken(db, request);
      if (!user) {
        return fail(401, "AUTHENTICATION_REQUIRED", "Yêu cầu thông tin xác thực để thực hiện thao tác.");
      }
      const body = await request.json() as Record<string, unknown>;
      if ("student_id" in body) {
        return fail(403, "STUDENT_ID_IMMUTABLE", "Không được tự sửa MSSV.");
      }
      const unknown = Object.keys(body).filter((key) => !PROFILE_FIELDS.has(key));
      if (unknown.length > 0) {
        return fail(400, "VALIDATION_ERROR", "Dữ liệu đầu vào không hợp lệ.",
          unknown.map((field) => ({ field, issue: "Unknown field." })));
      }
      const updated = { ...user, ...body };
      updated.display_name = `${updated.last_name} ${updated.first_name}`.trim();
      db.authUsersById[user.id] = updated;
      return ok({
        display_name: updated.display_name,
        phone_number: updated.phone_number,
        bio: updated.bio,
        preferences: updated.preferences,
      });
    }),

    http.post("/api/auth/password-change", async ({ request }) => {
      await sleepFor(scenario);
      if (scenario === "server-error") {
        return fail(503, "IDENTITY_UNAVAILABLE", "Dịch vụ tạm thời không khả dụng.");
      }
      const user = userForToken(db, request);
      if (!user) {
        return fail(401, "AUTHENTICATION_REQUIRED", "Yêu cầu thông tin xác thực để thực hiện thao tác.");
      }
      const body = await request.json() as Record<string, string>;
      if (body.old_password !== DEMO_PASSWORD) {
        return fail(400, "VALIDATION_ERROR", "Dữ liệu đầu vào không hợp lệ.",
          [{ field: "old_password", issue: "Your old password was entered incorrectly." }]);
      }
      if (body.new_password1 !== body.new_password2) {
        return fail(400, "VALIDATION_ERROR", "Dữ liệu đầu vào không hợp lệ.",
          [{ field: "new_password2", issue: "The two password fields didn't match." }]);
      }
      for (const [id, session] of sessions) {
        if (session.userId === user.id) {
          sessions.delete(id);
        }
      }
      setRefreshCookie("", 0);
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
