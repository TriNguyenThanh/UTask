import { useQuery } from "@tanstack/react-query";

import { useAuth } from "@/features/auth/AuthProvider";
import { useApiClient } from "@/lib/api/ApiClientProvider";
import {
  closeSprint,
  createSprint,
  getProjectDashboard,
  getSprint,
  getSprintBurndown,
  getSprintProgress,
  patchMemberCapacity,
  patchSprint,
  startSprint,
  type SprintFieldsInput,
} from "@/lib/api/work/endpoints";
import { useRefetchingMutation } from "@/lib/query/workWriteHooks";

function useUserId(): string {
  const { user } = useAuth();
  if (!user) throw new Error("Hook Work chỉ dùng được khi đã đăng nhập.");
  return user.id;
}

/** Khóa nằm dưới `["work", userId]` nên `invalidateQueries(workKeys.all)` sau lệnh ghi làm mới chúng. */
export const workSprintKeys = {
  progress: (userId: string, sprintId: string) => ["work", userId, "sprint-progress", sprintId] as const,
  burndown: (userId: string, sprintId: string) => ["work", userId, "sprint-burndown", sprintId] as const,
  dashboard: (userId: string, projectId: string) => ["work", userId, "dashboard", projectId] as const,
};

export function useSprintProgress(sprintId: string, enabled = true) {
  const client = useApiClient();
  const userId = useUserId();
  return useQuery({
    queryKey: workSprintKeys.progress(userId, sprintId),
    queryFn: () => getSprintProgress(client, sprintId),
    enabled,
  });
}

export function useSprintBurndown(sprintId: string, enabled = true) {
  const client = useApiClient();
  const userId = useUserId();
  return useQuery({
    queryKey: workSprintKeys.burndown(userId, sprintId),
    queryFn: () => getSprintBurndown(client, sprintId),
    enabled,
  });
}

export function useProjectDashboard(projectId: string, enabled = true) {
  const client = useApiClient();
  const userId = useUserId();
  return useQuery({
    queryKey: workSprintKeys.dashboard(userId, projectId),
    queryFn: () => getProjectDashboard(client, projectId),
    enabled,
  });
}

export function useCreateSprint(projectId: string) {
  const client = useApiClient();
  return useRefetchingMutation((input: SprintFieldsInput & { name: string }) => createSprint(client, projectId, input));
}

/** Đọc lại `version` ngay trước khi gửi: người dùng có thể vừa thêm/bớt issue làm version tăng. */
export function usePatchSprint(sprintId: string) {
  const client = useApiClient();
  return useRefetchingMutation(async (input: SprintFieldsInput) => {
    const current = await getSprint(client, sprintId);
    return patchSprint(client, sprintId, { ...input, expectedVersion: current.version });
  });
}

/** `idempotencyKey` do nút sinh một lần cho mỗi ý định bắt đầu. */
export function useStartSprint(projectId: string, sprintId: string) {
  const client = useApiClient();
  return useRefetchingMutation(async ({ idempotencyKey }: { idempotencyKey: string }) => {
    const current = await getSprint(client, sprintId);
    return startSprint(client, projectId, sprintId, { expectedVersion: current.version, idempotencyKey });
  });
}

export function useCloseSprint(sprintId: string) {
  const client = useApiClient();
  return useRefetchingMutation(
    async ({ targetSprintId, idempotencyKey }: { targetSprintId: string | null; idempotencyKey: string }) => {
      const current = await getSprint(client, sprintId);
      return closeSprint(client, sprintId, { expectedVersion: current.version, targetSprintId, idempotencyKey });
    },
  );
}

export function useSetMemberCapacity(projectId: string) {
  const client = useApiClient();
  return useRefetchingMutation(({ userId, weeklyCapacity }: { userId: string; weeklyCapacity: number }) =>
    patchMemberCapacity(client, projectId, userId, weeklyCapacity));
}
