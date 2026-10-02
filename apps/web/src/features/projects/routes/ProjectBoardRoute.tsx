import { Plus, Search, Zap } from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";
import { useSearchParams } from "react-router-dom";

import { EmptyState } from "@/components/feedback/EmptyState";
import { Button } from "@/components/ui/button";
import { IssuePanel } from "@/features/projects/components/IssuePanel";
import type { Issue, IssueStatus, Sprint } from "@/features/projects/types";
import { useProjectWorkspaceContext } from "@/features/projects/routes/ProjectWorkspaceLayout";
import {
  aiRequiresKey,
  canBreakdownTaskWithAI,
  canCreateTask,
  type ProjectPermissionContext,
} from "@/lib/permissions";
import {
  useIssueDetail,
  useProjectAiSettings,
} from "@/lib/query/studentFlowHooks";
import { cn } from "@/lib/utils";

/* ------------------------------------------------------------------ */
/* Board primitives                                                   */
/* ------------------------------------------------------------------ */

const COLUMNS: { status: IssueStatus; label: string; dotClass: string }[] = [
  { status: "todo", label: "Cần làm (To Do)", dotClass: "bg-slate-400" },
  { status: "in-progress", label: "Đang làm (In Progress)", dotClass: "bg-blue-500" },
  { status: "review", label: "Chờ Review (In Review)", dotClass: "bg-amber-500" },
  { status: "done", label: "Hoàn thành (Done)", dotClass: "bg-emerald-600" },
];

const TYPE_LABELS: Record<Issue["type"], string> = {
  story: "Story",
  task: "Task",
  bug: "Bug",
};

const PRIORITY_LABELS: Record<Issue["priority"], string> = {
  high: "Cao",
  medium: "Trung bình",
  low: "Thấp",
};

const PRIORITY_STYLES: Record<Issue["priority"], string> = {
  high: "text-rose-600 bg-rose-50 border-rose-200",
  medium: "text-amber-700 bg-amber-50 border-amber-200",
  low: "text-slate-600 bg-slate-100 border-slate-200",
};

/** Days between today and the end date, rounded to whole days. */
function daysLeft(endDate: string): number {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const end = new Date(endDate);
  end.setHours(0, 0, 0, 0);
  return Math.round((end.getTime() - today.getTime()) / 86_400_000);
}

function formatShortDate(value: string): string {
  return new Date(value).toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit" });
}

interface BoardFilters {
  search: string;
  mineOnly: boolean;
  prOnly: boolean;
  bugsOnly: boolean;
}

function matchesFilters(issue: Issue, filters: BoardFilters): boolean {
  if (filters.mineOnly && !issue.isMine) return false;
  if (filters.prOnly && !issue.hasPullRequest) return false;
  if (filters.bugsOnly && issue.type !== "bug") return false;
  const needle = filters.search.trim().toLowerCase();
  if (needle && !`${issue.key} ${issue.title}`.toLowerCase().includes(needle)) return false;
  return true;
}

/* ------------------------------------------------------------------ */
/* Issue card + column                                                 */
/* ------------------------------------------------------------------ */

function IssueCard({
  issue,
  onOpen,
}: {
  issue: Issue;
  onOpen: (key: string) => void;
}) {
  const done = issue.status === "done";
  return (
    <button
      type="button"
      onClick={() => onOpen(issue.key)}
      className={cn(
        "w-full rounded-md border border-outline-subtle bg-card p-3 text-left transition-all hover:border-primary/40 hover:shadow-sm focus-visible:border-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50",
        done && "opacity-90",
      )}
      aria-label={`Mở chi tiết issue ${issue.key}: ${issue.title}`}
    >
      <div className="mb-1.5 flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-1.5">
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
        {issue.hasPullRequest ? (
          <span
            className="inline-flex shrink-0 items-center gap-1 rounded border border-emerald-200 bg-emerald-50 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-700"
            title="Có Pull Request"
          >
            <span className="size-1.5 rounded-full bg-emerald-600" aria-hidden />
            PR
          </span>
        ) : null}
      </div>
      <p
        className={cn("mb-3 text-xs font-medium leading-relaxed", done && "text-muted-foreground")}
      >
        {issue.title}
      </p>
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
    </button>
  );
}

