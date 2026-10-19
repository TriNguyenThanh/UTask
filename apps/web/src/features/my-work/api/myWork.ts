import type { ApiClient } from "@/lib/api/client";
import type { MyWorkOverview } from "@/features/my-work/types";

const WORK_ROOT = "/api/work/api/v1/my-work";

export function myWorkOverviewRequest(client: ApiClient): Promise<MyWorkOverview> {
  return client.request<MyWorkOverview>(`${WORK_ROOT}/overview`);
}
