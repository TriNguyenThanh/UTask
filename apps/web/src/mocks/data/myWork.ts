import type {
  CourseEnrollment,
  CourseSprint,
  GitHubActivity,
  MyTask,
  MyWorkOverview,
} from "@/features/my-work/types";
import { MOCK_PEOPLE, MOCK_TEAM_META } from "@/mocks/data/directory";
import {
  MOCK_TEAM_PROJECTS,
  assignmentFor,
  enrolledCoursesFor,
  ownerInstructorId,
  pendingRequestFor,
  projectRoleForUser,
} from "@/mocks/data/relationships";

/** Lecturer shown on Home sprint cards: the class owner from the graph. */
function lecturerOf(courseId: string): string {
  const ownerId = ownerInstructorId(courseId);
  return (ownerId && MOCK_PEOPLE[ownerId]?.displayName) || "Chưa phân công";
}

function teamLabel(teamId: string): string {
  return MOCK_TEAM_META[teamId]?.name ?? teamId;
}

/**
 * Fixture clock anchor. All fixture dates derive from this timestamp so
 * "today / this week / overdue" buckets stay deterministic in tests.
 * Scenario fixtures may override it via `buildOverview({ now })`.
 */
const ANCHOR_DATE = "2026-10-20T08:30:00.000Z";

function daysFrom(now: Date, days: number, hours = 17, minutes = 0): string {
  const target = new Date(now);
  target.setDate(target.getDate() + days);
  target.setHours(hours, minutes, 0, 0);
  return target.toISOString();
}

/**
 * Memberships live in `mocks/data/relationships.ts`; this module only
 * shapes Home data for the account that is currently logged in.
 */

/* ------------------------------------------------------------------ */
/* Per-user enrollment sets                                             */
/* ------------------------------------------------------------------ */

/**
 * Task keys mirror real workspace issues (NEXUS-101…/DELI-01… in
 * `mocks/data/studentFlow.ts`) so clicking a task opens an issue that
 * actually exists, and "My tasks" only contains issues assigned to the
 * logged-in account.
 */
function leaderTasks(now: Date): MyTask[] {
  return [
    {
      id: "task-nexus-104",
      issueKey: "NEXUS-104",
      title: "Tích hợp cổng thanh toán VNPay Sandbox và IPN",
      courseId: "course-se330",
      courseCode: "SE330",
      projectName: "Smart Supply Chain",
      projectId: "project-nexus",
      priority: "high",
      status: "in-progress",
      dueAt: daysFrom(now, 0, 18),
      subtasks: { completed: 2, total: 4 },
      branchName: "feat/vnpay-ipn",
    },
    {
      id: "task-nexus-101",
      issueKey: "NEXUS-101",
      title: "Thiết kế schema CSDL Giỏ hàng",
      courseId: "course-se330",
      courseCode: "SE330",
      projectName: "Smart Supply Chain",
      projectId: "project-nexus",
      priority: "medium",
      status: "todo",
      dueAt: daysFrom(now, 2),
    },
    {
      id: "task-nexus-98",
      issueKey: "NEXUS-98",
      title: "Refactor Auth JWT Middleware",
      courseId: "course-se330",
      courseCode: "SE330",
      projectName: "Smart Supply Chain",
      projectId: "project-nexus",
      priority: "high",
      status: "review",
      dueAt: daysFrom(now, 1),
    },
  ];
}

function memberTasks(now: Date): MyTask[] {
  return [
    {
      id: "task-deli-02",
      issueKey: "DELI-02",
      title: "Đăng nhập email + password",
      courseId: "course-cs402",
      courseCode: "CS402",
      projectName: "Ứng dụng Theo dõi Sức khỏe & Dinh dưỡng",
      projectId: "project-deli",
      priority: "high",
      status: "in-progress",
      dueAt: daysFrom(now, 0, 21),
      branchName: "feat/auth-email",
    },
    {
      id: "task-deli-03",
      issueKey: "DELI-03",
      title: "Cài đặt CI Flutter analyze + test",
      courseId: "course-cs402",
      courseCode: "CS402",
      projectName: "Ứng dụng Theo dõi Sức khỏe & Dinh dưỡng",
      projectId: "project-deli",
      priority: "low",
      status: "todo",
      dueAt: daysFrom(now, 3),
    },
  ];
}

