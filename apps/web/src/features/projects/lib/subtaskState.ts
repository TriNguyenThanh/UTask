import type { ProjectState } from "@/features/projects/types";

/**
 * State đích khi tick/bỏ tick một subtask: "xong" → state COMPLETED đầu tiên theo `sequence`,
 * "chưa xong" → state UNSTARTED đầu tiên. `null` khi dự án không có state nhóm đó.
 */
export function stateForSubtask(states: readonly ProjectState[], done: boolean): ProjectState | null {
  const group = done ? "COMPLETED" : "UNSTARTED";
  return [...states].filter((state) => state.group === group).sort((a, b) => a.sequence - b.sequence)[0] ?? null;
}
