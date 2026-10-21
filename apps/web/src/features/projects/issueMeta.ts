import type { Issue, IssueStatus, ProjectState, StateGroup } from "@/features/projects/types";

/** Board columns, in workflow order. One source for Board, Backlog and IssuePanel. */
export const COLUMNS: { status: IssueStatus; label: string; dotClass: string }[] = [
  { status: "todo", label: "Cần làm (To Do)", dotClass: "bg-slate-400" },
  { status: "in-progress", label: "Đang làm (In Progress)", dotClass: "bg-blue-500" },
  { status: "review", label: "Chờ Review (In Review)", dotClass: "bg-amber-500" },
  { status: "done", label: "Hoàn thành (Done)", dotClass: "bg-emerald-600" },
];

/** Maps a WorkService StateGroup to the legacy IssueStatus used by UI components. */
export function statusForGroup(group: StateGroup): IssueStatus {
  if (group === "STARTED") return "in-progress";
  if (group === "REVIEW") return "review";
  if (group === "COMPLETED" || group === "CANCELLED") return "done";
  return "todo"; // BACKLOG | UNSTARTED
}

/** Stable demo states matching the legacy COLUMNS labels; used by fixtures and tests. */
export const DEMO_STATES: ProjectState[] = [
  { id: "state-todo", name: "Cần làm (To Do)", color: "#94a3b8", sequence: 1, group: "UNSTARTED", isDefault: true },
  { id: "state-in-progress", name: "Đang làm (In Progress)", color: "#3b82f6", sequence: 2, group: "STARTED", isDefault: false },
  { id: "state-review", name: "Chờ Review (In Review)", color: "#f59e0b", sequence: 3, group: "REVIEW", isDefault: false },
  { id: "state-done", name: "Hoàn thành (Done)", color: "#10b981", sequence: 4, group: "COMPLETED", isDefault: false },
];

export const STATUS_LABELS: Record<IssueStatus, string> = {
  todo: "Cần làm",
  "in-progress": "Đang làm",
  review: "Chờ Review",
  done: "Hoàn thành",
};

export const TYPE_LABELS: Record<Issue["type"], string> = {
  story: "Story",
  task: "Task",
  bug: "Bug",
};

export const PRIORITY_LABELS: Record<Issue["priority"], string> = {
  high: "Cao",
  medium: "Trung bình",
  low: "Thấp",
};

export const PRIORITY_STYLES: Record<Issue["priority"], string> = {
  high: "text-rose-700 bg-rose-50 border-rose-200",
  medium: "text-amber-700 bg-amber-50 border-amber-200",
  low: "text-slate-600 bg-slate-100 border-slate-200",
};

const DAY_MS = 86_400_000;

/** Whole days between today and `endDate` (negative once past). */
export function daysLeft(endDate: string, now: Date = new Date()): number {
  const today = new Date(now);
  today.setHours(0, 0, 0, 0);
  const end = new Date(endDate);
  end.setHours(0, 0, 0, 0);
  return Math.round((end.getTime() - today.getTime()) / DAY_MS);
}

/** An issue with no `dueAt` is never overdue; a finished one is not either. */
export function isOverdue(issue: Pick<Issue, "dueAt" | "status">, now: Date = new Date()): boolean {
  if (!issue.dueAt || issue.status === "done") return false;
  return daysLeft(issue.dueAt, now) < 0;
}

export function formatShortDate(value: string): string {
  return new Date(value).toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit" });
}
