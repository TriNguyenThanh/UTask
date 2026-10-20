import { useQuery } from "@tanstack/react-query";

import { useAuth } from "@/features/auth/AuthProvider";
import { useApiClient } from "@/lib/api/ApiClientProvider";
import type { TaskScopeDto } from "@/lib/api/work/dto";
import {
  changeTaskLifecycle,
  createEpic,
  createLabel,
  createRelation,
  deleteEpic,
  deleteLabel,
  deleteRelation,
  listEpics,
  listLabels,
  listTasksInScope,
  patchEpic,
  patchLabel,
  setTaskLabels,
  type EpicInput,
  type LabelInput,
  type TaskLifecycleAction,
} from "@/lib/api/work/endpoints";
import { useRefetchingMutation } from "@/lib/query/workWriteHooks";

function useUserId(): string {
  const { user } = useAuth();
  if (!user) throw new Error("Hook Work chỉ dùng được khi đã đăng nhập.");
  return user.id;
}

/** Khóa nằm dưới `["work", userId]` nên `invalidateQueries(workKeys.all)` sau lệnh ghi làm mới chúng. */
export const workMetaKeys = {
  epics: (userId: string, projectId: string) => ["work", userId, "epics", projectId] as const,
  labels: (userId: string, projectId: string) => ["work", userId, "labels", projectId] as const,
  scoped: (userId: string, projectId: string, scope: TaskScopeDto) =>
    ["work", userId, "scoped-tasks", projectId, scope] as const,
};

/** Epic đầy đủ (có lead, trạng thái, ngày) cho form sửa; workspace chỉ giữ tên và màu. */
export function useEpicsReal(projectId: string, enabled = true) {
  const client = useApiClient();
  const userId = useUserId();
  return useQuery({
    queryKey: workMetaKeys.epics(userId, projectId),
    queryFn: () => listEpics(client, projectId),
    enabled,
  });
}

export function useLabelsReal(projectId: string, enabled = true) {
  const client = useApiClient();
  const userId = useUserId();
  return useQuery({
    queryKey: workMetaKeys.labels(userId, projectId),
    queryFn: () => listLabels(client, projectId),
    enabled,
  });
}

/** Task đã lưu trữ hoặc đã xóa; chỉ tải khi người dùng chọn phạm vi đó. */
export function useScopedTasksReal(projectId: string, scope: TaskScopeDto) {
  const client = useApiClient();
  const userId = useUserId();
  return useQuery({
    queryKey: workMetaKeys.scoped(userId, projectId, scope),
    queryFn: () => listTasksInScope(client, projectId, scope),
    enabled: scope !== "active",
  });
}

export function useCreateEpic(projectId: string) {
  const client = useApiClient();
  return useRefetchingMutation((input: EpicInput & { name: string }) => createEpic(client, projectId, input));
}

export function usePatchEpic(projectId: string, epicId: string) {
  const client = useApiClient();
  return useRefetchingMutation((input: EpicInput) => patchEpic(client, projectId, epicId, input));
}

export function useDeleteEpic(projectId: string) {
  const client = useApiClient();
  return useRefetchingMutation((epicId: string) => deleteEpic(client, projectId, epicId));
}

export function useCreateLabel(projectId: string) {
  const client = useApiClient();
  return useRefetchingMutation((input: LabelInput) => createLabel(client, projectId, input));
}

export function usePatchLabel(projectId: string) {
  const client = useApiClient();
  return useRefetchingMutation(({ labelId, ...input }: Partial<LabelInput> & { labelId: string }) =>
    patchLabel(client, projectId, labelId, input));
}

/** Xóa nhãn gỡ nó khỏi mọi task: `workKeys.all` được làm mới nên cả Board lẫn panel cập nhật. */
export function useDeleteLabel(projectId: string) {
  const client = useApiClient();
  return useRefetchingMutation((labelId: string) => deleteLabel(client, projectId, labelId));
}

export function useSetTaskLabels(taskId: string) {
  const client = useApiClient();
  return useRefetchingMutation((input: { expectedVersion: number; action: "ADD" | "REMOVE"; labelIds: string[] }) =>
    setTaskLabels(client, taskId, input));
}

export function useCreateRelation(taskId: string) {
  const client = useApiClient();
  return useRefetchingMutation((input: Parameters<typeof createRelation>[2]) => createRelation(client, taskId, input));
}

export function useDeleteRelation(taskId: string) {
  const client = useApiClient();
  return useRefetchingMutation((relationId: string) => deleteRelation(client, taskId, relationId));
}

export function useTaskLifecycle() {
  const client = useApiClient();
  return useRefetchingMutation((input: { taskId: string; action: TaskLifecycleAction; expectedVersion: number }) =>
    changeTaskLifecycle(client, input.taskId, input.action, input.expectedVersion));
}
