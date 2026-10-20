import { http } from "msw";
import { describe, expect, it } from "vitest";

import type { CourseEnrollment } from "@/features/my-work/types";
import { createApiClient } from "@/lib/api/client";
import type { WorkProjectCard } from "@/lib/api/work/adapters";
import { attachProjects, buildMyWorkOverview, loadMyWorkOverview, sprintHealth, toCourseSprint, toMyTask } from "@/lib/api/work/myWork";
import { server } from "@/mocks/server";
import { buildClass, buildCourse, buildGroup, classroomHandlers, envelopeError } from "@/test/classroomHandlers";
import {
  buildDefaultStates,
  buildProgress,
  buildProject,
  buildProjectMember,
  buildSprint,
  buildTask,
  workHandlers,
  type WorkFixture,
} from "@/test/workHandlers";

const NOW = new Date("2026-10-20T08:00:00");
const client = createApiClient({ baseUrl: "http://localhost", getAccessToken: () => "token", onUnauthorized: () => undefined });

const card = (overrides: Partial<WorkProjectCard> = {}): WorkProjectCard => ({
  projectId: "project-1",
  identifier: "NEXUS",
  name: "Nexus",
  archived: false,
  classId: "class-1",
  classCode: "SE100.A",
  className: "Lớp A",
  courseCode: "SE100",
  groupId: "group-1",
  groupName: "Nhóm 1",
  myRole: "MEMBER",
  repository: null,
  createdAt: "2026-09-01T00:00:00Z",
  ...overrides,
});

const enrollment = (overrides: Partial<CourseEnrollment> = {}): CourseEnrollment => ({
  courseId: "class-1",
  courseCode: "SE100",
  courseName: "Lớp A",
  semester: "HK1 2026–2027",
  teamFormation: { mode: "self-select", registrationDeadline: null },
  projectId: null,
  membership: { status: "assigned", teamId: "group-1", teamName: "Nhóm 1", role: "member" },
  ...overrides,
});

describe("sprintHealth", () => {
  it("is late once the deadline passed unfinished, at risk when well behind the clock, otherwise on track", () => {
    expect(sprintHealth(50, "2026-10-01", "2026-10-10", NOW)).toBe("late");
    expect(sprintHealth(100, "2026-10-01", "2026-10-10", NOW)).toBe("on-track");
    expect(sprintHealth(10, "2026-10-10", "2026-10-30", NOW)).toBe("at-risk"); // 50% of time gone, 10% done
    expect(sprintHealth(45, "2026-10-10", "2026-10-30", NOW)).toBe("on-track");
  });

  it("assumes on track when dates are missing", () => {
    expect(sprintHealth(0, "2026-10-10", null, NOW)).toBe("on-track");
    expect(sprintHealth(0, null, "2026-10-30", NOW)).toBe("on-track");
  });
});

describe("toMyTask", () => {
  it("maps state group to status, URGENT to high, and a date-only due to the end of that day", () => {
    const task = toMyTask(
      buildTask({ priority: "URGENT", due_date: "2026-10-25", state: buildDefaultStates()[2] }),
      card(),
    );
    expect(task).toMatchObject({ priority: "high", status: "in-progress", dueAt: "2026-10-25T23:59:00", courseCode: "SE100", projectName: "Nexus" });
  });

  it("keeps a missing due date as null and skips subtasks", () => {
    expect(toMyTask(buildTask({ due_date: null }), card())?.dueAt).toBeNull();
    expect(toMyTask(buildTask({ type: "SUBTASK" }), card())).toBeNull();
  });
});

describe("attachProjects", () => {
  it("links the first live project of the class and ignores archived ones", () => {
    const linked = attachProjects(
      [enrollment(), enrollment({ courseId: "class-2" })],
      [card({ projectId: "old", archived: true }), card({ projectId: "live" })],
    );
    expect(linked.map((row) => row.projectId)).toEqual(["live", null]);
  });
});

