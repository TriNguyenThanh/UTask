import { useQuery } from "@tanstack/react-query";
import { useRef } from "react";

import { useApiClient } from "@/lib/api/ApiClientProvider";
import { ApiError } from "@/lib/api/errors";
import { newIdempotencyKey } from "@/lib/api/idempotency";
import {
  declareGitHubUsername,
  getProjectRepository,
  requestGitHubVerification,
  selectProjectRepositoryAndWait,
} from "@/lib/api/work/endpoints.github";
import { useAuth } from "@/features/auth/AuthProvider";
import { useRefetchingMutation } from "@/lib/query/workWriteHooks";

/** Nằm dưới `["work", userId]` nên `invalidateQueries(workKeys.all)` sau lệnh ghi làm mới nó. */
export const workGithubKeys = {
  repository: (userId: string, projectId: string) => ["work", userId, "github-repository", projectId] as const,
};

/** Thành công thì tải lại dữ liệu Work (gồm danh sách thành viên của `ProjectInfoRoute`). */
export function useDeclareGitHubUsername(projectId: string) {
  const client = useApiClient();
  return useRefetchingMutation(({ userId, githubUsername }: { userId: string; githubUsername: string }) =>
    declareGitHubUsername(client, projectId, userId, githubUsername));
}

export function useRequestGitHubVerification(projectId: string) {
  const client = useApiClient();
  return useRefetchingMutation(({ userId }: { userId: string }) =>
    requestGitHubVerification(client, projectId, userId, newIdempotencyKey()));
}

export function useProjectRepository(projectId: string) {
  const client = useApiClient();
  const { user } = useAuth();
  const userId = user?.id ?? "";
  return useQuery({
    queryKey: workGithubKeys.repository(userId, projectId),
    queryFn: () => getProjectRepository(client, projectId),
    enabled: userId !== "",
  });
}

/**
 * `operationId` giữ nguyên khi thử lại cùng repo (cùng `Idempotency-Key`), sinh mới khi đổi repo hoặc
 * sau khi chọn thành công.
 */
export function useSelectProjectRepository(projectId: string) {
  const client = useApiClient();
  const attempt = useRef<{ repoId: string; operationId: string } | null>(null);
  return useRefetchingMutation(async ({ githubRepoId, expectedGeneration }: { githubRepoId: string; expectedGeneration: number }) => {
    if (attempt.current?.repoId !== githubRepoId) {
      attempt.current = { repoId: githubRepoId, operationId: newIdempotencyKey() };
    }
    try {
      const result = await selectProjectRepositoryAndWait(client, projectId, {
        githubRepoId,
        expectedGeneration,
        operationId: attempt.current.operationId,
      });
      attempt.current = null;
      return result;
    } catch (error) {
      // 409: thế hệ kết nối đã đổi, payload mới không được dùng lại key cũ.
      if (error instanceof ApiError && error.status === 409) attempt.current = null;
      throw error;
    }
  });
}
