import { QueryClient } from "@tanstack/react-query";
import { http } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  loadInstructors,
  loadTeacherCourse,
  loadTeacherCourses,
  toTeacherStudents,
  toTeacherTeams,
  toTeacherCourseDetail,
  type ClassRoster,
} from "@/lib/api/classroom/teacherLoaders";
import type { TeacherCourseDetail } from "@/lib/api/teacherFlow";
import type { ProjectDto } from "@/lib/api/work/dto";
import { createApiClient } from "@/lib/api/client";
import { server } from "@/mocks/server";
import {
  buildClass,
  buildCourse,
  buildEnrollment,
  buildGroup,
  buildMember,
  buildTeacher,
  classroomHandlers,
  envelope,
  envelopeError,
  type ClassroomFixture,
} from "@/test/classroomHandlers";

const client = createApiClient({ baseUrl: "http://localhost", getAccessToken: () => "token", onUnauthorized: () => undefined });

function fixture(): ClassroomFixture {
  return {
    classes: [buildClass()],
    courses: [buildCourse()],
    teachers: {
      "class-1": [
        buildTeacher({ id: "t2", user_id: "tu2", role: "CO_TEACHER" }),
        buildTeacher({ id: "t1", user_id: "tu1", role: "PRIMARY" }),
      ],
    },
    enrollments: {
      "class-1": [
        buildEnrollment({ id: "e1", user_id: "u1" }),
        buildEnrollment({ id: "e2", user_id: "u2", profile: { display_name: "Trần Thị Bình", email: "b@st.edu.vn", student_id: "6451071002" } }),
        buildEnrollment({ id: "e3", user_id: "u3", profile: { display_name: "Lê Văn Cường", email: "c@st.edu.vn", student_id: "6451071003" } }),
      ],
    },
    groups: { "class-1": [buildGroup({ id: "g1", name: "Nhóm 1" })] },
    members: {
      g1: [
        buildMember({ id: "m1", group_id: "g1", user_id: "u1", role: "LEADER" }),
        buildMember({ id: "m2", group_id: "g1", user_id: "u2", role: "MEMBER", profile: { display_name: "Trần Thị Bình", email: "b@st.edu.vn", student_id: "6451071002" } }),
      ],
    },
    users: [
      { id: "tu1", email: "d@utask.test", student_id: null, display_name: "TS. Đức", avatar_url: null, bio: null, roles: ["TEACHER"], account_status: "ACTIVE" },
    ],
  };
}

describe("loadTeacherCourses", () => {
  it("counts students and groups and leaves Work-owned figures null instead of zero", async () => {
    server.use(...classroomHandlers(fixture()));
    const { courses } = await loadTeacherCourses(client);
    expect(courses).toEqual([
      expect.objectContaining({
        courseId: "class-1",
        courseCode: "SE100",
        section: "SE100.N11",
        name: "Đồ án phần mềm",
        studentCount: 3,
        teamCount: 1,
        studentsWithoutTeam: null,
        teamsWithoutProject: null,
        teamsWithSignals: null,
        overdue: null,
        lastActivity: null,
      }),
    ]);
  });

  it("returns an empty list for a teacher with no class", async () => {
    server.use(...classroomHandlers({ classes: [], courses: [] }));
    expect((await loadTeacherCourses(client)).courses).toEqual([]);
  });

  it("falls back to the class code when its course is not in the course list", async () => {
    server.use(...classroomHandlers({ ...fixture(), courses: [] }));
    expect((await loadTeacherCourses(client)).courses[0].courseCode).toBe("SE100.N11");
  });
});

describe("loadTeacherCourse", () => {
  it("builds the detail with the version, state and students without a team", async () => {
    server.use(...classroomHandlers(fixture()));
    const detail = await loadTeacherCourse(new QueryClient(), client, ["roster"], "class-1");
    expect(detail).toMatchObject({
      courseId: "class-1",
      studentCount: 3,
      studentsWithoutTeam: 1,
      teamCount: 1,
      joinCode: null,
      teamSize: { min: 3, max: 5 },
      classroom: { version: 1, status: "OPEN", groupingPhase: "FORMING", joinCodeExpiresAt: null, code: "SE100.N11" },
    });
  });

  it("propagates a 404 so the layout can show the unavailable-class state", async () => {
    server.use(...classroomHandlers({ classes: [], courses: [] }));
    await expect(loadTeacherCourse(new QueryClient(), client, ["roster"], "missing")).rejects.toMatchObject({ status: 404 });
  });

  it("reuses one roster fetch for detail and a second consumer within the stale window", async () => {
    let enrollmentCalls = 0;
    server.use(
      http.get("/api/classroom/classes/class-1/enrollments/", () => {
        enrollmentCalls += 1;
        return envelope(fixture().enrollments?.["class-1"] ?? []);
      }),
      ...classroomHandlers(fixture()),
    );
    const queryClient = new QueryClient();
    await loadTeacherCourse(queryClient, client, ["roster"], "class-1");
    await loadTeacherCourse(queryClient, client, ["roster"], "class-1");
    expect(enrollmentCalls).toBe(1);
  });
});

describe("loadInstructors", () => {
  it("lists the primary teacher first and names them from the batch lookup", async () => {
    server.use(...classroomHandlers(fixture()));
    const instructors = await loadInstructors(client, "class-1");
    expect(instructors).toEqual([
      { userId: "tu1", name: "TS. Đức", isOwner: true },
      { userId: "tu2", name: "Chưa rõ tên", isOwner: false },
    ]);
  });

  it("still lists teachers when the name lookup fails", async () => {
    server.use(http.post("/api/auth/users/batch", () => envelopeError(500, "INTERNAL_ERROR", "Lỗi")), ...classroomHandlers(fixture()));
    const instructors = await loadInstructors(client, "class-1");
    expect(instructors.map((entry) => entry.name)).toEqual(["Chưa rõ tên", "Chưa rõ tên"]);
  });
});

