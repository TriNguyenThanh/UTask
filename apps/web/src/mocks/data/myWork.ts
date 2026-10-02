import type {
  CourseEnrollment,
  CourseSprint,
  GitHubActivity,
  MyTask,
  MyWorkOverview,
} from "@/features/my-work/types";

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
 * Mixed scenario — the canonical Home state:
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

  const tasks: MyTask[] = [
    {
      id: "task-nexus-12",
      issueKey: "NEXUS-12",
      title: "Thiết kế ERD cơ sở dữ liệu chuỗi cung ứng",
      courseId: "course-se330",
      courseCode: "SE330",
      projectName: "Project NEXUS",
      priority: "high",
      status: "in-progress",
      dueAt: daysFrom(now, 0),
      subtasks: { completed: 2, total: 5 },
    },
    {
      id: "task-deli-08",
      issueKey: "DELI-08",
      title: "Tích hợp bản đồ GPS và tính toán lộ trình giao hàng (Mapbox SDK)",
      courseId: "course-cs402",
      courseCode: "CS402",
      projectName: "Project DELI",
      priority: "medium",
      status: "in-progress",
      dueAt: daysFrom(now, 0, 21),
      branchName: "feat/tracking-v1",
    },
    {
      id: "task-nexus-15",
      issueKey: "NEXUS-15",
      title: "Chuẩn bị slide báo cáo tiến độ Sprint 2 cho Giảng viên hướng dẫn",
      courseId: "course-se330",
      courseCode: "SE330",
      projectName: "Project NEXUS",
      priority: "low",
      status: "todo",
      dueAt: daysFrom(now, 0, 23, 59),
    },
    {
      id: "task-nexus-07",
      issueKey: "NEXUS-07",
      title: "Viết migration cho bảng inventory và supplier",
      courseId: "course-se330",
      courseCode: "SE330",
      projectName: "Project NEXUS",
      priority: "medium",
      status: "review",
      dueAt: daysFrom(now, 2),
    },
    {
      id: "task-deli-04",
      issueKey: "DELI-04",
      title: "Cấu hình CI chạy unit test cho module driver",
      courseId: "course-cs402",
      courseCode: "CS402",
      projectName: "Project DELI",
      priority: "medium",
      status: "todo",
      dueAt: daysFrom(now, 3),
    },
    {
      id: "task-nexus-03",
      issueKey: "NEXUS-03",
      title: "Khởi tạo schema Auth service và user seeding",
      courseId: "course-se330",
      courseCode: "SE330",
      projectName: "Project NEXUS",
      priority: "high",
      status: "in-progress",
      dueAt: daysFrom(now, -2, 12),
    },
  ];

  const sprints: CourseSprint[] = [
    {
      courseId: "course-se330",
      courseCode: "SE330",
      courseName: "Đồ án Chuyên ngành SE330",
      semester: "HK1",
      projectName: "Project NEXUS",
      teamId: "team-nexus",
      teamName: "Team NEXUS",
      role: "leader",
      sprintName: "Sprint 2",
      completedPoints: 26,
      totalPoints: 40,
      deadline: daysFrom(now, 4),
      health: "on-track",
      instructorName: "TS. Đặng Văn Cường",
    },
    {
      courseId: "course-cs402",
      courseCode: "CS402",
      courseName: "Phát triển Di động CS402",
      semester: "HK1",
      projectName: "Project DELI",
      teamId: "team-deli",
      teamName: "Team DELI",
      role: "member",
      sprintName: "Sprint 1",
      completedPoints: 12,
      totalPoints: 40,
      deadline: daysFrom(now, 9),
      health: "at-risk",
      instructorName: "ThS. Trần Mai Linh",
    },
  ];


  const dueToday = tasks.filter(
    (task) => new Date(task.dueAt).toDateString() === now.toDateString(),
  );
  const overdue = tasks.filter((task) => new Date(task.dueAt) < now);

  return {
    semester: "HK1 2026–2027",
    refreshedAt: now.toISOString(),
    enrollments,
    tasks,
    sprints,
    summary: {
      dueToday: dueToday.length,
      overdue: overdue.length,
      openPullRequests: 2,
      sprintProgressPercent: 47,
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
        title: "Add authentication middleware",
        repository: "nexus-team/supply-chain",
        author: "Trần Minh Tuấn (@tris_tuan)",
        updatedAt: daysFrom(now, 0, 8, 12),
        kind: "to-review",
      },
      {
        id: "pr-09",
        number: 9,
        title: "Setup socket connection for real-time delivery tracking",
        repository: "deli-app/driver-client",
        author: "Phạm Mai Hương (@huong_pm)",
        updatedAt: daysFrom(now, 0, 7, 30),
        kind: "to-review",
      },
      {
        id: "pr-21",
        number: 21,
        title: "feat: route optimization v2 draft",
        repository: "deli-app/driver-client",
        author: "Lê Minh Khoa (@minhkhoa)",
        updatedAt: daysFrom(now, 0, 10, 40),
        kind: "awaiting-review",
      },
    ],
    commits: [
      {
        id: "commit-1",
        message: "feat(tracking): bind GPS stream to driver screen",
        repository: "deli-app/driver-client",
        branchName: "feat/tracking-v1",
        issueKey: "DELI-08",
        committedAt: daysFrom(now, -1, 15),
      },
      {
        id: "commit-2",
        message: "chore(db): index inventory lookup columns",
        repository: "nexus-team/supply-chain",
        branchName: "feat/erd-v1",
        issueKey: "NEXUS-12",
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
        : { ...enrollment, membership: { status: "none" as const } },
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
    id: "task-nexus-01",
    issueKey: "NEXUS-01",
    title: "Thiết lập repository và bảo vệ nhánh chính",
    courseId: "course-se330",
    courseCode: "SE330",
    projectName: "Project NEXUS",
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