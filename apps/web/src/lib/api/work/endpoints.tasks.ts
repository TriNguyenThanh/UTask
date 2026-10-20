import type { ApiClient } from "@/lib/api/client";
import { collectAllPages } from "@/lib/api/pagination";
import type { EpicDto, LabelDto, StateDto, TaskDto, TaskPriorityDto } from "@/lib/api/work/dto";
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

/** Các trường người dùng nhập khi tạo task; khóa `undefined` không được gửi. */
export interface TaskFieldsInput {
  title?: string;
  descriptionHtml?: string;
  acceptanceCriteria?: string;
  priority?: TaskPriorityDto;
  storyPoints?: number | null;
  dueDate?: string | null;
  epicId?: string | null;
  assigneeIds?: string[];
  labelIds?: string[];
}

export interface CreateTaskInput extends TaskFieldsInput {
  title: string;
  type?: "TASK" | "BUG" | "STORY";
  /** Bỏ trống thì server dùng state mặc định. */
  stateId?: string;
}

export type PatchTaskInput = TaskFieldsInput & { expectedVersion: number };

function taskFieldsBody(input: TaskFieldsInput): Record<string, unknown> {
  const body: Record<string, unknown> = {};
  if (input.title !== undefined) body.title = input.title;
  if (input.descriptionHtml !== undefined) body.description_html = input.descriptionHtml;
  if (input.acceptanceCriteria !== undefined) body.acceptance_criteria = input.acceptanceCriteria;
  if (input.priority !== undefined) body.priority = input.priority;
  if (input.storyPoints !== undefined) body.story_points = input.storyPoints;
  if (input.dueDate !== undefined) body.due_date = input.dueDate;
  if (input.epicId !== undefined) body.epic_id = input.epicId;
  if (input.assigneeIds !== undefined) body.assignee_ids = input.assigneeIds;
  if (input.labelIds !== undefined) body.label_ids = input.labelIds;
  return body;
}

const task = (taskId: string) => `${ROOT}/tasks/${encodeURIComponent(taskId)}`;

/** `Idempotency-Key` bắt buộc: sinh một lần cho mỗi ý định tạo. */
export async function createTask(
  client: ApiClient,
  projectId: string,
  input: CreateTaskInput & { idempotencyKey: string },
) {
  const body = taskFieldsBody(input);
  if (input.type !== undefined) body.type = input.type;
  if (input.stateId !== undefined) body.state_id = input.stateId;
  const { data } = await client.requestEnvelope<TaskDto>(`${ROOT}${project(projectId)}/tasks/`, {
    method: "POST",
    body,
    idempotencyKey: input.idempotencyKey,
  });
  return data;
}

/** `Idempotency-Key` bắt buộc. Thành viên không phải Leader chỉ đặt được title/mô tả/tiêu chí. */
export async function createSubtask(
  client: ApiClient,
  parentTaskId: string,
  input: TaskFieldsInput & { title: string; idempotencyKey: string },
) {
  const { data } = await client.requestEnvelope<TaskDto>(`${task(parentTaskId)}/subtasks/`, {
    method: "POST",
    body: taskFieldsBody(input),
    idempotencyKey: input.idempotencyKey,
  });
  return data;
}

/** Chỉ gửi khóa đổi + `expected_version`. Backend không nhận `state_id`: đổi cột qua `transitionTask`. Không gửi `Idempotency-Key`. */
export async function patchTask(client: ApiClient, taskId: string, input: PatchTaskInput) {
  const { data } = await client.requestEnvelope<TaskDto>(`${task(taskId)}/`, {
    method: "PATCH",
    body: { expected_version: input.expectedVersion, ...taskFieldsBody(input) },
  });
  return data;
}

export interface TransitionInput {
  expectedVersion: number;
  targetStateId: string;
  /** Hàng xóm liền kề trong cột đích (kể cả task bị ẩn); cột rỗng thì cả hai `null`. */
  previousTaskId: string | null;
  nextTaskId: string | null;
}

export type TransitionedTaskDto = TaskDto & { board_revision: number };

export async function transitionTask(client: ApiClient, taskId: string, input: TransitionInput) {
  const { data } = await client.requestEnvelope<TransitionedTaskDto>(`${task(taskId)}/transition/`, {
    method: "PATCH",
    body: {
      expected_version: input.expectedVersion,
      target_state_id: input.targetStateId,
      previous_task_id: input.previousTaskId,
      next_task_id: input.nextTaskId,
    },
  });
  return data;
}

export async function blockTask(
  client: ApiClient,
  taskId: string,
  input: { expectedVersion: number; blockedReason: string },
) {
  const { data } = await client.requestEnvelope<TaskDto>(`${task(taskId)}/block/`, {
    method: "PATCH",
    body: { expected_version: input.expectedVersion, blocked_reason: input.blockedReason },
  });
  return data;
}

export async function unblockTask(client: ApiClient, taskId: string, input: { expectedVersion: number }) {
  const { data } = await client.requestEnvelope<TaskDto>(`${task(taskId)}/unblock/`, {
    method: "PATCH",
    body: { expected_version: input.expectedVersion },
  });
  return data;
}

/**
 * Toàn bộ task chưa lưu trữ trong một state (kể cả SUBTASK và task ngoài sprint), theo thứ tự
 * `sort_order`. Server tính vị trí theo cột đầy đủ này nên hàng xóm phải lấy từ đây, không từ Board.
 */
export async function listTaskOrderInState(client: ApiClient, projectId: string, stateId: string) {
  const rows = await collectAllPages((cursor) =>
    fetchPage<Pick<TaskDto, "id" | "sort_order">>(client, `${project(projectId)}/tasks/`, {
      cursor,
      params: { fields: "id,sort_order", state_id: stateId },
    }));
  return rows
    .slice()
    .sort((a, b) => a.sort_order - b.sort_order || a.id.localeCompare(b.id))
    .map((row) => row.id);
}