/**
 * Tasks are derived from real team memberships: the fixture sets mirror
 * issues assigned to the demo accounts, so a user gets NEXUS tasks when
 * they are on team NEXUS and DELI tasks when on team DELI.
 */
export function tasksForUser(userId: string, now = new Date(ANCHOR_DATE)): MyTask[] {
  const nexusRole = projectRoleForUser(userId, "project-nexus");
  const deliRole = projectRoleForUser(userId, "project-deli");
  const tasks: MyTask[] = [];
  if (nexusRole !== null) {
    tasks.push(...leaderTasks(now));
  }
  if (deliRole !== null) {
    tasks.push(...memberTasks(now));
  }
  return tasks;
}

/* ------------------------------------------------------------------ */
/* Mixed scenario — canonical multi-membership fixture                  */
/* ------------------------------------------------------------------ */

/**
 * Mixed scenario — the canonical Home state used by the my-work
 * scenario fixtures (leader + member + none + pending memberships):
 * - SE330: student is leader of team NEXUS (sprint 2, on track)
 * - CS402: student is member of team DELI (sprint 1, at risk)
 * - IT3090: no team, self-select registration closing in 2 days
 * - SE331: pending request to team PHOENIX
 */
export function buildMixedOverview(now = new Date(ANCHOR_DATE)): MyWorkOverview {
  const enrollments: CourseEnrollment[] = [
    {
      courseId: "course-se330",
      courseCode: "SE330",
      courseName: "Đồ án Chuyên ngành SE330",
      semester: "HK1 2026–2027",
      teamFormation: { mode: "self-select", registrationDeadline: daysFrom(now, 12) },
      projectId: "project-nexus",
      membership: {
        status: "assigned",
        teamId: "team-nexus",
        teamName: "Team NEXUS",
        role: "leader",
      },
    },
    {
      courseId: "course-cs402",
      courseCode: "CS402",
      courseName: "Phát triển Di động CS402",
      semester: "HK1 2026–2027",
      teamFormation: { mode: "join-code", registrationDeadline: null },
      projectId: "project-deli",
      membership: {
        status: "assigned",
        teamId: "team-deli",
        teamName: "Team DELI",
        role: "member",
      },
    },
    {
      courseId: "course-it3090",
      courseCode: "IT3090",
      courseName: "Đồ án IoT IT3090",
      semester: "HK1 2026–2027",
      teamFormation: { mode: "self-select", registrationDeadline: daysFrom(now, 2) },
      projectId: null,
      membership: { status: "none" },
    },
    {
      courseId: "course-se331",
      courseCode: "SE331",
      courseName: "Kiểm thử Phần mềm SE331",
      semester: "HK1 2026–2027",
      teamFormation: { mode: "instructor-assigned", registrationDeadline: null },
      projectId: null,
      membership: {
        status: "pending",
        teamId: "team-phoenix",
        teamName: "Team PHOENIX",
        requestedAt: daysFrom(now, -3, 9, 15),
      },
    },
  ];

  const tasks = [...leaderTasks(now), ...memberTasks(now)];

  const sprints: CourseSprint[] = [
    {
      courseId: "course-se330",
      courseCode: "SE330",
      courseName: "Đồ án Chuyên ngành SE330",
      semester: "HK1",
      projectName: "Smart Supply Chain",
      projectId: "project-nexus",
      teamId: "team-nexus",
      teamName: "Team NEXUS",
      role: "leader",
      sprintName: "Sprint 2",
      completedPoints: 26,
      totalPoints: 40,
      deadline: daysFrom(now, 4),
      health: "on-track",
      instructorName: lecturerOf("course-se330"),
    },
    {
      courseId: "course-cs402",
      courseCode: "CS402",
      courseName: "Phát triển Di động CS402",
      semester: "HK1",
      projectName: "Ứng dụng Theo dõi Sức khỏe & Dinh dưỡng",
      projectId: "project-deli",
      teamId: "team-deli",
      teamName: "Team DELI",
      role: "member",
      sprintName: "Sprint 1",
      completedPoints: 12,
      totalPoints: 40,
      deadline: daysFrom(now, 9),
      health: "at-risk",
      instructorName: lecturerOf("course-cs402"),
    },
  ];

  const open = tasks.filter((task) => task.status !== "done");
  const dueToday = open.filter(
    (task) => new Date(task.dueAt).toDateString() === now.toDateString(),
  );
  const overdue = open.filter((task) => new Date(task.dueAt) < now);

  return {
    semester: "HK1 2026–2027",
    refreshedAt: now.toISOString(),
    enrollments,
    tasks: open,
    sprints,
    summary: {
      dueToday: dueToday.length,
      overdue: overdue.length,
      openPullRequests: 2,
      sprintProgressPercent: 47,
    },
  };
}