function BoardColumn({
  column,
  issues,
  onOpenIssue,
}: {
  column: (typeof COLUMNS)[number];
  issues: Issue[];
  onOpenIssue: (key: string) => void;
}) {
  const points = issues.reduce((sum, issue) => sum + issue.storyPoints, 0);
  return (
    <section
      className="flex max-h-full w-72 min-w-[18rem] flex-1 flex-col rounded-lg border border-outline-subtle/60 bg-muted/50 p-3"
      aria-label={column.label}
    >
      <div className="mb-2 flex shrink-0 items-center justify-between border-b border-outline-subtle/60 pb-2.5">
        <div className="flex min-w-0 items-center gap-2">
          <span className={cn("size-2 shrink-0 rounded-full", column.dotClass)} aria-hidden />
          <h2 className="truncate text-xs font-bold uppercase tracking-wide">{column.label}</h2>
          <span className="rounded-full border border-outline-subtle bg-card px-1.5 py-0.5 font-mono text-[11px] font-medium text-muted-foreground">
            {issues.length}
          </span>
        </div>
        <span className="shrink-0 text-[11px] font-medium text-muted-foreground">
          {points} pts
        </span>
      </div>
      <div className="flex-1 space-y-2.5 overflow-y-auto">
        {issues.length === 0 ? (
          <p className="rounded-md border border-dashed border-outline-subtle px-2 py-4 text-center text-[11px] text-muted-foreground">
            Không có issue
          </p>
        ) : (
          issues.map((issue) => (
            <IssueCard key={issue.id} issue={issue} onOpen={onOpenIssue} />
          ))
        )}
      </div>
    </section>
  );
}

/* ------------------------------------------------------------------ */
/* Toolbar                                                             */
/* ------------------------------------------------------------------ */

function FilterChip({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50",
        active
          ? "bg-primary text-white"
          : "border border-outline-subtle bg-card text-muted-foreground hover:bg-muted hover:text-foreground",
      )}
    >
      {children}
    </button>
  );
}

function BoardToolbar({
  sprint,
  filters,
  onFiltersChange,
  canCreate,
}: {
  sprint: Sprint | null;
  filters: BoardFilters;
  onFiltersChange: (next: BoardFilters) => void;
  canCreate: boolean;
}) {
  const remainingDays = sprint ? daysLeft(sprint.endDate) : null;
  return (
    <section className="flex flex-wrap items-center justify-between gap-3 border-b border-outline-subtle bg-background px-6 py-3">
      <div className="flex flex-wrap items-center gap-2.5">
        {sprint ? (
          <div className="mr-1 flex flex-wrap items-center gap-2">
            <Zap className="size-4 text-primary" aria-hidden />
            <span className="text-sm font-bold tracking-tight">{sprint.name}</span>
            <span className="font-mono text-xs text-muted-foreground">
              ({formatShortDate(sprint.startDate)} - {formatShortDate(sprint.endDate)})
            </span>
            {remainingDays !== null && remainingDays >= 0 ? (
              <span className="inline-flex items-center gap-1 rounded-full border border-emerald-200 bg-emerald-100 px-2 py-0.5 text-[11px] font-medium text-emerald-800">
                <span className="size-1.5 rounded-full bg-emerald-600" aria-hidden />
                Còn {remainingDays} ngày
              </span>
            ) : null}
          </div>
        ) : null}
        <div className="hidden h-4 w-px bg-outline-subtle sm:block" aria-hidden />
        <div className="flex flex-wrap items-center gap-1.5">
          <FilterChip
            active={filters.mineOnly}
            onClick={() => onFiltersChange({ ...filters, mineOnly: !filters.mineOnly })}
          >
            Chỉ việc của tôi
          </FilterChip>
          <FilterChip
            active={filters.prOnly}
            onClick={() => onFiltersChange({ ...filters, prOnly: !filters.prOnly })}
          >
            Có Pull Request
          </FilterChip>
          <FilterChip
            active={filters.bugsOnly}
            onClick={() => onFiltersChange({ ...filters, bugsOnly: !filters.bugsOnly })}
          >
            Chỉ lỗi (Bugs)
          </FilterChip>
        </div>
      </div>

      <div className="ml-auto flex items-center gap-2">
        <div className="relative">
          <Search
            className="absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
            aria-hidden
          />
          <input
            type="search"
            value={filters.search}
            onChange={(event) => onFiltersChange({ ...filters, search: event.target.value })}
            placeholder="Tìm kiếm issue..."
            aria-label="Tìm kiếm issue"
            className="h-8 w-44 rounded-md border border-outline-subtle bg-card pl-8 pr-3 text-xs transition-all placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary lg:w-52"
          />
        </div>
        {canCreate ? (
          <Button size="sm" disabled title="Chưa có API tạo issue" aria-label="Tạo issue (chưa khả dụng)">
            <Plus aria-hidden />
            Tạo Issue
          </Button>
        ) : null}
      </div>
    </section>
  );
}

