import { isRealService } from "@/lib/config/services";
import { RealWorkspaceBoundary } from "@/features/projects/components/RealWorkspaceBoundary";
import { useRealProjectContext } from "@/features/projects/components/RealProjectLayout";
import { useRealIssueDetail, type IssueDetailState } from "@/features/projects/hooks/useRealIssueDetail";
import { Plus, Zap } from "lucide-react";
import { useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { toast } from "sonner";

import { EmptyState } from "@/components/feedback/EmptyState";
import { Button } from "@/components/ui/button";
import { IssueActionsMenu } from "@/features/projects/components/IssueActionsMenu";
import { useIssueMover, type IssueMover } from "@/features/projects/hooks/useIssueMover";
import { DraggableIssueCard } from "@/features/projects/dnd/DraggableIssueCard";
import {
  useBoardAutoScroll,
  useBoardDropMonitor,
  useColumnDropTarget,
} from "@/features/projects/dnd/boardDnd";
import { IssueFilterBar } from "@/features/projects/components/IssueFilterBar";
import { CreateIssueDialog } from "@/features/projects/components/CreateIssueDialog";
import { IssuePanel } from "@/features/projects/components/IssuePanel";
import { RealIssueEditor, SubtaskCreateForm } from "@/features/projects/components/RealIssueSlots";
import type { IssueWrites } from "@/features/projects/lib/issueWrites";
import { issueWriteErrorMessage } from "@/features/projects/lib/moveErrors";
import { useRealIssueWrites, useToggleSubtask } from "@/lib/query/workWriteHooks";
import { daysLeft, formatShortDate, statusForGroup } from "@/features/projects/issueMeta";
import {
  matchesFilters,
  useIssueFilters,
  type FlagFilter,
  type IssueFilters,
} from "@/features/projects/lib/issueFilters";
import type { Issue, ProjectState, Sprint } from "@/features/projects/types";
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
  state,
  issues,
  onOpenIssue,
  mover,
}: Readonly<{
  state: ProjectState;
  issues: Issue[];
  onOpenIssue: (key: string) => void;
  mover: IssueMover;
}>) {
  const points = issues.reduce((sum, issue) => sum + issue.storyPoints, 0);
  const columnRef = useRef<HTMLElement | null>(null);
  const listRef = useRef<HTMLDivElement | null>(null);
  const status = statusForGroup(state.group);
  const isOver = useColumnDropTarget(columnRef, listRef, status, state.id, mover.enabled);
  return (
    <section
      ref={columnRef}
      className={cn(
        "flex max-h-full w-72 min-w-[18rem] flex-1 flex-col rounded-lg border border-outline-subtle/60 bg-muted/50 p-3 transition-colors",
        isOver && "border-primary/50 bg-primary/10",
      )}
      aria-label={state.name}
    >
      <div className="mb-2 flex shrink-0 items-center justify-between border-b border-outline-subtle/60 pb-2.5">
        <div className="flex min-w-0 items-center gap-2">
          <span
            className="size-2 shrink-0 rounded-full"
            style={{ backgroundColor: state.color }}
            aria-hidden
          />
          <h2 className="truncate text-xs font-bold uppercase tracking-wide">{state.name}</h2>
          <span className="rounded-full border border-outline-subtle bg-card px-1.5 py-0.5 font-mono text-[11px] font-medium text-muted-foreground">
            {issues.length}
          </span>
        </div>
        <span className="shrink-0 text-[11px] font-medium text-muted-foreground">
          {points} pts
        </span>
      </div>
      <div ref={listRef} className="flex-1 space-y-2.5 overflow-y-auto">
        {issues.length === 0 ? (
          <p className="rounded-md border border-dashed border-outline-subtle px-2 py-4 text-center text-[11px] text-muted-foreground">
            Không có issue
          </p>
        ) : (
          issues.map((issue) => (
            <DraggableIssueCard
              key={issue.id}
              issue={issue}
              onOpen={onOpenIssue}
              highlighted={mover.flashKey === issue.key}
              canDrag={mover.canDragIssue(issue)}
              canReorder={mover.role === "leader"}
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
  onCreate,
  showMine,
}: Readonly<{
  sprint: Sprint | null;
  issues: readonly Issue[];
  filters: IssueFilters;
  onFiltersChange: (next: IssueFilters) => void;
  onToggleFlag: (flag: FlagFilter) => void;
  onClear: () => void;
  canCreate: boolean;
  /** Work thật: mở form tạo issue. Bỏ trống (demo) thì nút bị khóa vì chưa có API. */
  onCreate?: () => void;
  /** An instructor has no tasks of their own, so there is no "mine" filter. */
  showMine: boolean;
}>) {
  const remainingDays = sprint ? daysLeft(sprint.endDate) : null;
  return (
    <section className="flex flex-wrap items-center justify-between gap-3 border-b border-outline-subtle bg-background px-6 py-3 short:py-2">
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
        <Button
          size="sm"
          disabled={!onCreate}
          onClick={onCreate}
          {...(onCreate ? {} : { title: "Chưa có API tạo issue", "aria-label": "Tạo issue (chưa khả dụng)" })}
        >
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

/**
 * `real`: dữ liệu đến từ Work thật. Phase 10 chỉ đọc, nên tắt kéo-thả/menu di chuyển và không hỏi
 * cài đặt AI của demo.
 */
function BoardView({
  detail,
  real,
  realTools,
}: Readonly<{
  detail: IssueDetailState;
  real: boolean;
  /** Work thật: cách ghi Board và tick nhiệm vụ con. */
  realTools?: { writes: IssueWrites; toggleSubtask: (subtaskId: string, done: boolean) => void };
}>) {
  const { projectId, workspace, viewer, readOnly, archived, assignees } = useProjectWorkspaceContext();
  const [createOpen, setCreateOpen] = useState(false);
  const [searchParams, setSearchParams] = useSearchParams();
  const { filters, setFilters, toggleFlag, clear } = useIssueFilters();

  const issueKey = searchParams.get("issue");
  // Only the leader can read project settings; nobody else asks for them.
  const aiSettingsQuery = useProjectAiSettings(
    projectId,
    !real && viewer.kind === "team-member" && viewer.role === "leader",
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

  const sprint = useMemo(
    () => workspace.sprints.find((candidate) => candidate.state === "active") ?? null,
    [workspace],
  );

  const boardStates = useMemo(
    () => [...workspace.states].filter((s) => s.group !== "CANCELLED").sort((a, b) => a.sequence - b.sequence),
    [workspace.states],
  );

  const sprintIssues = useMemo(() => {
    const sprintId = sprint?.id ?? null;
    return workspace.issues.filter((issue) => issue.sprintId === sprintId);
  }, [workspace, sprint]);

  const mover = useIssueMover({
    projectId,
    workspace,
    role: viewerRole(viewer),
    canWrite: real ? !archived && !readOnly : undefined,
    writes: realTools?.writes,
  });

  // Work thật: Leader sửa mọi issue, thành viên chỉ issue của mình; dự án lưu trữ và giảng viên chỉ đọc.
  const canEditRealIssue =
    real && !archived && !readOnly && detail.data !== undefined && (mover.role === "leader" || detail.data.issue.isMine);

  const [boardElement, setBoardElement] = useState<HTMLDivElement | null>(null);

  const visibleIssues = useMemo(
    () => sprintIssues.filter((issue) => matchesFilters(issue, filters)),
    [sprintIssues, filters],
  );

  useBoardAutoScroll(boardElement, mover.enabled);
  useBoardDropMonitor({
    enabled: mover.enabled,
    isLeader: mover.role === "leader",
    issues: workspace.issues,
    visibleIssuesFor: (status) => visibleIssues.filter((issue) => issue.status === status),
    onMove: mover.requestMove,
  });

  return (
    <div className="flex min-h-80 flex-1 flex-col">
      <BoardToolbar
        sprint={sprint}
        issues={workspace.issues}
        filters={filters}
        onFiltersChange={setFilters}
        onToggleFlag={toggleFlag}
        onClear={clear}
        canCreate={permissionCtx !== null && canCreateTask(permissionCtx) && !archived}
        onCreate={real ? () => setCreateOpen(true) : undefined}
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
        <div ref={setBoardElement} className="min-h-0 flex-1 overflow-x-auto bg-background p-6 short:p-3">
          <div className="flex h-full items-start gap-4">
            {boardStates.map((state) => (
              <BoardColumn
                key={state.id}
                state={state}
                issues={visibleIssues.filter((issue) => issue.statusId === state.id)}
                onOpenIssue={openIssue}
                mover={mover}
              />
            ))}
          </div>
        </div>
      )}

      {mover.dialog}

      {real ? (
        <CreateIssueDialog
          projectId={projectId}
          open={createOpen}
          onOpenChange={setCreateOpen}
          epics={workspace.epics}
          assignees={assignees}
        />
      ) : null}

      {/* Panel is a sibling overlay: the board above never remounts, so
          filter and scroll state survive panel open/close. */}
      {issueKey !== null ? (
        <IssuePanel
          projectId={projectId}
          projectName={workspace.name}
          issueKey={issueKey}
          epics={workspace.epics}
          sprints={workspace.sprints}
          detail={detail.data}
          isLoading={detail.isPending}
          error={detail.error}
          canBreakdownWithAI={
            permissionCtx !== null && canBreakdownTaskWithAI(permissionCtx)
          }
          aiKeyMissing={
            !real && permissionCtx !== null && aiRequiresKey(permissionCtx)
          }
          readOnly={readOnly}
          states={workspace.states}
          subtasksEditable={!real || canEditRealIssue}
          editSlot={
            real && canEditRealIssue && detail.data ? (
              <RealIssueEditor
                issueId={detail.data.issue.id}
                epics={workspace.epics}
                assignees={assignees}
                textOnly={mover.role !== "leader"}
              />
            ) : undefined
          }
          subtaskCreateSlot={
            real && canEditRealIssue && detail.data ? <SubtaskCreateForm parentId={detail.data.issue.id} /> : undefined
          }
          onToggleSubtaskRemote={real ? realTools?.toggleSubtask : undefined}
          onChangeStatus={
            detail.data && mover.enabled && canUpdateTask(permissionCtx, detail.data.issue.isMine)
              ? (state) =>
                  mover.requestMove({
                    issue: detail.data!.issue,
                    toStatus: statusForGroup(state.group),
                    toStateId: state.id,
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

function DemoBoard() {
  const { projectId } = useProjectWorkspaceContext();
  const [searchParams] = useSearchParams();
  const detail = useIssueDetail(projectId, searchParams.get("issue"));
  return <BoardView detail={detail} real={false} />;
}

function RealBoardContent() {
  const { projectId, workspace } = useProjectWorkspaceContext();
  const { shell } = useRealProjectContext();
  const [searchParams] = useSearchParams();
  const detail = useRealIssueDetail(workspace, shell, searchParams.get("issue"));
  const writes = useRealIssueWrites(projectId);
  const toggle = useToggleSubtask(projectId, workspace.states);
  const toggleSubtask = (subtaskId: string, done: boolean) =>
    toggle.mutate({ subtaskId, done }, { onError: (error) => toast.error(issueWriteErrorMessage(error)) });
  return <BoardView detail={detail} real realTools={{ writes, toggleSubtask }} />;
}

function RealBoard() {
  return (
    <RealWorkspaceBoundary>
      <RealBoardContent />
    </RealWorkspaceBoundary>
  );
}

export function Component() {
  return isRealService("work") ? <RealBoard /> : <DemoBoard />;
}