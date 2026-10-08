import type {
  AccountSettings,
  StudentNotification,
} from "@/features/notifications/types";
import type { CourseDetail, TeamMember } from "@/features/courses/types";

import { MEMBER_ID, STUDENT_ID } from "@/mocks/data/database";
import { MOCK_COURSE_META, MOCK_PEOPLE, MOCK_TEAM_META } from "@/mocks/data/directory";
import {
  assignmentFor,
  classSizeFor,
  membersOfTeam,
  ownerInstructorId,
  MOCK_TEAM_COURSES,
  pendingRequestFor,
  projectRoleForUser,
  projectViewerFor,
  studentsOfCourse,
  teamOfProject,
  teamsOfCourse,
} from "@/mocks/data/relationships";

/**
 * Scenario-controlled fixtures for courses, teams, topics, projects, backlog,
 * board, issue detail, code stats, notifications and account settings.
 *
 * All dates derive from `daysFrom` on a scenario anchor so relative badges
 * ("Còn 5 ngày", "15 phút trước") stay plausible for any scenario.
 */

const ANCHOR_DATE = "2026-10-20T08:30:00.000Z";

/** Fixed clock for read models that must be deterministic (Teacher dashboards). */
export function mockAnchorDate(): Date {
  return new Date(ANCHOR_DATE);
}

function daysFrom(now: Date, days: number, hours = 17, minutes = 0): string {
  const target = new Date(now);
  target.setDate(target.getDate() + days);
  target.setHours(hours, minutes, 0, 0);
  return target.toISOString();
}

function minutesBefore(now: Date, minutes: number): string {
  return new Date(now.getTime() - minutes * 60_000).toISOString();
}

/* ------------------------------------------------------------------ */
/* Courses & teams                                                     */
/**
 * Rosters, class size, lecturer and team names are derived from the shared
 * relationship graph (relationships.ts + directory.ts), so the Student and
 * Teacher views of the same class always agree.
 */
function personName(userId: string): string {
  return MOCK_PEOPLE[userId]?.displayName ?? "Chưa rõ";
}

function teamName(teamId: string): string {
  return MOCK_TEAM_META[teamId]?.name ?? teamId;
}

function rosterFor(teamId: string): TeamMember[] {
  return membersOfTeam(teamId).map((member) => {
    const person = MOCK_PEOPLE[member.userId];
    return {
      userId: member.userId,
      displayName: person?.displayName ?? "Chưa rõ",
      studentId: person?.studentCode ?? "",
      email: person?.email ?? "",
      skill: person?.skill ?? "",
      responsibility: member.responsibility ?? "",
      role: member.role,
    };
  });
}

function courseBase(courseId: string) {
  const meta = MOCK_COURSE_META[courseId];
  const ownerId = ownerInstructorId(courseId);
  return {
    courseId,
    courseCode: meta.courseCode,
    courseName: meta.courseName,
    semester: meta.term,
    instructorName: ownerId ? personName(ownerId) : "Chưa phân công",
    teamSize: meta.teamSize,
    classSize: classSizeFor(courseId),
  };
}

/** Formation view derived from the graph: open teams and classmates without a team. */
function formationFromGraph(courseId: string): NonNullable<CourseDetail["formation"]> {
  const maxMembers = MOCK_COURSE_META[courseId].teamSize.max;
  return {
    openTeams: teamsOfCourse(courseId).map((teamId) => {
      const members = membersOfTeam(teamId);
      const leader = members.find((member) => member.role === "leader");
      return {
        teamId,
        teamName: teamName(teamId),
        leaderName: leader ? personName(leader.userId) : "Chưa có",
        memberCount: members.length,
        maxMembers,
        neededSkills: MOCK_TEAM_META[teamId]?.neededSkills ?? [],
      };
    }),
    unassignedClassmates: studentsOfCourse(courseId)
      .filter((userId) => assignmentFor(userId, courseId) === null)
      .map((userId) => ({
        userId,
        displayName: personName(userId),
        studentId: MOCK_PEOPLE[userId]?.studentCode ?? "",
        skill: MOCK_PEOPLE[userId]?.skill ?? "",
      })),
  };
}

