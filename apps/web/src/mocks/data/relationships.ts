import type { TeamRole } from "@/features/my-work/types";
import { LEADER_ID, MEMBER_ID, STUDENT_ID, TEACHER2_ID, TEACHER_ID } from "@/mocks/data/database";
import {
  CHAU_ID,
  CUONG_ID,
  DANG_KHOA_ID,
  DIEP_ID,
  DIEU_ANH_ID,
  HUONG_ID,
  HUY_ID,
  KHANG_ID,
  KHANH_ID,
  LONG_ID,
  MAI_STUDENT_ID,
  THANG_ID,
} from "@/mocks/data/directory";

/**
 * Relationship graph for the demo mock: the single source of truth for who
 * teaches which class, who is enrolled, which team belongs to which class,
 * who is in each team (and with which role) and which team owns which
 * project. Student and Teacher read models are both derived from here.
 * Display names, student codes and class/team metadata live in
 * `directory.ts`.
 *
 * A demo account never has a global team role; every permission is derived
 * from (user, resource) pairs below. Instructor access is per class.
 *
 * Demo members (SV01 = `student@utask.test` is the canonical multi-class
 * student: leader of NEXUS in SE330, member of DELI in CS402, no team in
 * IT3090, pending request to PHOENIX in SE331).
 *
 * Simplification kept from the Student demo: NEXUS has two leaders (the
 * `leader` and `student` accounts) so both demo logins can act as leader.
 */

export type MockTeamRole = TeamRole;

export interface MockAssignment {
  teamId: string;
  role: MockTeamRole;
}

export interface MockPendingRequest {
  teamId: string;
}

export interface MockTeamMember {
  userId: string;
  role: MockTeamRole;
  /** Optional per-team responsibility line shown in the Student roster. */
  responsibility?: string;
}

/** courseId → instructors. `isOwner` is the class owner shown as its lecturer. */
export const MOCK_COURSE_INSTRUCTORS: Record<string, { userId: string; isOwner: boolean }[]> = {
  "course-se330": [{ userId: TEACHER_ID, isOwner: true }],
  // Same subject code as SE330, different class: empty by design.
  "course-se330-n2": [{ userId: TEACHER_ID, isOwner: true }],
  "course-it3090": [
    { userId: CUONG_ID, isOwner: true },
    { userId: TEACHER_ID, isOwner: false },
  ],
  "course-cs402": [{ userId: TEACHER2_ID, isOwner: true }],
  "course-se331": [{ userId: HUONG_ID, isOwner: true }],
};

/** courseId → enrolled students. Enrollment of any user is derived from this. */
export const MOCK_COURSE_STUDENTS: Record<string, readonly string[]> = {
  "course-se330": [LEADER_ID, STUDENT_ID, MEMBER_ID, THANG_ID, LONG_ID, KHANG_ID],
  "course-se330-n2": [],
  "course-it3090": [STUDENT_ID, LEADER_ID, MEMBER_ID, KHANG_ID, DANG_KHOA_ID, HUY_ID, DIEP_ID, MAI_STUDENT_ID, KHANH_ID],
  "course-cs402": [LEADER_ID, STUDENT_ID, MEMBER_ID, HUY_ID, DIEU_ANH_ID, CHAU_ID],
  "course-se331": [LEADER_ID, STUDENT_ID, MAI_STUDENT_ID],
};

/**
 * Display order of a user's classes on Home and in the sidebar. Order only:
 * enrollment itself is derived from `MOCK_COURSE_STUDENTS`. Classes missing
 * here follow in graph order.
 */
const ENROLLMENT_DISPLAY_ORDER: Record<string, readonly string[]> = {
  [LEADER_ID]: ["course-se330", "course-cs402", "course-it3090", "course-se331"],
  [MEMBER_ID]: ["course-cs402", "course-it3090", "course-se330"],
  [STUDENT_ID]: ["course-it3090", "course-se330", "course-cs402", "course-se331"],
};

/** teamId → courseId */
export const MOCK_TEAM_COURSES: Record<string, string> = {
  "team-nexus": "course-se330",
  "team-deli": "course-cs402",
  "team-phoenix": "course-se331",
  "team-iot-vision": "course-it3090",
  "team-iot-sense": "course-it3090",
};

/** teamId → members, in roster display order. */
export const MOCK_TEAM_MEMBERS: Record<string, readonly MockTeamMember[]> = {
  "team-nexus": [
    { userId: LEADER_ID, role: "leader", responsibility: "Quản lý dự án, Thiết kế kiến trúc Microservices" },
    { userId: STUDENT_ID, role: "leader", responsibility: "Frontend Web Portal & tích hợp VNPay IPN" },
    { userId: MEMBER_ID, role: "member", responsibility: "Xây dựng giao diện Web & Mobile" },
    { userId: THANG_ID, role: "member", responsibility: "Huấn luyện mô hình gợi ý & tối ưu hóa" },
    { userId: LONG_ID, role: "member", responsibility: "Thiết kế CSDL PostgreSQL, viết kịch bản kiểm thử" },
  ],
  "team-deli": [
    { userId: HUY_ID, role: "leader", responsibility: "Kiến trúc API & CSDL" },
    { userId: STUDENT_ID, role: "member", responsibility: "UI Onboarding & đồng bộ Health Connect" },
    { userId: MEMBER_ID, role: "member", responsibility: "UI Cart, Checkout, Catalog" },
    { userId: LEADER_ID, role: "member", responsibility: "Tích hợp CI/CD và hỗ trợ backend" },
    { userId: DIEU_ANH_ID, role: "member", responsibility: "Thiết kế trải nghiệm người dùng" },
  ],
  // SV01 has only a pending request here (MOCK_PENDING_REQUESTS), not a seat.
  "team-phoenix": [{ userId: MAI_STUDENT_ID, role: "leader" }],
  "team-iot-vision": [
    { userId: HUY_ID, role: "leader" },
    { userId: DIEP_ID, role: "member" },
  ],
  "team-iot-sense": [
    { userId: MAI_STUDENT_ID, role: "leader" },
    { userId: KHANH_ID, role: "member" },
  ],
};

