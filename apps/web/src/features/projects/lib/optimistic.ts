import { compareByRank } from "@/features/projects/lib/rank";
import type { Issue, ProjectWorkspace } from "@/features/projects/types";

export type IssuePatch = Partial<
  Pick<Issue, "status" | "statusId" | "stateGroup" | "sprintId" | "rank" | "blocked" | "blockedReason">
>;

/**
 * The workspace as it will look once the server accepts `patch`: the issue
 * changed and the list back in rank order. The version is left alone on
 * purpose: it is what the next write sends, and only the server's answer
 * (see `applyServerVersion`) may move it.
 * Returns the same object when the issue is unknown.
 */
export function applyIssuePatch(
  workspace: ProjectWorkspace,
  issueKey: string,
  patch: IssuePatch,
): ProjectWorkspace {
  if (!workspace.issues.some((issue) => issue.key === issueKey)) return workspace;
  const issues = workspace.issues
    .map((issue) => (issue.key === issueKey ? { ...issue, ...patch } : issue))
    .sort(compareByRank);
  return { ...workspace, issues };
}

/** Records the version the server answered with, so the next write is not seen as stale. */
export function applyServerVersion(
  workspace: ProjectWorkspace,
  issueKey: string,
  version: number,
): ProjectWorkspace {
  return {
    ...workspace,
    issues: workspace.issues.map((issue) =>
      issue.key === issueKey ? { ...issue, version } : issue,
    ),
  };
}
