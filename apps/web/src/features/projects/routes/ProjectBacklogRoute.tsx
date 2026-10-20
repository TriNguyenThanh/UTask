import { isRealService } from "@/lib/config/services";
import { RealWorkspaceBoundary } from "@/features/projects/components/RealWorkspaceBoundary";
import {
  BookOpen,
  Bug,
  Calculator,
  CheckCircle2,
  ChevronLeft,
  CircleDot,
  GitPullRequest,
  Plus,
  Sparkles,
  SquareCheckBig,
  UserRound,
  Zap,
} from "lucide-react";
import { Fragment, useMemo, useRef, useState, type ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";

import { useAuth } from "@/features/auth/AuthProvider";

import { EmptyState } from "@/components/feedback/EmptyState";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  CreateEpicButton,
  EpicEditButton,
  LabelManagerButton,
  ScopedTaskList,
  TaskScopeTabs,
} from "@/features/projects/components/RealBacklogTools";
import { IssueActionsMenu } from "@/features/projects/components/IssueActionsMenu";
import { CreateSprintButton, SprintHeaderActions, SprintInsights } from "@/features/projects/components/RealSprintTools";
import type { IssueWrites } from "@/features/projects/lib/issueWrites";
import { useRealIssueWrites } from "@/lib/query/workWriteHooks";
import { IssueFilterBar } from "@/features/projects/components/IssueFilterBar";
import { useBacklogDropMonitor, useSectionDropTarget } from "@/features/projects/dnd/backlogDnd";
import { PressableText } from "@/features/projects/components/PressableText";
import { useDraggableIssue } from "@/features/projects/dnd/useDraggableIssue";
import { useIssueMover } from "@/features/projects/hooks/useIssueMover";
import { daysLeft, STATUS_LABELS } from "@/features/projects/issueMeta";
import {
  hasActiveFilters,
  matchesFilters,
  useIssueFilters,
  type FlagFilter,
} from "@/features/projects/lib/issueFilters";
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
  viewerRole,
  type ProjectPermissionContext,
} from "@/lib/permissions";
import type { TaskScopeDto } from "@/lib/api/work/dto";
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

