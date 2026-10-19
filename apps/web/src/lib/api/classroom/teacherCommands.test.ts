import { http } from "msw";
import { describe, expect, it } from "vitest";

import {
  assignTeacher,
  countActiveEnrollments,
  countActiveGroups,
  createClass,
  createCourse,
  issueClassJoinCode,
  lockGrouping,
  patchClass,
  setClassState,
} from "@/lib/api/classroom/endpoints";
import { createApiClient } from "@/lib/api/client";
import { server } from "@/mocks/server";
import { buildClass, buildCourse, buildEnrollment, buildGroup, envelope, envelopeError } from "@/test/classroomHandlers";

const client = createApiClient({ baseUrl: "http://localhost", getAccessToken: () => "token", onUnauthorized: () => undefined });
const KEY = "22222222-2222-4222-8222-222222222222";

interface Seen {
  method: string;
  path: string;
  key: string | null;
  body: unknown;
}

function capture(method: "post" | "patch", path: string, data: unknown) {
  const seen: Seen[] = [];
  server.use(
    http[method](path, async ({ request }) => {
      seen.push({ method: request.method, path: new URL(request.url).pathname, key: request.headers.get("Idempotency-Key"), body: await request.json() });
      return envelope(data);
    }),
  );
  return seen;
}

describe("teacher class commands", () => {
  it("createCourse posts code and name with the idempotency key", async () => {
    const seen = capture("post", "/api/classroom/courses/", buildCourse());
    await createCourse(client, { code: "SE330", name: "Đồ án", idempotencyKey: KEY });
    expect(seen).toEqual([{ method: "POST", path: "/api/classroom/courses/", key: KEY, body: { code: "SE330", name: "Đồ án" } }]);
  });

  it("createClass maps camelCase fields to the snake_case contract", async () => {
    const seen = capture("post", "/api/classroom/classes/", buildClass());
    await createClass(client, {
      courseId: "course-1",
      code: "SE330.P11",
      name: "Đồ án",
      term: "HK1",
      startsOn: "2026-09-01",
      endsOn: "2027-01-15",
      groupMinSize: 2,
      groupMaxSize: 5,
      idempotencyKey: KEY,
    });
    expect(seen[0].key).toBe(KEY);
    expect(seen[0].body).toEqual({
      course_id: "course-1",
      code: "SE330.P11",
      name: "Đồ án",
      term: "HK1",
      starts_on: "2026-09-01",
      ends_on: "2027-01-15",
      group_min_size: 2,
      group_max_size: 5,
    });
  });

  it("patchClass sends the version and only the fields given", async () => {
    const seen = capture("patch", "/api/classroom/classes/c1/", buildClass({ version: 4 }));
    await patchClass(client, "c1", { version: 3, name: "Tên mới", groupMaxSize: 6, idempotencyKey: KEY });
    expect(seen[0]).toMatchObject({ method: "PATCH", key: KEY, body: { version: 3, name: "Tên mới", group_max_size: 6 } });
    expect(seen[0].body).not.toHaveProperty("term");
  });

  it("setClassState, lockGrouping and assignTeacher post the version they were given", async () => {
    const state = capture("post", "/api/classroom/classes/c1/state/", buildClass());
    const lock = capture("post", "/api/classroom/classes/c1/lock-grouping/", buildClass());
    const teacher = capture("post", "/api/classroom/classes/c1/teachers/assign/", buildClass());
    await setClassState(client, "c1", { version: 2, status: "CLOSED", idempotencyKey: KEY });
    await lockGrouping(client, "c1", { version: 3, idempotencyKey: KEY });
    await assignTeacher(client, "c1", { version: 4, userId: "u9", role: "CO_TEACHER", status: "ACTIVE", idempotencyKey: KEY });
    expect(state[0].body).toEqual({ version: 2, status: "CLOSED" });
    expect(lock[0].body).toEqual({ version: 3 });
    expect(teacher[0].body).toEqual({ version: 4, user_id: "u9", role: "CO_TEACHER", status: "ACTIVE" });
  });

  it("issueClassJoinCode returns the one-time raw code only when enabling", async () => {
    const seen = capture("post", "/api/classroom/classes/c1/join-code/", { id: "c1", version: 5, code: "ABCD1234", expires_at: "2030-01-01T00:00:00Z", enabled: true });
    const result = await issueClassJoinCode(client, "c1", { version: 4, enabled: true, idempotencyKey: KEY });
    expect(result.code).toBe("ABCD1234");
    expect(seen[0].body).toEqual({ version: 4, enabled: true });
  });

  it("surfaces a version conflict and a not-a-teacher refusal with the backend codes", async () => {
    server.use(
      http.post("/api/classroom/classes/c1/state/", () => envelopeError(409, "VERSION_CONFLICT", "Lớp học đã thay đổi. Vui lòng tải lại dữ liệu.")),
      http.post("/api/classroom/classes/c2/state/", () => envelopeError(403, "PERMISSION_DENIED", "Bạn không có quyền quản lý lớp học này.")),
    );
    await expect(setClassState(client, "c1", { version: 1, status: "CLOSED", idempotencyKey: KEY })).rejects.toMatchObject({ status: 409, code: "VERSION_CONFLICT" });
    await expect(setClassState(client, "c2", { version: 1, status: "CLOSED", idempotencyKey: KEY })).rejects.toMatchObject({ status: 403, code: "PERMISSION_DENIED" });
  });
});

describe("page-size-one counts", () => {
  it("read total_count instead of loading every row, with the ACTIVE filter", async () => {
    const urls: string[] = [];
    server.use(
      http.get("/api/classroom/classes/c1/enrollments/", ({ request }) => {
        urls.push(request.url);
        return envelope([buildEnrollment(), buildEnrollment({ id: "enr-2" })]);
      }),
      http.get("/api/classroom/classes/c1/groups/", ({ request }) => {
        urls.push(request.url);
        return envelope([buildGroup()]);
      }),
    );
    expect(await countActiveEnrollments(client, "c1")).toBe(2);
    expect(await countActiveGroups(client, "c1")).toBe(1);
    for (const url of urls) {
      expect(new URL(url).searchParams.get("page_size")).toBe("1");
      expect(new URL(url).searchParams.get("status")).toBe("ACTIVE");
    }
  });
});
