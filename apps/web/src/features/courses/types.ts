/**
 * Domain types for the courses & teams feature.
 *
 * Membership is per-course: a Student can be leader in one course, member in
 * another, pending in a third, and unteamed in a fourth.
 */

import type { TeamMembership } from "@/features/my-work/types";

export type TopicStatus =
  | "draft"
  | "submitted"
  | "under_review"
  | "revision_required"
  | "approved"
  | "rejected";

export interface TopicProposal {
  status: TopicStatus;
  title: string | null;
  description: string | null;
  objectives: string[];
  /** Who last acted on the proposal and when (ISO 8601). */
  reviewedBy: string | null;
  reviewedAt: string | null;
  /** Instructor feedback, present from `revision_required`/`rejected` onward. */
  feedback: string | null;
}

export interface TeamMember {
  userId: string;
  displayName: string;
  studentId: string;
  email: string;
  /** Professional skill tag shown in the roster. */
  skill: string;
  /** Responsibility description for the project. */
  responsibility: string;
  role: "leader" | "member";
}

export interface OpenTeamSlot {
  teamId: string;
  teamName: string;
  leaderName: string;
  memberCount: number;
  maxMembers: number;
  /** Skills the team is actively looking for. */
  neededSkills: string[];
}

export interface UnassignedClassmate {
  userId: string;
  displayName: string;
  studentId: string;
  skill: string;
}

export interface CourseDetail {
  courseId: string;
  courseCode: string;
  courseName: string;
  semester: string;
  instructorName: string;
  /** Allowed team size range. */
  teamSize: { min: number; max: number };
  classSize: { total: number; teamed: number };
  membership: TeamMembership;
  teamFormation: {
    mode: "self-select" | "join-code" | "instructor-assigned";
    registrationDeadline: string | null;
    selfCreateAllowed: boolean;
  };
  /** Present when membership.status === "assigned". */
  team: {
    teamId: string;
    teamName: string;
    isLeader: boolean;
    memberCount: number;
    maxMembers: number;
    members: TeamMember[];
    topic: TopicProposal;
    /** Repository full name once the project is provisioned. */
    repository: string | null;
    /** Project key once the topic is approved and workspace provisioned. */
    projectKey: string | null;
    /** Project workspace id once provisioned; null until the workspace exists. */
    projectId: string | null;
  } | null;
  /** Present when membership.status === "none" — team formation data. */
  formation: {
    openTeams: OpenTeamSlot[];
    unassignedClassmates: UnassignedClassmate[];
  } | null;
}