/**
 * Static course metadata shared by the graph-derived overview. Dates are
 * relative to the overview `now` so badges stay deterministic.
 */
const COURSE_META: Record<
  string,
  {
    courseCode: string;
    courseName: string;
    mode: "self-select" | "join-code" | "instructor-assigned";
    deadline: (now: Date) => string | null;
  }
> = {
  "course-se330": {
    courseCode: "SE330",
    courseName: "Đồ án Chuyên ngành SE330",
    mode: "self-select",
    deadline: (now) => daysFrom(now, 12),
  },
  "course-cs402": {
    courseCode: "CS402",
    courseName: "Phát triển Di động CS402",
    mode: "join-code",
    deadline: () => null,
  },
  "course-it3090": {
    courseCode: "IT3090",
    courseName: "Đồ án IoT IT3090",
    mode: "self-select",
    deadline: (now) => daysFrom(now, 2),
  },
  "course-se331": {
    courseCode: "SE331",
    courseName: "Kiểm thử Phần mềm SE331",
    mode: "instructor-assigned",
    deadline: () => null,
  },
};

const SPRINT_BY_PROJECT: Record<string, Omit<CourseSprint, "role">> = {
  "project-nexus": {
    courseId: "course-se330",
    courseCode: "SE330",
    courseName: "Đồ án Chuyên ngành SE330",
    semester: "HK1",
    projectName: "Smart Supply Chain",
    projectId: "project-nexus",
    teamId: "team-nexus",
    teamName: "Team NEXUS",
    sprintName: "Sprint 2",
    completedPoints: 26,
    totalPoints: 40,
    deadline: daysFrom(new Date(ANCHOR_DATE), 4),
    health: "on-track",
    instructorName: lecturerOf("course-se330"),
  },
  "project-deli": {
    courseId: "course-cs402",
    courseCode: "CS402",
    courseName: "Phát triển Di động CS402",
    semester: "HK1",
    projectName: "Ứng dụng Theo dõi Sức khỏe & Dinh dưỡng",
    projectId: "project-deli",
    teamId: "team-deli",
    teamName: "Team DELI",
    sprintName: "Sprint 1",
    completedPoints: 12,
    totalPoints: 40,
    deadline: daysFrom(new Date(ANCHOR_DATE), 9),
    health: "at-risk",
    instructorName: lecturerOf("course-cs402"),
  },
};

/**
 * Default-scenario Home overview, fully derived from the relationship
 * graph: enrollments per user, membership status per course (assigned
 * with the real role / pending / none), tasks and sprint cards only for
 * teams the user actually belongs to.
 */
