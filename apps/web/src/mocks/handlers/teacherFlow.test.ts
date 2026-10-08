import { describe, expect, it } from "vitest";

import {
  LEADER_ID,
  MEMBER_ID,
  STUDENT_ID,
  TEACHER2_ID,
  TEACHER_ID,
} from "@/mocks/data/database";
import { createMockHandlers } from "@/mocks/handlers";
import { server } from "@/mocks/server";
import { createMemoryRepository, type MockRepository } from "@/mocks/data/storage";
import type { MockScenario } from "@/mocks/scenarios";

const BASE = "http://localhost/api/work/api/v1";

function useRepo(scenario: MockScenario = "default"): MockRepository {
  const repository = createMemoryRepository(scenario);
  server.use(...createMockHandlers(scenario, repository));
  return repository;
}

async function call(path: string, userId: string | null, init: RequestInit = {}) {
  const response = await fetch(`${BASE}${path}`, {
    ...init,
    headers: userId ? { Authorization: `Bearer mock-access:${userId}:test` } : {},
  });
  const text = await response.text();
  return { status: response.status, text, json: text ? JSON.parse(text) : null };
}

describe("Teacher read endpoints: authentication and role", () => {
  it("rejects a request without a session", async () => {
    useRepo();
    expect((await call("/teacher/courses", null)).status).toBe(401);
  });

  it.each([
    ["leader", LEADER_ID],
    ["member", MEMBER_ID],
    ["SV01", STUDENT_ID],
  ])("blocks the student account %s from every Teacher endpoint", async (_name, userId) => {
    useRepo();
    for (const path of [
      "/teacher/courses",
      "/teacher/courses/course-se330",
      "/teacher/courses/course-se330/students",
      "/teacher/courses/course-se330/teams",
      "/teacher/courses/course-se330/oversight",
    ]) {
      expect((await call(path, userId)).status, path).toBe(403);
    }
  });

  it("does not let a TEACHER role alone open a class the account is not assigned to", async () => {
    // SV01 is enrolled in SE330 as a student. Granting the role must not grant the class.
    const repository = useRepo();
    repository.db.authUsersById[STUDENT_ID] = {
      ...repository.db.authUsersById[STUDENT_ID],
      roles: ["STUDENT", "TEACHER"],
    };
    expect((await call("/teacher/courses", STUDENT_ID)).json).toEqual({ courses: [] });
    expect((await call("/teacher/courses/course-se330", STUDENT_ID)).status).toBe(404);
    expect((await call("/teacher/courses/course-se330/students", STUDENT_ID)).status).toBe(404);
  });
});

describe("Teacher read endpoints: per-class assignment", () => {
  it("lists exactly the classes each teacher is assigned to", async () => {
    useRepo();
    const first = await call("/teacher/courses", TEACHER_ID);
    expect(first.json.courses.map((c: { courseId: string }) => c.courseId).sort()).toEqual([
      "course-it3090",
      "course-se330",
      "course-se330-n2",
    ]);
    const second = await call("/teacher/courses", TEACHER2_ID);
    expect(second.json.courses.map((c: { courseId: string }) => c.courseId)).toEqual(["course-cs402"]);
  });

  it("answers an unassigned class and a nonexistent class identically", async () => {
    useRepo();
    for (const suffix of ["", "/students", "/teams", "/oversight"]) {
      const outside = await call(`/teacher/courses/course-cs402${suffix}`, TEACHER_ID);
      const sameElsewhere = await call(`/teacher/courses/course-se331${suffix}`, TEACHER_ID);
      const missing = await call(`/teacher/courses/course-does-not-exist${suffix}`, TEACHER_ID);
      expect(outside.status).toBe(404);
      expect(outside.text).toBe(missing.text);
      expect(sameElsewhere.status).toBe(missing.status);
      expect(sameElsewhere.text).toBe(missing.text);
    }
  });

  it("keeps the second teacher out of the first teacher's classes and vice versa", async () => {
    useRepo();
    expect((await call("/teacher/courses/course-se330/students", TEACHER2_ID)).status).toBe(404);
    expect((await call("/teacher/courses/course-cs402/students", TEACHER_ID)).status).toBe(404);
    expect((await call("/teacher/courses/course-cs402/students", TEACHER2_ID)).status).toBe(200);
  });

  it("returns different data for the two SE330 classes", async () => {
    useRepo();
    const first = await call("/teacher/courses/course-se330", TEACHER_ID);
    const second = await call("/teacher/courses/course-se330-n2", TEACHER_ID);
    expect(first.json.courseCode).toBe(second.json.courseCode);
    expect(first.json.studentCount).toBeGreaterThan(0);
    expect(second.json.studentCount).toBe(0);
    expect((await call("/teacher/courses/course-se330-n2/students", TEACHER_ID)).json.students).toEqual([]);
    expect((await call("/teacher/courses/course-se330-n2/teams", TEACHER_ID)).json.teams).toEqual([]);
    expect((await call("/teacher/courses/course-se330-n2/oversight", TEACHER_ID)).json.teams).toEqual([]);
  });

  it("never exposes secrets or hidden fields in student rows", async () => {
    useRepo();
    const { json } = await call("/teacher/courses/course-se330/students", TEACHER_ID);
    for (const student of json.students) {
      expect(Object.keys(student).sort()).toEqual(
        ["email", "name", "pendingTeam", "studentCode", "team", "userId"].sort(),
      );
    }
  });
});

