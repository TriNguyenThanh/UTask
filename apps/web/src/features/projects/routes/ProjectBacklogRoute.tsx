import {
  BookOpen,
  Bug,
  Calculator,
  CheckCircle2,
  ChevronLeft,
  CircleDot,
  GitPullRequest,
  Plus,
  Search,
  Sparkles,
  SquareCheckBig,
  UserRound,
  Zap,
} from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { EmptyState } from "@/components/feedback/EmptyState";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import type {
  Issue,
  IssueType,
  Sprint,
} from "@/features/projects/types";
import { useProjectWorkspaceContext } from "@/features/projects/routes/ProjectWorkspaceLayout";
import {
  aiRequiresKey,
  canCreateTask,
  canManageSprint,
  projectPermissionContext,
  type ProjectPermissionContext,
} from "@/lib/permissions";
import { useProjectAiSettings } from "@/lib/query/studentFlowHooks";
import { cn } from "@/lib/utils";

/* ------------------------------------------------------------------ */
/* Presentation helpers                                                */
/* ------------------------------------------------------------------ */

const typeIcons: Record<IssueType, typeof BookOpen> = {
  story: BookOpen,
  task: SquareCheckBig,
  bug: Bug,
};

const typeLabels: Record<IssueType, string> = {
  story: "Story",
  task: "Task",
  bug: "Bug",
};

const typeColors: Record<IssueType, string> = {
  story: "bg-emerald-600",
  task: "bg-blue-600",
  bug: "bg-rose-600",
};

const priorityConfig: Record<Issue["priority"], { label: string; badge: string }> = {
  high: { label: "Ưu tiên Cao", badge: "bg-rose-50 text-rose-700 border-rose-200" },
  medium: { label: "Ưu tiên Trung bình", badge: "bg-amber-50 text-amber-700 border-amber-200" },
  low: { label: "Ưu tiên Thấp", badge: "bg-slate-100 text-slate-600 border-slate-200" },
};

const statusLabels: Record<Issue["status"], string> = {
  todo: "Cần làm",
  "in-progress": "Đang làm",
  review: "Chờ Review",
  done: "Hoàn thành",
};

