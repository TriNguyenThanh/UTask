import { useMemo } from "react";

import type { Issue, IssueDetail, ProjectWorkspace } from "@/features/projects/types";
import { ApiError } from "@/lib/api/errors";
import type { WorkProjectShell } from "@/lib/api/work/adapters";
import { toIssueDetail } from "@/lib/api/work/workspaceAdapters";
import { useTaskReal } from "@/lib/query/workHooks";

export interface IssueDetailState {
  data: IssueDetail | undefined;
  isPending: boolean;
  error: unknown;
}

const NOT_FOUND = new ApiError({ status: 404, message: "Không tìm thấy công việc.", code: "RESOURCE_NOT_FOUND" });

/**
 * Chi tiết issue của Work thật. URL mang mã hiển thị (`NEXUS-1`), còn API cần `id`,
 * nên tra `id` từ workspace đã tải; mã không có trong workspace → 404.
 */
export function useRealIssueDetail(
  workspace: ProjectWorkspace,
  shell: WorkProjectShell,
  issueKey: string | null,
): IssueDetailState {
  const issue: Issue | undefined = issueKey === null
    ? undefined
    : workspace.issues.find((candidate) => candidate.key === issueKey);
  const query = useTaskReal(issue?.id ?? null);

  const data = useMemo(
    () => (query.data && issue ? toIssueDetail(query.data, issue, shell.members) : undefined),
    [query.data, issue, shell.members],
  );

  if (issueKey === null) return { data: undefined, isPending: false, error: null };
  if (!issue) return { data: undefined, isPending: false, error: NOT_FOUND };
  return { data, isPending: query.isPending, error: query.error };
}
