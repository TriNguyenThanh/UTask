import { http } from "msw";
import { describe, expect, it } from "vitest";

import {
  CLASS_CONCURRENCY,
  loadCourseDetail,
  loadCourseEnrollments,
  loadMyGroup,
  MAX_GROUPS_PROBED,
} from "@/lib/api/classroom/loaders";
import { createApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { server } from "@/mocks/server";
import {
  buildClass,
  buildCourse,
  buildGroup,
  buildMember,
  buildTeacher,
  classroomHandlers,
  envelope,
  envelopeError,
} from "@/test/classroomHandlers";

const client = createApiClient({ baseUrl: "http://localhost", getAccessToken: () => "token", onUnauthorized: () => undefined });
const ME = "user-1";

function user(id: string, display_name: string) {
  return { id, email: "", student_id: null, display_name, avatar_url: null, bio: null, roles: [], account_status: "ACTIVE" };
}

describe("loadMyGroup", () => {
  it("returns null when the class has no groups", async () => {
    server.use(...classroomHandlers({ classes: [buildClass()], courses: [] }));
    expect(await loadMyGroup(client, "class-1")).toBeNull();
  });

  it("skips groups that answer 404 and returns the one the user belongs to", async () => {
    server.use(
      ...classroomHandlers({
        classes: [buildClass()],
        courses: [],
        groups: { "class-1": [buildGroup({ id: "g1" }), buildGroup({ id: "g2", name: "Nhóm 2" })] },
        members: { g2: [buildMember({ group_id: "g2" })] },
      }),
    );
    const mine = await loadMyGroup(client, "class-1");
    expect(mine?.group.id).toBe("g2");
    expect(mine?.members).toHaveLength(1);
  });

  it("propagates a non-404 failure instead of reporting no group", async () => {
    server.use(
      http.get("/api/classroom/groups/:groupId/members/", () => envelopeError(500, "INTERNAL_ERROR", "Lỗi máy chủ.")),
      ...classroomHandlers({ classes: [buildClass()], courses: [], groups: { "class-1": [buildGroup()] } }),
    );
    await expect(loadMyGroup(client, "class-1")).rejects.toBeInstanceOf(ApiError);
  });

  it("probes at most MAX_GROUPS_PROBED groups", async () => {
    const groups = Array.from({ length: MAX_GROUPS_PROBED + 10 }, (_, index) => buildGroup({ id: `g${index}` }));
    let probed = 0;
    server.use(
      http.get("/api/classroom/groups/:groupId/members/", () => {
        probed += 1;
        return envelopeError(404, "RESOURCE_NOT_FOUND", "Không tìm thấy nhóm học tập.");
      }),
      ...classroomHandlers({ classes: [buildClass()], courses: [], groups: { "class-1": groups } }),
    );
    expect(await loadMyGroup(client, "class-1")).toBeNull();
    expect(probed).toBe(MAX_GROUPS_PROBED);
  });
});

describe("loadCourseEnrollments", () => {
  it("maps each class with its membership", async () => {
    server.use(
      ...classroomHandlers({
        classes: [buildClass({ id: "c1" }), buildClass({ id: "c2", name: "Lớp 2" })],
        courses: [buildCourse()],
        groups: { c2: [buildGroup({ id: "g1", class_section: "c2" })] },
        members: { g1: [buildMember({ user_id: ME, role: "LEADER" })] },
      }),
    );
    const result = await loadCourseEnrollments(client, ME);
    expect(result.map((item) => item.membership.status)).toEqual(["none", "assigned"]);
    expect(result[1].membership).toMatchObject({ role: "leader" });
  });

  it("probes several classes at once, never more than CLASS_CONCURRENCY, and keeps class order", async () => {
    const ids = Array.from({ length: 8 }, (_, index) => `c${index + 1}`);
    let inFlight = 0;
    let peak = 0;
    // Giữ các request `groups` cho tới khi đủ CLASS_CONCURRENCY request đang chờ; nếu loader
    // chạy ít lớp hơn thế thì test treo, nếu nhiều hơn thì `peak` vượt.
    let openGate: () => void = () => undefined;
    const gate = new Promise<void>((resolve) => {
      openGate = resolve;
    });
    server.use(
      http.get("/api/classroom/classes/:classId/groups/", async ({ params }) => {
        inFlight += 1;
        peak = Math.max(peak, inFlight);
        if (inFlight >= CLASS_CONCURRENCY) openGate();
        await gate;
        inFlight -= 1;
        return envelope(params.classId === "c8" ? [buildGroup({ id: "g8", class_section: "c8" })] : []);
      }),
      ...classroomHandlers({
        classes: ids.map((id) => buildClass({ id, name: id })),
        courses: [buildCourse()],
        members: { g8: [buildMember({ user_id: ME })] },
      }),
    );
    const result = await loadCourseEnrollments(client, ME);
    expect(result.map((item) => item.courseId)).toEqual(ids);
    expect(result.map((item) => item.membership.status)).toEqual([...Array(7).fill("none"), "assigned"]);
    expect(peak).toBe(CLASS_CONCURRENCY);
  });

  it("returns an empty list for a user with no classes", async () => {
    server.use(...classroomHandlers({ classes: [], courses: [] }));
    expect(await loadCourseEnrollments(client, ME)).toEqual([]);
  });
});

describe("loadCourseDetail", () => {
  it("fills the instructor name from users/batch", async () => {
    server.use(
      ...classroomHandlers({
        classes: [buildClass()],
        courses: [buildCourse()],
        teachers: { "class-1": [buildTeacher({ user_id: "t1" })] },
        users: [user("t1", "Cô Lan")],
      }),
    );
    expect((await loadCourseDetail(client, ME, "class-1")).instructorName).toBe("Cô Lan");
  });

  it("keeps the page when the instructor lookup fails", async () => {
    server.use(
      http.post("/api/auth/users/batch", () => envelopeError(500, "INTERNAL_ERROR", "Lỗi.")),
      ...classroomHandlers({
        classes: [buildClass()],
        courses: [buildCourse()],
        teachers: { "class-1": [buildTeacher()] },
      }),
    );
    expect((await loadCourseDetail(client, ME, "class-1")).instructorName).toBe("");
  });

  it("rejects with the 404 for an unknown class", async () => {
    server.use(...classroomHandlers({ classes: [], courses: [] }));
    await expect(loadCourseDetail(client, ME, "nope")).rejects.toMatchObject({ status: 404 });
  });
});