function sprintDateRange(sprint: Sprint): string {
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

function sprintDaysLeft(sprint: Sprint): number {
  const end = new Date(sprint.endDate);
  const now = new Date();
  return Math.ceil((end.getTime() - now.getTime()) / 86_400_000);
}

/* ------------------------------------------------------------------ */
/* Issue row                                                           */
/* ------------------------------------------------------------------ */

function IssueRow({
  projectId,
  issue,
  onOpenIssue,
}: {
  projectId: string;
  issue: Issue;
  onOpenIssue: (projectId: string, issueKey: string) => void;
}) {
  const TypeIcon = typeIcons[issue.type];
  const priority = priorityConfig[issue.priority];

  return (
    <div className="flex items-center justify-between gap-3 rounded px-3 py-2.5 text-sm transition-colors hover:bg-muted/50">
      <div className="flex min-w-0 items-center gap-3 pr-4">
        <span
          className={cn(
            "flex size-3.5 shrink-0 items-center justify-center rounded text-white",
            typeColors[issue.type],
          )}
          title={typeLabels[issue.type]}
        >
          <TypeIcon className="size-2.5" aria-hidden />
        </span>
        <button
          type="button"
          onClick={() => onOpenIssue(projectId, issue.key)}
          className="shrink-0 text-xs font-semibold text-primary hover:underline focus-visible:underline focus-visible:outline-none"
          aria-label={`Mở issue ${issue.key}: ${issue.title}`}
        >
          {issue.key}
        </button>
        <button
          type="button"
          onClick={() => onOpenIssue(projectId, issue.key)}
          className="min-w-0 truncate text-left text-xs font-medium hover:text-primary focus-visible:underline focus-visible:outline-none"
          aria-label={`Mở issue ${issue.key}: ${issue.title}`}
        >
          {issue.title}
        </button>
        {issue.hasPullRequest ? (
          <span
            className="inline-flex shrink-0 items-center gap-1 rounded bg-indigo-50 px-2 py-0.5 text-[10px] font-semibold text-indigo-700"
            title="Issue có Pull Request"
          >
            <GitPullRequest className="size-3" aria-hidden />
            PR
          </span>
        ) : null}
      </div>
      <div className="flex shrink-0 items-center gap-2.5">
        <span
          className="hidden rounded-md border px-2 py-0.5 text-[10px] font-semibold sm:inline-flex"
          title={priority.label}
        >
          <span className={cn("rounded px-1", priority.badge)}>
            {issue.priority === "high" ? "Cao" : issue.priority === "medium" ? "TB" : "Thấp"}
          </span>
        </span>
        <span
          className="rounded-full bg-muted px-2 py-0.5 text-xs font-bold"
          title="Story Points"
        >
          {issue.storyPoints}
        </span>
        {issue.assignee ? (
          <span
            className="flex size-6 items-center justify-center rounded-full bg-primary text-[10px] font-semibold text-primary-foreground"
            title={issue.assignee.displayName}
          >
            {issue.assignee.initials}
          </span>
        ) : (
          <span
            className="flex size-6 items-center justify-center rounded-full border border-dashed text-muted-foreground"
            title="Chưa phân công"
          >
            <UserRound className="size-3" aria-hidden />
          </span>
        )}
        <span className="hidden w-20 text-center text-[11px] font-medium text-muted-foreground md:inline-flex md:items-center">
          {statusLabels[issue.status]}
          {issue.status === "done" ? (
            <CheckCircle2 className="ml-1 size-3 text-emerald-600" aria-hidden />
          ) : null}
        </span>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Sprint section                                                      */
/* ------------------------------------------------------------------ */

function SprintSection({
  projectId,
  sprint,
  issues,
  onOpenIssue,
  canComplete,
}: {
  projectId: string;
  sprint: Sprint;
  issues: Issue[];
  onOpenIssue: (projectId: string, issueKey: string) => void;
  canComplete: boolean;
}) {
  const [collapsed, setCollapsed] = useState(false);
  const percent =
    sprint.totalPoints > 0
      ? Math.round((sprint.completedPoints / sprint.totalPoints) * 100)
      : 0;
  const daysLeft = sprintDaysLeft(sprint);
  const isActive = sprint.state === "active";

  return (
    <section className="mb-6">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2 border-b pb-2">
        <div className="flex flex-wrap items-center gap-2.5">
          <button
            type="button"
            onClick={() => setCollapsed(!collapsed)}
            aria-expanded={!collapsed}
            aria-label={collapsed ? "Mở rộng danh sách issue" : "Thu gọn danh sách issue"}
            className="rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <ChevronLeft
              className={cn(
                "size-4 transition-transform",
                collapsed ? "-rotate-90" : "rotate-[-90deg]",
              )}
              aria-hidden
            />
          </button>
          <h2 className="text-sm font-bold">{sprint.name}</h2>
          <span className="text-xs font-medium text-muted-foreground">
            ({sprintDateRange(sprint)})
          </span>
          {isActive ? (
            <Badge className="gap-1 bg-emerald-100 text-[11px] font-semibold text-emerald-800 hover:bg-emerald-100">
              <span className="size-1.5 rounded-full bg-emerald-600" aria-hidden />
              Đang diễn ra
            </Badge>
          ) : (
            <Badge variant="secondary" className="text-[11px] font-semibold">
              Kế hoạch
            </Badge>
          )}
          {isActive && daysLeft >= 0 ? (
            <Badge variant="secondary" className="text-[11px] font-medium">
              Còn {daysLeft} ngày
            </Badge>
          ) : null}
          {sprint.goal ? (
            <span className="border-l pl-2.5 text-xs italic text-muted-foreground">
              Mục tiêu: {sprint.goal}
            </span>
          ) : null}
        </div>
        <div className="flex items-center gap-3">
          <span className="text-[11px] font-bold text-muted-foreground">
            {sprint.completedPoints}/{sprint.totalPoints} SP
          </span>
          {canComplete && isActive ? (
            <Button
              variant="outline"
              size="xs"
              disabled
              title="Chưa có API hoàn thành Sprint"
              className="text-xs"
            >
              <CheckCircle2 className="size-3.5" aria-hidden />
              Hoàn thành Sprint
            </Button>
          ) : null}
        </div>
      </div>

      {!collapsed ? (
        <>
          {/* Progress bar */}
          <div className="mb-2 flex items-center gap-3 px-3">
            <div className="h-1.5 w-full max-w-64 overflow-hidden rounded-full bg-muted">
              <div
                className="h-full rounded-full bg-primary transition-all"
                style={{ width: `${percent}%` }}
              />
            </div>
            <span className="text-[11px] font-semibold text-primary">
              {percent}%
            </span>
          </div>

          {issues.length === 0 ? (
            <p className="px-3 py-3 text-xs text-muted-foreground">
              Chưa có issue nào trong Sprint này.
            </p>
          ) : (
            <div className="divide-y border-b">
              {issues.map((issue) => (
                <IssueRow
                  key={issue.id}
                  projectId={projectId}
                  issue={issue}
                  onOpenIssue={onOpenIssue}
                />
              ))}
            </div>
          )}
        </>
      ) : null}
    </section>
  );
}

/* ------------------------------------------------------------------ */
/* Backlog route                                                       */
/* ------------------------------------------------------------------ */

type FilterChip = "mine" | "unassigned" | "pull-request" | "bug";

const filterChips: { id: FilterChip; label: string }[] = [
  { id: "mine", label: "Chỉ việc của tôi" },
  { id: "unassigned", label: "Chưa phân công" },
  { id: "pull-request", label: "Có Pull Request" },
  { id: "bug", label: "Bugs" },
];

function emptyBacklogDescription(hasActiveFilters: boolean, readOnly: boolean): string {
  if (hasActiveFilters) {
    return "Không issue nào khớp epic, từ khóa hoặc bộ lọc đang chọn. Thử xóa bộ lọc để xem toàn bộ.";
  }
  if (readOnly) return "Nhóm này chưa có issue nào trong dự án.";
  return "Dự án này chưa có issue nào. Trưởng nhóm sẽ thêm issue khi bắt đầu lập kế hoạch Sprint.";
}

function BacklogSkeleton() {
  return (
    <div
      className="flex flex-col gap-5 p-4 md:p-6"
      role="status"
      aria-label="Đang tải backlog dự án"
    >
      <div className="space-y-2">
        <Skeleton className="h-6 w-1/2" />
        <Skeleton className="h-4 w-3/4" />
      </div>
      <div className="flex gap-4">
        <Skeleton className="hidden w-56 shrink-0 md:block" />
        <div className="flex-1 space-y-4">
          <Skeleton className="h-8 w-72" />
          <Skeleton className="h-10 w-full" />
          {[0, 1, 2].map((row) => (
            <Skeleton key={row} className="h-16 w-full" />
          ))}
        </div>
      </div>
    </div>
  );
}

function issueMatches(
  issue: Issue,
  epicFilter: string | null,
  query: string,
  chips: FilterChip[],
): boolean {
  if (epicFilter !== null && issue.epicId !== epicFilter) return false;
  if (query && !`${issue.key} ${issue.title}`.toLowerCase().includes(query)) return false;
  if (chips.includes("mine") && !issue.isMine) return false;
  if (chips.includes("unassigned") && issue.assignee !== null) return false;
  if (chips.includes("pull-request") && !issue.hasPullRequest) return false;
  return !(chips.includes("bug") && issue.type !== "bug");
}

export default function ProjectBacklogRoute() {
  const navigate = useNavigate();
  const { projectId, workspace: data, viewer, readOnly } = useProjectWorkspaceContext();
  // Only the leader can read project settings; nobody else asks for them.
  const { data: aiSettings } = useProjectAiSettings(
    projectId,
    viewer.kind === "team-member" && viewer.role === "leader",
  );

  const [epicFilter, setEpicFilter] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [chips, setChips] = useState<FilterChip[]>([]);

  const openIssue = (pid: string, key: string) => {
    navigate(`/projects/${pid}/board?issue=${key}`);
  };

  const toggleChip = (chip: FilterChip) => {
    setChips((current) =>
      current.includes(chip)
        ? current.filter((item) => item !== chip)
        : [...current, chip],
    );
  };

  const hasActiveFilters =
    epicFilter !== null || search.trim() !== "" || chips.length > 0;

  const clearFilters = () => {
    setEpicFilter(null);
    setSearch("");
    setChips([]);
  };

  const filteredIssues = useMemo(() => {
    if (!data) return [];
    const q = search.trim().toLowerCase();
    return data.issues.filter((issue) => issueMatches(issue, epicFilter, q, chips));
  }, [data, epicFilter, search, chips]);

  const workspace = data;
  const permCtx: ProjectPermissionContext = projectPermissionContext(
    viewer,
    aiSettings?.ai.keyConfigured ?? false,
  );
  const isLeader = permCtx.role === "leader";
  const needsAiKey = aiRequiresKey(permCtx);
  const canCompleteSprint = canManageSprint(permCtx);
  const showCreateEpic = canCreateTask(permCtx);

  const activeSprints = workspace.sprints.filter(
    (sprint) => sprint.state === "active",
  );
  const upcomingSprints = workspace.sprints.filter(
    (sprint) => sprint.state === "upcoming",
  );

  const backlogIssues = filteredIssues.filter(
    (issue) => issue.sprintId === null,
  );

  const aiAction = (label: string, icon: typeof Sparkles) => {
    const Icon = icon;
    if (needsAiKey) {
      return (
        <Button
          asChild
          key={label}
          variant="outline"
          size="sm"
          className="h-7 gap-1 border-indigo-200 bg-indigo-50/60 px-2.5 text-xs font-semibold text-indigo-700 hover:bg-indigo-50"
        >
          <Link
            to={`/projects/${projectId}/settings`}
            title="Chưa cấu hình AI key — mở Project Settings"
          >
            <Icon className="size-3.5" aria-hidden />
            {label}
            <span className="text-[10px] font-medium text-indigo-500">
              (cần AI key)
            </span>
          </Link>
        </Button>
      );
    }
    return (
      <Button
        key={label}
        variant="outline"
        size="sm"
        disabled
        title="Chưa có API cho tính năng AI này"
        className="h-7 gap-1 border-indigo-200 bg-indigo-50/60 px-2.5 text-xs font-semibold text-indigo-700 hover:bg-indigo-50"
      >
        <Icon className="size-3.5" aria-hidden />
        {label}
      </Button>
    );
  };

  return (
    <div className="flex min-h-0 flex-col">
      {/* 2-column workspace */}
      <div className="flex flex-1 min-h-0 flex-col md:flex-row">

        {/* Epic panel */}
        <aside className="w-full shrink-0 border-b bg-background p-4 md:w-56 md:border-b-0 md:border-r">
          <div className="mb-3 flex items-center justify-between border-b pb-1">
            <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
              Epics
            </span>
            {showCreateEpic ? (
              <Button
                variant="link"
                size="xs"
                disabled
                title="Chưa có API tạo Epic"
                className="h-auto p-0 text-xs"
              >
                <Plus className="size-3.5" aria-hidden />
                Tạo Epic
              </Button>
            ) : null}
          </div>
          <div className="space-y-1">
            <button
              type="button"
              onClick={() => setEpicFilter(null)}
              aria-pressed={epicFilter === null}
              className={cn(
                "flex w-full items-center justify-between rounded px-2.5 py-1.5 text-left text-xs transition-colors",
                epicFilter === null
                  ? "bg-primary/10 font-semibold text-primary"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground",
              )}
            >
              <span className="truncate">Tất cả issues</span>
              <span
                className={cn(
                  "shrink-0 text-xs font-bold",
                  epicFilter === null ? "text-primary" : "text-muted-foreground",
                )}
              >
                {workspace.issues.length}
              </span>
            </button>
            {workspace.epics.map((epic) => {
              const count = workspace.issues.filter(
                (issue) => issue.epicId === epic.id,
              ).length;
              return (
                <button
                  key={epic.id}
                  type="button"
                  onClick={() => setEpicFilter(epic.id)}
                  aria-pressed={epicFilter === epic.id}
                  className={cn(
                    "flex w-full items-center justify-between rounded px-2.5 py-1.5 text-left text-xs transition-colors",
                    epicFilter === epic.id
                      ? "bg-primary/10 font-semibold text-primary"
                      : "text-muted-foreground hover:bg-muted hover:text-foreground",
                  )}
                >
                  <span className="flex min-w-0 items-center gap-2">
                    <span
                      className="size-2.5 shrink-0 rounded-full"
                      style={{ backgroundColor: epic.color }}
                      aria-hidden
                    />
                    <span className="truncate font-medium">{epic.name}</span>
                  </span>
                  <span className="ml-1 shrink-0 text-xs text-muted-foreground">
                    {count}
                  </span>
                </button>
              );
            })}
          </div>
        </aside>

        {/* Sprints + backlog */}
        <div className="min-w-0 flex-1 bg-background p-4 md:p-5">
          {/* Search + chips */}
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <div className="relative w-72 max-w-full">
              <Search
                className="absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
                aria-hidden
              />
              <Input
                type="search"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Tìm kiếm issue trong backlog..."
                aria-label="Tìm kiếm issue theo key hoặc tiêu đề"
                className="h-8 pl-8 text-xs"
              />
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {filterChips
                .filter((chip) => !(readOnly && chip.id === "mine"))
                .map((chip) => {
                const active = chips.includes(chip.id);
                return (
                  <button
                    key={chip.id}
                    type="button"
                    onClick={() => toggleChip(chip.id)}
                    aria-pressed={active}
                    className={cn(
                      "rounded-full border px-2.5 py-1 text-xs font-medium transition-colors",
                      active
                        ? "border-primary bg-primary text-primary-foreground"
                        : "border-border bg-muted text-foreground hover:bg-muted/60",
                    )}
                  >
                    {chip.label}
                  </button>
                );
              })}
              {hasActiveFilters ? (
                <button
                  type="button"
                  onClick={clearFilters}
                  className="ml-1 text-xs font-semibold text-primary hover:underline focus-visible:underline"
                >
                  Xóa bộ lọc
                </button>
              ) : null}
            </div>
          </div>

          {/* Leader-only toolbar */}
          {isLeader ? (
            <div className="mb-5 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-indigo-100 bg-indigo-50/50 px-4 py-2.5">
              <div className="flex items-center gap-2 text-xs font-semibold text-indigo-700">
                <Sparkles className="size-4" aria-hidden />
                Trợ lý AI Scrum Copilot
              </div>
              <div className="flex flex-wrap items-center gap-2">
                {aiAction("AI ước lượng Story Point", Calculator)}
                {aiAction("AI đề xuất phân bổ Sprint", Zap)}
              </div>
            </div>
          ) : null}

          {filteredIssues.length === 0 ? (
            <EmptyState
              title={hasActiveFilters ? "Không có issue khớp bộ lọc" : "Backlog trống"}
              description={emptyBacklogDescription(hasActiveFilters, readOnly)}
              action={
                hasActiveFilters ? (
                  <Button size="sm" variant="outline" onClick={clearFilters}>
                    Xóa bộ lọc
                  </Button>
                ) : undefined
              }
            />
          ) : (
            <>
              {activeSprints.map((sprint) => (
                <SprintSection
                  key={sprint.id}
                  projectId={projectId}
                  sprint={sprint}
                  issues={filteredIssues.filter(
                    (issue) => issue.sprintId === sprint.id,
                  )}
                  onOpenIssue={openIssue}
                  canComplete={canCompleteSprint}
                />
              ))}
              {upcomingSprints.map((sprint) => (
                <SprintSection
                  key={sprint.id}
                  projectId={projectId}
                  sprint={sprint}
                  issues={filteredIssues.filter(
                    (issue) => issue.sprintId === sprint.id,
                  )}
                  onOpenIssue={openIssue}
                  canComplete={canCompleteSprint}
                />
              ))}

              {/* Product Backlog */}
              <section className="mb-10">
                <div className="mb-2 mt-6 flex flex-wrap items-center justify-between gap-2 border-b pb-2">
                  <div className="flex items-center gap-2.5">
                    <h2 className="text-sm font-bold">Product Backlog</h2>
                    <span className="text-xs font-medium text-muted-foreground">
                      ({backlogIssues.length} issue
                      {backlogIssues.length === 1 ? "" : "s"} •{" "}
                      {backlogIssues.reduce(
                        (sum, issue) => sum + issue.storyPoints,
                        0,
                      )}{" "}
                      pts)
                    </span>
                  </div>
                </div>
                {backlogIssues.length === 0 ? (
                  <p className="px-3 py-3 text-xs text-muted-foreground">
                    Không còn issue nào chưa phân vào Sprint.
                  </p>
                ) : (
                  <div className="divide-y border-b">
                    {backlogIssues.map((issue) => (
                      <IssueRow
                        key={issue.id}
                        projectId={projectId}
                        issue={issue}
                        onOpenIssue={openIssue}
                      />
                    ))}
                  </div>
                )}
              </section>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

export function Component() {
  return <ProjectBacklogRoute />;
}