/* ------------------------------------------------------------------ */
/* Route component                                                     */
/* ------------------------------------------------------------------ */

export function Component() {
  const { projectId, workspace } = useProjectWorkspaceContext();
  const [searchParams, setSearchParams] = useSearchParams();
  const [filters, setFilters] = useState<BoardFilters>({
    search: "",
    mineOnly: false,
    prOnly: false,
    bugsOnly: false,
  });

  const issueKey = searchParams.get("issue");
  const issueQuery = useIssueDetail(projectId, issueKey);
  const aiSettingsQuery = useProjectAiSettings(projectId);

  function openIssue(key: string) {
    const next = new URLSearchParams(searchParams);
    next.set("issue", key);
    setSearchParams(next, { preventScrollReset: true });
  }

  function closeIssue() {
    const next = new URLSearchParams(searchParams);
    next.delete("issue");
    setSearchParams(next, { preventScrollReset: true });
  }

  const aiEnabled = aiSettingsQuery.data?.ai.keyConfigured ?? false;
  const permissionCtx: ProjectPermissionContext = {
    role: workspace.myRole,
    aiEnabled,
  };

  const sprint = useMemo(() => {
    return workspace.sprints.find((candidate) => candidate.state === "active") ?? null;
  }, [workspace]);

  const sprintIssues = useMemo(() => {
    const sprintId = sprint?.id ?? null;
    return workspace.issues.filter((issue) => issue.sprintId === sprintId);
  }, [workspace, sprint]);

  const visibleIssues = useMemo(
    () => sprintIssues.filter((issue) => matchesFilters(issue, filters)),
    [sprintIssues, filters],
  );

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <BoardToolbar
        sprint={sprint}
        filters={filters}
        onFiltersChange={setFilters}
        canCreate={permissionCtx !== null && canCreateTask(permissionCtx)}
      />

      {sprint === null ? (
        <div className="p-6">
          <EmptyState
            title="Chưa có Sprint đang chạy"
            description="Sprint hiện chưa được khởi tạo. Vui lòng liên hệ Trưởng nhóm để khởi tạo Sprint cho dự án."
          />
        </div>
      ) : visibleIssues.length === 0 ? (
        <div className="p-6">
          <EmptyState
            title="Không có issue khớp bộ lọc"
            description="Thử bỏ bộ lọc hoặc từ khóa tìm kiếm để xem toàn bộ issue của Sprint."
            action={
              <Button
                variant="outline"
                size="sm"
                onClick={() =>
                  setFilters({ search: "", mineOnly: false, prOnly: false, bugsOnly: false })
                }
              >
                Xóa bộ lọc
              </Button>
            }
          />
        </div>
      ) : (
        <div className="min-h-0 flex-1 overflow-x-auto bg-background p-6">
          <div className="flex h-full items-start gap-4">
            {COLUMNS.map((column) => (
              <BoardColumn
                key={column.status}
                column={column}
                issues={visibleIssues.filter((issue) => issue.status === column.status)}
                onOpenIssue={openIssue}
              />
            ))}
          </div>
        </div>
      )}

      {/* Panel is a sibling overlay: the board above never remounts, so
          filter and scroll state survive panel open/close. */}
      {issueKey !== null ? (
        <IssuePanel
          projectId={projectId}
          projectName={workspace.name}
          issueKey={issueKey}
          epics={workspace.epics}
          sprints={workspace.sprints}
          detail={issueQuery.data}
          isLoading={issueQuery.isPending}
          error={issueQuery.error}
          canBreakdownWithAI={
            permissionCtx !== null && canBreakdownTaskWithAI(permissionCtx)
          }
          aiKeyMissing={
            permissionCtx !== null && aiRequiresKey(permissionCtx)
          }
          onClose={closeIssue}
        />
      ) : null}
    </div>
  );
}