function buildCourseSe330(now: Date, userId: string): CourseDetail {
  const assignment = assignmentFor(userId, "course-se330");
  return {
    ...courseBase("course-se330"),
    membership: assignment
      ? {
          status: "assigned",
          teamId: "team-nexus",
          teamName: teamName("team-nexus"),
          role: assignment.role,
        }
      : { status: "none" },
    teamFormation: {
      mode: "self-select",
      registrationDeadline: daysFrom(now, 12),
      selfCreateAllowed: false,
    },
    team: assignment
      ? {
          teamId: "team-nexus",
          teamName: teamName("team-nexus"),
          isLeader: assignment.role === "leader",
          memberCount: membersOfTeam("team-nexus").length,
          maxMembers: MOCK_COURSE_META["course-se330"].teamSize.max,
          members: rosterFor("team-nexus"),
          topic: {
            status: "approved",
            title:
              "Hệ thống Quản lý Chuỗi cung ứng Thông minh & Truy xuất Nguồn gốc",
            description:
              "Hệ thống hướng tới ứng dụng kiến trúc Microservices hiệu năng cao kết hợp Smart Contracts và IoT sensors nhằm giám sát điều kiện bảo quản nhiệt độ thời gian thực của container hàng hóa, tự động xác thực chứng từ xuất xứ CO/CQ và cảnh báo sớm rủi ro vận chuyển.",
            objectives: [
              "Xây dựng kiến trúc Microservices với gRPC giao tiếp nội bộ và API Gateway.",
              "Tích hợp Smart Contract lưu trữ bất biến nhật ký kiểm định và chứng từ CO/CQ.",
              "Module kết nối cảm biến IoT (MQTT Broker) cập nhật biểu đồ nhiệt độ & độ ẩm real-time.",
              "Web Portal quản trị cho doanh nghiệp logistics và mobile app cho tài xế giao nhận.",
            ],
            reviewedBy: "TS. Trần Minh Đức",
            reviewedAt: daysFrom(now, 0, 9, 30),
            feedback:
              "Đề tài có tính thực tiễn cao, phạm vi phù hợp nhóm 4 sinh viên. Nhóm chú ý hoàn thiện sơ đồ ERD và chuẩn bị Backlog cho Sprint 1.",
          },
          repository: "nexus-team/smart-supply-chain",
          projectKey: "NEXUS",
          projectId: "project-nexus",
        }
      : null,
    formation: null,
  };
}

function buildFormationSe330(now: Date): CourseDetail {
  return {
    ...courseBase("course-se330"),
    membership: { status: "none" },
    teamFormation: {
      mode: "self-select",
      registrationDeadline: daysFrom(now, 2, 23, 59),
      selfCreateAllowed: true,
    },
    team: null,
    formation: {
      openTeams: [
        {
          teamId: "team-atlas",
          teamName: "Team ATLAS",
          leaderName: "Phạm Quốc Huy",
          memberCount: 3,
          maxMembers: 5,
          neededSkills: ["Backend Node.js", "DevOps"],
        },
        {
          teamId: "team-orbit",
          teamName: "Team ORBIT",
          leaderName: "Võ Thanh Mai",
          memberCount: 4,
          maxMembers: 5,
          neededSkills: ["UI/UX", "QA"],
        },
        {
          teamId: "team-quark",
          teamName: "Team QUARK",
          leaderName: "Đỗ Hải Nam",
          memberCount: 2,
          maxMembers: 4,
          neededSkills: ["Machine Learning", "Frontend React"],
        },
        {
          teamId: "team-nova",
          teamName: "Team NOVA",
          leaderName: "Lê Thu Hà",
          memberCount: 3,
          maxMembers: 5,
          neededSkills: ["Backend Java Spring"],
        },
      ],
      unassignedClassmates: [
        {
          userId: STUDENT_ID,
          displayName: "Lê Minh Khoa",
          studentId: "21020999",
          skill: "Frontend React & TypeScript",
        },
        {
          userId: "00000000-0000-4000-8000-000000000006",
          displayName: "Hoàng Trọng Khang",
          studentId: "21021004",
          skill: "Backend FastAPI",
        },
        {
          userId: "00000000-0000-4000-8000-00000000000d",
          displayName: "Ngô Diệu Anh",
          studentId: "21021058",
          skill: "UI/UX & Figma",
        },
        {
          userId: "00000000-0000-4000-8000-000000000008",
          displayName: "Trần Đăng Khoa",
          studentId: "21021061",
          skill: "Embedded & IoT",
        },
        {
          userId: "00000000-0000-4000-8000-00000000000e",
          displayName: "Lý Bảo Châu",
          studentId: "21021090",
          skill: "QA Automation",
        },
        {
          userId: "00000000-0000-4000-8000-00000000000a",
          displayName: "Vũ Ngọc Diệp",
          studentId: "21021103",
          skill: "Data Engineering",
        },
        {
          userId: "00000000-0000-4000-8000-00000000000b",
          displayName: "Đinh Tuấn Khanh",
          studentId: "21021120",
          skill: "Backend Golang",
        },
      ],
    },
  };
}

function buildCourseCs402(now: Date, userId: string): CourseDetail {
  const assignment = assignmentFor(userId, "course-cs402");
  return {
    ...courseBase("course-cs402"),
    membership: assignment
      ? {
          status: "assigned",
          teamId: "team-deli",
          teamName: teamName("team-deli"),
          role: assignment.role,
        }
      : { status: "none" },
    teamFormation: {
      mode: "join-code",
      registrationDeadline: null,
      selfCreateAllowed: false,
    },
    team: assignment
      ? {
          teamId: "team-deli",
          teamName: teamName("team-deli"),
          isLeader: assignment.role === "leader",
          memberCount: membersOfTeam("team-deli").length,
          maxMembers: MOCK_COURSE_META["course-cs402"].teamSize.max,
          members: rosterFor("team-deli"),
          topic: {
            status: "under_review",
            title:
              "Ứng dụng Theo dõi Sức khỏe & Dinh dưỡng Cá nhân hóa (Flutter & FastAPI)",
            description:
              "Ứng dụng di động theo dõi sức khỏe và dinh dưỡng cá nhân, gợi ý thực đơn theo mục tiêu calo, đồng bộ dữ liệu wearable qua Health Connect.",
            objectives: [
              "Onboarding đánh giá mục tiêu sức khỏe cá nhân.",
              "Gợi ý thực đơn theo calo và dị ứng.",
              "Đồng bộ wearable qua Health Connect API.",
            ],
            reviewedBy: null,
            reviewedAt: null,
            feedback: null,
          },
          repository: null,
          projectKey: "DELI",
          projectId: "project-deli",
        }
      : null,
    formation: null,
  };
}