export function buildOverviewForUser(
  userId: string,
  now = new Date(ANCHOR_DATE),
): MyWorkOverview {
  const enrollments: CourseEnrollment[] = enrolledCoursesFor(userId).flatMap(
    (courseId) => {
      const meta = COURSE_META[courseId];
      if (!meta) {
        return [];
      }
      const assignment = assignmentFor(userId, courseId);
      const pending = pendingRequestFor(userId, courseId);
      const projectId = assignment
        ? (MOCK_TEAM_PROJECTS[assignment.teamId] ?? null)
        : null;
      return [
        {
          courseId,
          courseCode: meta.courseCode,
          courseName: meta.courseName,
          semester: "HK1 2026–2027",
          teamFormation: {
            mode: meta.mode,
            registrationDeadline: meta.deadline(now),
          },
          projectId,
          membership: assignment
            ? {
                status: "assigned",
                teamId: assignment.teamId,
                teamName: teamLabel(assignment.teamId),
                role: assignment.role,
              }
            : pending
              ? {
                  status: "pending",
                  teamId: pending.teamId,
                  teamName: teamLabel(pending.teamId),
                  requestedAt: daysFrom(now, -3, 9, 15),
                }
              : { status: "none" },
        },
      ];
    },
  );

  const tasks = tasksForUser(userId, now);

  const sprints: CourseSprint[] = [];
  for (const enrollment of enrollments) {
    if (enrollment.membership.status !== "assigned") {
      continue;
    }
    const sprint = enrollment.projectId
      ? SPRINT_BY_PROJECT[enrollment.projectId]
      : undefined;
    if (!sprint) {
      continue;
    }
    sprints.push({
      ...sprint,
      role: enrollment.membership.role,
    });
  }

  const open = tasks.filter((task) => task.status !== "done");
  const dueToday = open.filter(
    (task) => new Date(task.dueAt).toDateString() === now.toDateString(),
  );
  const overdue = open.filter((task) => new Date(task.dueAt) < now);
  const sprintProgressPercent =
    sprints.length > 0
      ? Math.round(
          sprints.reduce(
            (sum, sprint) => sum + (sprint.completedPoints / sprint.totalPoints) * 100,
            0,
          ) / sprints.length,
        )
      : 0;

  return {
    semester: "HK1 2026–2027",
    refreshedAt: now.toISOString(),
    enrollments,
    tasks: open,
    sprints,
    summary: {
      dueToday: dueToday.length,
      overdue: overdue.length,
      openPullRequests: open.filter((task) => task.branchName).length,
      sprintProgressPercent,
    },
  };
}

/** Full GitHub activity for the connected, two-project state. */
export function buildGitHubActivity(now = new Date(ANCHOR_DATE)): GitHubActivity {
  return {
    sync: { state: "connected", linkedProjectCount: 2 },
    pullRequests: [
      {
        id: "pr-14",
        number: 14,
        title: "feat(payment): VNPay sandbox + IPN handler",
        repository: "nexus-team/smart-supply-chain",
        author: "Trần Bảo Long (@longtb_qa)",
        updatedAt: daysFrom(now, 0, 8, 12),
        kind: "to-review",
      },
      {
        id: "pr-09",
        number: 9,
        title: "feat(cart): responsive cart UI",
        repository: "deli-team/health-app",
        author: "Đặng Thảo Linh (@thaolinh_dev)",
        updatedAt: daysFrom(now, 0, 7, 30),
        kind: "to-review",
      },
      {
        id: "pr-21",
        number: 21,
        title: "feat: onboarding screen polish",
        repository: "deli-team/health-app",
        author: "Lê Minh Khoa (@minhkhoa)",
        updatedAt: daysFrom(now, 0, 10, 40),
        kind: "awaiting-review",
      },
    ],
    commits: [
      {
        id: "commit-1",
        message: "NEXUS-104 add IPN signature verify",
        repository: "nexus-team/smart-supply-chain",
        branchName: "feat/vnpay-ipn",
        issueKey: "NEXUS-104",
        committedAt: daysFrom(now, -1, 15),
      },
      {
        id: "commit-2",
        message: "NEXUS-101 draft cart schema ERD",
        repository: "nexus-team/smart-supply-chain",
        branchName: "feat/erd-v1",
        issueKey: "NEXUS-101",
        committedAt: daysFrom(now, -2, 10),
      },
    ],
  };
}