describe("roster adapters", () => {
  const roster: ClassRoster = {
    cls: buildClass({ group_max_size: 4 }),
    course: buildCourse(),
    enrollments: fixture().enrollments?.["class-1"] ?? [],
    groups: [buildGroup({ id: "g1", name: "Nhóm 1" })],
    membersByGroup: { g1: fixture().members?.g1 ?? [] },
  };

  it("marks each student's team and role, and leaves ungrouped students without a team", () => {
    const students = toTeacherStudents(roster);
    expect(students.map((student) => [student.userId, student.team?.role ?? null])).toEqual([
      ["u1", "leader"],
      ["u2", "member"],
      ["u3", null],
    ]);
    expect(students[2]).toMatchObject({ studentCode: "6451071003", pendingTeam: null });
  });

  it("builds teams with the class maximum, leaders, and no invented project or progress", () => {
    const [team] = toTeacherTeams(roster);
    expect(team).toMatchObject({ teamId: "g1", name: "Nhóm 1", memberCount: 2, maxMembers: 4, project: null, progress: null, lastActivity: null });
    expect(team.leaders).toEqual([{ userId: "u1", name: "Nguyễn Văn An" }]);
  });
});

describe("toTeacherTeams with projectsByGroup", () => {
  const roster: ClassRoster = {
    cls: buildClass({ group_max_size: 4 }),
    course: buildCourse(),
    enrollments: fixture().enrollments?.["class-1"] ?? [],
    groups: [buildGroup({ id: "g1", name: "Nhóm 1" }), buildGroup({ id: "g2", name: "Nhóm 2" })],
    membersByGroup: { g1: fixture().members?.g1 ?? [], g2: [] },
  };

  const activeProject = {
    id: "p1", identifier: "NEXUS", name: "Hệ thống Nexus",
    description: "", target_goals: "", tech_stack: {},
    start_date: null, end_date: null,
    classroom_group_id: "g1", class_id: "class-1",
    group_source_version: 1, version: 1, board_revision: 0,
    github_repo_name: null, github_repo_id: null,
    github_connection_status: null, github_synced_at: null,
    created_at: "2026-09-01T00:00:00Z", updated_at: "2026-09-01T00:00:00Z", archived_at: null,
  } as const;

  afterEach(() => vi.unstubAllEnvs());

  it("fills project when projectsByGroup has an active project for the group", () => {
    const projectsByGroup = new Map([["g1", [activeProject]], ["g2", []]]);
    const [team1, team2] = toTeacherTeams(roster, projectsByGroup);
    expect(team1.project).toEqual({ projectId: "p1", key: "NEXUS", name: "Hệ thống Nexus" });
    expect(team2.project).toBeNull();
  });

  it("leaves project null when projectsByGroup is undefined (not called with Work)", () => {
    const [team] = toTeacherTeams(roster);
    expect(team.project).toBeNull();
  });

  it("leaves project null when the group's only projects are all archived", () => {
    const archived = { ...activeProject, archived_at: "2026-10-01T00:00:00Z" };
    const projectsByGroup = new Map([["g1", [archived]]]);
    const [team] = toTeacherTeams(roster, projectsByGroup);
    expect(team.project).toBeNull();
  });
});

describe("toTeacherCourseDetail with projectsByGroup", () => {
  const roster: ClassRoster = {
    cls: buildClass({ group_max_size: 4 }),
    course: buildCourse(),
    enrollments: fixture().enrollments?.["class-1"] ?? [],
    groups: [buildGroup({ id: "g1", name: "Nhóm 1" }), buildGroup({ id: "g2", name: "Nhóm 2" })],
    membersByGroup: { g1: fixture().members?.g1 ?? [], g2: [] },
  };
  const noInstructors: TeacherCourseDetail["instructors"] = [];

  function proj(id: string, groupId: string): ProjectDto {
    return {
      id, identifier: id.toUpperCase(), name: `Dự án ${id}`,
      description: "", target_goals: "", tech_stack: {},
      start_date: null, end_date: null,
      classroom_group_id: groupId, class_id: "class-1",
      group_source_version: 1, version: 1, board_revision: 0,
      github_repo_name: null, github_repo_id: null,
      github_connection_status: null, github_synced_at: null,
      created_at: "2026-09-01T00:00:00Z", updated_at: "2026-09-01T00:00:00Z", archived_at: null,
    };
  }

  it("teamsWithoutProject is null when projectsByGroup not provided", () => {
    expect(toTeacherCourseDetail(roster, noInstructors).teamsWithoutProject).toBeNull();
  });

  it("counts groups with empty project array when projectsByGroup provided", () => {
    const projectsByGroup = new Map<string, ProjectDto[]>([["g1", [proj("p1", "g1")]], ["g2", []]]);
    expect(toTeacherCourseDetail(roster, noInstructors, projectsByGroup).teamsWithoutProject).toBe(1);
  });

  it("counts all groups when every project array is empty", () => {
    const projectsByGroup = new Map<string, ProjectDto[]>([["g1", []], ["g2", []]]);
    expect(toTeacherCourseDetail(roster, noInstructors, projectsByGroup).teamsWithoutProject).toBe(2);
  });

  it("loadTeacherCourses still returns teamsWithoutProject null (unchanged)", async () => {
    server.use(...classroomHandlers(fixture()));
    const { courses } = await loadTeacherCourses(client);
    expect(courses[0].teamsWithoutProject).toBeNull();
  });
});