function buildPendingCourseSe331(now: Date): CourseDetail {
  return {
    ...courseBase("course-se331"),
    membership: {
      status: "pending",
      teamId: "team-phoenix",
      teamName: teamName("team-phoenix"),
      requestedAt: daysFrom(now, -3, 9, 15),
    },
    teamFormation: {
      mode: "instructor-assigned",
      registrationDeadline: null,
      selfCreateAllowed: false,
    },
    team: null,
    formation: null,
  };
}

/** SE331 as seen by an enrolled student without a team or pending request. */
function buildUnTeamedCourseSe331(): CourseDetail {
  return {
    ...courseBase("course-se331"),
    membership: { status: "none" },
    teamFormation: {
      mode: "instructor-assigned",
      registrationDeadline: null,
      selfCreateAllowed: false,
    },
    team: null,
    formation: null,
  };
}

/** Class A fixture: the enrolled student has no team here. */
function buildCourseIt3090(now: Date): CourseDetail {
  return {
    ...courseBase("course-it3090"),
    membership: { status: "none" },
    teamFormation: {
      mode: "self-select",
      registrationDeadline: daysFrom(now, 2, 23, 59),
      selfCreateAllowed: true,
    },
    team: null,
    formation: formationFromGraph("course-it3090"),
  };
}

/* ------------------------------------------------------------------ */
/* Topic lifecycle variants                                            */
/* ------------------------------------------------------------------ */

export function courseDetailForScenario(
  courseId: string,
  scenario: string,
  userId: string,
  now = new Date(ANCHOR_DATE),
): CourseDetail | null {
  switch (courseId) {
    case "course-se330":
      if (scenario === "student-no-team" || scenario === "student-join-pending") {
        return buildFormationSe330(now);
      }
      if (scenario === "student-team-leader-topic-draft") {
        return buildCourseSe330WithTopic(now, userId, "draft");
      }
      if (scenario === "student-topic-revision-required") {
        return buildCourseSe330WithTopic(now, userId, "revision_required");
      }
      if (scenario === "student-team-member-topic-pending") {
        return buildCourseSe330WithTopic(now, userId, "submitted");
      }
      return buildCourseSe330(now, userId);
    case "course-cs402":
      return buildCourseCs402(now, userId);
    case "course-se331":
      if (pendingRequestFor(userId, "course-se331")) {
        return buildPendingCourseSe331(now);
      }
      return buildUnTeamedCourseSe331();
    case "course-it3090":
      return buildCourseIt3090(now);
    default:
      return null;
  }
}

function buildCourseSe330WithTopic(
  now: Date,
  userId: string,
  status: "draft" | "submitted" | "revision_required",
): CourseDetail {
  const base = buildCourseSe330(now, userId);
  if (!base.team) throw new Error("SE330 base must have a team");
  const titleByStatus: Record<string, string | null> = {
    draft: null,
    submitted:
      "Hệ thống Quản lý Chuỗi cung ứng Thông minh & Truy xuất Nguồn gốc",
    revision_required:
      "Hệ thống Quản lý Chuỗi cung ứng Thông minh & Truy xuất Nguồn gốc",
  };
  return {
    ...base,
    team: {
      ...base.team,
      projectKey: status === "draft" ? null : base.team.projectKey,
      repository: status === "draft" ? null : base.team.repository,
      topic: {
        status,
        title: titleByStatus[status],
        description:
          status === "draft"
            ? null
            : "Ứng dụng Microservices giám sát chuỗi cung ứng, tích hợp IoT và Smart Contract.",
        objectives:
          status === "draft"
            ? []
            : [
                "Kiến trúc Microservices gRPC + API Gateway.",
                "Smart Contract lưu chứng từ CO/CQ.",
                "Module IoT MQTT biểu đồ real-time.",
              ],
        reviewedBy: status === "revision_required" ? "TS. Trần Minh Đức" : null,
        reviewedAt: status === "revision_required" ? daysFrom(now, -1, 15, 0) : null,
        feedback:
          status === "revision_required"
            ? "Nhóm bổ sung sơ đồ ERD chi tiết và thu hẹp phạm vi module IoT chỉ còn giám sát nhiệt độ."
            : null,
      },
    },
  };
}

/* ------------------------------------------------------------------ */
/* Projects                                                            */
/* ------------------------------------------------------------------ */

import type {
  CodeContributor,
  Issue,
  IssueDetail,
  ProjectCode,
  ProjectSummary,
  ProjectWorkspace,
} from "@/features/projects/types";

/** Project facts without any viewer: who is looking is decided separately. */
type WorkspaceData = Omit<ProjectWorkspace, "viewer" | "myRole" | "courseId" | "teamId">;

const NEXUS_MEMBERS = [
  { userId: "00000000-0000-4000-8000-000000000001", displayName: "Nguyễn Hoàng Nam", initials: "HN" },
  { userId: "00000000-0000-4000-8000-000000000002", displayName: "Đặng Thảo Linh", initials: "TL" },
  { userId: "00000000-0000-4000-8000-000000000004", displayName: "Bùi Quang Thắng", initials: "QT" },
  { userId: "00000000-0000-4000-8000-000000000005", displayName: "Trần Bảo Long", initials: "BL" },
];