export function buildNoCoursesOverview(now = new Date(ANCHOR_DATE)): MyWorkOverview {
  return {
    semester: "HK1 2026–2027",
    refreshedAt: now.toISOString(),
    enrollments: [],
    tasks: [],
    sprints: [],
    summary: { dueToday: 0, overdue: 0, openPullRequests: 0, sprintProgressPercent: 0 },
  };
}

export function buildNoTeamOverview(now = new Date(ANCHOR_DATE)): MyWorkOverview {
  const mixed = buildMixedOverview(now);
  return {
    ...mixed,
    enrollments: mixed.enrollments.map((enrollment) => ({
      ...enrollment,
      projectId: null,
      membership: { status: "none" as const },
    })),
    tasks: [],
    sprints: [],
    summary: { dueToday: 0, overdue: 0, openPullRequests: 0, sprintProgressPercent: 0 },
  };
}
export function buildPendingOnlyOverview(now = new Date(ANCHOR_DATE)): MyWorkOverview {
  const mixed = buildMixedOverview(now);
  return {
    ...mixed,
    enrollments: mixed.enrollments.map((enrollment) =>
      enrollment.courseId === "course-se331"
        ? enrollment
        : { ...enrollment, projectId: null, membership: { status: "none" as const } },
    ),
    tasks: [],
    sprints: [],
    summary: { dueToday: 0, overdue: 0, openPullRequests: 0, sprintProgressPercent: 0 },
  };
}

export function buildMemberOnlyOverview(now = new Date(ANCHOR_DATE)): MyWorkOverview {
  const mixed = buildMixedOverview(now);
  return {
    ...mixed,
    enrollments: mixed.enrollments.map((enrollment) =>
      enrollment.membership.status === "assigned"
        ? { ...enrollment, membership: { ...enrollment.membership, role: "member" as const } }
        : enrollment,
    ),
    sprints: mixed.sprints.map((sprint) => ({ ...sprint, role: "member" as const })),
  };
}

export function buildLeaderOnlyOverview(now = new Date(ANCHOR_DATE)): MyWorkOverview {
  const mixed = buildMixedOverview(now);
  return {
    ...mixed,
    enrollments: mixed.enrollments.map((enrollment) =>
      enrollment.membership.status === "assigned"
        ? { ...enrollment, membership: { ...enrollment.membership, role: "leader" as const } }
        : enrollment,
    ),
    sprints: mixed.sprints.map((sprint) => ({ ...sprint, role: "leader" as const })),
  };
}

export function buildEmptyTasksOverview(now = new Date(ANCHOR_DATE)): MyWorkOverview {
  const mixed = buildMixedOverview(now);
  return {
    ...mixed,
    tasks: [],
    summary: { ...mixed.summary, dueToday: 0, overdue: 0 },
  };
}

export function buildOverdueOverview(now = new Date(ANCHOR_DATE)): MyWorkOverview {
  const mixed = buildMixedOverview(now);
  const overdueTask: MyTask = {
    id: "task-nexus-111",
    issueKey: "NEXUS-111",
    title: "Lỗi 500 khi thanh toán COD > 10 triệu",
    courseId: "course-se330",
    courseCode: "SE330",
    projectName: "Smart Supply Chain",
    projectId: "project-nexus",
    priority: "high",
    status: "in-progress",
    dueAt: daysFrom(now, -1),
  };
  const lateSprint: CourseSprint = {
    ...mixed.sprints[1],
    health: "late",
    completedPoints: 4,
    totalPoints: 40,
    deadline: daysFrom(now, 9),
  };
  return {
    ...mixed,
    tasks: [overdueTask, ...mixed.tasks],
    sprints: [mixed.sprints[0], lateSprint],
    summary: { ...mixed.summary, overdue: 1 },
  };
}

/** GitHub connected but the student is not part of any linked project yet. */
export function buildGitHubNoProjectsActivity(): GitHubActivity {
  return {
    sync: { state: "connected", linkedProjectCount: 0 },
    pullRequests: [],
    commits: [],
  };
}

/** GitHub account not linked at all. */
export function buildGitHubDisconnectedActivity(): GitHubActivity {
  return { sync: { state: "disconnected" }, pullRequests: [], commits: [] };
}