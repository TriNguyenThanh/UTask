import type { TeamRole } from "@/features/my-work/types";
import { LEADER_ID, MEMBER_ID, STUDENT_ID } from "@/mocks/data/database";

/**
 * Relationship graph for the demo mock: who is enrolled in which course,
 * who belongs to which team (and with which role), and which team owns
 * which project. This is the single source of truth for per-user access
 * checks — a demo account never has a global role; every permission is
 * derived from (user, resource) pairs below.
 *
 * Demo members (SV01 = `student@utask.test` is the canonical multi-class
 * student: leader of NEXUS in SE330, member of DELI in CS402, no team in
 * IT3090, pending request to PHOENIX in SE331).
 */

export type MockTeamRole = TeamRole;

export interface MockAssignment {
  teamId: string;
  role: MockTeamRole;
}

export interface MockPendingRequest {
  teamId: string;
}

/** userId → enrolled course ids (order drives the sidebar / Home order). */
export const MOCK_ENROLLMENTS: Record<string, readonly string[]> = {
  [LEADER_ID]: ["course-se330", "course-cs402", "course-it3090", "course-se331"],
  [MEMBER_ID]: ["course-cs402", "course-it3090", "course-se330"],
  [STUDENT_ID]: ["course-it3090", "course-se330", "course-cs402", "course-se331"],
};

/** `userId:courseId` → team assignment. Absent = no team in that course. */
export const MOCK_ASSIGNMENTS: Record<string, MockAssignment> = {
  [`${LEADER_ID}:course-se330`]: { teamId: "team-nexus", role: "leader" },
  [`${LEADER_ID}:course-cs402`]: { teamId: "team-deli", role: "member" },
  [`${MEMBER_ID}:course-cs402`]: { teamId: "team-deli", role: "member" },
  [`${MEMBER_ID}:course-se330`]: { teamId: "team-nexus", role: "member" },
  [`${STUDENT_ID}:course-se330`]: { teamId: "team-nexus", role: "leader" },
  [`${STUDENT_ID}:course-cs402`]: { teamId: "team-deli", role: "member" },
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

export function enrolledCoursesFor(userId: string): readonly string[] {
  return MOCK_ENROLLMENTS[userId] ?? [];
}

export function assignmentFor(userId: string, courseId: string): MockAssignment | null {
  return MOCK_ASSIGNMENTS[`${userId}:${courseId}`] ?? null;
}

export function pendingRequestFor(
  userId: string,
  courseId: string,
): MockPendingRequest | null {
  return MOCK_PENDING_REQUESTS[`${userId}:${courseId}`] ?? null;
}

/** Role of `userId` inside `projectId`, or null when not a member. */
export function projectRoleForUser(userId: string, projectId: string): MockTeamRole | null {
  for (const [teamId, ownedProjectId] of Object.entries(MOCK_TEAM_PROJECTS)) {
    if (ownedProjectId !== projectId) {
      continue;
    }
    for (const [key, assignment] of Object.entries(MOCK_ASSIGNMENTS)) {
      if (key.startsWith(`${userId}:`) && assignment.teamId === teamId) {
        return assignment.role;
      }
    }
  }
  return null;
}

/** Project workspace ids the user may open (via any team membership). */
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