function buildProjectSummaries(now: Date, userId: string): ProjectSummary[] {
  const summaries: ProjectSummary[] = [
    {
      projectId: "project-nexus",
      projectKey: "NEXUS",
      name: "Smart Supply Chain — Quản lý Chuỗi cung ứng Thông minh",
      courseCode: "SE330",
      courseName: "Đồ án Chuyên ngành Công nghệ Phần mềm",
      instructorName: "TS. Trần Minh Đức",
      teamName: "Team NEXUS",
      role: "member",
      archived: false,
      sprint: {
        name: "Sprint 2: Thiết kế ERD & API Gateway",
        deadline: daysFrom(now, 4),
        completedPoints: 26,
        totalPoints: 40,
      },
      repository: "nexus-team/smart-supply-chain",
    },
    {
      projectId: "project-deli",
      projectKey: "DELI",
      name: "Ứng dụng Theo dõi Sức khỏe & Dinh dưỡng (Flutter & FastAPI)",
      courseCode: "CS402",
      courseName: "Phát triển Ứng dụng Di động Nâng cao",
      instructorName: "ThS. Lê Thị Mai",
      teamName: "Team DELI",
      role: "member",
      archived: false,
      sprint: {
        name: "Sprint 1: Onboarding & Auth",
        deadline: daysFrom(now, 7),
        completedPoints: 8,
        totalPoints: 21,
      },
      repository: null,
    },
    {
      projectId: "project-legacy",
      projectKey: "LEG",
      name: "Website Rao vặt Đồ án Cũ (HK4 2025–2026)",
      courseCode: "SE225",
      courseName: "Nhập môn Công nghệ Phần mềm",
      instructorName: "TS. Vũ Thu Hương",
      teamName: "Team LEGACY",
      role: "member",
      archived: true,
      sprint: null,
      repository: "legacy-team/classifieds",
    },
  ];
  // Role per user+project from the relationship graph, not per account.
  for (const summary of summaries) {
    const role = projectRoleForUser(userId, summary.projectId);
    if (role !== null) {
      summary.role = role;
    }
  }
  return summaries;
}

function buildNexusIssues(now: Date): Issue[] {
  return [
    { id: "i1", key: "NEXUS-101", dueAt: daysFrom(now, 3), type: "story", title: "Thiết kế schema CSDL Giỏ hàng", status: "todo", priority: "medium", storyPoints: 5, epicId: "epic-cart", sprintId: "sprint-2", assignee: NEXUS_MEMBERS[1], hasPullRequest: false, isMine: false, updatedAt: daysFrom(now, -2) },
    { id: "i2", key: "NEXUS-102", dueAt: daysFrom(now, -1), type: "task", title: "Cập nhật tài liệu API Swagger", status: "todo", priority: "low", storyPoints: 3, epicId: null, sprintId: "sprint-2", assignee: NEXUS_MEMBERS[3], hasPullRequest: false, isMine: false, updatedAt: daysFrom(now, -1) },
    { id: "i3", key: "NEXUS-104", dueAt: daysFrom(now, 2), type: "story", title: "Tích hợp cổng thanh toán VNPay Sandbox và IPN", status: "in-progress", priority: "high", storyPoints: 5, epicId: "epic-payment", sprintId: "sprint-2", assignee: NEXUS_MEMBERS[0], hasPullRequest: true, isMine: false, updatedAt: daysFrom(now, 0, 10) },
    { id: "i4", key: "NEXUS-105", type: "story", title: "Giao diện responsive Giỏ hàng", status: "in-progress", priority: "medium", storyPoints: 3, epicId: "epic-cart", sprintId: "sprint-2", assignee: NEXUS_MEMBERS[1], hasPullRequest: false, isMine: false, updatedAt: daysFrom(now, 0, 9) },
    { id: "i5", key: "NEXUS-98", dueAt: daysFrom(now, -2), type: "task", title: "Refactor Auth JWT Middleware", status: "review", priority: "high", storyPoints: 5, epicId: "epic-auth", sprintId: "sprint-2", assignee: NEXUS_MEMBERS[2], hasPullRequest: true, isMine: false, updatedAt: daysFrom(now, 0, 8) },
    { id: "i6", key: "NEXUS-95", type: "task", title: "Khởi tạo boilerplate dự án React + Vite", status: "done", priority: "medium", storyPoints: 2, epicId: null, sprintId: "sprint-1", assignee: NEXUS_MEMBERS[0], hasPullRequest: true, isMine: false, updatedAt: daysFrom(now, -9) },
    { id: "i7", key: "NEXUS-110", type: "story", title: "Module Giỏ hàng: thêm/sửa/xóa sản phẩm", status: "todo", priority: "high", storyPoints: 8, epicId: "epic-cart", sprintId: null, assignee: null, hasPullRequest: false, isMine: false, updatedAt: daysFrom(now, -5) },
    { id: "i8", key: "NEXUS-111", type: "bug", title: "Lỗi 500 khi thanh toán COD > 10 triệu", status: "todo", priority: "high", storyPoints: 3, epicId: "epic-payment", sprintId: null, assignee: null, hasPullRequest: false, isMine: false, updatedAt: daysFrom(now, -4) },
    { id: "i9", key: "NEXUS-112", type: "story", title: "Đăng nhập Google OAuth2 cho portal", status: "todo", priority: "medium", storyPoints: 5, epicId: "epic-auth", sprintId: null, assignee: null, hasPullRequest: false, isMine: false, updatedAt: daysFrom(now, -6) },
    { id: "i10", key: "NEXUS-113", type: "story", title: "Truy xuất nguồn gốc bằng QR + Smart Contract", status: "todo", priority: "high", storyPoints: 13, epicId: "epic-trace", sprintId: null, assignee: null, hasPullRequest: false, isMine: false, updatedAt: daysFrom(now, -7) },
  ];
}

