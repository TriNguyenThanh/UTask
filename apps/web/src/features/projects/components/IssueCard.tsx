import { AlertTriangle, Ban } from "lucide-react";
import type { ReactNode } from "react";

import type { Issue } from "@/features/projects/types";
import {
  isOverdue,
  PRIORITY_LABELS,
  PRIORITY_STYLES,
  TYPE_LABELS,
} from "@/features/projects/issueMeta";
import { cn } from "@/lib/utils";

/**
 * One card on the Kanban board. The card itself is an <article>: the open
 * button, the drag handle and the actions menu are separate controls so each
 * keeps its own accessible name and keyboard behaviour.
 */
export function IssueCard({
  issue,
  onOpen,
  handle,
  actions,
  highlighted = false,
  closestEdge = null,
}: Readonly<{
  issue: Issue;
  onOpen: (key: string) => void;
  /** Drag handle; rendered only when the viewer may drag this card. */
  handle?: ReactNode;
  /** Per-card actions menu (the non-drag alternative to moving a card). */
  actions?: ReactNode;
  /** Briefly true right after a move, so the card flashes where it landed. */
  highlighted?: boolean;
  /** Drop indicator edge while another card is dragged over this one. */
  closestEdge?: "top" | "bottom" | null;
}>) {
  const done = issue.status === "done";
  const overdue = isOverdue(issue);
  return (
    <article
      data-issue-key={issue.key}
      className={cn(
        "relative rounded-md border border-outline-subtle bg-card p-3 transition-all hover:border-primary/40 hover:shadow-sm focus-within:border-primary",
        done && "opacity-90",
        issue.blocked && "border-rose-300",
        highlighted && "bg-primary/10",
      )}
    >
      {closestEdge ? (
        <span
          aria-hidden
          className={cn(
            "pointer-events-none absolute inset-x-0 z-10 h-0.5 bg-primary",
            closestEdge === "top" ? "-top-1.5" : "-bottom-1.5",
          )}
        />
      ) : null}
      <div className="mb-1.5 flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-1.5">
          {handle}
          <span
            className={cn(
              "shrink-0 rounded border px-1 py-0.5 text-[10px] font-semibold",
              issue.type === "bug"
                ? "border-rose-200 bg-rose-50 text-rose-600"
                : issue.type === "story"
                  ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                  : "border-blue-200 bg-blue-50 text-blue-700",
            )}
          >
            {TYPE_LABELS[issue.type]}
          </span>
          <span
            className={cn(
              "font-mono text-xs font-semibold",
              done ? "text-muted-foreground line-through" : "text-foreground",
            )}
          >
            {issue.key}
          </span>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          {issue.hasPullRequest ? (
            <span
              className="inline-flex items-center gap-1 rounded border border-emerald-200 bg-emerald-50 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-700"
              title="Có Pull Request"
            >
              <span className="size-1.5 rounded-full bg-emerald-600" aria-hidden />
              PR
            </span>
          ) : null}
          {actions}
        </div>
      </div>

      <button
        type="button"
        onClick={() => onOpen(issue.key)}
        className="mb-3 block w-full rounded text-left text-xs font-medium leading-relaxed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
        aria-label={`Mở chi tiết issue ${issue.key}: ${issue.title}`}
      >
        <span className={cn(done && "text-muted-foreground")}>{issue.title}</span>
      </button>

      {issue.blocked || overdue ? (
        <div className="mb-2 flex flex-wrap gap-1.5">
          {issue.blocked ? (
            <span
              className="inline-flex items-center gap-1 rounded border border-rose-200 bg-rose-50 px-1.5 py-0.5 text-[10px] font-semibold text-rose-700"
              title={issue.blockedReason ?? "Đang bị chặn"}
            >
              <Ban className="size-3" aria-hidden />
              Bị chặn
            </span>
          ) : null}
          {overdue ? (
            <span className="inline-flex items-center gap-1 rounded border border-amber-200 bg-amber-50 px-1.5 py-0.5 text-[10px] font-semibold text-amber-800">
              <AlertTriangle className="size-3" aria-hidden />
              Quá hạn
            </span>
          ) : null}
        </div>
      ) : null}

      <div className="flex items-center justify-between gap-2 border-t border-muted pt-1">
        <span
          className={cn(
            "rounded border px-1.5 py-0.5 text-[10px] font-medium",
            PRIORITY_STYLES[issue.priority],
          )}
        >
          {PRIORITY_LABELS[issue.priority]}
        </span>
        <div className="flex items-center gap-2">
          <span
            className="flex size-5 items-center justify-center rounded-full bg-muted font-mono text-[10px] font-semibold text-muted-foreground"
            title="Story Points"
          >
            {issue.storyPoints}
          </span>
          {issue.assignee ? (
            <span
              className="flex size-5 items-center justify-center rounded-full bg-primary/10 text-[10px] font-bold text-primary"
              title={issue.assignee.displayName}
            >
              {issue.assignee.initials}
            </span>
          ) : (
            <span
              className="flex size-5 items-center justify-center rounded-full border border-dashed border-outline-subtle text-[9px] text-muted-foreground"
              title="Chưa gán"
            >
              ?
            </span>
          )}
        </div>
      </div>
    </article>
  );
}
