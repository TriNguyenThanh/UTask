import type { ApiClient } from "@/lib/api/client";
import type { GitHubMemberMappingDto, GitHubVerificationRequestDto } from "@/lib/api/work/dto";
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