function buildNexusWorkspace(now: Date): WorkspaceData {
  return {
    projectId: "project-nexus",
    projectKey: "NEXUS",
    name: "Smart Supply Chain — Quản lý Chuỗi cung ứng Thông minh",
    courseCode: "SE330",
    courseName: "Đồ án Chuyên ngành Công nghệ Phần mềm",
    instructorName: "TS. Trần Minh Đức",
    teamName: "Team NEXUS",
    repository: "nexus-team/smart-supply-chain",
    epics: [
      { id: "epic-auth", name: "Module Xác thực & Phân quyền", color: "#7c3aed", issueCount: 4 },
      { id: "epic-cart", name: "Module Giỏ hàng & Đơn hàng", color: "#f59e0b", issueCount: 5 },
      { id: "epic-payment", name: "Module Thanh toán VNPay", color: "#10b981", issueCount: 6 },
      { id: "epic-trace", name: "Truy xuất nguồn gốc", color: "#3b82f6", issueCount: 6 },
    ],
    sprints: [
      { id: "sprint-2", name: "Sprint 2: ERD & API Gateway", state: "active", startDate: daysFrom(now, -10), endDate: daysFrom(now, 5), goal: "Hoàn thiện thiết kế ERD, tích hợp thanh toán VNPay sandbox.", completedPoints: 26, totalPoints: 40 },
      { id: "sprint-3", name: "Sprint 3: Module Giỏ hàng", state: "upcoming", startDate: daysFrom(now, 6), endDate: daysFrom(now, 20), goal: "Xây dựng module giỏ hàng end-to-end.", completedPoints: 0, totalPoints: 24 },
      { id: "sprint-1", name: "Sprint 1: Khởi tạo", state: "completed", startDate: daysFrom(now, -25), endDate: daysFrom(now, -11), goal: "Boilerplate, CI/CD, auth cơ bản.", completedPoints: 21, totalPoints: 21 },
    ],
    issues: buildNexusIssues(now),
  };
}

function buildDeliWorkspace(now: Date): WorkspaceData {
  return {
    projectId: "project-deli",
    projectKey: "DELI",
    name: "Ứng dụng Theo dõi Sức khỏe & Dinh dưỡng",
    courseCode: "CS402",
    courseName: "Phát triển Ứng dụng Di động Nâng cao",
    instructorName: "ThS. Lê Thị Mai",
    teamName: "Team DELI",
    repository: null,
    epics: [{ id: "epic-deli-onboard", name: "Onboarding & Auth", color: "#7c3aed", issueCount: 3 }],
    sprints: [
      { id: "sprint-deli-1", name: "Sprint 1: Onboarding & Auth", state: "active", startDate: daysFrom(now, -7), endDate: daysFrom(now, 7), goal: "Onboarding flow và đăng nhập.", completedPoints: 8, totalPoints: 21 },
    ],
    issues: [
      { id: "d1", key: "DELI-01", type: "story", title: "Màn hình onboarding 3 bước", status: "done", priority: "medium", storyPoints: 5, epicId: "epic-deli-onboard", sprintId: "sprint-deli-1", assignee: { userId: MEMBER_ID, displayName: "Đặng Thảo Linh", initials: "TL" }, hasPullRequest: true, isMine: false, updatedAt: daysFrom(now, -2) },
      { id: "d2", key: "DELI-02", type: "story", title: "Đăng nhập email + password", status: "in-progress", priority: "high", storyPoints: 8, epicId: "epic-deli-onboard", sprintId: "sprint-deli-1", assignee: { userId: MEMBER_ID, displayName: "Đặng Thảo Linh", initials: "TL" }, hasPullRequest: false, isMine: false, updatedAt: daysFrom(now, 0, 11) },
      { id: "d3", key: "DELI-03", type: "task", title: "Cài đặt CI Flutter analyze + test", status: "todo", priority: "low", storyPoints: 3, epicId: null, sprintId: null, assignee: null, hasPullRequest: false, isMine: false, updatedAt: daysFrom(now, -3) },
    ],
  };
}

export function projectSummariesForScenario(
  scenario: string,
  userId: string,
): ProjectSummary[] {
  const now = new Date();
  if (scenario === "student-empty") return [];
  if (scenario === "student-project-leader") {
    return buildProjectSummaries(now, userId).filter((project) => project.role === "leader");
  }
  if (scenario === "student-project-member") {
    return buildProjectSummaries(now, userId).filter((project) => project.role === "member" && !project.archived);
  }
  return buildProjectSummaries(now, userId);
}

