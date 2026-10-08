/**
 * Permission layer.
 *
 * Roles are per-context: `ProjectRole`/`TeamRole` belong to a course or
 * project, never to the user globally. The UI layer hides or disables actions
 * that the backend would reject; backend remains the source of truth.
 */

import type { TeamRole } from "@/features/my-work/types";
import type { TopicStatus } from "@/features/courses/types";

export interface CoursePermissionContext {
  membershipStatus: "none" | "pending" | "assigned";
  role: TeamRole | null;
  selfCreateAllowed: boolean;
  formationDeadlinePassed: boolean;
}

export interface ProjectPermissionContext {
  role: TeamRole | null;
  /** BYOK key configured at project level. */
  aiEnabled: boolean;
}

export function canCreateTeam(ctx: CoursePermissionContext): boolean {
  return (
    ctx.membershipStatus === "none" &&
    ctx.selfCreateAllowed &&
    !ctx.formationDeadlinePassed
  );
}

export function canManageTeam(ctx: CoursePermissionContext): boolean {
  return ctx.membershipStatus === "assigned" && ctx.role === "leader";
}

export function canApproveJoinRequest(ctx: CoursePermissionContext): boolean {
  return canManageTeam(ctx);
}

export function canSubmitTopic(
  ctx: CoursePermissionContext,
  topicStatus: TopicStatus | null,
): boolean {
  if (!canManageTeam(ctx)) return false;
  if (topicStatus === null) return true;
  return topicStatus === "draft" || topicStatus === "revision_required";
}

export function canViewProject(ctx: ProjectPermissionContext): boolean {
  return ctx.role !== null;
}

export function canCreateTask(ctx: ProjectPermissionContext): boolean {
  return ctx.role === "leader";
}

export function canAssignTask(ctx: ProjectPermissionContext): boolean {
  return ctx.role === "leader";
}

export function canManageSprint(ctx: ProjectPermissionContext): boolean {
  return ctx.role === "leader";
}

export function canManageProjectSettings(ctx: ProjectPermissionContext): boolean {
  return ctx.role === "leader";
}

/**
 * AI actions are leader-only AND require a configured key. When the key is
 * missing, callers should route the leader to Project Settings (CTA).
 */
export function canBreakdownTaskWithAI(ctx: ProjectPermissionContext): boolean {
  return ctx.role === "leader" && ctx.aiEnabled;
}

export function aiRequiresKey(ctx: ProjectPermissionContext): boolean {
  return ctx.role === "leader" && !ctx.aiEnabled;
}

export function canUpdateTask(
  ctx: ProjectPermissionContext,
  assigneeIsMe: boolean,
): boolean {
  if (ctx.role === "leader") return true;
  return ctx.role === "member" && assigneeIsMe;
}