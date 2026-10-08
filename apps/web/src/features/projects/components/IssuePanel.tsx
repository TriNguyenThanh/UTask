import {
  GitBranch,
  GitCommitHorizontal,
  GitPullRequest,
  History,
  MessageSquare,
  Sparkles,
  X,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import type { Epic, IssueDetail, IssueStatus, Sprint } from "@/features/projects/types";
import { ApiError } from "@/lib/api/errors";
import { cn } from "@/lib/utils";

/* ------------------------------------------------------------------ */
/* Helpers                                                             */
/* ------------------------------------------------------------------ */

const STATUS_OPTIONS: { value: IssueStatus; label: string }[] = [
  { value: "todo", label: "Cần làm (To Do)" },
  { value: "in-progress", label: "Đang làm (In Progress)" },
  { value: "review", label: "Chờ Review (In Review)" },
  { value: "done", label: "Hoàn thành (Done)" },
];

const PRIORITY_LABELS: Record<string, string> = {
  high: "Cao (High)",
  medium: "Trung bình (Medium)",
  low: "Thấp (Low)",
};

const PRIORITY_STYLES: Record<string, string> = {
  high: "text-rose-600 bg-rose-50 border-rose-200",
  medium: "text-amber-700 bg-amber-50 border-amber-200",
  low: "text-slate-600 bg-slate-100 border-slate-200",
};

function formatDayRange(sprint: Sprint): string {
  const start = new Date(sprint.startDate).toLocaleDateString("vi-VN", {
    day: "2-digit",
    month: "2-digit",
  });
  const end = new Date(sprint.endDate).toLocaleDateString("vi-VN", {
    day: "2-digit",
    month: "2-digit",
  });
  return `${start} - ${end}`;
}

function formatDateTime(value: string): string {
  return new Date(value).toLocaleString("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function GitLinkBadge({ link }: { link: IssueDetail["gitLinks"][number] }) {
  const Icon =
    link.kind === "branch" ? GitBranch : link.kind === "pr" ? GitPullRequest : GitCommitHorizontal;
  const kindLabel =
    link.kind === "branch" ? "Nhánh" : link.kind === "pr" ? "Pull Request" : "Commit";
  return (
    <span
      className="inline-flex max-w-full items-center gap-1.5 rounded-md border border-outline-subtle bg-card px-2 py-1 font-mono text-xs text-primary"
      title={`${kindLabel}: ${link.label}`}
    >
      <Icon className="size-3.5 shrink-0" aria-hidden />
      <span className="truncate">{link.label}</span>
    </span>
  );
}

function PanelSkeleton() {
  return (
    <div className="space-y-5 p-6" role="status" aria-label="Đang tải chi tiết issue">
      <Skeleton className="h-6 w-3/4" />
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-3 lg:col-span-2">
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-32 w-full" />
          <Skeleton className="h-40 w-full" />
        </div>
        <div className="space-y-3">
          <Skeleton className="h-5 w-36" />
          <Skeleton className="h-8 w-full" />
          <Skeleton className="h-8 w-full" />
          <Skeleton className="h-8 w-full" />
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Subtask checklist — toggle is local-only, never mutated to server   */
/* ------------------------------------------------------------------ */

function SubtaskList({
  subtasks,
  onToggle,
  readOnly,
}: {
  subtasks: { id: string; title: string; done: boolean }[];
  onToggle: (id: string) => void;
  /** Instructors see the checklist but cannot change it, not even locally. */
  readOnly: boolean;
}) {
  const doneCount = subtasks.filter((subtask) => subtask.done).length;
  const percent = subtasks.length > 0 ? Math.round((doneCount / subtasks.length) * 100) : 0;

  return (
    <div className="space-y-3">
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
        <div
          className="h-full rounded-full bg-emerald-500 transition-all"
          style={{ width: `${percent}%` }}
        />
      </div>
      <ul className="divide-y divide-outline-subtle/60 overflow-hidden rounded-lg border border-outline-subtle bg-card text-xs">
        {subtasks.map((subtask) => (
          <li key={subtask.id} className="flex items-center justify-between gap-2.5 p-2.5 hover:bg-muted/50">
            <label className="flex min-w-0 flex-1 cursor-pointer items-center gap-2.5">
              <input
                type="checkbox"
                checked={subtask.done}
                disabled={readOnly}
                onChange={() => onToggle(subtask.id)}
                className="size-4 shrink-0 cursor-pointer rounded accent-primary disabled:cursor-not-allowed"
              />
              <span className={cn("truncate", subtask.done && "text-muted-foreground line-through")}>
                {subtask.title}
              </span>
            </label>
            <span
              className={cn(
                "shrink-0 rounded border px-2 py-0.5 text-[10px] font-semibold",
                subtask.done
                  ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                  : "border-outline-subtle bg-muted text-muted-foreground",
              )}
            >
              {subtask.done ? "Hoàn thành" : "Cần làm"}
            </span>
          </li>
        ))}
      </ul>
      <p className="text-[11px] text-muted-foreground">
        {readOnly
          ? "Bạn chỉ có quyền xem nhiệm vụ con."
          : "Đánh dấu chỉ áp dụng cho phiên xem hiện tại."}
      </p>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Issue panel (large modal, Stitch 12)                                */
/* ------------------------------------------------------------------ */

export function IssuePanel({
  projectId,
  projectName,
  issueKey,
  epics,
  sprints,
  detail,
  isLoading,
  error,
  canBreakdownWithAI,
  aiKeyMissing,
  readOnly = false,
  onClose,
}: {
  projectId: string;
  projectName: string;
  issueKey: string;
  epics: Epic[];
  sprints: Sprint[];
  detail: IssueDetail | undefined;
  isLoading: boolean;
  error: unknown;
  /** Leader + AI key configured (API itself not implemented → disabled CTA). */
  canBreakdownWithAI: boolean;
  /** Leader but AI key missing → link to Project Settings. */
  aiKeyMissing: boolean;
  /** Instructor view: no subtask toggling, and a note that comments are view-only. */
  readOnly?: boolean;
  onClose: () => void;
}) {
  const panelRef = useRef<HTMLDivElement | null>(null);
  const closeButtonRef = useRef<HTMLButtonElement | null>(null);
  /** Local-only subtask overrides keyed by subtask id. */
  const [localDone, setLocalDone] = useState<Record<string, boolean>>({});

  /* Focus X button on open; restore focus to the issue card on close. */
  useEffect(() => {
    const previouslyFocused = document.activeElement as HTMLElement | null;
    closeButtonRef.current?.focus();
    return () => {
      previouslyFocused?.focus?.();
    };
  }, []);

  /* Escape closes; Tab is trapped inside the panel. */
  useEffect(() => {
    function handleKeyDown(event: globalThis.KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== "Tab") return;
      const panel = panelRef.current;
      if (!panel) return;
      const focusables = panel.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
      );
      if (focusables.length === 0) return;
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  /* Reset local checkbox state when a different issue is opened. */
  useEffect(() => {
    setLocalDone({});
  }, [issueKey]);

  const subtasks = useMemo(() => {
    if (!detail) return [];
    return detail.subtasks.map((subtask) => ({
      ...subtask,
      done: localDone[subtask.id] ?? subtask.done,
    }));
  }, [detail, localDone]);

  function toggleSubtask(id: string) {
    setLocalDone((prev) => ({
      ...prev,
      [id]: !(prev[id] ?? detail?.subtasks.find((s) => s.id === id)?.done ?? false),
    }));
  }

  const issue = detail?.issue;
  const epic =
    issue?.epicId != null
      ? (epics.find((candidate) => candidate.id === issue.epicId) ?? null)
      : null;
  const sprint =
    issue?.sprintId != null
      ? (sprints.find((candidate) => candidate.id === issue.sprintId) ?? null)
      : null;
  const isNotFound = error instanceof ApiError && error.status === 404;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 sm:p-6 md:p-8"
      onClick={onClose}
      data-testid="issue-panel-overlay"
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={`Chi tiết issue ${issueKey}`}
        className="flex max-h-[92vh] w-full max-w-5xl flex-col overflow-hidden rounded-xl border bg-card"
        onClick={(event) => event.stopPropagation()}
      >
        {/* Header: breadcrumb + close */}
        <div className="flex shrink-0 items-center justify-between gap-3 border-b px-6 py-3.5">
          <nav className="flex min-w-0 flex-wrap items-center gap-2 text-xs font-medium text-muted-foreground">
            <span className="truncate">{projectName}</span>
            <span aria-hidden>/</span>
            <span className="truncate">{sprint?.name ?? "Sprint"}</span>
            <span aria-hidden>/</span>
            <span className="rounded bg-primary/10 px-2 py-0.5 font-mono font-bold text-primary">
              {issueKey}
            </span>
          </nav>
          <Button
            ref={closeButtonRef}
            variant="ghost"
            size="icon-sm"
            onClick={onClose}
            aria-label="Đóng chi tiết issue"
            title="Đóng (Esc)"
          >
            <X aria-hidden />
          </Button>
        </div>

        {isLoading ? <PanelSkeleton /> : null}

        {!isLoading && isNotFound ? (
          <div className="flex flex-col items-center gap-3 px-6 py-14 text-center">
            <p className="text-sm font-semibold">Issue không tồn tại</p>
            <p className="text-sm text-muted-foreground">
              Không tìm thấy issue {issueKey} trong dự án này.
            </p>
            <Button variant="outline" size="sm" onClick={onClose}>
              Đóng
            </Button>
          </div>
        ) : null}

        {!isLoading && !isNotFound && error ? (
          <div className="p-6 text-sm text-muted-foreground">
            Không tải được chi tiết issue. Đóng và thử lại.
          </div>
        ) : null}

        {!isLoading && !error && detail && issue ? (
          <div className="flex-1 overflow-y-auto p-6">
            {/* Title + type + priority */}
            <div className="mb-5">
              <div className="mb-2 flex flex-wrap items-center gap-2">
                <span className="rounded border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[11px] font-bold text-emerald-700">
                  {issue.type === "story" ? "Story" : issue.type === "task" ? "Task" : "Bug"}
                </span>
                {sprint ? (
                  <span className="text-xs text-muted-foreground">
                    • Sprint:{" "}
                    <span className="font-semibold text-foreground">{sprint.name}</span>{" "}
                    ({formatDayRange(sprint)})
                  </span>
                ) : null}
                <span
                  className={cn(
                    "rounded border px-1.5 py-0.5 text-[11px] font-semibold",
                    PRIORITY_STYLES[issue.priority],
                  )}
                >
                  Ưu tiên: {PRIORITY_LABELS[issue.priority]}
                </span>
              </div>
              <h2 className="text-xl font-bold leading-snug tracking-tight md:text-2xl">
                {issue.title}
              </h2>
            </div>

            <div className="grid items-start gap-8 lg:grid-cols-12">
              {/* Left column */}
              <div className="space-y-6 lg:col-span-8">
                {/* Status — read-only until the API supports updates */}
                <div>
                  <label
                    htmlFor="issue-status-select"
                    className="text-xs font-semibold text-muted-foreground"
                  >
                    Trạng thái
                  </label>
                  <select
                    id="issue-status-select"
                    value={issue.status}
                    disabled
                    title="Cập nhật trạng thái sẽ khả dụng khi API hỗ trợ"
                    className="mt-1.5 w-full max-w-xs cursor-not-allowed rounded-md border border-outline-subtle bg-muted px-3 py-1.5 text-xs font-medium text-muted-foreground"
                  >
                    {STATUS_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </div>

                {/* Description + acceptance criteria */}
                <section className="space-y-3">
                  <h3 className="text-xs font-bold uppercase tracking-wider">
                    Mô tả công việc (Description)
                  </h3>
                  <div className="space-y-3.5 rounded-lg border border-outline-subtle bg-muted/40 p-4 text-[13px] leading-relaxed">
                    <p>{detail.description}</p>
                    <div className="border-t border-outline-subtle pt-3">
                      <div className="mb-2 text-[11px] font-bold uppercase tracking-wider text-primary">
                        Tiêu chí nghiệm thu (Acceptance Criteria)
                      </div>
                      <ul className="space-y-2 text-xs text-muted-foreground">
                        {detail.acceptanceCriteria.map((criterion) => (
                          <li key={criterion} className="flex items-start gap-2">
                            <span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-primary" />
                            <span>{criterion}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  </div>
                </section>

                {/* Subtasks */}
                <section className="space-y-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <h3 className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider">
                      Nhiệm vụ con (Sub-tasks)
                      <span className="rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-xs font-semibold text-emerald-700">
                        {subtasks.filter((s) => s.done).length}/{subtasks.length} hoàn thành
                      </span>
                    </h3>
                    {canBreakdownWithAI ? (
                      <Button
                        variant="outline"
                        size="xs"
                        disabled
                        title="Chưa có API sinh sub-tasks bằng AI"
                      >
                        <Sparkles aria-hidden />
                        AI Tự động sinh Sub-tasks
                      </Button>
                    ) : aiKeyMissing ? (
                      <Button asChild variant="link" size="xs" title="Cấu hình AI key tại Project Settings">
                        <Link to={`/projects/${projectId}/settings`}>
                          Cấu hình AI key tại Project Settings
                        </Link>
                      </Button>
                    ) : null}
                  </div>
                  {subtasks.length > 0 ? (
                    <SubtaskList subtasks={subtasks} onToggle={toggleSubtask} readOnly={readOnly} />
                  ) : (
                    <p className="text-xs text-muted-foreground">Chưa có nhiệm vụ con nào.</p>
                  )}
                </section>

                {/* Comments */}
                <section className="space-y-3 border-t border-outline-subtle pt-4">
                  <h3 className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider">
                    <MessageSquare className="size-4" aria-hidden />
                    Bình luận (Comments)
                  </h3>
                  {readOnly ? (
                    <p className="text-xs text-muted-foreground">
                      Bạn đang xem bình luận. Gửi bình luận sẽ khả dụng khi có hợp đồng API cho phản hồi
                      của giảng viên.
                    </p>
                  ) : null}
                  {detail.comments.length === 0 ? (
                    <p className="text-xs text-muted-foreground">Chưa có bình luận nào.</p>
                  ) : (
                    <ul className="space-y-2.5">
                      {detail.comments.map((comment) => (
                        <li
                          key={comment.id}
                          className="rounded-lg border border-outline-subtle bg-muted/40 p-3"
                        >
                          <div className="flex items-center justify-between gap-2">
                            <div className="flex min-w-0 items-center gap-2">
                              <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-primary/10 text-[10px] font-bold text-primary">
                                {comment.authorInitials}
                              </span>
                              <span className="truncate text-xs font-bold">
                                {comment.authorName}
                              </span>
                            </div>
                            <time dateTime={comment.createdAt} className="shrink-0 text-[11px] text-muted-foreground">
                              {formatDateTime(comment.createdAt)}
                            </time>
                          </div>
                          <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">
                            {comment.body}
                          </p>
                        </li>
                      ))}
                    </ul>
                  )}
                </section>

                {/* History */}
                <section className="space-y-3 border-t border-outline-subtle pt-4">
                  <h3 className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider">
                    <History className="size-4" aria-hidden />
                    Lịch sử (History)
                  </h3>
                  {detail.history.length === 0 ? (
                    <p className="text-xs text-muted-foreground">Chưa có hoạt động nào.</p>
                  ) : (
                    <ul className="space-y-2">
                      {detail.history.map((entry) => (
                        <li
                          key={entry.id}
                          className="flex items-start justify-between gap-3 rounded-md border border-outline-subtle bg-card px-3 py-2"
                        >
                          <span className="text-xs">
                            <span className="font-semibold">{entry.actorName}</span>{" "}
                            <span className="text-muted-foreground">{entry.summary}</span>
                          </span>
                          <time dateTime={entry.at} className="shrink-0 text-[11px] text-muted-foreground">
                            {formatDateTime(entry.at)}
                          </time>
                        </li>
                      ))}
                    </ul>
                  )}
                </section>
              </div>

              {/* Right column: meta grid */}
              <div className="space-y-5 border-outline-subtle lg:col-span-4 lg:border-l lg:pl-6">
                <h3 className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                  Chi tiết &amp; Thuộc tính
                </h3>
                <dl className="space-y-3 text-xs">
                  <div className="flex items-center justify-between gap-2 border-b border-outline-subtle/60 pb-2">
                    <dt className="shrink-0 text-muted-foreground">Mức độ ưu tiên</dt>
                    <dd
                      className={cn(
                        "rounded border px-2 py-0.5 text-[11px] font-semibold",
                        PRIORITY_STYLES[issue.priority],
                      )}
                    >
                      {PRIORITY_LABELS[issue.priority]}
                    </dd>
                  </div>
                  <div className="flex items-center justify-between gap-2 border-b border-outline-subtle/60 pb-2">
                    <dt className="shrink-0 text-muted-foreground">Người thực hiện</dt>
                    <dd className="flex min-w-0 items-center gap-1.5">
                      <span className="flex size-5 shrink-0 items-center justify-center rounded-full bg-primary/10 text-[10px] font-bold text-primary">
                        {issue.assignee?.initials ?? "?"}
                      </span>
                      <span className="truncate font-medium">
                        {issue.assignee?.displayName ?? "Chưa gán"}
                      </span>
                    </dd>
                  </div>
                  <div className="flex items-center justify-between gap-2 border-b border-outline-subtle/60 pb-2">
                    <dt className="shrink-0 text-muted-foreground">Người báo cáo</dt>
                    <dd className="truncate font-medium">{detail.reporterName}</dd>
                  </div>
                  <div className="flex items-center justify-between gap-2 border-b border-outline-subtle/60 pb-2">
                    <dt className="shrink-0 text-muted-foreground">Story Points</dt>
                    <dd className="rounded border border-outline-subtle bg-muted px-2 py-0.5 font-bold">
                      {issue.storyPoints}
                    </dd>
                  </div>
                  <div className="flex items-center justify-between gap-2 border-b border-outline-subtle/60 pb-2">
                    <dt className="shrink-0 text-muted-foreground">Epic</dt>
                    <dd className="min-w-0 truncate">
                      {epic ? (
                        <span
                          className="rounded border px-2 py-0.5 text-[11px] font-semibold"
                          style={{
                            backgroundColor: `${epic.color}1a`,
                            borderColor: `${epic.color}55`,
                            color: epic.color,
                          }}
                        >
                          {epic.name}
                        </span>
                      ) : (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </dd>
                  </div>
                  <div className="flex items-center justify-between gap-2">
                    <dt className="shrink-0 text-muted-foreground">Sprint</dt>
                    <dd className="min-w-0 truncate font-medium">
                      {sprint ? sprint.name : "Product Backlog"}
                    </dd>
                  </div>
                </dl>

                {/* Git links */}
                <section className="space-y-2.5 rounded-lg border border-outline-subtle bg-muted/40 p-3.5">
                  <h3 className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">
                    GitHub Development
                  </h3>
                  {detail.gitLinks.length === 0 ? (
                    <p className="text-xs text-muted-foreground">Chưa có liên kết mã nguồn.</p>
                  ) : (
                    <div className="flex flex-wrap gap-1.5">
                      {detail.gitLinks.map((link) => (
                        <GitLinkBadge key={`${link.kind}-${link.label}`} link={link} />
                      ))}
                    </div>
                  )}
                </section>

                <Button variant="outline" size="sm" className="w-full" onClick={onClose}>
                  Quay lại Bảng công việc Sprint
                </Button>
              </div>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}