function buildWorkspaceData(projectId: string, now: Date): WorkspaceData | null {
  if (projectId === "project-nexus") return buildNexusWorkspace(now);
  if (projectId === "project-deli") return buildDeliWorkspace(now);
  return null;
}

/** `isMine` follows the signed-in user; with no user nothing is "mine". */
function markMine(data: WorkspaceData, userId: string | null): WorkspaceData {
  return {
    ...data,
    issues: data.issues.map((issue) => ({
      ...issue,
      isMine: userId !== null && issue.assignee?.userId === userId,
    })),
  };
}

/**
 * Viewer-independent project facts for read models (Teacher dashboards).
 * Nothing in it belongs to a particular user, so no issue is "mine".
 */
export function projectDataFor(projectId: string, now: Date): WorkspaceData | null {
  const data = buildWorkspaceData(projectId, now);
  return data ? markMine(data, null) : null;
}

/**
 * Workspace as seen by `userId`. Without a viewer relationship (team member,
 * or instructor of the owning class) there is no workspace: the caller gets
 * null, never a default role.
 */
export function projectWorkspaceFor(
  projectId: string,
  scenario: string,
  userId: string,
  now: Date = new Date(),
): ProjectWorkspace | null {
  const viewer = projectViewerFor(userId, projectId);
  const data = buildWorkspaceData(projectId, now);
  const teamId = teamOfProject(projectId);
  if (!viewer || !data || !teamId) return null;
  return {
    ...markMine(data, userId),
    courseId: MOCK_TEAM_COURSES[teamId],
    teamId,
    viewer,
    ...(viewer.kind === "team-member" ? { myRole: viewer.role } : {}),
  };
}

export function issueDetailFor(
  projectId: string,
  issueKey: string,
  userId: string,
  now: Date = new Date(),
): IssueDetail | null {
  const workspace = projectWorkspaceFor(projectId, "default", userId, now);
  if (!workspace) return null;
  const issue = workspace.issues.find((candidate) => candidate.key === issueKey);
  if (!issue) return null;
  return {
    issue,
    description:
      issue.key === "NEXUS-104"
        ? "Tích hợp cổng thanh toán VNPay ở chế độ Sandbox: tạo payment URL, xử lý IPN callback, xác thực chữ ký HMAC, ghi nhận trạng thái đơn hàng và retry an toàn khi VNPay timeout."
        : "Chi tiết công việc theo mô tả trong sprint backlog.",
    acceptanceCriteria:
      issue.key === "NEXUS-104"
        ? [
            "Tạo được payment URL cho đơn hàng test ở sandbox.",
            "IPN callback xác thực chữ ký HMAC-SHA512 đúng.",
            "Trạng thái đơn hàng chuyển sang PAID chỉ một lần (idempotent).",
            "Unit test độ phủ ≥ 80% cho module payment.",
          ]
        : ["Hoàn thành theo định nghĩa Done của nhóm."],
    reporterName: "Nguyễn Hoàng Nam",
    comments: [
      {
        id: "c1",
        authorName: "Đặng Thảo Linh",
        authorInitials: "TL",
        body: "Mình đã có wireframe trang kết quả thanh toán, check giúp phần state loading nhé.",
        createdAt: daysFrom(now, -1, 14, 30),
      },
      {
        id: "c2",
        authorName: "Nguyễn Hoàng Nam",
        authorInitials: "HN",
        body: "OK, mình xử lý IPN xong sẽ ghép với state đó.",
        createdAt: daysFrom(now, -1, 15, 10),
      },
    ],
    history: [
      { id: "h1", actorName: "Nguyễn Hoàng Nam", summary: "tạo issue", at: daysFrom(now, -5, 9, 0) },
      { id: "h2", actorName: "Nguyễn Hoàng Nam", summary: "chuyển trạng thái sang In Progress", at: daysFrom(now, -2, 10, 15) },
      { id: "h3", actorName: "Nguyễn Hoàng Nam", summary: "liên kết pull request PR #12", at: daysFrom(now, 0, 10, 0) },
    ],
    subtasks:
      issue.key === "NEXUS-104"
        ? [
            { id: "s1", title: "Tạo payment URL sandbox", done: true },
            { id: "s2", title: "Xử lý IPN callback + HMAC", done: true },
            { id: "s3", title: "Idempotency trạng thái đơn", done: false },
            { id: "s4", title: "Unit test module payment", done: false },
          ]
        : [],
    gitLinks:
      issue.key === "NEXUS-104"
        ? [
            { kind: "branch", label: "feat/vnpay-ipn" },
            { kind: "commit", label: "9a4d8c2" },
            { kind: "pr", label: "PR #12" },
          ]
        : [],
  };
}

const NO_REPOSITORY_STATS: ProjectCode["stats"] = {
  commits: 0,
  commitsWeekDelta: 0,
  pullRequests: { total: 0, merged: 0, open: 0, review: 0 },
  branches: 0,
  linesChanged: { added: 0, removed: 0 },
};

/**
 * Code view for a project. A project that exists but has no repository is
 * answered with the `no-repository` state, not with "not found": the two
 * mean different things to the person looking. `isMe` follows `userId`.
 */
