import { useApiClient } from "@/lib/api/ApiClientProvider";
import { newIdempotencyKey } from "@/lib/api/idempotency";
import { declareGitHubUsername, requestGitHubVerification } from "@/lib/api/work/endpoints.github";
import { useRefetchingMutation } from "@/lib/query/workWriteHooks";

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
