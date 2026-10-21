import { toast } from "sonner";

import type { IssueWrites } from "@/features/projects/lib/issueWrites";
import { issueWriteErrorMessage } from "@/features/projects/lib/moveErrors";
import type { ProjectState } from "@/features/projects/types";
import { useRealIssueWrites, useToggleSubtask } from "@/lib/query/workWriteHooks";

/** Work thật: cách ghi issue và tick nhiệm vụ con, dùng chung cho Board và Backlog. */
export function useRealIssueTools(
  projectId: string,
  states: readonly ProjectState[],
): { writes: IssueWrites; toggleSubtask: (subtaskId: string, done: boolean) => void } {
  const writes = useRealIssueWrites(projectId);
  const toggle = useToggleSubtask(projectId, states);
  const toggleSubtask = (subtaskId: string, done: boolean) =>
    toggle.mutate({ subtaskId, done }, { onError: (error) => toast.error(issueWriteErrorMessage(error)) });
  return { writes, toggleSubtask };
}
