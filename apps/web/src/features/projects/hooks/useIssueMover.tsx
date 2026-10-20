import { announce } from "@atlaskit/pragmatic-drag-and-drop-live-region";
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import {
  ReasonDialog,
} from "@/components/feedback/ReasonDialog";
import type {
  IssueMenuGroup,
} from "@/features/projects/components/IssueActionsMenu";
import { DEMO_STATES, STATUS_LABELS, statusForGroup } from "@/features/projects/issueMeta";
import {
  planMove,
  planReorderToEdge,
  type MoveIntent,
  type MoveRequest,
} from "@/features/projects/lib/moveIntent";
import type { Issue, IssueStatus, ProjectWorkspace } from "@/features/projects/types";
import type { TeamRole } from "@/features/my-work/types";
import { demoWritesEnabled } from "@/lib/featureFlags";
import { useMoveIssue, useSetIssueBlocked } from "@/lib/query/studentFlowHooks";

const FLASH_MS = 700;

type Pending =
  | { kind: "move"; issue: Issue; intent: MoveIntent; destination: readonly Issue[] }
  | { kind: "block"; issue: Issue };

/** What a request looks like once the issue and the viewer are known. */
export type MoveDrop = Omit<MoveRequest, "role" | "activeSprintIds">;

interface FocusRequest {
  key: string;
  status: IssueStatus;
  sprintId: string | null;
  rank: number;
}

/** 1-based place `rank` takes among `destination` once `issue` is moved there. */
function positionAfterMove(destination: readonly Issue[], issue: Issue, rank: number): number {
  return destination.filter((other) => other.key !== issue.key && other.rank < rank).length + 1;
}

function sprintName(workspace: ProjectWorkspace, sprintId: string | null): string {
  if (sprintId === null) return "Product Backlog";
  return workspace.sprints.find((sprint) => sprint.id === sprintId)?.name ?? "Sprint";
}

/**
 * Everything a board or backlog needs to change an issue: plan a drop, ask for
 * a reason when the rules want one, call the server (optimistically), tell
 * assistive technology what happened, flash the card where it landed, and put
 * keyboard focus back on its menu button.
 *
 * `enabled` is false for an instructor and whenever the demo writes are off;
 * then `requestMove` does nothing and `menuFor` returns no groups.
 */
/** Public contract of the mover returned by `useIssueMover`. */
export interface IssueMover {
  enabled: boolean;
  role: TeamRole | null;
  flashKey: string | null;
  canDragIssue: (issue: Issue) => boolean;
  requestMove: (drop: MoveDrop) => void;
  toggleBlocked: (issue: Issue) => void;
  menuFor: (issue: Issue, context: { kind: "board" | "backlog"; destination: readonly Issue[] }) => IssueMenuGroup[];
  dialog: ReactNode;
}

