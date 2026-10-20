import { useMutation, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { useAuth } from "@/features/auth/AuthProvider";
import { applyIssuePatch, applyServerVersion, type IssuePatch } from "@/features/projects/lib/optimistic";
import { issueWriteErrorMessage } from "@/features/projects/lib/moveErrors";
import { planNeighbours } from "@/features/projects/lib/transitionNeighbours";
import { statusForGroup } from "@/features/projects/issueMeta";
import type { BlockCommand, IssueWrites, MoveCommand } from "@/features/projects/lib/issueWrites";
import { stateForSubtask } from "@/features/projects/lib/subtaskState";
import type { ProjectState, ProjectWorkspace } from "@/features/projects/types";
import { useApiClient } from "@/lib/api/ApiClientProvider";
import {
  blockTask,
  createSubtask,
  createTask,
  getTask,
  listTaskOrderInState,
  patchTask,
  transitionTask,
  unblockTask,
  type CreateTaskInput,
  type PatchTaskInput,
  type TaskFieldsInput,
} from "@/lib/api/work/endpoints";
import { workKeys } from "@/lib/query/workHooks";

function useUserId(): string {
  const { user } = useAuth();
  if (!user) throw new Error("Hook Work chỉ dùng được khi đã đăng nhập.");
  return user.id;
}

interface Snapshot {
  workspace: ProjectWorkspace | undefined;
}

/** Áp thay đổi lên workspace trong cache ngay; trả bản cũ để hoàn tác. */
async function applyOptimistic(
  queryClient: QueryClient,
  key: readonly unknown[],
  issueKey: string,
  patch: IssuePatch,
): Promise<Snapshot> {
  await queryClient.cancelQueries({ queryKey: key, exact: true });
  const workspace = queryClient.getQueryData<ProjectWorkspace>(key);
  queryClient.setQueryData<ProjectWorkspace>(key, (current) =>
    current ? applyIssuePatch(current, issueKey, patch) : current,
  );
  return { workspace };
}

function currentIssue(queryClient: QueryClient, key: readonly unknown[], issueId: string, fallback: MoveCommand["issue"]) {
  return queryClient.getQueryData<ProjectWorkspace>(key)?.issues.find((issue) => issue.id === issueId) ?? fallback;
}

/**
 * Ghi Board/Backlog thật cho `useIssueMover`. Các lệnh xếp hàng theo dự án nên hai lần kéo liền nhau
 * tới server đúng thứ tự, và `version` được đọc từ cache lúc gửi (sau khi lệnh trước đã tăng nó).
 * Lạc quan: sửa cache trước, hoàn tác khi lỗi. Thành công thì ghi `version` và `sort_order` thật của
 * server, không tải lại cả workspace (tải workspace tốn nhiều lời gọi).
 */
export function useRealIssueWrites(projectId: string): IssueWrites {
  const client = useApiClient();
  const queryClient = useQueryClient();
  const userId = useUserId();
  const workspaceKey = workKeys.workspace(userId, projectId);

  const onError = (error: unknown, snapshot: Snapshot | undefined) => {
    if (snapshot) queryClient.setQueryData(workspaceKey, snapshot.workspace);
    toast.error(issueWriteErrorMessage(error));
    void queryClient.invalidateQueries({ queryKey: workKeys.all });
  };

  const move = useMutation({
    scope: { id: `work-issue-write:${projectId}` },
    mutationFn: async ({ issue, intent }: MoveCommand) => {
      const current = currentIssue(queryClient, workspaceKey, issue.id, issue);
      const targetStateId = intent.statusId ?? current.statusId;
      const column = (await listTaskOrderInState(client, projectId, targetStateId)).filter((id) => id !== issue.id);
      const siblings = (queryClient.getQueryData<ProjectWorkspace>(workspaceKey)?.issues ?? [])
        .filter((other) => other.statusId === targetStateId && other.id !== issue.id)
        .map((other) => ({ id: other.id, rank: other.rank }));
      const neighbours = planNeighbours(column, siblings, intent.rank);
      return transitionTask(client, issue.id, { expectedVersion: current.version, targetStateId, ...neighbours });
    },
    onMutate: async ({ issue, intent }: MoveCommand) => {
      const states = queryClient.getQueryData<ProjectWorkspace>(workspaceKey)?.states ?? [];
      const target = intent.statusId ? states.find((state) => state.id === intent.statusId) : undefined;
      const patch: IssuePatch = {
        ...(target
          ? { statusId: target.id, stateGroup: target.group, status: statusForGroup(target.group) }
          : {}),
        ...(intent.rank !== undefined ? { rank: intent.rank } : {}),
      };
      return applyOptimistic(queryClient, workspaceKey, issue.key, patch);
    },
    onSuccess: (task, { issue }) => {
      queryClient.setQueryData<ProjectWorkspace>(workspaceKey, (current) =>
        current
          ? applyServerVersion(applyIssuePatch(current, issue.key, { rank: task.sort_order }), issue.key, task.version)
          : current,
      );
      void queryClient.invalidateQueries({ queryKey: workKeys.task(userId, issue.id), exact: true });
    },
    onError: (error, _command, snapshot) => onError(error, snapshot),
  });

  const block = useMutation({
    scope: { id: `work-issue-write:${projectId}` },
    mutationFn: ({ issue, blocked, reason }: BlockCommand) => {
      const { version } = currentIssue(queryClient, workspaceKey, issue.id, issue);
      return blocked
        ? blockTask(client, issue.id, { expectedVersion: version, blockedReason: reason ?? "" })
        : unblockTask(client, issue.id, { expectedVersion: version });
    },
    onMutate: ({ issue, blocked, reason }: BlockCommand) =>
      applyOptimistic(queryClient, workspaceKey, issue.key, {
        blocked,
        blockedReason: blocked ? (reason?.trim() ?? null) : null,
      }),
    onSuccess: (task, { issue }) => {
      queryClient.setQueryData<ProjectWorkspace>(workspaceKey, (current) =>
        current ? applyServerVersion(current, issue.key, task.version) : current,
      );
      void queryClient.invalidateQueries({ queryKey: workKeys.task(userId, issue.id), exact: true });
    },
    onError: (error, _command, snapshot) => onError(error, snapshot),
  });

  return { move: move.mutate, setBlocked: block.mutate };
}

/** Sau lệnh ghi không lạc quan: tải lại mọi dữ liệu Work (kể cả khi 409, vì dữ liệu đang hiện đã cũ). */
export function useRefetchingMutation<V, R>(run: (variables: V) => Promise<R>) {
  const queryClient = useQueryClient();
  const refetch = () => queryClient.invalidateQueries({ queryKey: workKeys.all });
  return useMutation({
    mutationFn: run,
    onSuccess: refetch,
    onError: (error) => {
      if (error instanceof Object && "status" in error && (error as { status: number }).status === 409) void refetch();
    },
  });
}

/** `idempotencyKey` do dialog sinh một lần cho mỗi ý định tạo. */
export function useCreateTask(projectId: string) {
  const client = useApiClient();
  return useRefetchingMutation((input: CreateTaskInput & { idempotencyKey: string }) =>
    createTask(client, projectId, input));
}

export function useCreateSubtask(parentTaskId: string) {
  const client = useApiClient();
  return useRefetchingMutation((input: TaskFieldsInput & { title: string; idempotencyKey: string }) =>
    createSubtask(client, parentTaskId, input));
}

export function usePatchTask(taskId: string) {
  const client = useApiClient();
  return useRefetchingMutation((input: PatchTaskInput) => patchTask(client, taskId, input));
}

/**
 * Tick/bỏ tick subtask: chuyển subtask sang state COMPLETED/UNSTARTED, xếp cuối cột. Đọc lại subtask ngay
 * trước khi gửi để dùng đúng `version` (chi tiết issue chỉ có id, tiêu đề và trạng thái xong).
 */
export function useToggleSubtask(projectId: string, states: readonly ProjectState[]) {
  const client = useApiClient();
  return useRefetchingMutation(async ({ subtaskId, done }: { subtaskId: string; done: boolean }) => {
    const target = stateForSubtask(states, done);
    if (!target) throw new Error("Dự án chưa có trạng thái phù hợp cho nhiệm vụ con.");
    const subtask = await getTask(client, subtaskId);
    const column = (await listTaskOrderInState(client, projectId, target.id)).filter((id) => id !== subtaskId);
    return transitionTask(client, subtaskId, {
      expectedVersion: subtask.version,
      targetStateId: target.id,
      ...planNeighbours(column, [], undefined),
    });
  });
}
