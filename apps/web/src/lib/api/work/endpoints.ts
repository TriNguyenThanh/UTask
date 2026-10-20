import type { ApiClient, ApiEnvelopeResult } from "@/lib/api/client";
import { collectAllPages, DEFAULT_MAX_PAGES, MAX_PAGE_SIZE, type ListMeta } from "@/lib/api/pagination";
import type {
  ProjectDto,
  ProjectMemberDto,
  ProjectMemberStatus,
  ProjectStatusFilter,
} from "@/lib/api/work/dto";

const ROOT = "/api/work";

export interface WorkListMeta extends ListMeta {
  scope?: { partial: boolean; source: "WORK_MEMBERSHIP"; teacher_scope: "UNAVAILABLE" };
}

export interface ProjectListResult {
  projects: ProjectDto[];
  /** Work không hỏi được Classroom nên thiếu dự án của lớp giảng viên phụ trách. */
  partial: boolean;
}

export interface CreateProjectInput {
  classroomGroupId: string;
  identifier: string;
  name: string;
  description: string;
  targetGoals: string;
  startDate: string | null;
  endDate: string | null;
}

export interface PatchProjectInput {
  name?: string;
  description?: string;
  targetGoals?: string;
  startDate?: string | null;
  endDate?: string | null;
}

interface PageQuery {
  cursor?: string | null;
  pageSize?: number;
  status?: string;
}

function listUrl(path: string, { cursor, pageSize = MAX_PAGE_SIZE, status }: PageQuery) {
  const params = new URLSearchParams({ page_size: String(pageSize) });
  if (cursor) params.set("cursor", cursor);
  if (status) params.set("status", status);
  return `${ROOT}${path}?${params.toString()}`;
}

function fetchPage<T>(client: ApiClient, path: string, query: PageQuery) {
  return client.requestEnvelope<T[], WorkListMeta>(listUrl(path, query));
}

/**
 * Tải hết dự án của tôi. Không truyền `classroom_group_id`: sinh viên truyền sẽ nhận 403
 * (B16), còn giảng viên tự lọc phía client sau khi tải tất cả.
 */
export async function listProjects(client: ApiClient, status: ProjectStatusFilter): Promise<ProjectListResult> {
  const projects: ProjectDto[] = [];
  let partial = false;
  let cursor: string | null = null;

  for (let page = 0; page < DEFAULT_MAX_PAGES; page += 1) {
    const result: ApiEnvelopeResult<ProjectDto[], WorkListMeta> = await fetchPage<ProjectDto>(client, "/projects/", { cursor, status });
    const { data, meta } = result;
    projects.push(...(data ?? []));
    // `meta.scope` chỉ có ở trang đầu.
    if (page === 0) partial = meta?.scope?.partial === true;

    const pagination = meta?.pagination;
    if (!pagination?.has_next || pagination.next_cursor === null) {
      return { projects, partial };
    }
    cursor = pagination.next_cursor;
  }

  throw new Error("Danh sách quá dài để tải hết.");
}

export async function getProject(client: ApiClient, projectId: string) {
  const { data } = await client.requestEnvelope<ProjectDto>(`${ROOT}/projects/${encodeURIComponent(projectId)}/`);
  return data;
}

export function listProjectMembers(client: ApiClient, projectId: string, status?: ProjectMemberStatus) {
  return collectAllPages((cursor) =>
    fetchPage<ProjectMemberDto>(client, `/projects/${encodeURIComponent(projectId)}/members/`, { cursor, status }));
}

/** `Idempotency-Key` bắt buộc; sinh một lần cho mỗi ý định của người dùng. */
export async function createProject(client: ApiClient, input: CreateProjectInput & { idempotencyKey: string }) {
  const { data } = await client.requestEnvelope<ProjectDto>(`${ROOT}/projects/`, {
    method: "POST",
    body: {
      classroom_group_id: input.classroomGroupId,
      identifier: input.identifier,
      name: input.name,
      description: input.description,
      target_goals: input.targetGoals,
      start_date: input.startDate,
      end_date: input.endDate,
      // OpenAPI chỉ khai báo object tự do, chưa có cấu trúc (B17).
      tech_stack: {},
    },
    idempotencyKey: input.idempotencyKey,
  });
  return data;
}

/** Chỉ gửi các khóa `!== undefined` cộng `expected_version`. Backend không dedupe PATCH nên không gửi `Idempotency-Key`. */
export async function patchProject(
  client: ApiClient,
  projectId: string,
  input: PatchProjectInput & { expectedVersion: number },
) {
  const body: Record<string, unknown> = { expected_version: input.expectedVersion };
  if (input.name !== undefined) body.name = input.name;
  if (input.description !== undefined) body.description = input.description;
  if (input.targetGoals !== undefined) body.target_goals = input.targetGoals;
  if (input.startDate !== undefined) body.start_date = input.startDate;
  if (input.endDate !== undefined) body.end_date = input.endDate;

  const { data } = await client.requestEnvelope<ProjectDto>(`${ROOT}/projects/${encodeURIComponent(projectId)}/`, {
    method: "PATCH",
    body,
  });
  return data;
}

/**
 * Không gửi `Idempotency-Key`: backend không đăng ký receipt cho hai path này. Gọi lại khi
 * trạng thái đã đúng trả 200 nhưng `version` không tăng, nên người gọi đọc `version` từ phản hồi.
 */
export async function setProjectArchived(
  client: ApiClient,
  projectId: string,
  input: { archived: boolean; expectedVersion: number },
) {
  const action = input.archived ? "archive" : "unarchive";
  const { data } = await client.requestEnvelope<ProjectDto>(
    `${ROOT}/projects/${encodeURIComponent(projectId)}/${action}/`,
    { method: "POST", body: { expected_version: input.expectedVersion } },
  );
  return data;
}