describe("toCourseSprint", () => {
  it("takes points from the server totals and the team from the enrollment", () => {
    const sprint = toCourseSprint(
      buildSprint({ name: "Sprint 2", start_date: "2026-10-01", end_date: "2026-10-30", status: "ACTIVE" }),
      buildProgress({ completed_estimate_points: 8, known_estimate_points: 20, completion_percent: 40 }),
      card(),
      enrollment(),
      NOW,
    );
    expect(sprint).toMatchObject({ sprintName: "Sprint 2", completedPoints: 8, totalPoints: 20, teamName: "Nhóm 1", role: "member", deadline: "2026-10-30T23:59:00", instructorName: "" });
  });
});

describe("buildMyWorkOverview", () => {
  it("counts due today and overdue only for open tasks and picks the latest semester", () => {
    const overview = buildMyWorkOverview({
      enrollments: [enrollment({ semester: "HK1 2025–2026", courseId: "class-0" }), enrollment()],
      cards: [card()],
      slices: [
        {
          card: card(),
          sprint: null,
          progress: null,
          tasks: [
            buildTask({ id: "a", due_date: "2026-10-20", state: buildDefaultStates()[1] }),
            buildTask({ id: "b", due_date: "2026-10-01", state: buildDefaultStates()[1] }),
            buildTask({ id: "c", due_date: "2026-10-01", state: buildDefaultStates()[4] }),
            buildTask({ id: "d", due_date: null, state: buildDefaultStates()[1] }),
          ],
        },
      ],
      partial: false,
      now: NOW,
    });
    expect(overview.semester).toBe("HK1 2026–2027");
    expect(overview.summary).toMatchObject({ dueToday: 1, overdue: 1, openPullRequests: 0 });
    expect(overview.tasks).toHaveLength(4);
  });
});

describe("loadMyWorkOverview", () => {
  function serve(extra: Omit<WorkFixture, "projects">) {
    server.use(
      ...workHandlers({
        projects: [buildProject({ id: "project-1", class_id: "class-1" }), buildProject({ id: "project-2", class_id: "class-1", identifier: "BAD" })],
        members: {
          "project-1": [buildProjectMember({ user_id: "u1", role: "MEMBER" })],
          "project-2": [buildProjectMember({ user_id: "u1", role: "MEMBER" })],
        },
        states: buildDefaultStates(),
        ...extra,
      }),
      ...classroomHandlers({
        classes: [buildClass({ id: "class-1", course: "course-1" })],
        courses: [buildCourse({ id: "course-1" })],
        groups: { "class-1": [buildGroup({ id: "group-1", name: "Nhóm 1" })] },
      }),
    );
  }

  it("gathers my tasks and the active sprint progress per project", async () => {
    serve({
      tasks: [buildTask({ id: "mine", assignee_ids: ["u1"], due_date: "2026-10-25" }), buildTask({ id: "other", assignee_ids: ["u2"] })],
      sprints: [buildSprint({ id: "s1", status: "ACTIVE" })],
      progress: { s1: buildProgress({ completed_estimate_points: 3, known_estimate_points: 6, completion_percent: 50 }, "s1") },
    });
    const overview = await loadMyWorkOverview(client, "u1", [enrollment()], NOW);
    expect(overview.tasks.map((task) => task.id)).toEqual(["mine", "mine"]); // one per project from the shared fixture
    expect(overview.sprints[0]).toMatchObject({ completedPoints: 3, totalPoints: 6 });
    expect(overview.partial).toBe(false);
  });

  it("drops a project whose tasks fail, flags partial, and keeps the others", async () => {
    serve({ tasks: [buildTask({ id: "mine", assignee_ids: ["u1"] })] });
    server.use(http.get("/api/work/projects/project-2/tasks/", () => envelopeError(500, "INTERNAL_ERROR", "Lỗi")));
    const overview = await loadMyWorkOverview(client, "u1", [enrollment()], NOW);
    expect(overview.tasks).toHaveLength(1);
    expect(overview.partial).toBe(true);
  });

  it("keeps a project's tasks when only its sprint progress fails", async () => {
    serve({ tasks: [buildTask({ id: "mine", assignee_ids: ["u1"] })], sprints: [buildSprint({ id: "s1", status: "ACTIVE" })] });
    const overview = await loadMyWorkOverview(client, "u1", [enrollment()], NOW);
    expect(overview.tasks.length).toBeGreaterThan(0);
    expect(overview.sprints).toEqual([]);
    expect(overview.partial).toBe(false);
  });
});