/** `userId:courseId` → pending join request. Absent = no pending request. */
export const MOCK_PENDING_REQUESTS: Record<string, MockPendingRequest> = {
  [`${STUDENT_ID}:course-se331`]: { teamId: "team-phoenix" },
};

/** teamId → project workspace id. Absent = no provisioned workspace. */
export const MOCK_TEAM_PROJECTS: Record<string, string> = {
  "team-nexus": "project-nexus",
  "team-deli": "project-deli",
};

/* ------------------------------------------------------------------ */
/* Derived lookups                                                     */
/* ------------------------------------------------------------------ */

export function studentsOfCourse(courseId: string): readonly string[] {
  return MOCK_COURSE_STUDENTS[courseId] ?? [];
}

export function teamsOfCourse(courseId: string): string[] {
  return Object.entries(MOCK_TEAM_COURSES)
    .filter(([, teamCourseId]) => teamCourseId === courseId)
    .map(([teamId]) => teamId);
}

export function membersOfTeam(teamId: string): readonly MockTeamMember[] {
  return MOCK_TEAM_MEMBERS[teamId] ?? [];
}

export function enrolledCoursesFor(userId: string): readonly string[] {
  const enrolled = Object.keys(MOCK_COURSE_STUDENTS).filter((courseId) =>
    MOCK_COURSE_STUDENTS[courseId].includes(userId),
  );
  const order = ENROLLMENT_DISPLAY_ORDER[userId] ?? [];
  const rank = (courseId: string) => {
    const index = order.indexOf(courseId);
    return index === -1 ? order.length : index;
  };
  return [...enrolled].sort((a, b) => rank(a) - rank(b));
}

export function assignmentFor(userId: string, courseId: string): MockAssignment | null {
  if (!studentsOfCourse(courseId).includes(userId)) {
    return null;
  }
  for (const teamId of teamsOfCourse(courseId)) {
    const member = membersOfTeam(teamId).find((candidate) => candidate.userId === userId);
    if (member) {
      return { teamId, role: member.role };
    }
  }
  return null;
}

export function pendingRequestFor(
  userId: string,
  courseId: string,
): MockPendingRequest | null {
  return MOCK_PENDING_REQUESTS[`${userId}:${courseId}`] ?? null;
}

/** Class size and how many of those students sit in a team. */
export function classSizeFor(courseId: string): { total: number; teamed: number } {
  const students = studentsOfCourse(courseId);
  return {
    total: students.length,
    teamed: students.filter((userId) => assignmentFor(userId, courseId) !== null).length,
  };
}

export function coursesTaughtBy(userId: string): readonly string[] {
  return Object.entries(MOCK_COURSE_INSTRUCTORS)
    .filter(([, instructors]) => instructors.some((entry) => entry.userId === userId))
    .map(([courseId]) => courseId);
}

export function isInstructorOf(userId: string, courseId: string): boolean {
  return MOCK_COURSE_INSTRUCTORS[courseId]?.some((entry) => entry.userId === userId) ?? false;
}

/** User id of the class owner (the lecturer a Student sees). */
export function ownerInstructorId(courseId: string): string | null {
  return MOCK_COURSE_INSTRUCTORS[courseId]?.find((entry) => entry.isOwner)?.userId ?? null;
}

/** Role of `userId` inside `projectId` as a team member, or null. */
export function projectRoleForUser(userId: string, projectId: string): MockTeamRole | null {
  for (const [teamId, ownedProjectId] of Object.entries(MOCK_TEAM_PROJECTS)) {
    if (ownedProjectId !== projectId) {
      continue;
    }
    const member = membersOfTeam(teamId).find((candidate) => candidate.userId === userId);
    if (member) {
      return member.role;
    }
  }
  return null;
}

/**
 * Project workspace ids the user may open. Phase 1 grants this only through
 * team membership; instructors get no project access yet.
 */
export function accessibleProjectsForUser(userId: string): readonly string[] {
  const projects: string[] = [];
  for (const courseId of enrolledCoursesFor(userId)) {
    const assignment = assignmentFor(userId, courseId);
    if (!assignment) {
      continue;
    }
    const projectId = MOCK_TEAM_PROJECTS[assignment.teamId];
    if (projectId && !projects.includes(projectId)) {
      projects.push(projectId);
    }
  }
  return projects;
}

/** Classes whose class-level notifications `userId` may see (student or instructor). */
export function classesVisibleForNotifications(userId: string): readonly string[] {
  return [...new Set([...enrolledCoursesFor(userId), ...coursesTaughtBy(userId)])];
}
