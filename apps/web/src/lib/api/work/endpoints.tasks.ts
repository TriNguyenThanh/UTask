import type { ApiClient } from "@/lib/api/client";
import { collectAllPages } from "@/lib/api/pagination";
import type {
  EpicDto,
  EpicStatusDto,
  LabelDto,
  RelationTypeDto,
  StateDto,
  TaskDto,
  TaskPriorityDto,
  TaskScopeDto,
} from "@/lib/api/work/dto";
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
export async function getTask(client: ApiClient, taskId: string, expand = "state,epic,labels,assignees,subtasks,relations") {
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

/** Task đã lưu trữ hoặc đã xóa mềm (danh sách mặc định chỉ có task đang hoạt động). */
export function listTasksInScope(client: ApiClient, projectId: string, scope: TaskScopeDto) {
  return collectAllPages((cursor) =>
    fetchPage<TaskDto>(client, `${project(projectId)}/tasks/`, { cursor, params: { status: scope } }));
}

/** Lưu trữ/mở lại/xóa mềm/khôi phục: chỉ Leader, không gửi `Idempotency-Key`. `delete` xóa cả cây con. */
export type TaskLifecycleAction = "archive" | "unarchive" | "delete" | "restore";

export async function changeTaskLifecycle(
  client: ApiClient,
  taskId: string,
  action: TaskLifecycleAction,
  expectedVersion: number,
) {
  const { data } = await client.requestEnvelope<TaskDto>(
    action === "delete" ? `${task(taskId)}/` : `${task(taskId)}/${action}/`,
    { method: action === "delete" ? "DELETE" : "POST", body: { expected_version: expectedVersion } },
  );
  return data;
}

export async function setTaskLabels(
  client: ApiClient,
  taskId: string,
  input: { expectedVersion: number; action: "ADD" | "REMOVE"; labelIds: string[] },
) {
  const { data } = await client.requestEnvelope<TaskDto>(`${task(taskId)}/labels/`, {
    method: "POST",
    body: { expected_version: input.expectedVersion, action: input.action, label_ids: input.labelIds },
  });
  return data;
}

export async function createRelation(
  client: ApiClient,
  taskId: string,
  input: { relatedTaskId: string; relationType: RelationTypeDto },
) {
  const { data } = await client.requestEnvelope<{ id: string }>(`${task(taskId)}/relations/`, {
    method: "POST",
    body: { related_task_id: input.relatedTaskId, relation_type: input.relationType },
  });
  return data;
}

export async function deleteRelation(client: ApiClient, taskId: string, relationId: string) {
  const { data } = await client.requestEnvelope<{ deleted_relation_id: string }>(
    `${task(taskId)}/relations/${encodeURIComponent(relationId)}/`,
    { method: "DELETE" },
  );
  return data;
}

export interface EpicInput {
  name?: string;
  description?: string;
  leadUserId?: string | null;
  status?: EpicStatusDto;
  startDate?: string | null;
  targetDate?: string | null;
}

function epicBody(input: EpicInput): Record<string, unknown> {
  const body: Record<string, unknown> = {};
  if (input.name !== undefined) body.name = input.name;
  if (input.description !== undefined) body.description = input.description;
  if (input.leadUserId !== undefined) body.lead_user_id = input.leadUserId;
  if (input.status !== undefined) body.status = input.status;
  if (input.startDate !== undefined) body.start_date = input.startDate;
  if (input.targetDate !== undefined) body.target_date = input.targetDate;
  return body;
}

const epics = (projectId: string) => `${ROOT}${project(projectId)}/epics/`;
const labels = (projectId: string) => `${ROOT}${project(projectId)}/labels/`;

export async function createEpic(client: ApiClient, projectId: string, input: EpicInput & { name: string }) {
  const { data } = await client.requestEnvelope<EpicDto>(epics(projectId), { method: "POST", body: epicBody(input) });
  return data;
}

/** Epic không có `version`: backend ghi đè theo khóa gửi lên. */
export async function patchEpic(client: ApiClient, projectId: string, epicId: string, input: EpicInput) {
  const { data } = await client.requestEnvelope<EpicDto>(`${epics(projectId)}${encodeURIComponent(epicId)}/`, {
    method: "PATCH",
    body: epicBody(input),
  });
  return data;
}

export async function deleteEpic(client: ApiClient, projectId: string, epicId: string) {
  const { data } = await client.requestEnvelope<{ deleted_epic_id: string }>(
    `${epics(projectId)}${encodeURIComponent(epicId)}/`,
    { method: "DELETE" },
  );
  return data;
}

export interface LabelInput {
  name: string;
  /** `#RRGGBB`. */
  color: string;
  description?: string | null;
}

export async function createLabel(client: ApiClient, projectId: string, input: LabelInput) {
  const { data } = await client.requestEnvelope<LabelDto>(labels(projectId), { method: "POST", body: labelBody(input) });
  return data;
}

function labelBody(input: Partial<LabelInput>): Record<string, unknown> {
  const body: Record<string, unknown> = {};
  if (input.name !== undefined) body.name = input.name;
  if (input.color !== undefined) body.color = input.color;
  if (input.description !== undefined) body.description = input.description;
  return body;
}

export async function patchLabel(client: ApiClient, projectId: string, labelId: string, input: Partial<LabelInput>) {
  const { data } = await client.requestEnvelope<LabelDto>(`${labels(projectId)}${encodeURIComponent(labelId)}/`, {
    method: "PATCH",
    body: labelBody(input),
  });
  return data;
}

/** Xóa nhãn gỡ nó khỏi mọi task nên mọi cache task phải làm mới. */
export async function deleteLabel(client: ApiClient, projectId: string, labelId: string) {
  const { data } = await client.requestEnvelope<{ deleted_label_id: string }>(
    `${labels(projectId)}${encodeURIComponent(labelId)}/`,
    { method: "DELETE" },
  );
  return data;
}