export function projectCodeFor(
  projectId: string,
  scenario: string,
  userId: string,
  now: Date = new Date(),
): ProjectCode | null {
  if (projectId === "project-deli") {
    return {
      repository: null,
      defaultBranch: null,
      latestCommitSha: null,
      syncState: "no-repository",
      stats: NO_REPOSITORY_STATS,
      contributors: [],
      pullRequests: [],
      commits: [],
      branches: [],
    };
  }
  if (projectId !== "project-nexus") {
    return null;
  }
  const syncState =
    scenario === "student-github-disconnected"
      ? "disconnected"
      : scenario === "student-webhook-error" || scenario === "teacher-github-error"
        ? "webhook-error"
        : scenario === "student-token-expired"
          ? "token-expired"
          : "synced";
  return {
    repository: "nexus-team/smart-supply-chain",
    defaultBranch: "main",
    latestCommitSha: "9a4d8c2",
    syncState,
    stats: {
      commits: 142,
      commitsWeekDelta: 18,
      pullRequests: { total: 28, merged: 24, open: 3, review: 1 },
      branches: 6,
      linesChanged: { added: 14250, removed: 3120 },
    },
    contributors: ([
      { userId: "00000000-0000-4000-8000-000000000001", displayName: "Nguyễn Hoàng Nam", studentId: "21120015", githubUsername: "hoangnam21", roleTitle: "Trưởng nhóm / Fullstack", commits: 48, commitPercent: 34, additions: 6000, deletions: 1250, pullRequestCount: 10, mergedCount: 9, linkedIssuePercent: 96, status: "key", isMe: false },
      { userId: "00000000-0000-4000-8000-000000000003", displayName: "Lê Minh Khoa", studentId: "21020999", githubUsername: "khoalm_fe", roleTitle: "Trưởng nhóm / Frontend", commits: 18, commitPercent: 13, additions: 1840, deletions: 370, pullRequestCount: 3, mergedCount: 3, linkedIssuePercent: 78, status: "active", isMe: false },
      { userId: "00000000-0000-4000-8000-000000000002", displayName: "Đặng Thảo Linh", studentId: "21020872", githubUsername: "thaolinh_dev", roleTitle: "Frontend Developer", commits: 38, commitPercent: 27, additions: 3710, deletions: 780, pullRequestCount: 8, mergedCount: 7, linkedIssuePercent: 88, status: "active", isMe: false },
      { userId: "00000000-0000-4000-8000-000000000004", displayName: "Bùi Quang Thắng", studentId: "21020215", githubUsername: "thangbq_ai", roleTitle: "AI & Data", commits: 22, commitPercent: 15, additions: 1800, deletions: 420, pullRequestCount: 5, mergedCount: 5, linkedIssuePercent: 73, status: "active", isMe: false },
      { userId: "00000000-0000-4000-8000-000000000005", displayName: "Trần Bảo Long", studentId: "21020301", githubUsername: "longtb_qa", roleTitle: "QA & Database", commits: 16, commitPercent: 11, additions: 900, deletions: 300, pullRequestCount: 2, mergedCount: 0, linkedIssuePercent: 45, status: "watch", isMe: false },
    ] as CodeContributor[]).map((contributor) => ({ ...contributor, isMe: contributor.userId === userId })),
    pullRequests: [
      { id: "pr1", number: 12, title: "feat(payment): VNPay sandbox + IPN handler", author: "Nguyễn Hoàng Nam", branch: "feat/vnpay-ipn", state: "open", linkedIssueKey: "NEXUS-104", updatedAt: daysFrom(now, 0, 10) },
      { id: "pr2", number: 11, title: "refactor(auth): JWT middleware", author: "Bùi Quang Thắng", branch: "refactor/jwt-middleware", state: "merged", linkedIssueKey: "NEXUS-98", updatedAt: daysFrom(now, -1, 16) },
      { id: "pr3", number: 10, title: "feat(cart): responsive cart UI", author: "Đặng Thảo Linh", branch: "feat/cart-responsive", state: "open", linkedIssueKey: "NEXUS-105", updatedAt: daysFrom(now, 0, 9) },
    ],
    commits: [
      { id: "cm1", sha: "9a4d8c2", message: "NEXUS-104 add IPN signature verify", author: "Nguyễn Hoàng Nam", branch: "feat/vnpay-ipn", linkedIssueKey: "NEXUS-104", committedAt: daysFrom(now, 0, 10) },
      { id: "cm2", sha: "3f1b9e7", message: "NEXUS-105 cart grid breakpoints", author: "Đặng Thảo Linh", branch: "feat/cart-responsive", linkedIssueKey: "NEXUS-105", committedAt: daysFrom(now, 0, 9) },
      { id: "cm3", sha: "a02cc41", message: "NEXUS-98 extract jwt verify", author: "Bùi Quang Thắng", branch: "refactor/jwt-middleware", linkedIssueKey: "NEXUS-98", committedAt: daysFrom(now, -1, 16) },
      { id: "cm4", sha: "77de310", message: "chore: bump eslint config", author: "Trần Bảo Long", branch: "main", linkedIssueKey: null, committedAt: daysFrom(now, -2, 11) },
    ],
    branches: [
      { id: "b1", name: "feat/vnpay-ipn", author: "Nguyễn Hoàng Nam", linkedIssueKey: "NEXUS-104", updatedDaysAgo: 0 },
      { id: "b2", name: "feat/cart-responsive", author: "Đặng Thảo Linh", linkedIssueKey: "NEXUS-105", updatedDaysAgo: 0 },
      { id: "b3", name: "refactor/jwt-middleware", author: "Bùi Quang Thắng", linkedIssueKey: "NEXUS-98", updatedDaysAgo: 1 },
    ],
  };
}

