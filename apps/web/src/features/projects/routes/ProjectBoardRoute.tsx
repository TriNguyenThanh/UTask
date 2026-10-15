import { Plus, Zap } from "lucide-react";
import { useMemo } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { EmptyState } from "@/components/feedback/EmptyState";
import { Button } from "@/components/ui/button";
import { IssueActionsMenu } from "@/features/projects/components/IssueActionsMenu";
import { useIssueMover } from "@/features/projects/hooks/useIssueMover";
import { IssueCard } from "@/features/projects/components/IssueCard";
import { IssueFilterBar } from "@/features/projects/components/IssueFilterBar";
import { IssuePanel } from "@/features/projects/components/IssuePanel";
import { COLUMNS, daysLeft, formatShortDate } from "@/features/projects/issueMeta";
import {
  matchesFilters,
  useIssueFilters,
  type FlagFilter,
  type IssueFilters,
} from "@/features/projects/lib/issueFilters";
import type { Issue, Sprint } from "@/features/projects/types";
import { useProjectWorkspaceContext } from "@/features/projects/routes/ProjectWorkspaceLayout";
import {
  aiRequiresKey,
  canBreakdownTaskWithAI,
  canCreateTask,
  canUpdateTask,
  projectPermissionContext,
  viewerRole,
  type ProjectPermissionContext,
} from "@/lib/permissions";
import {
  useIssueDetail,
  useProjectAiSettings,
} from "@/lib/query/studentFlowHooks";
import { cn } from "@/lib/utils";

/* ------------------------------------------------------------------ */
/* Column                                                              */
/* ------------------------------------------------------------------ */

const BOARD_FLAGS: readonly FlagFilter[] = ["mine", "pr", "bug", "blocked", "overdue"];

function BoardColumn({
  column,
  issues,
  onOpenIssue,
  mover,
}: Readonly<{
  column: (typeof COLUMNS)[number];
  issues: Issue[];
  onOpenIssue: (key: string) => void;
  mover: ReturnType<typeof useIssueMover>;
}>) {
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
            <IssueCard
              key={issue.id}
              issue={issue}
              onOpen={onOpenIssue}
              highlighted={mover.flashKey === issue.key}
              actions={
                <IssueActionsMenu
                  issueKey={issue.key}
                  groups={mover.menuFor(issue, { kind: "board", destination: issues })}
                />
              }
            />
          ))
        )}
      </div>
    </section>
  );
}

/* ------------------------------------------------------------------ */
/* Toolbar                                                             */
/* ------------------------------------------------------------------ */

function BoardToolbar({
  sprint,
  issues,
  filters,
  onFiltersChange,
  onToggleFlag,
  onClear,
  canCreate,
  showMine,
}: Readonly<{
  sprint: Sprint | null;
  issues: readonly Issue[];
  filters: IssueFilters;
  onFiltersChange: (next: IssueFilters) => void;
  onToggleFlag: (flag: FlagFilter) => void;
  onClear: () => void;
  canCreate: boolean;
  /** An instructor has no tasks of their own, so there is no "mine" filter. */
  showMine: boolean;
}>) {
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
        <IssueFilterBar
          issues={issues}
          filters={filters}
          flags={BOARD_FLAGS.filter((flag) => showMine || flag !== "mine")}
          onChange={onFiltersChange}
          onToggleFlag={onToggleFlag}
          onClear={onClear}
        />
      </div>

      {canCreate ? (
        <Button size="sm" disabled title="Chưa có API tạo issue" aria-label="Tạo issue (chưa khả dụng)">
          <Plus aria-hidden />
          Tạo Issue
        </Button>
      ) : null}
    </section>
  );
}

/* ------------------------------------------------------------------ */
/* Route component                                                     */
/* ------------------------------------------------------------------ */

export function Component() {
  const { projectId, workspace, viewer, readOnly } = useProjectWorkspaceContext();
  const [searchParams, setSearchParams] = useSearchParams();
  const { filters, setFilters, toggleFlag, clear } = useIssueFilters();

  const issueKey = searchParams.get("issue");
  const issueQuery = useIssueDetail(projectId, issueKey);
  // Only the leader can read project settings; nobody else asks for them.
  const aiSettingsQuery = useProjectAiSettings(
    projectId,
    viewer.kind === "team-member" && viewer.role === "leader",
  );

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
  const permissionCtx: ProjectPermissionContext = projectPermissionContext(viewer, aiEnabled);

  const sprint = useMemo(() => {
    return workspace.sprints.find((candidate) => candidate.state === "active") ?? null;
  }, [workspace]);

  const sprintIssues = useMemo(() => {
    const sprintId = sprint?.id ?? null;
    return workspace.issues.filter((issue) => issue.sprintId === sprintId);
  }, [workspace, sprint]);

  const mover = useIssueMover({ projectId, workspace, role: viewerRole(viewer) });

  const visibleIssues = useMemo(
    () => sprintIssues.filter((issue) => matchesFilters(issue, filters)),
    [sprintIssues, filters],
  );

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <BoardToolbar
        sprint={sprint}
        issues={workspace.issues}
        filters={filters}
        onFiltersChange={setFilters}
        onToggleFlag={toggleFlag}
        onClear={clear}
        canCreate={permissionCtx !== null && canCreateTask(permissionCtx)}
        showMine={!readOnly}
      />

      {sprint === null ? (
        <div className="p-6">
          {readOnly ? (
            <EmptyState
              title="Nhóm chưa có Sprint đang chạy"
              description="Bảng công việc chỉ hiển thị issue của Sprint đang chạy, nên hiện chưa có gì để xem ở đây. Các issue của nhóm vẫn có trong Backlog."
              action={
                <Button asChild size="sm" variant="outline">
                  <Link to={`/projects/${projectId}/backlog`}>Xem Backlog của nhóm</Link>
                </Button>
              }
            />
          ) : (
            <EmptyState
              title="Chưa có Sprint đang chạy"
              description="Sprint hiện chưa được khởi tạo. Vui lòng liên hệ Trưởng nhóm để khởi tạo Sprint cho dự án."
            />
          )}
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
                onClick={clear}
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
                mover={mover}
              />
            ))}
          </div>
        </div>
      )}

      {mover.dialog}

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
          readOnly={readOnly}
          onChangeStatus={
            issueQuery.data && mover.enabled && canUpdateTask(permissionCtx, issueQuery.data.issue.isMine)
              ? (status) =>
                  mover.requestMove({
                    issue: issueQuery.data.issue,
                    toStatus: status,
                    destination: [],
                  })
              : undefined
          }
          onClose={closeIssue}
        />
      ) : null}
    </div>
  );
}