function sprintDateRange(sprint: Sprint): string {
  if (!sprint.startDate || !sprint.endDate) return "Chưa đặt ngày";
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

/* ------------------------------------------------------------------ */
/* Issue row                                                           */
/* ------------------------------------------------------------------ */

function IssueRow({
  projectId,
  issue,
  onOpenIssue,
  actions,
}: {
  projectId: string;
  issue: Issue;
  onOpenIssue: (projectId: string, issueKey: string) => void;
  /** Per-row actions menu, the non-drag way to move it. */
  actions?: ReactNode;
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
        <PressableText
          onActivate={() => onOpenIssue(projectId, issue.key)}
          label={`Mở issue ${issue.key}: ${issue.title}`}
          className="shrink-0 text-xs font-semibold text-primary hover:underline focus-visible:underline focus-visible:outline-none"
        >
          {issue.key}
        </PressableText>
        <PressableText
          onActivate={() => onOpenIssue(projectId, issue.key)}
          label={`Mở issue ${issue.key}: ${issue.title}`}
          className="min-w-0 truncate text-left text-xs font-medium hover:text-primary focus-visible:underline focus-visible:outline-none"
        >
          {issue.title}
        </PressableText>
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
          {STATUS_LABELS[issue.status]}
          {issue.status === "done" ? (
            <CheckCircle2 className="ml-1 size-3 text-emerald-600" aria-hidden />
          ) : null}
        </span>
        {actions}
      </div>
    </div>
  );
}

/**
 * One backlog row that can be dragged (leader only) and dropped on. Position
 * comes from the row under the pointer, the sprint from the section around it.
 */
function BacklogRow({
  projectId,
  issue,
  onOpenIssue,
  mover,
  destination,
}: {
  projectId: string;
  issue: Issue;
  onOpenIssue: (projectId: string, issueKey: string) => void;
  mover: ReturnType<typeof useIssueMover>;
  /** Rows shown in the section this row sits in. */
  destination: readonly Issue[];
}) {
  const wrapperRef = useRef<HTMLDivElement | null>(null);
  const isLeader = mover.role === "leader";
  const canDrag = isLeader && mover.canDragIssue(issue);
  const { dragging, closestEdge } = useDraggableIssue({
    elementRef: wrapperRef,
    issueKey: issue.key,
    canDrag,
    canReorder: isLeader,
  });
  return (
    <div
      ref={wrapperRef}
      data-issue-key={issue.key}
      className={cn(
        "relative transition-colors",
        canDrag && "cursor-grab active:cursor-grabbing",
        dragging && "opacity-40",
        mover.flashKey === issue.key && "bg-primary/10",
      )}
    >
      {closestEdge ? (
        <span
          aria-hidden
          className={cn(
            "pointer-events-none absolute inset-x-0 z-10 h-0.5 bg-primary",
            closestEdge === "top" ? "-top-px" : "-bottom-px",
          )}
        />
      ) : null}
      <IssueRow
        projectId={projectId}
        issue={issue}
        onOpenIssue={onOpenIssue}
        actions={
          <IssueActionsMenu
            issueKey={issue.key}
            groups={mover.menuFor(issue, { kind: "backlog", destination })}
          />
        }
      />
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
  mover,
  actions,
  insights,
}: {
  projectId: string;
  sprint: Sprint;
  issues: Issue[];
  onOpenIssue: (projectId: string, issueKey: string) => void;
  canComplete: boolean;
  mover: ReturnType<typeof useIssueMover>;
  /** Chế độ Work thật: thay nút "Hoàn thành Sprint" chưa có API bằng bộ nút thật. */
  actions?: ReactNode;
  insights?: ReactNode;
}) {
  const [collapsed, setCollapsed] = useState(false);
  const sectionRef = useRef<HTMLElement | null>(null);
  const isOver = useSectionDropTarget(sectionRef, sprint.id, mover.enabled && mover.role === "leader");
  const percent =
    sprint.totalPoints > 0
      ? Math.round((sprint.completedPoints / sprint.totalPoints) * 100)
      : 0;
  const remaining = daysLeft(sprint.endDate);
  const isActive = sprint.state === "active";

  return (
    <section
      ref={sectionRef}
      className={cn("mb-6 rounded transition-colors", isOver && "bg-primary/5 ring-2 ring-primary/30")}
    >
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
          {isActive && remaining >= 0 ? (
            <Badge variant="secondary" className="text-[11px] font-medium">
              Còn {remaining} ngày
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
          {actions !== undefined ? (
            actions
          ) : canComplete && isActive ? (
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
          {insights}

          {issues.length === 0 ? (
            <p className="px-3 py-3 text-xs text-muted-foreground">
              Chưa có issue nào trong Sprint này.
            </p>
          ) : (
            <div className="divide-y border-b">
              {issues.map((issue) => (
                <BacklogRow
                  key={issue.id}
                  projectId={projectId}
                  issue={issue}
                  onOpenIssue={onOpenIssue}
                  mover={mover}
                  destination={issues}
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

const BACKLOG_FLAGS: readonly FlagFilter[] = [
  "mine",
  "unassigned",
  "pr",
  "bug",
  "blocked",
  "overdue",
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

/** `real`: dữ liệu Work thật; `writes` là cách ghi thật cho menu/kéo-thả. AI chưa tích hợp nên ẩn thanh AI. */
function BacklogView({ real, writes }: Readonly<{ real: boolean; writes?: IssueWrites }>) {
  const navigate = useNavigate();
  const { projectId, workspace: data, viewer, readOnly, archived, assignees } = useProjectWorkspaceContext();
  const { user } = useAuth();
  const [scope, setScope] = useState<TaskScopeDto>("active");
  // Only the leader can read project settings; nobody else asks for them.
  const { data: aiSettings } = useProjectAiSettings(
    projectId,
    !real && viewer.kind === "team-member" && viewer.role === "leader",
  );

  const { filters, setFilters, toggleFlag, clear: clearFilters } = useIssueFilters();
  const epicFilter = filters.epic;
  const setEpicFilter = (epic: string | null) => setFilters({ ...filters, epic });

  const openIssue = (pid: string, key: string) => {
    navigate(`/projects/${pid}/board?issue=${key}`);
  };

  const filtersActive = hasActiveFilters(filters);

  const filteredIssues = useMemo(
    () => data.issues.filter((issue) => matchesFilters(issue, filters)),
    [data, filters],
  );

  const workspace = data;
  const permCtx: ProjectPermissionContext = projectPermissionContext(
    viewer,
    aiSettings?.ai.keyConfigured ?? false,
  );
  const isLeader = permCtx.role === "leader";
  const needsAiKey = aiRequiresKey(permCtx);
  const canCompleteSprint = canManageSprint(permCtx);
  const realCanWrite = real && !archived && !readOnly;
  const showCreateEpic = real ? realCanWrite && isLeader : canCreateTask(permCtx);

  const mover = useIssueMover({
    projectId,
    workspace,
    role: viewerRole(viewer),
    canWrite: real ? realCanWrite : undefined,
    writes,
  });
  const backlogSectionRef = useRef<HTMLElement | null>(null);
  const backlogOver = useSectionDropTarget(
    backlogSectionRef,
    null,
    mover.enabled && mover.role === "leader",
  );
  useBacklogDropMonitor({
    enabled: mover.enabled && mover.role === "leader",
    issues: workspace.issues,
    issuesIn: (sprintId) => filteredIssues.filter((issue) => issue.sprintId === sprintId),
    onMove: mover.requestMove,
  });

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

  /** Chế độ thật: nút của Leader trên đầu sprint, và tiến độ/burndown cho sprint đang chạy. */
  const sprintExtras = (sprint: Sprint) =>
    real
      ? {
          actions:
            realCanWrite && isLeader ? (
              <SprintHeaderActions
                projectId={projectId}
                sprint={sprint}
                sprints={workspace.sprints}
                issues={workspace.issues.filter((issue) => issue.sprintId === sprint.id)}
              />
            ) : null,
          insights: sprint.state === "active" ? <SprintInsights sprintId={sprint.id} /> : null,
        }
      : {};

  return (
    <div className="flex min-h-0 flex-col">
      {mover.dialog}
      {/* 2-column workspace */}
      <div className="flex flex-1 min-h-0 flex-col md:flex-row">

        {/* Epic panel */}
        <aside className="w-full shrink-0 border-b bg-background p-4 md:w-56 md:border-b-0 md:border-r">
          <div className="mb-3 flex items-center justify-between border-b pb-1">
            <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
              Epics
            </span>
            {showCreateEpic ? (
              real ? (
                <CreateEpicButton projectId={projectId} assignees={assignees} />
              ) : (
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
              )
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
              const row = (
                <button
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
              if (!real || !user || !realCanWrite) return <Fragment key={epic.id}>{row}</Fragment>;
              return (
                <div key={epic.id} className="flex items-center gap-0.5">
                  {row}
                  <EpicEditButton
                    projectId={projectId}
                    epic={epic}
                    role={isLeader ? "leader" : "member"}
                    userId={user.id}
                    assignees={assignees}
                  />
                </div>
              );
            })}
          </div>
          {real && realCanWrite && isLeader ? (
            <div className="mt-3 border-t pt-2">
              <LabelManagerButton projectId={projectId} />
            </div>
          ) : null}
        </aside>

        {/* Sprints + backlog */}
        <div className="min-w-0 flex-1 bg-background p-4 md:p-5">
          <div className="mb-4">
            <IssueFilterBar
              issues={workspace.issues}
              filters={filters}
              flags={BACKLOG_FLAGS.filter((flag) => !(readOnly && flag === "mine"))}
              onChange={setFilters}
              onToggleFlag={toggleFlag}
              onClear={clearFilters}
            />
          </div>

          {real ? <TaskScopeTabs scope={scope} onChange={setScope} /> : null}
          {real && realCanWrite && isLeader ? (
            <div className="mb-3">
              <CreateSprintButton projectId={projectId} />
            </div>
          ) : null}

          {/* Leader-only toolbar */}
          {isLeader && !real ? (
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

          {real && scope !== "active" ? (
            <ScopedTaskList projectId={projectId} scope={scope} canRestore={realCanWrite && isLeader} />
          ) : filteredIssues.length === 0 ? (
            <EmptyState
              title={filtersActive ? "Không có issue khớp bộ lọc" : "Backlog trống"}
              description={emptyBacklogDescription(filtersActive, readOnly)}
              action={
                filtersActive ? (
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
                  mover={mover}
                  {...sprintExtras(sprint)}
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
                  mover={mover}
                  {...sprintExtras(sprint)}
                />
              ))}

              {/* Product Backlog */}
              <section
                ref={backlogSectionRef}
                className={cn(
                  "mb-10 rounded transition-colors",
                  backlogOver && "bg-primary/5 ring-2 ring-primary/30",
                )}
              >
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
                      <BacklogRow
                        key={issue.id}
                        projectId={projectId}
                        issue={issue}
                        onOpenIssue={openIssue}
                        mover={mover}
                        destination={backlogIssues}
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

export default function ProjectBacklogRoute() {
  return <BacklogView real={false} />;
}

function RealBacklog() {
  return (
    <RealWorkspaceBoundary>
      <RealBacklogContent />
    </RealWorkspaceBoundary>
  );
}

function RealBacklogContent() {
  const { projectId } = useProjectWorkspaceContext();
  const writes = useRealIssueWrites(projectId);
  return <BacklogView real writes={writes} />;
}

export function Component() {
  return isRealService("work") ? <RealBacklog /> : <ProjectBacklogRoute />;
}