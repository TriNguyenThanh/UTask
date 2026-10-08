import { describe, expect, it } from "vitest";

import { LEADER_ID, MEMBER_ID, MOCK_USERS, STUDENT_ID, TEACHER2_ID, TEACHER_ID } from "@/mocks/data/database";
import { MOCK_COURSE_META, MOCK_PEOPLE, MOCK_TEAM_META } from "@/mocks/data/directory";
import { buildOverviewForUser } from "@/mocks/data/myWork";
import {
  MOCK_COURSE_INSTRUCTORS,
  MOCK_COURSE_STUDENTS,
  MOCK_PENDING_REQUESTS,
  MOCK_TEAM_COURSES,
  MOCK_TEAM_MEMBERS,
  MOCK_TEAM_PROJECTS,
  assignmentFor,
  classSizeFor,
  coursesTaughtBy,
  enrolledCoursesFor,
  teamsOfCourse,
} from "@/mocks/data/relationships";
import { courseDetailForScenario, projectWorkspaceFor } from "@/mocks/data/studentFlow";
import {
  STALE_AFTER_DAYS,
  buildTeacherCourseDetail,
  buildTeacherCourseSummary,
  buildTeacherOversight,
  buildTeacherStudents,
  buildTeacherTeams,
  signalsFor,
  type ProjectFacts,
} from "@/mocks/data/teacherFlow";
import { mockAnchorDate } from "@/mocks/data/studentFlow";

/**
 * The mock graph is the single source for Student and Teacher views. These
 * checks fail if a roster, count, name or id drifts between them.
 */

const COURSE_IDS = Object.keys(MOCK_COURSE_STUDENTS);
const LOGIN_STUDENT_IDS = [LEADER_ID, MEMBER_ID, STUDENT_ID];

