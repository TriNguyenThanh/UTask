import { rankBetween } from "@/features/projects/lib/rank";
import type { TeamRole } from "@/features/my-work/types";
import type { Issue, IssueStatus } from "@/features/projects/types";

/** What to ask the server for after a card was dropped or a menu item chosen. */
export interface MoveIntent {
  status?: IssueStatus;
  /** `null` = Product Backlog. */
  sprintId?: string | null;
  rank?: string;
  /** The move changes the scope of an active sprint, so the leader must say why. */
  needsReason: boolean;
}

export interface MoveRequest {
  issue: Issue;
  /** Team role of the viewer; `null` for an instructor, who never moves anything. */
  role: TeamRole | null;
  /** Board: the column dropped on. */
  toStatus?: IssueStatus;
  /** Backlog: the section dropped on; `null` is the Product Backlog. */
  toSprintId?: string | null;
  /** Cards visible in the destination list, in order. May contain the moved card. */
  destination: readonly Issue[];
  /**
   * Where in the list: next to this card, or `null` for the end of the list.
   * Left out (`undefined`), the position is not part of the move and the rank
   * is never touched: a status change from a menu keeps the card's priority.
   */
  target?: { key: string; edge: "top" | "bottom" } | null;
  /** Ids of sprints in the `active` state. */
  activeSprintIds: ReadonlySet<string>;
}

/**
 * Turns a drop into the change to send. Pure, so the permission rules live in
 * one place that tests can reach: the board only mirrors them, the server is
 * the one that decides.
 *
 * - Leader: may change status, sprint and position.
 * - Member: may only change the status of their own task, and keeps its rank.
 * - Anyone else (instructor): nothing.
 *
 * Returns `null` when the drop changes nothing.
 */
export function planMove(request: MoveRequest): MoveIntent | null {
  const { issue, role } = request;
  if (role === null) return null;

  if (role === "member") {
    if (!issue.isMine) return null;
    if (request.toStatus === undefined || request.toStatus === issue.status) return null;
    return { status: request.toStatus, needsReason: false };
  }

  const intent: MoveIntent = { needsReason: false };
  if (request.toStatus !== undefined && request.toStatus !== issue.status) {
    intent.status = request.toStatus;
  }
  if (request.toSprintId !== undefined && request.toSprintId !== issue.sprintId) {
    intent.sprintId = request.toSprintId;
    intent.needsReason =
      (issue.sprintId !== null && request.activeSprintIds.has(issue.sprintId)) ||
      (request.toSprintId !== null && request.activeSprintIds.has(request.toSprintId));
  }

  if (request.target === undefined) {
    return intent.status === undefined && intent.sprintId === undefined ? null : intent;
  }

  // Dropped on itself: the drop target is the card being dragged, nothing moves.
  if (request.target?.key === issue.key && intent.status === undefined && intent.sprintId === undefined) {
    return null;
  }

  const others = request.destination.filter((candidate) => candidate.key !== issue.key);
  let insertAt = others.length;
  if (request.target) {
    const targetIndex = others.findIndex((candidate) => candidate.key === request.target?.key);
    if (targetIndex >= 0) insertAt = request.target.edge === "top" ? targetIndex : targetIndex + 1;
  }
  const before = insertAt > 0 ? others[insertAt - 1].rank : null;
  const after = insertAt < others.length ? others[insertAt].rank : null;

  // Already between the neighbours it would land between: no new rank needed.
  const alreadyThere =
    (before === null || before < issue.rank) && (after === null || issue.rank < after);
  if (!alreadyThere) {
    const rank = rankBetween(before, after);
    if (rank === null) return null;
    intent.rank = rank;
  }

  if (intent.status === undefined && intent.sprintId === undefined && intent.rank === undefined) {
    return null;
  }
  return intent;
}

/** Position of the move inside a list, for the "lên đầu / xuống cuối" menu items. */
export function planReorderToEdge(
  request: Omit<MoveRequest, "target" | "toStatus" | "toSprintId"> & { edge: "first" | "last" },
): MoveIntent | null {
  const others = request.destination.filter((candidate) => candidate.key !== request.issue.key);
  const target =
    request.edge === "first"
      ? others[0] && { key: others[0].key, edge: "top" as const }
      : null;
  return planMove({
    ...request,
    toStatus: request.issue.status,
    toSprintId: request.issue.sprintId,
    target,
  });
}
