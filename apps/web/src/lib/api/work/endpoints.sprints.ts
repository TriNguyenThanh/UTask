import type { ApiClient } from "@/lib/api/client";
import { collectAllPages } from "@/lib/api/pagination";
import type {
  SprintBurndownDto,
  SprintCloseResultDto,
  SprintDto,
  SprintProgressDto,
  SprintScopeResultDto,
} from "@/lib/api/work/dto";
import { fetchPage, ROOT } from "@/lib/api/work/endpoints.shared";

const sprint = (sprintId: string) => `${ROOT}/sprints/${encodeURIComponent(sprintId)}`;

export function listSprints(client: ApiClient, projectId: string) {
  return collectAllPages((cursor) =>
    fetchPage<SprintDto>(client, `/projects/${encodeURIComponent(projectId)}/sprints/`, { cursor }));
}

/** Đọc lại `version` ngay trước khi ghi: workspace không giữ version của sprint. */
export async function getSprint(client: ApiClient, sprintId: string) {
  const { data } = await client.requestEnvelope<SprintDto>(`${sprint(sprintId)}/`);
  return data;
}

export interface SprintFieldsInput {
  name?: string;
  goal?: string;
  startDate?: string | null;
  endDate?: string | null;
}

function sprintBody(input: SprintFieldsInput): Record<string, unknown> {
  const body: Record<string, unknown> = {};
  if (input.name !== undefined) body.name = input.name;
  if (input.goal !== undefined) body.goal = input.goal;
  if (input.startDate !== undefined) body.start_date = input.startDate;
  if (input.endDate !== undefined) body.end_date = input.endDate;
  return body;
}

/** Chỉ Leader. Không gửi `Idempotency-Key`: backend không đăng ký receipt cho tạo sprint. */
export async function createSprint(client: ApiClient, projectId: string, input: SprintFieldsInput & { name: string }) {
  const { data } = await client.requestEnvelope<SprintDto>(`${ROOT}/projects/${encodeURIComponent(projectId)}/sprints/`, {
    method: "POST",
    body: sprintBody(input),
  });
  return data;
}

export async function patchSprint(
  client: ApiClient,
  sprintId: string,
  input: SprintFieldsInput & { expectedVersion: number },
) {
  const { data } = await client.requestEnvelope<SprintDto>(`${sprint(sprintId)}/`, {
    method: "PATCH",
    body: { expected_version: input.expectedVersion, ...sprintBody(input) },
  });
  return data;
}

/** `Idempotency-Key` bắt buộc. Cần đủ hai ngày; dự án đã có sprint đang chạy thì 409 `ACTIVE_SPRINT_EXISTS`. */
export async function startSprint(
  client: ApiClient,
  projectId: string,
  sprintId: string,
  input: { expectedVersion: number; idempotencyKey: string },
) {
  const { data } = await client.requestEnvelope<SprintDto>(
    `${ROOT}/projects/${encodeURIComponent(projectId)}/sprints/${encodeURIComponent(sprintId)}/start/`,
    { method: "POST", body: { expected_version: input.expectedVersion }, idempotencyKey: input.idempotencyKey },
  );
  return data;
}

/**
 * Thêm/bớt task khỏi sprint. `Idempotency-Key` bắt buộc. Sprint `ACTIVE` bắt buộc `scopeChangeReason`
 * (422 `SCOPE_CHANGE_REASON_REQUIRED`).
 */
export async function setSprintScope(
  client: ApiClient,
  sprintId: string,
  input: {
    expectedVersion: number;
    action: "ADD" | "REMOVE";
    taskIds: string[];
    scopeChangeReason?: string;
    idempotencyKey: string;
  },
) {
  const body: Record<string, unknown> = {
    expected_version: input.expectedVersion,
    action: input.action,
    task_ids: input.taskIds,
  };
  if (input.scopeChangeReason !== undefined) body.scope_change_reason = input.scopeChangeReason;
  const { data } = await client.requestEnvelope<SprintScopeResultDto>(`${sprint(sprintId)}/tasks/`, {
    method: "POST",
    body,
    idempotencyKey: input.idempotencyKey,
  });
  return data;
}

/** `Idempotency-Key` bắt buộc. `targetSprintId` là sprint DRAFT nhận task chưa xong; `null` trả chúng về backlog. */
export async function closeSprint(
  client: ApiClient,
  sprintId: string,
  input: { expectedVersion: number; targetSprintId: string | null; idempotencyKey: string },
) {
  const { data } = await client.requestEnvelope<SprintCloseResultDto>(`${sprint(sprintId)}/close/`, {
    method: "POST",
    body: { expected_version: input.expectedVersion, target_sprint_id: input.targetSprintId },
    idempotencyKey: input.idempotencyKey,
  });
  return data;
}

export async function getSprintProgress(client: ApiClient, sprintId: string) {
  const { data } = await client.requestEnvelope<SprintProgressDto>(`${sprint(sprintId)}/progress/`);
  return data;
}

export async function getSprintBurndown(client: ApiClient, sprintId: string) {
  const { data } = await client.requestEnvelope<SprintBurndownDto>(`${sprint(sprintId)}/burndown/`);
  return data;
}