describe("graph integrity", () => {
  it("keeps teacher accounts out of every student id", () => {
    const studentIds = new Set([
      ...Object.values(MOCK_COURSE_STUDENTS).flat(),
      ...Object.values(MOCK_TEAM_MEMBERS).flatMap((members) => members.map((m) => m.userId)),
    ]);
    // Regression: the teacher ids once collided with two NEXUS students.
    expect(studentIds.has(TEACHER_ID)).toBe(false);
    expect(studentIds.has(TEACHER2_ID)).toBe(false);
    const teacherIds = MOCK_USERS.filter((user) => user.roles?.includes("TEACHER")).map((u) => u.id);
    for (const id of teacherIds) {
      expect(studentIds.has(id)).toBe(false);
    }
  });

  it("has unique ids across all demo logins", () => {
    const ids = MOCK_USERS.map((user) => user.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it("gives every person in the graph a directory entry keyed by its own id", () => {
    for (const [key, person] of Object.entries(MOCK_PEOPLE)) {
      expect(person.userId).toBe(key);
    }
    const referenced = [
      ...Object.values(MOCK_COURSE_STUDENTS).flat(),
      ...Object.values(MOCK_TEAM_MEMBERS).flatMap((members) => members.map((m) => m.userId)),
      ...Object.values(MOCK_COURSE_INSTRUCTORS).flatMap((list) => list.map((i) => i.userId)),
    ];
    for (const id of referenced) {
      expect(MOCK_PEOPLE[id], `missing directory entry for ${id}`).toBeDefined();
    }
  });

  it("does not create login accounts for directory-only people", () => {
    const loginIds = new Set(MOCK_USERS.map((user) => user.id));
    const directoryOnly = Object.keys(MOCK_PEOPLE).filter((id) => !loginIds.has(id));
    expect(directoryOnly.length).toBeGreaterThan(0);
    // Login ids are exactly the five demo accounts.
    expect(loginIds.size).toBe(5);
  });

  it("only seats enrolled students in a team of the same class", () => {
    for (const [teamId, members] of Object.entries(MOCK_TEAM_MEMBERS)) {
      const courseId = MOCK_TEAM_COURSES[teamId];
      expect(courseId, `${teamId} has no class`).toBeDefined();
      for (const member of members) {
        expect(MOCK_COURSE_STUDENTS[courseId]).toContain(member.userId);
      }
    }
  });

  it("puts a student in at most one team per class", () => {
    for (const courseId of COURSE_IDS) {
      const seen = new Map<string, string>();
      for (const teamId of teamsOfCourse(courseId)) {
        for (const member of MOCK_TEAM_MEMBERS[teamId] ?? []) {
          expect(seen.get(member.userId), `${member.userId} twice in ${courseId}`).toBeUndefined();
          seen.set(member.userId, teamId);
        }
      }
    }
  });

  it("respects the team size limit and has a leader in every team", () => {
    for (const [teamId, members] of Object.entries(MOCK_TEAM_MEMBERS)) {
      const limit = MOCK_COURSE_META[MOCK_TEAM_COURSES[teamId]].teamSize.max;
      expect(members.length).toBeLessThanOrEqual(limit);
      expect(members.some((member) => member.role === "leader")).toBe(true);
      expect(MOCK_TEAM_META[teamId]).toBeDefined();
    }
  });

  it("gives every class exactly one owner and metadata", () => {
    for (const courseId of COURSE_IDS) {
      expect(MOCK_COURSE_META[courseId]).toBeDefined();
      const owners = MOCK_COURSE_INSTRUCTORS[courseId].filter((entry) => entry.isOwner);
      expect(owners).toHaveLength(1);
    }
  });

  it("keys classes by id, not by subject code", () => {
    const codes = COURSE_IDS.map((id) => MOCK_COURSE_META[id].courseCode);
    expect(new Set(codes).size).toBeLessThan(codes.length); // SE330 appears twice
    expect(MOCK_COURSE_META["course-se330"].section).not.toEqual(
      MOCK_COURSE_META["course-se330-n2"].section,
    );
  });

  it("assigns the documented classes to each teacher", () => {
    expect([...coursesTaughtBy(TEACHER_ID)].sort()).toEqual(
      ["course-it3090", "course-se330", "course-se330-n2"].sort(),
    );
    expect([...coursesTaughtBy(TEACHER2_ID)]).toEqual(["course-cs402"]);
    // SE331 belongs to neither demo teacher.
    expect(coursesTaughtBy(TEACHER_ID)).not.toContain("course-se331");
    expect(coursesTaughtBy(TEACHER2_ID)).not.toContain("course-se331");
  });

  it("keeps the documented SV01 memberships", () => {
    expect(assignmentFor(STUDENT_ID, "course-se330")).toEqual({ teamId: "team-nexus", role: "leader" });
    expect(assignmentFor(STUDENT_ID, "course-cs402")).toEqual({ teamId: "team-deli", role: "member" });
    expect(assignmentFor(STUDENT_ID, "course-it3090")).toBeNull();
    expect(assignmentFor(STUDENT_ID, "course-se331")).toBeNull();
    expect(MOCK_PENDING_REQUESTS[`${STUDENT_ID}:course-se331`]).toEqual({ teamId: "team-phoenix" });
    // NEXUS keeps its documented two-leader simplification.
    expect(MOCK_TEAM_MEMBERS["team-nexus"].filter((m) => m.role === "leader")).toHaveLength(2);
  });

  it("leaves the empty class empty and the IT3090 teams without projects", () => {
    expect(MOCK_COURSE_STUDENTS["course-se330-n2"]).toHaveLength(0);
    expect(teamsOfCourse("course-se330-n2")).toHaveLength(0);
    for (const teamId of teamsOfCourse("course-it3090")) {
      expect(MOCK_TEAM_PROJECTS[teamId]).toBeUndefined();
    }
    expect(teamsOfCourse("course-it3090").length).toBeGreaterThan(0);
  });
});

describe("Student view is derived from the graph", () => {
  it("enrolls each login account in the classes the graph lists", () => {
    for (const userId of LOGIN_STUDENT_IDS) {
      const overview = buildOverviewForUser(userId);
      expect(overview.enrollments.map((e) => e.courseId).sort()).toEqual(
        [...enrolledCoursesFor(userId)].sort(),
      );
    }
  });

  it("derives class size, lecturer, team name and roster from the graph", () => {
    for (const courseId of ["course-se330", "course-cs402", "course-se331", "course-it3090"]) {
      const detail = courseDetailForScenario(courseId, "default", STUDENT_ID);
      expect(detail, courseId).not.toBeNull();
      const meta = MOCK_COURSE_META[courseId];
      expect(detail?.courseCode).toBe(meta.courseCode);
      expect(detail?.courseName).toBe(meta.courseName);
      expect(detail?.teamSize).toEqual(meta.teamSize);
      expect(detail?.classSize).toEqual(classSizeFor(courseId));
      const owner = MOCK_COURSE_INSTRUCTORS[courseId].find((entry) => entry.isOwner);
      expect(detail?.instructorName).toBe(MOCK_PEOPLE[owner!.userId].displayName);
    }
  });

  it("shows the same roster, roles and counts as the graph for SV01's teams", () => {
    for (const [courseId, teamId] of [
      ["course-se330", "team-nexus"],
      ["course-cs402", "team-deli"],
    ] as const) {
      const team = courseDetailForScenario(courseId, "default", STUDENT_ID)?.team;
      expect(team?.teamName).toBe(MOCK_TEAM_META[teamId].name);
      expect(team?.members.map((m) => [m.userId, m.role])).toEqual(
        MOCK_TEAM_MEMBERS[teamId].map((m) => [m.userId, m.role]),
      );
      expect(team?.memberCount).toBe(MOCK_TEAM_MEMBERS[teamId].length);
      expect(team?.memberCount).toBeLessThanOrEqual(team?.maxMembers ?? 0);
    }
  });

  it("builds the IT3090 formation view from the same teams and unassigned students", () => {
    const formation = courseDetailForScenario("course-it3090", "default", STUDENT_ID)?.formation;
    expect(formation?.openTeams.map((t) => t.teamId).sort()).toEqual(
      [...teamsOfCourse("course-it3090")].sort(),
    );
    const unassigned = buildTeacherStudents("course-it3090")
      .filter((student) => student.team === null)
      .map((student) => student.userId);
    expect(formation?.unassignedClassmates.map((c) => c.userId).sort()).toEqual([...unassigned].sort());
  });

  it("uses the class owner as the lecturer on Home sprint cards", () => {
    const overview = buildOverviewForUser(STUDENT_ID);
    for (const sprint of overview.sprints) {
      const owner = MOCK_COURSE_INSTRUCTORS[sprint.courseId].find((entry) => entry.isOwner);
      expect(sprint.instructorName).toBe(MOCK_PEOPLE[owner!.userId].displayName);
    }
  });
});

describe("Teacher view matches the Student view", () => {
  it("shows each login student's team exactly as that student's own Home does", () => {
    for (const userId of LOGIN_STUDENT_IDS) {
      for (const enrollment of buildOverviewForUser(userId).enrollments) {
        const row = buildTeacherStudents(enrollment.courseId).find((s) => s.userId === userId);
        expect(row, `${userId} in ${enrollment.courseId}`).toBeDefined();
        const { membership } = enrollment;
        if (membership.status === "assigned") {
          expect(row?.team).toEqual({
            teamId: membership.teamId,
            name: membership.teamName,
            role: membership.role,
          });
          expect(row?.pendingTeam).toBeNull();
        } else if (membership.status === "pending") {
          expect(row?.team).toBeNull();
          expect(row?.pendingTeam).toEqual({ teamId: membership.teamId, name: membership.teamName });
        } else {
          expect(row?.team).toBeNull();
          expect(row?.pendingTeam).toBeNull();
        }
      }
    }
  });

  it("counts students and teams from the lists it shows", () => {
    for (const courseId of COURSE_IDS) {
      const summary = buildTeacherCourseSummary(courseId)!;
      const students = buildTeacherStudents(courseId);
      const teams = buildTeacherTeams(courseId);
      expect(summary.studentCount).toBe(students.length);
      expect(summary.studentCount).toBe(classSizeFor(courseId).total);
      expect(summary.studentsWithoutTeam).toBe(students.filter((s) => s.team === null).length);
      expect(summary.studentsWithoutTeam).toBe(
        classSizeFor(courseId).total - classSizeFor(courseId).teamed,
      );
      expect(summary.teamCount).toBe(teams.length);
      expect(summary.teamsWithoutProject).toBe(teams.filter((t) => t.project === null).length);
      for (const team of teams) {
        expect(team.memberCount).toBe(MOCK_TEAM_MEMBERS[team.teamId].length);
        expect(team.maxMembers).toBe(MOCK_COURSE_META[courseId].teamSize.max);
      }
    }
  });

  it("keeps the two SE330 classes apart", () => {
    const first = buildTeacherCourseDetail("course-se330")!;
    const second = buildTeacherCourseDetail("course-se330-n2")!;
    expect(first.courseCode).toBe(second.courseCode);
    expect(first.courseId).not.toBe(second.courseId);
    expect(second.studentCount).toBe(0);
    expect(second.teamCount).toBe(0);
    expect(first.studentCount).toBeGreaterThan(0);
    expect(first.joinCode).not.toBe(second.joinCode);
  });

  it("names the lecturers from the instructor assignment", () => {
    const detail = buildTeacherCourseDetail("course-it3090")!;
    expect(detail.instructors.map((i) => [i.name, i.isOwner])).toEqual([
      ["TS. Đặng Văn Cường", true],
      ["TS. Trần Minh Đức", false],
    ]);
  });
});

describe("Teacher metrics never invent data", () => {
  it("reports no progress or activity for a team without a project", () => {
    for (const team of buildTeacherTeams("course-it3090")) {
      expect(team.project).toBeNull();
      expect(team.progress).toBeNull();
      expect(team.lastActivity).toBeNull();
    }
  });

  it("reports no activity for an empty class", () => {
    expect(buildTeacherCourseSummary("course-se330-n2")!.lastActivity).toBeNull();
    expect(buildTeacherCourseSummary("course-it3090")!.lastActivity).toBeNull();
  });

  it("derives NEXUS progress from the Sprint points in the project fixture", () => {
    const nexus = buildTeacherTeams("course-se330").find((team) => team.teamId === "team-nexus")!;
    const workspace = projectWorkspaceFor("project-nexus", "default", "", new Date("2026-10-20T08:30:00Z"))!;
    const sprint = workspace.sprints.find((candidate) => candidate.state === "active")!;
    expect(nexus.progress).toEqual({
      percent: Math.round((sprint.completedPoints / sprint.totalPoints) * 100),
      basis: "sprint-points",
    });
    expect(nexus.lastActivity?.kind).toBe("issue-updated");
  });

  it("uses a fixed clock, so last activity does not move with the real time", () => {
    const first = buildTeacherTeams("course-se330");
    const second = buildTeacherTeams("course-se330");
    expect(second).toEqual(first);
  });
});

describe("Teacher team members and oversight signals", () => {
  it("lists the same members, roles and student codes as the roster and the team count", () => {
    for (const courseId of COURSE_IDS) {
      for (const team of buildTeacherTeams(courseId)) {
        expect(team.members).toHaveLength(team.memberCount);
        expect(team.members.filter((m) => m.role === "leader").map((m) => m.userId)).toEqual(
          team.leaders.map((l) => l.userId),
        );
        for (const member of team.members) {
          expect(member.studentCode).toBe(MOCK_PEOPLE[member.userId]?.studentCode);
        }
      }
    }
  });

  it("builds oversight rows for exactly the teams of each class", () => {
    for (const courseId of COURSE_IDS) {
      expect(buildTeacherOversight(courseId).map((row) => row.teamId)).toEqual(
        buildTeacherTeams(courseId).map((team) => team.teamId),
      );
    }
  });

  describe("signal rules", () => {
    const anchor = mockAnchorDate();
    const daysAgo = (days: number) => new Date(anchor.getTime() - days * 86_400_000).toISOString();
    const facts = (overrides: Partial<ProjectFacts> = {}): ProjectFacts => ({
      key: "KEY",
      name: "Project",
      progress: { percent: 50, basis: "issues" },
      issues: { done: 1, total: 2 },
      sprint: null,
      lastActivity: { at: daysAgo(1), kind: "issue-updated" },
      ...overrides,
    });
    const codes = (...args: Parameters<typeof signalsFor>) => signalsFor(...args).map((s) => s.code);

    it("gives no signal to a complete, recently active team", () => {
      expect(codes(facts(), 4, 3)).toEqual([]);
    });

    it("signals a team without a project and stops there for project rules", () => {
      expect(codes(null, 4, 3)).toEqual(["no-project"]);
    });

    it("signals missing progress data and missing activity separately", () => {
      expect(codes(facts({ progress: null, issues: null, lastActivity: null }), 4, 3)).toEqual([
        "no-progress-data",
        "no-activity",
      ]);
    });

    it("signals stale activity exactly at the threshold, not one day before", () => {
      expect(codes(facts({ lastActivity: { at: daysAgo(STALE_AFTER_DAYS - 1), kind: "issue-updated" } }), 4, 3)).toEqual([]);
      const stale = signalsFor(facts({ lastActivity: { at: daysAgo(STALE_AFTER_DAYS), kind: "issue-updated" } }), 4, 3);
      expect(stale.map((s) => s.code)).toEqual(["stale-activity"]);
      expect(stale[0].label).toContain(`${STALE_AFTER_DAYS} ngày`);
    });

    it("signals a team below the class minimum with the counts in the label", () => {
      const [signal] = signalsFor(facts(), 2, 3);
      expect(signal.code).toBe("below-min-size");
      expect(signal.label).toContain("2/3");
    });
  });
});
