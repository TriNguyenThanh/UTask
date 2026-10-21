import type { ApiClient } from "@/lib/api/client";
import type { GitHubLinkTypeDto, GitHubMemberMappingDto, GitHubVerificationRequestDto, ProjectRepositoryDto, TaskGitHubLinkDto } from "@/lib/api/work/dto";
import { ROOT } from "@/lib/api/work/endpoints.shared";

const member = (projectId: string, userId: string) =>
  `${ROOT}/projects/${encodeURIComponent(projectId)}/members/${encodeURIComponent(userId)}/github/`;

/**
 * Thành viên tự khai báo username GitHub (chỉ chính mình, dự án chưa lưu trữ). Không gửi `Idempotency-Key`:
 * PATCH này idempotent theo giá trị. Đã xác minh thì đổi username bị từ chối `INVALID_OPERATION`.
 */
export async function declareGitHubUsername(
  client: ApiClient,
  projectId: string,
  userId: string,
  githubUsername: string,
) {
  const { data } = await client.requestEnvelope<GitHubMemberMappingDto>(member(projectId, userId), {
    method: "PATCH",
    body: { github_username: githubUsername },
  });
  return data;
}

/** Chỉ Leader. Không body; `Idempotency-Key` là tùy chọn (server tự sinh khi thiếu). */
export async function requestGitHubVerification(
  client: ApiClient,
  projectId: string,
  userId: string,
  idempotencyKey?: string,
) {
  const { data } = await client.requestEnvelope<GitHubVerificationRequestDto>(
    `${member(projectId, userId)}request-verification/`,
    { method: "POST", idempotencyKey },
  );
  return data;
}

const repository = (projectId: string) => `${ROOT}/projects/${encodeURIComponent(projectId)}/github/repository/`;

export async function getProjectRepository(client: ApiClient, projectId: string) {
  const { data } = await client.requestEnvelope<ProjectRepositoryDto>(repository(projectId));
  return data;
}

export interface SelectRepositoryInput {
  githubRepoId: string;
  /** Sinh một lần cho mỗi ý định chọn repo; dùng cả làm `Idempotency-Key`. */
  operationId: string;
  expectedGeneration: number;
}

/**
 * Chỉ Leader. Backend trả 200 (xong) hoặc 202 (`status: "PENDING"`); `requestEnvelope` không trả
 * HTTP status nên nhận diện pending bằng `data.status`.
 */
export async function selectProjectRepository(client: ApiClient, projectId: string, input: SelectRepositoryInput) {
  const { data } = await client.requestEnvelope<ProjectRepositoryDto>(repository(projectId), {
    method: "POST",
    idempotencyKey: input.operationId,
    body: {
      github_repo_id: input.githubRepoId,
      operation_id: input.operationId,
      expected_connection_generation: input.expectedGeneration,
    },
  });
  return data;
}

/** Hết số lần hỏi lại mà kết nối vẫn `PENDING` của đúng thao tác này. */
export class RepositoryPendingTimeoutError extends Error {
  constructor() {
    super("Kết nối đang chờ xử lý, tải lại sau.");
    this.name = "RepositoryPendingTimeoutError";
  }
}

export interface SettleOptions {
  intervalMs?: number;
  maxPolls?: number;
  sleep?: (ms: number) => Promise<void>;
  /** Hủy vòng hỏi lại (ví dụ hộp thoại đóng): ném `signal.reason`, không gọi `GET` nữa. */
  signal?: AbortSignal;
}

/**
 * Chọn repo rồi hỏi lại tới khi hết `PENDING`. Dừng khi `status` khác `PENDING` hoặc `operation_id`
 * không còn là thao tác này (có thao tác khác ghi đè). Mặc định 15 lần x 2000ms.
 */
export async function selectProjectRepositoryAndWait(
  client: ApiClient,
  projectId: string,
  input: SelectRepositoryInput,
  {
    intervalMs = 2000,
    maxPolls = 15,
    sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
    signal,
  }: SettleOptions = {},
) {
  let current = await selectProjectRepository(client, projectId, input);
  for (let poll = 0; poll < maxPolls; poll += 1) {
    if (current.status !== "PENDING" || current.operation_id !== input.operationId) return current;
    await sleep(intervalMs);
    signal?.throwIfAborted();
    current = await getProjectRepository(client, projectId);
  }
  if (current.status !== "PENDING" || current.operation_id !== input.operationId) return current;
  throw new RepositoryPendingTimeoutError();
}

const links = (taskId: string) => `${ROOT}/tasks/${encodeURIComponent(taskId)}/github-links/`;

/** Danh sách không phân trang. Gồm cả link đã xóa mềm (`deleted_at`); UI lọc bỏ. */
export async function listTaskGitHubLinks(client: ApiClient, taskId: string) {
  const { data } = await client.requestEnvelope<TaskGitHubLinkDto[]>(links(taskId));
  return data;
}

/**
 * `github_ref_id` gửi nguyên văn: server tự bỏ `#` đầu và chuẩn hóa số của Pull Request.
 * `Idempotency-Key` là tùy chọn ở backend nhưng luôn gửi để thử lại không tạo trùng.
 */
export async function createTaskGitHubLink(
  client: ApiClient,
  taskId: string,
  input: { linkType: GitHubLinkTypeDto; githubRefId: string },
  idempotencyKey: string,
) {
  const { data } = await client.requestEnvelope<TaskGitHubLinkDto>(links(taskId), {
    method: "POST",
    idempotencyKey,
    body: { link_type: input.linkType, github_ref_id: input.githubRefId },
  });
  return data;
}

/** Không body; `Idempotency-Key` bắt buộc. Server từ chối khi `is_verified === false`. */
export async function confirmTaskGitHubLink(client: ApiClient, taskId: string, linkId: string, idempotencyKey: string) {
  const { data } = await client.requestEnvelope<TaskGitHubLinkDto>(`${links(taskId)}${encodeURIComponent(linkId)}/confirm/`, {
    method: "POST",
    idempotencyKey,
  });
  return data;
}

export async function deleteTaskGitHubLink(client: ApiClient, taskId: string, linkId: string) {
  const { data } = await client.requestEnvelope<{ unlinked_id: string }>(`${links(taskId)}${encodeURIComponent(linkId)}/`, {
    method: "DELETE",
  });
  return data;
}
