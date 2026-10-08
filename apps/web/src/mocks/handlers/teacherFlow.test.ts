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

  it("teacher-empty: project access, which follows the same assignments, is gone too", async () => {
    useRepo("teacher-empty");
    for (const path of ["", "/issues/NEXUS-104", "/code", "/settings"]) {
      expect((await call(`/projects/project-nexus${path}`, TEACHER_ID)).status, path).toBe(404);
    }
    // Team members are not instructors: their access does not depend on this scenario.
    expect((await call("/projects/project-nexus", LEADER_ID)).status).toBe(200);
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

describe("Student endpoints stay closed to a Teacher", () => {
  it("does not open Student course or team-creation endpoints", async () => {
    useRepo();
    expect((await call("/courses/course-se330", TEACHER_ID)).status).toBe(404);
    const create = await call("/courses/course-it3090/teams", TEACHER_ID, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer mock-access:${TEACHER_ID}:test` },
      body: JSON.stringify({ teamName: "Nhom giang vien", maxMembers: 4 }),
    });
    expect(create.status).toBe(404);
    expect((await call("/projects", TEACHER_ID)).json).toEqual([]);
  });
});

describe("Teacher reads a project through the class assignment", () => {
  const OPEN = ["", "/issues/NEXUS-104", "/code"];

  it("opens the workspace, an issue and the code of a project in a class they teach", async () => {
    useRepo();
    for (const path of OPEN) {
      expect((await call(`/projects/project-nexus${path}`, TEACHER_ID)).status, path).toBe(200);
    }
  });

  it("describes the viewer as an instructor of the class and never invents a team role", async () => {
    useRepo();
    const { json } = await call("/projects/project-nexus", TEACHER_ID);
    expect(json.viewer).toEqual({ kind: "course-instructor", courseId: "course-se330" });
    expect(json.courseId).toBe("course-se330");
    expect(json.teamId).toBe("team-nexus");
    expect("myRole" in json).toBe(false);
    // Nothing is "mine" for someone with no tasks.
    expect(json.issues.some((issue: { isMine: boolean }) => issue.isMine)).toBe(false);
  });

  it("keeps a member's viewer and role, with mine derived from the real user", async () => {
    useRepo();
    const nam = (await call("/projects/project-nexus", LEADER_ID)).json;
    expect(nam.viewer).toEqual({ kind: "team-member", role: "leader" });
    expect(nam.myRole).toBe("leader");
    const mine = (list: { key: string; isMine: boolean }[]) => list.filter((i) => i.isMine).map((i) => i.key);
    expect(mine(nam.issues)).toEqual(["NEXUS-104", "NEXUS-95"]);
    const linh = (await call("/projects/project-nexus", MEMBER_ID)).json;
    expect(linh.viewer).toEqual({ kind: "team-member", role: "member" });
    expect(mine(linh.issues)).toEqual(["NEXUS-101", "NEXUS-105"]);
  });

  it("marks contributors as 'me' only for the signed-in user", async () => {
    useRepo();
    const isMe = async (userId: string) =>
      ((await call("/projects/project-nexus/code", userId)).json.contributors as { displayName: string; isMe: boolean }[])
        .filter((c) => c.isMe)
        .map((c) => c.displayName);
    expect(await isMe(LEADER_ID)).toEqual(["Nguyễn Hoàng Nam"]);
    expect(await isMe(STUDENT_ID)).toEqual(["Lê Minh Khoa"]);
    expect(await isMe(TEACHER_ID)).toEqual([]);
  });

  it("lists the same five people in the code view as the team roster", async () => {
    useRepo();
    const code = (await call("/projects/project-nexus/code", TEACHER_ID)).json;
    const members = (await call("/teacher/courses/course-se330/teams/team-nexus", TEACHER_ID)).json.members;
    expect(code.contributors.map((c: { userId: string }) => c.userId).sort()).toEqual(
      members.map((m: { userId: string }) => m.userId).sort(),
    );
    const sum = (key: string) => code.contributors.reduce((n: number, c: Record<string, number>) => n + c[key], 0);
    expect(sum("commits")).toBe(code.stats.commits);
    expect(sum("additions")).toBe(code.stats.linesChanged.added);
    expect(sum("deletions")).toBe(code.stats.linesChanged.removed);
    expect(sum("pullRequestCount")).toBe(code.stats.pullRequests.total);
    expect(sum("commitPercent")).toBe(100);
  });

  it("refuses project settings and the AI key to an instructor with 403, not 404", async () => {
    useRepo();
    expect((await call("/projects/project-nexus/settings", TEACHER_ID)).status).toBe(403);
    const put = await call("/projects/project-nexus/settings/ai-key", TEACHER_ID, {
      method: "PUT",
      headers: { "Content-Type": "application/json", Authorization: `Bearer mock-access:${TEACHER_ID}:test` },
      body: JSON.stringify({ provider: "openai", apiKey: "sk-test-1234" }),
    });
    expect(put.status).toBe(403);
  });

  it("does not let an instructor of another class open the project, existing or not", async () => {
    useRepo();
    for (const path of [...OPEN, "/settings"]) {
      const outside = await call(`/projects/project-nexus${path}`, TEACHER2_ID);
      const missing = await call(`/projects/project-nope${path}`, TEACHER2_ID);
      expect(outside.status, path).toBe(404);
      expect(outside.text.replace("project-nexus", "")).toBe(missing.text.replace("project-nope", ""));
    }
    expect((await call("/projects/project-deli", TEACHER_ID)).status).toBe(404);
    expect((await call("/projects/project-deli", TEACHER2_ID)).status).toBe(200);
  });

  it("does not let the TEACHER role alone open any project", async () => {
    const repository = useRepo();
    repository.db.authUsersById[STUDENT_ID] = {
      ...repository.db.authUsersById[STUDENT_ID],
      roles: ["STUDENT", "TEACHER"],
    };
    // SV01 teaches nothing, so a project outside their teams stays closed.
    expect((await call("/projects/project-legacy", STUDENT_ID)).status).toBe(404);
    // And SV01 on NEXUS is still a member (leader), not an instructor.
    expect((await call("/projects/project-nexus", STUDENT_ID)).json.viewer).toEqual({
      kind: "team-member",
      role: "leader",
    });
  });

  it("does not honour an instructor assignment for an account without the TEACHER role", async () => {
    const repository = useRepo();
    repository.db.authUsersById[TEACHER_ID] = {
      ...repository.db.authUsersById[TEACHER_ID],
      roles: ["STUDENT"],
    };
    expect((await call("/projects/project-nexus", TEACHER_ID)).status).toBe(404);
  });

  it("answers an instructor at a fixed clock, and a student at the live one", async () => {
    useRepo();
    const stamp = async (userId: string) =>
      ((await call("/projects/project-nexus", userId)).json.issues as { key: string; updatedAt: string }[]).find(
        (issue) => issue.key === "NEXUS-104",
      )!.updatedAt;
    expect(await stamp(TEACHER_ID)).toBe(await stamp(TEACHER_ID));
    expect(await stamp(TEACHER_ID)).toMatch(/^2026-10-20T/);
  });

  it("says 'no repository' for a project that exists without one, not 'not found'", async () => {
    useRepo();
    for (const userId of [MEMBER_ID, TEACHER2_ID]) {
      const code = await call("/projects/project-deli/code", userId);
      expect(code.status).toBe(200);
      expect(code.json.syncState).toBe("no-repository");
      expect(code.json.repository).toBeNull();
      expect(code.json.contributors).toEqual([]);
    }
    expect((await call("/projects/project-nope/code", TEACHER_ID)).status).toBe(404);
  });
});

describe("Teacher team dashboard endpoint", () => {
  it("returns members, measured progress, issue counts and the overdue formula inputs", async () => {
    useRepo();
    const { status, json } = await call("/teacher/courses/course-se330/teams/team-nexus", TEACHER_ID);
    expect(status).toBe(200);
    expect(json.team).toEqual({ teamId: "team-nexus", name: "Team NEXUS", courseId: "course-se330" });
    expect(json.members).toHaveLength(5);
    expect(json.project.projectId).toBe("project-nexus");
    expect(json.progress.basis).toBe("sprint-points");
    const counts = Object.values(json.issues.byStatus as Record<string, number>);
    expect(counts.reduce((a, b) => a + b, 0)).toBe(json.issues.total);
    // Four issues carry a deadline; two are open and past it at the fixed clock.
    expect(json.overdue).toEqual({ overdue: 2, withDueDate: 4 });
    expect(json.asOf).toBe("2026-10-20T08:30:00.000Z");
  });

  it("reports no data, not zero, for a team without a project", async () => {
    useRepo();
    const { json } = await call("/teacher/courses/course-it3090/teams/team-iot-vision", TEACHER_ID);
    expect(json.project).toBeNull();
    expect(json.progress).toBeNull();
    expect(json.issues).toBeNull();
    expect(json.sprint).toBeNull();
    expect(json.overdue).toBeNull();
    expect(json.signals.map((s: { code: string }) => s.code)).toContain("no-project");
  });

  it("answers 404 for a team outside the class like a team that does not exist", async () => {
    useRepo();
    const outside = await call("/teacher/courses/course-se330/teams/team-deli", TEACHER_ID);
    const missing = await call("/teacher/courses/course-se330/teams/team-nope", TEACHER_ID);
    expect(outside.status).toBe(404);
    expect(outside.text).toBe(missing.text);
    // A class the caller does not teach hides its teams the same way as one that is absent.
    const otherClass = await call("/teacher/courses/course-se330/teams/team-nexus", TEACHER2_ID);
    const absentClass = await call("/teacher/courses/course-nope/teams/team-nexus", TEACHER2_ID);
    expect(otherClass.status).toBe(404);
    expect(otherClass.text).toBe(absentClass.text);
  });

  it("is closed to students and fails with the partial-error scenario", async () => {
    useRepo();
    expect((await call("/teacher/courses/course-se330/teams/team-nexus", STUDENT_ID)).status).toBe(403);
    useRepo("teacher-partial-error");
    expect((await call("/teacher/courses/course-se330/teams/team-nexus", TEACHER_ID)).status).toBe(500);
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