describe("Teacher oversight endpoint", () => {
  it("returns one row per team with measured fields, the rule threshold and no member data", async () => {
    useRepo();
    const { json } = await call("/teacher/courses/course-se330/oversight", TEACHER_ID);
    expect(json.staleAfterDays).toBe(7);
    expect(json.teams).toHaveLength(1);
    const [nexus] = json.teams;
    expect(Object.keys(nexus).sort()).toEqual(
      ["issues", "lastActivity", "memberCount", "name", "progress", "project", "signals", "sprint", "teamId"].sort(),
    );
    expect(nexus.progress.basis).toBe("sprint-points");
    expect(nexus.issues.total).toBeGreaterThan(0);
    expect(nexus.sprint.name).toMatch(/^Sprint/);
  });

  it("signals a team without a project, with the cause, and never invents progress", async () => {
    useRepo();
    const { json } = await call("/teacher/courses/course-it3090/oversight", TEACHER_ID);
    expect(json.teams).toHaveLength(2);
    for (const team of json.teams) {
      expect(team.project).toBeNull();
      expect(team.progress).toBeNull();
      expect(team.issues).toBeNull();
      expect(team.signals.map((s: { code: string }) => s.code)).toContain("no-project");
    }
  });

  it("matches the class summary count of teams with signals", async () => {
    useRepo();
    for (const id of ["course-se330", "course-it3090", "course-se330-n2"]) {
      const summary = (await call(`/teacher/courses/${id}`, TEACHER_ID)).json;
      const oversight = (await call(`/teacher/courses/${id}/oversight`, TEACHER_ID)).json;
      const flagged = oversight.teams.filter((t: { signals: unknown[] }) => t.signals.length > 0);
      expect(summary.teamsWithSignals, id).toBe(flagged.length);
    }
  });
});

describe("Teacher scenarios", () => {
  it("teacher-empty: no classes, and every class is unavailable", async () => {
    useRepo("teacher-empty");
    expect((await call("/teacher/courses", TEACHER_ID)).json).toEqual({ courses: [] });
    expect((await call("/teacher/courses/course-se330", TEACHER_ID)).status).toBe(404);
  });

  it("teacher-partial-error: classes load, students and teams fail", async () => {
    useRepo("teacher-partial-error");
    expect((await call("/teacher/courses", TEACHER_ID)).status).toBe(200);
    expect((await call("/teacher/courses/course-se330", TEACHER_ID)).status).toBe(200);
    expect((await call("/teacher/courses/course-se330/students", TEACHER_ID)).status).toBe(500);
    expect((await call("/teacher/courses/course-se330/teams", TEACHER_ID)).status).toBe(500);
    expect((await call("/teacher/courses/course-se330/oversight", TEACHER_ID)).status).toBe(500);
  });

  it("server-error: everything fails", async () => {
    useRepo("server-error");
    expect((await call("/teacher/courses", TEACHER_ID)).status).toBe(500);
  });
});

