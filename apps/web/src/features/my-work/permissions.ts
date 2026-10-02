import type { TeamMembership, TeamRole } from "@/features/my-work/types";

export type TeamPermission =
  | "task:create"
  | "task:assign"
  | "task:update-assigned"
  | "task:comment"
  | "task:link-git"
  | "board:open"
  | "members:view-requests"
  | "members:manage"
  | "settings:open";

const MEMBER_PERMISSIONS: TeamPermission[] = [
  "task:update-assigned",
  "task:comment",
  "task:link-git",
  "board:open",
];

const LEADER_PERMISSIONS: TeamPermission[] = [
  ...MEMBER_PERMISSIONS,
  "task:create",
  "task:assign",
  "members:view-requests",
  "members:manage",
  "settings:open",
];

export const ROLE_PERMISSIONS: Record<TeamRole, readonly TeamPermission[]> = {
  member: MEMBER_PERMISSIONS,
  leader: LEADER_PERMISSIONS,
};

export function hasTeamPermission(role: TeamRole, permission: TeamPermission): boolean {
  return ROLE_PERMISSIONS[role].includes(permission);
}

/**
 * Pending members are blocked from team internals (board, backlog, repo)
 * until the request is approved.
 */
export function canOpenTeamWorkspace(membership: TeamMembership): boolean {
  return membership.status === "assigned";
}