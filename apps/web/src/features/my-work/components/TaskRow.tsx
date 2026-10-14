import { ChevronsDown, ChevronsUp, Clock, Minus } from "lucide-react";
import { Link } from "react-router-dom";

import type { MyTask, TaskPriority } from "@/features/my-work/types";
import { isOverdue as taskIsOverdue } from "@/features/my-work/taskFilters";
import { cn } from "@/lib/utils";

const priorityMeta: Record<TaskPriority, { label: string; icon: typeof ChevronsUp; classes: string; iconClasses: string }> = {
  high: {
    label: "Cao (High)",
    icon: ChevronsUp,
    classes: "border-rose-200/60 bg-rose-50 text-rose-700",
    iconClasses: "text-rose-600",
  },
  medium: {
    label: "Trung bình",
    icon: Minus,
    classes: "border-amber-200/60 bg-amber-50 text-amber-700",
    iconClasses: "text-amber-600",
  },
  low: {
    label: "Thấp (Low)",
    icon: ChevronsDown,
    classes: "border-border bg-secondary text-muted-foreground",
    iconClasses: "text-muted-foreground",
  },
};

function formatDue(dueAt: string, now: Date): string {
  const due = new Date(dueAt);
  const sameDay = due.toDateString() === now.toDateString();
  const time = `${String(due.getHours()).padStart(2, "0")}:${String(due.getMinutes()).padStart(2, "0")}`;
  if (sameDay) {
    return `Hôm nay, ${time}`;
  }
  const diffMs = due.getTime() - now.getTime();
  const diffDays = Math.round(diffMs / 86_400_000);
  if (diffDays < 0) {
    return `Quá hạn ${Math.abs(diffDays)} ngày`;
  }
  if (diffDays === 1) {
    return `Mai, ${time}`;
  }
  return due.toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit", year: "numeric" });
}

export function TaskRow({ task, now }: { task: MyTask; now: Date }) {
  const priority = priorityMeta[task.priority];
  const PriorityIcon = priority.icon;
  // Done tasks are never flagged overdue.
  const isOverdue = taskIsOverdue(task, now);

  return (
    <li className="group flex flex-col gap-3 px-2 py-3.5 transition-colors hover:bg-secondary/50 sm:flex-row sm:items-center sm:gap-4">
      <span
        className="shrink-0 rounded bg-primary-subtle px-2 py-0.5 font-mono text-xs font-bold text-primary"
        aria-label={`Mã issue ${task.issueKey}`}
      >
        {task.issueKey}
      </span>

      <div className="min-w-0 flex-1">
        {task.projectId ? (
          <Link
            to={`/projects/${encodeURIComponent(task.projectId)}/board?issue=${encodeURIComponent(task.issueKey)}`}
            className="block truncate text-sm font-semibold text-foreground transition-colors hover:text-primary"
          >
            {task.title}
          </Link>
        ) : (
          <span className="block truncate text-sm font-semibold text-foreground">
            {task.title}
          </span>
        )}
      </div>

      <span
        className={cn(
          "inline-flex w-fit shrink-0 items-center gap-1 rounded border px-2 py-0.5 text-[11px] font-semibold",
          priority.classes,
        )}
      >
        <PriorityIcon className={cn("size-3", priority.iconClasses)} aria-hidden />
        {priority.label}
      </span>

      <span
        className={cn(
          "flex w-fit shrink-0 items-center gap-1 text-xs sm:justify-end",
          isOverdue ? "font-semibold text-destructive" : "font-medium text-foreground",
        )}
      >
        <Clock className="size-3.5 text-muted-foreground" aria-hidden />
        {formatDue(task.dueAt, now)}
        {isOverdue ? <span className="sr-only"> (quá hạn)</span> : null}
      </span>
    </li>
  );
}