export function useIssueMover({
  projectId,
  workspace,
  role,
  canWrite = demoWritesEnabled(),
}: Readonly<{
  projectId: string;
  workspace: ProjectWorkspace;
  role: TeamRole | null;
  /** Mặc định theo cờ ghi của demo; chế độ Work thật truyền `false` cho tới khi nối API ghi. */
  canWrite?: boolean;
}>) {
  const moveMutation = useMoveIssue(projectId);
  const blockMutation = useSetIssueBlocked(projectId);
  const [pending, setPending] = useState<Pending | null>(null);
  const [flashKey, setFlashKey] = useState<string | null>(null);
  const focusRequest = useRef<FocusRequest | null>(null);
  const flashTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const enabled = canWrite && role !== null;
  const activeSprintIds = useMemo(
    () => new Set(workspace.sprints.filter((sprint) => sprint.state === "active").map((s) => s.id)),
    [workspace.sprints],
  );

  // Put focus back on the card's menu button once the card is where it should be.
  useEffect(() => {
    const request = focusRequest.current;
    if (!request) return;
    const issue = workspace.issues.find((candidate) => candidate.key === request.key);
    if (
      !issue ||
      issue.status !== request.status ||
      issue.sprintId !== request.sprintId ||
      issue.rank !== request.rank
    ) {
      return;
    }
    focusRequest.current = null;
    document
      .querySelector<HTMLElement>(`[data-issue-trigger="${CSS.escape(request.key)}"]`)
      ?.focus();
  }, [workspace.issues]);

  useEffect(() => () => clearTimeout(flashTimer.current), []);

  const flash = useCallback((key: string) => {
    setFlashKey(key);
    clearTimeout(flashTimer.current);
    flashTimer.current = setTimeout(() => setFlashKey(null), FLASH_MS);
  }, []);

  const run = useCallback(
    (issue: Issue, intent: MoveIntent, destination: readonly Issue[], reason?: string) => {
      const target = {
        status: intent.status ?? issue.status,
        sprintId: intent.sprintId === undefined ? issue.sprintId : intent.sprintId,
        rank: intent.rank ?? issue.rank,
      };
      focusRequest.current = { key: issue.key, ...target };
      moveMutation.mutate({
        issueKey: issue.key,
        ...(intent.status !== undefined ? { status: intent.status } : {}),
        ...(intent.statusId !== undefined ? { statusId: intent.statusId } : {}),
        ...(intent.sprintId !== undefined ? { sprintId: intent.sprintId } : {}),
        ...(intent.rank !== undefined ? { rank: intent.rank } : {}),
        ...(reason ? { reason } : {}),
      });

      const parts: string[] = [];
      if (intent.status !== undefined) {
        parts.push(
          `đã chuyển từ ${STATUS_LABELS[issue.status]} sang ${STATUS_LABELS[intent.status]}`,
        );
      }
      if (intent.sprintId !== undefined) {
        parts.push(`đã chuyển sang ${sprintName(workspace, intent.sprintId)}`);
      }
      if (intent.rank !== undefined && parts.length === 0) {
        parts.push(`đã chuyển lên vị trí ${positionAfterMove(destination, issue, target.rank)}`);
      }
      announce(`${issue.key} ${parts.join(", ")}`);
      flash(issue.key);
    },
    [flash, moveMutation, workspace],
  );

  const requestMove = useCallback(
    (drop: MoveDrop) => {
      if (!enabled) return;
      const intent = planMove({ ...drop, role, activeSprintIds });
      if (!intent) return;
      if (intent.needsReason) {
        setPending({ kind: "move", issue: drop.issue, intent, destination: drop.destination });
        return;
      }
      run(drop.issue, intent, drop.destination);
    },
    [activeSprintIds, enabled, role, run],
  );

  const setBlocked = useCallback(
    (issue: Issue, blocked: boolean, reason?: string) => {
      blockMutation.mutate({ issueKey: issue.key, blocked, ...(reason ? { reason } : {}) });
      announce(blocked ? `${issue.key} đã được đánh dấu bị chặn` : `${issue.key} không còn bị chặn`);
      flash(issue.key);
    },
    [blockMutation, flash],
  );

  const toggleBlocked = useCallback(
    (issue: Issue) => {
      if (!enabled) return;
      if (issue.blocked) setBlocked(issue, false);
      else setPending({ kind: "block", issue });
    },
    [enabled, setBlocked],
  );

  const canTouch = useCallback(
    (issue: Issue) => enabled && (role === "leader" || (role === "member" && issue.isMine)),
    [enabled, role],
  );

  /** Menu for one card. `destination` is the list the card sits in; `context` picks the extras. */
  const menuFor = useCallback(
    (
      issue: Issue,
      context: { kind: "board" | "backlog"; destination: readonly Issue[] },
    ): IssueMenuGroup[] => {
      if (!canTouch(issue)) return [];
      const { destination } = context;
      const groups: IssueMenuGroup[] = [];

      if (context.kind === "board") {
        const states = (workspace.states.length > 0 ? workspace.states : DEMO_STATES)
          .filter((s) => s.group !== "CANCELLED" && s.id !== issue.statusId)
          .sort((a, b) => a.sequence - b.sequence);
        groups.push({
          label: "Chuyển trạng thái",
          items: states.map((s) => ({
            id: `status-${s.id}`,
            label: `Chuyển sang ${s.name}`,
            onSelect: () =>
              requestMove({ issue, toStatus: statusForGroup(s.group), toStateId: s.id, destination: [] }),
          })),
        });
      }

      if (role === "leader") {
        const reorder = (edge: "first" | "last") => () => {
          const intent = planReorderToEdge({ issue, role, destination, activeSprintIds, edge });
          if (intent) run(issue, intent, destination);
        };
        groups.push({
          label: "Thứ tự ưu tiên",
          items: [
            { id: "first", label: "Lên đầu danh sách", onSelect: reorder("first") },
            { id: "last", label: "Xuống cuối danh sách", onSelect: reorder("last") },
          ],
        });
        if (context.kind === "backlog") {
          const sprintItems = workspace.sprints
            .filter((sprint) => sprint.state !== "completed" && sprint.id !== issue.sprintId)
            .map((sprint) => ({
              id: `sprint-${sprint.id}`,
              label: `Chuyển vào ${sprint.name}`,
              onSelect: () => requestMove({ issue, toSprintId: sprint.id, destination: [] }),
            }));
          if (issue.sprintId !== null) {
            sprintItems.push({
              id: "sprint-none",
              label: "Chuyển về Product Backlog",
              onSelect: () => requestMove({ issue, toSprintId: null, destination: [] }),
            });
          }
          groups.push({ label: "Sprint", items: sprintItems });
        }
      }

      groups.push({
        items: [
          {
            id: "blocked",
            label: issue.blocked ? "Bỏ đánh dấu bị chặn" : "Đánh dấu bị chặn…",
            onSelect: () => toggleBlocked(issue),
          },
        ],
      });
      return groups;
    },
    [activeSprintIds, canTouch, requestMove, role, run, toggleBlocked, workspace.sprints, workspace.states],
  );

  const dialog: ReactNode = (
    <ReasonDialog
      open={pending !== null}
      title={pending?.kind === "block" ? `Đánh dấu ${pending.issue.key} bị chặn` : "Thay đổi phạm vi Sprint đang chạy"}
      description={
        pending?.kind === "block"
          ? "Nêu rõ điều đang chặn công việc này để cả nhóm biết cần hỗ trợ gì."
          : "Việc thêm hoặc bớt issue của Sprint đang chạy sẽ được ghi vào lịch sử cùng lý do."
      }
      confirmLabel={pending?.kind === "block" ? "Đánh dấu bị chặn" : "Xác nhận thay đổi"}
      onCancel={() => setPending(null)}
      onConfirm={(reason) => {
        const current = pending;
        setPending(null);
        if (!current) return;
        if (current.kind === "block") setBlocked(current.issue, true, reason);
        else run(current.issue, current.intent, current.destination, reason);
      }}
    />
  );

  return {
    enabled,
    role,
    flashKey,
    canDragIssue: canTouch,
    requestMove,
    toggleBlocked,
    menuFor,
    dialog,
  };
}
