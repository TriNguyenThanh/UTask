import { useEffect, useState } from "react";

import { useAuth } from "@/features/auth/AuthProvider";
import { AiDecomposeButton } from "@/features/projects/components/ai/AiDecomposeDialog";
import { IssuePanel } from "@/features/projects/components/IssuePanel";
import { collabSlots } from "@/features/projects/components/RealCollab";
import { RealIssueEditor, SubtaskCreateForm } from "@/features/projects/components/RealIssueSlots";
import { RealGitHubLinks } from "@/features/projects/components/RealGitHubLinks";
import type { IssueDetailState } from "@/features/projects/hooks/useRealIssueDetail";
import type { IssueMover } from "@/features/projects/hooks/useIssueMover";
import { useIssueParam } from "@/features/projects/hooks/useIssueParam";
import type { ActivityLookup } from "@/features/projects/lib/activity";
import { statusForGroup } from "@/features/projects/issueMeta";
import { useProjectWorkspaceContext } from "@/features/projects/routes/ProjectWorkspaceLayout";
import {
  aiRequiresKey,
  canBreakdownTaskWithAI,
  canUpdateTask,
  type ProjectPermissionContext,
} from "@/lib/permissions";

/**
 * Panel chi tiết issue dùng chung cho Board và Backlog. Mở/đóng theo `?issue=` của URL,
 * nên trang bên dưới không remount và bộ lọc/vị trí cuộn được giữ nguyên.
 */
export function IssuePanelHost({
  detail,
  real,
  mover,
  permissionCtx,
  toggleSubtask,
  backLabel,
}: Readonly<{
  detail: IssueDetailState;
  real: boolean;
  mover: IssueMover;
  permissionCtx: ProjectPermissionContext;
  toggleSubtask?: (subtaskId: string, done: boolean) => void;
  backLabel: string;
}>) {
  const { projectId, workspace, readOnly, archived, assignees } = useProjectWorkspaceContext();
  const { user } = useAuth();
  const { issueKey, closeIssue } = useIssueParam();
  const [editDirty, setEditDirty] = useState(false);

  useEffect(() => setEditDirty(false), [issueKey]);

  if (issueKey === null) return null;

  const labelNames = new Map(workspace.issues.flatMap((issue) => (issue.labels ?? []).map((label) => [label.id, label.name] as const)));
  const activityLookup: ActivityLookup = {
    state_id: (id) => workspace.states.find((state) => state.id === id)?.name,
    epic_id: (id) => workspace.epics.find((epic) => epic.id === id)?.name,
    assignee_ids: (id) => assignees.find((person) => person.userId === id)?.name,
    label_ids: (id) => labelNames.get(id),
  };

  // Work thật: Leader sửa mọi issue, thành viên chỉ issue của mình; dự án lưu trữ và giảng viên chỉ đọc.
  const canEditRealIssue =
    real && !archived && !readOnly && detail.data !== undefined && (mover.role === "leader" || detail.data.issue.isMine);

  // Work thật: bình luận/lịch sử/tệp lấy từ server. Giảng viên (readOnly) vẫn bình luận được, dự án lưu trữ thì không.
  const collab =
    real && detail.data && user
      ? collabSlots(
          detail.data.issue.id,
          { userId: user.id, isLeader: mover.role === "leader", canComment: !archived, canUpload: !archived && !readOnly },
          assignees,
          activityLookup,
        )
      : undefined;

  return (
    <IssuePanel
      projectId={projectId}
      projectName={workspace.name}
      issueKey={issueKey}
      epics={workspace.epics}
      sprints={workspace.sprints}
      detail={detail.data}
      isLoading={detail.isPending}
      error={detail.error}
      canBreakdownWithAI={permissionCtx !== null && canBreakdownTaskWithAI(permissionCtx)}
      aiKeyMissing={!real && permissionCtx !== null && aiRequiresKey(permissionCtx)}
      readOnly={readOnly}
      states={workspace.states}
      subtasksEditable={!real || canEditRealIssue}
      editSlot={
        real && canEditRealIssue && detail.data ? (
          <RealIssueEditor
            projectId={projectId}
            issueId={detail.data.issue.id}
            epics={workspace.epics}
            assignees={assignees}
            issues={workspace.issues}
            textOnly={mover.role !== "leader"}
            isLeader={mover.role === "leader"}
            onGone={closeIssue}
            onDirtyChange={setEditDirty}
          />
        ) : undefined
      }
      subtaskCreateSlot={
        real && canEditRealIssue && detail.data ? <SubtaskCreateForm parentId={detail.data.issue.id} /> : undefined
      }
      aiSlot={
        real && canEditRealIssue && detail.data ? (
          <AiDecomposeButton
            taskId={detail.data.issue.id}
            description={detail.data.description}
            acceptanceCriteria={detail.data.acceptanceCriteria}
            isLeader={mover.role === "leader"}
          />
        ) : undefined
      }
      githubSlot={
        real && detail.data ? (
          <RealGitHubLinks taskId={detail.data.issue.id} projectId={projectId} editable={canEditRealIssue} />
        ) : undefined
      }
      {...collab}
      onToggleSubtaskRemote={real ? toggleSubtask : undefined}
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
      backLabel={backLabel}
      hasUnsavedChanges={editDirty}
    />
  );
}