/* ------------------------------------------------------------------ */
/* Notifications                                                       */
/* ------------------------------------------------------------------ */

export function notificationsForScenario(
  scenario: string,
  now = new Date(ANCHOR_DATE),
): StudentNotification[] {
  if (scenario === "student-empty") return [];
  return [
    {
      id: "n1",
      category: "ai-risk",
      title: "Sprint 2 đồ án SE330 có nguy cơ chậm 1 ngày",
      body: "Trợ lý AI UTask: 2 task Backend quan trọng chưa có commit/PR liên kết (NEXUS-110, NEXUS-104).",
      at: minutesBefore(now, 15),
      read: false,
      actionLabel: "Xem Backlog",
      target: { kind: "backlog", projectId: "project-nexus" },
    },
    {
      id: "n2",
      category: "course-team",
      title: "TS. Trần Minh Đức đã PHÊ DUYỆT đề tài của Team NEXUS",
      body: "Không gian Jira Workspace đã mở. Project key: NEXUS.",
      at: minutesBefore(now, 55),
      read: false,
      actionLabel: "Mở Project Workspace",
      target: { kind: "team-hub", courseId: "course-se330" },
    },
    {
      id: "n3",
      category: "task-pr",
      title: "Bùi Quang Thắng đề nghị review PR #11 (NEXUS-98)",
      body: "refactor(auth): JWT middleware — 2 files changed.",
      at: minutesBefore(now, 180),
      read: false,
      actionLabel: "Xem Pull Request",
      target: { kind: "code", projectId: "project-nexus" },
    },
    {
      id: "n4",
      category: "task-pr",
      title: "Bạn được gán issue NEXUS-104",
      body: "Tích hợp cổng thanh toán VNPay Sandbox và IPN — hạn " + daysFrom(now, 3, 17, 0).slice(0, 10) + ".",
      at: minutesBefore(now, 1440),
      read: true,
      actionLabel: "Xem Issue",
      target: { kind: "board-issue", projectId: "project-nexus", issueKey: "NEXUS-104" },
    },
    {
      id: "n5",
      category: "course-team",
      title: "Hạn đăng ký đề tài môn IT3090: còn 2 ngày",
      body: "Sinh viên chưa có nhóm sẽ được giảng viên phân nhóm ngẫu nhiên sau hạn.",
      at: minutesBefore(now, 2880),
      read: true,
      actionLabel: "Xem môn học",
      target: { kind: "team-formation", courseId: "course-se330" },
    },
    {
      id: "n6",
      category: "ai-risk",
      title: "Đóng góp GitHub của bạn giảm 40% trong 2 tuần",
      body: "Trợ lý AI khuyến nghị duy trì tần suất commit để bảo vệ điểm quá trình.",
      at: minutesBefore(now, 4320),
      read: true,
      actionLabel: "Xem thống kê",
      target: { kind: "code", projectId: "project-nexus" },
    },
    {
      id: "n7",
      category: "task-pr",
      title: "PR #10 (NEXUS-105) đang chờ bạn review",
      body: "feat(cart): responsive cart UI.",
      at: minutesBefore(now, 5760),
      read: true,
      actionLabel: "Xem Pull Request",
      target: { kind: "code", projectId: "project-nexus" },
    },
    {
      id: "n8",
      category: "course-team",
      title: "Lời mời ghép nhóm từ Team ORBIT (SE330)",
      body: "Võ Thanh Mai mời bạn tham gia Team ORBIT — còn 1 chỗ trống.",
      at: minutesBefore(now, 7200),
      read: true,
      actionLabel: "Xem yêu cầu",
      target: { kind: "team-formation", courseId: "course-se330" },
    },
  ];
}

export function accountSettingsForScenario(scenario: string): AccountSettings {
  const now = new Date();
  const githubStatus =
    scenario === "student-github-disconnected"
      ? "disconnected"
      : scenario === "student-token-expired"
        ? "token-expired"
        : "connected";
  return {
    studentId: "21120015",
    fullName: "Nguyễn Hoàng Nam",
    email: "nam.nh21120015@sis.edu.vn",
    cohortClass: "K21-CNPM-02",
    faculty: "Khoa Công nghệ Phần mềm • Trường ĐH CNTT",
    phone: "0987 654 321",
    updatedAt: daysFrom(now, -1, 16, 42),
    github: {
      status: githubStatus,
      username: githubStatus === "disconnected" ? null : "hoangnam21",
      profileUrl: githubStatus === "disconnected" ? null : "https://github.com/hoangnam21",
      lastSyncedAt: githubStatus === "disconnected" ? null : minutesBefore(now, 10),
      linkedRepositoryCount: githubStatus === "disconnected" ? 0 : 8,
    },
    sessions: [
      { id: "s1", device: "Chrome — Windows 11", location: "TP.HCM, VN", lastActiveAt: minutesBefore(now, 2), current: true },
      { id: "s2", device: "Mobile App — Android", location: "TP.HCM, VN", lastActiveAt: minutesBefore(now, 1500), current: false },
    ],
  };
}