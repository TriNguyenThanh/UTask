import { collectAllPages } from "@/lib/api/pagination";
import type { ApiClient } from "@/lib/api/client";
import type { SprintDto } from "@/lib/api/work/dto";
import { fetchPage } from "@/lib/api/work/endpoints.shared";

export function listSprints(client: ApiClient, projectId: string) {
  return collectAllPages((cursor) =>
    fetchPage<SprintDto>(client, `/projects/${encodeURIComponent(projectId)}/sprints/`, { cursor }));
}
