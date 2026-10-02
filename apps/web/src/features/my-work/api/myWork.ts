import type { ApiClient } from "@/lib/api/client";
import type { GitHubActivity, MyWorkOverview } from "@/features/my-work/types";

const WORK_ROOT = "/api/work/api/v1/my-work";

export function myWorkOverviewRequest(client: ApiClient): Promise<MyWorkOverview> {
  return client.request<MyWorkOverview>(`${WORK_ROOT}/overview`);
}

export function myWorkGitHubRequest(client: ApiClient): Promise<GitHubActivity> {
  return client.request<GitHubActivity>(`${WORK_ROOT}/github`);
}