import type { ApiClient } from "@/lib/api/client";
import { collectAllPages } from "@/lib/api/pagination";
import type { EpicDto, LabelDto, StateDto, TaskDto } from "@/lib/api/work/dto";
import { fetchPage, ROOT } from "@/lib/api/work/endpoints.shared";

const project = (projectId: string) => `/projects/${encodeURIComponent(projectId)}`;

export function listStates(client: ApiClient, projectId: string) {
  return collectAllPages((cursor) => fetchPage<StateDto>(client, `${project(projectId)}/states/`, { cursor }));
}

export function listEpics(client: ApiClient, projectId: string) {
  return collectAllPages((cursor) => fetchPage<EpicDto>(client, `${project(projectId)}/epics/`, { cursor }));
}

export function listLabels(client: ApiClient, projectId: string) {
  return collectAllPages((cursor) => fetchPage<LabelDto>(client, `${project(projectId)}/labels/`, { cursor }));
}

export interface ListTasksOptions {
  /** UUID của chu kỳ, hoặc `none` cho backlog. Task không có `sprint_id` nên phải hỏi theo chu kỳ (D4). */
  sprintId?: string;
}

/** Danh sách task kèm state/epic/labels/assignees. Gồm cả SUBTASK; adapter lọc bỏ. */
export function listTasks(client: ApiClient, projectId: string, options: ListTasksOptions = {}) {
  return collectAllPages((cursor) =>
    fetchPage<TaskDto>(client, `${project(projectId)}/tasks/`, {
      cursor,
      params: { expand: "state,epic,labels,assignees", sprint_id: options.sprintId },
    }));
}

/** Chi tiết task; backend chỉ cho `relations/subtasks/attachments/github_links` ở trang chi tiết. */
export async function getTask(client: ApiClient, taskId: string, expand = "state,epic,labels,assignees,subtasks") {
  const { data } = await client.requestEnvelope<TaskDto>(
    `${ROOT}/tasks/${encodeURIComponent(taskId)}/?expand=${encodeURIComponent(expand)}`,
  );
  return data;
}

/** Chỉ lấy `id` task thuộc một chu kỳ, để ghép `taskId → sprintId` mà không tải lại cả task (D4). */
export async function listTaskIdsInSprint(client: ApiClient, projectId: string, sprintId: string) {
  const rows = await collectAllPages((cursor) =>
    fetchPage<Pick<TaskDto, "id">>(client, `${project(projectId)}/tasks/`, {
      cursor,
      params: { fields: "id", sprint_id: sprintId },
    }));
  return rows.map((row) => row.id);
}