describe("Student endpoints stay closed to a Teacher in Phase 1", () => {
  it("does not open Student course, team-creation or project endpoints", async () => {
    useRepo();
    expect((await call("/courses/course-se330", TEACHER_ID)).status).toBe(404);
    const create = await call("/courses/course-it3090/teams", TEACHER_ID, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer mock-access:${TEACHER_ID}:test` },
      body: JSON.stringify({ teamName: "Nhom giang vien", maxMembers: 4 }),
    });
    expect(create.status).toBe(404);
    for (const path of [
      "/projects/project-nexus",
      "/projects/project-nexus/issues/NEXUS-104",
      "/projects/project-nexus/code",
      "/projects/project-nexus/settings",
    ]) {
      expect((await call(path, TEACHER_ID)).status, path).toBe(404);
    }
    expect((await call("/projects", TEACHER_ID)).json).toEqual([]);
  });
});

describe("Access failures do not reveal which ids exist", () => {
  it("answers 404 for outside and nonexistent projects alike, on every project endpoint", async () => {
    useRepo();
    // Linh is a Member of NEXUS and DELI but is not in a third project.
    for (const path of ["", "/issues/X-1", "/code", "/settings"]) {
      const outside = await call(`/projects/project-legacy${path}`, MEMBER_ID);
      const missing = await call(`/projects/project-nope${path}`, MEMBER_ID);
      expect(outside.status, path).toBe(404);
      expect(outside.text.replace("project-legacy", "")).toBe(missing.text.replace("project-nope", ""));
    }
  });

  it("keeps 403 for an action a project member may not perform", async () => {
    useRepo();
    // Linh is a Member of DELI: she can open the project but not its settings.
    expect((await call("/projects/project-deli", MEMBER_ID)).status).toBe(200);
    expect((await call("/projects/project-deli/settings", MEMBER_ID)).status).toBe(403);
  });

  it("answers 404 for a course the student is not enrolled in, existing or not", async () => {
    useRepo();
    const outside = await call("/courses/course-se330-n2", STUDENT_ID);
    const missing = await call("/courses/course-nope", STUDENT_ID);
    expect(outside.status).toBe(404);
    expect(outside.text).toBe(missing.text);
  });
});

describe("Notification scope is the same for list, mark-read and read-all", () => {
  const CLASS_LEVEL = ["n2", "n5", "n8"]; // all target course-se330
  const PROJECT_LEVEL = ["n1", "n3", "n4", "n6", "n7"]; // all target project-nexus

  const listIds = async (userId: string) =>
    ((await call("/notifications", userId)).json as { id: string }[]).map((n) => n.id).sort();

  it("shows a teacher only the class-level notifications of their own classes", async () => {
    useRepo();
    expect(await listIds(TEACHER_ID)).toEqual(CLASS_LEVEL);
    expect(await listIds(TEACHER2_ID)).toEqual([]);
  });

  it("keeps a student's class and project notifications, and hides other classes", async () => {
    useRepo();
    expect(await listIds(STUDENT_ID)).toEqual([...CLASS_LEVEL, ...PROJECT_LEVEL].sort());
    expect(await listIds(MEMBER_ID)).toEqual([...CLASS_LEVEL, ...PROJECT_LEVEL].sort());
  });

  it("refuses to mark a notification read when the caller cannot see it", async () => {
    const repository = useRepo();
    const post = (id: string, userId: string) =>
      call(`/notifications/${id}/read`, userId, { method: "POST" });

    expect((await post("n2", TEACHER2_ID)).status).toBe(404); // other teacher's class
    expect((await post("n1", TEACHER_ID)).status).toBe(404); // project-level, no project access
    expect((await post("n-nope", TEACHER_ID)).status).toBe(404); // nonexistent
    expect(repository.db.notificationReadByUser[TEACHER2_ID]).toBeUndefined();
    expect(repository.db.notificationReadByUser[TEACHER_ID]).toBeUndefined();

    expect((await post("n2", TEACHER_ID)).status).toBe(204);
    expect(repository.db.notificationReadByUser[TEACHER_ID]).toEqual(["n2"]);
  });

  it("read-all marks only what the caller can see", async () => {
    const repository = useRepo();
    const readAll = (userId: string) => call("/notifications/read-all", userId, { method: "POST" });

    expect((await readAll(TEACHER2_ID)).status).toBe(204);
    expect(repository.db.notificationReadByUser[TEACHER2_ID]).toEqual([]);

    expect((await readAll(TEACHER_ID)).status).toBe(204);
    expect([...repository.db.notificationReadByUser[TEACHER_ID]].sort()).toEqual(CLASS_LEVEL);

    const afterwards = (await call("/notifications", TEACHER_ID)).json as { read: boolean }[];
    expect(afterwards.every((notification) => notification.read)).toBe(true);
  });
});
