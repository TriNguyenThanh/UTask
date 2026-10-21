import type { ApiClient } from "@/lib/api/client";
import type {
  GitHubAccountDto,
  GitHubAuthorizationCompleteBody,
  GitHubAuthorizationStartDto,
  GitHubInstallationCompleteBody,
  GitHubInstallationCompleteDto,
  GitHubInstallationDto,
  GitHubInstallationStartDto,
  GitHubPageDto,
  GitHubRepositoryDto,
} from "@/lib/api/integration/dto";

/** Gateway chuyển nguyên đường dẫn `/api/integrations/...` cho Integration Service. */
const ROOT = "/api/integrations/api/v1/github";

export interface GitHubPageParams {
  page?: number;
  perPage?: number;
}

function pageQuery({ page = 1, perPage = 100 }: GitHubPageParams): string {
  return `?page=${page}&per_page=${perPage}`;
}

export async function getGitHubAccount(client: ApiClient): Promise<GitHubAccountDto> {
  const { data } = await client.requestEnvelope<GitHubAccountDto>(`${ROOT}/account`);
  return data;
}

export async function unlinkGitHubAccount(client: ApiClient): Promise<GitHubAccountDto> {
  const { data } = await client.requestEnvelope<GitHubAccountDto>(`${ROOT}/account`, { method: "DELETE" });
  return data;
}

/** Route `start` từ chối mọi body và query: KHÔNG truyền `body`. */
export async function startGitHubAuthorization(client: ApiClient): Promise<GitHubAuthorizationStartDto> {
  const { data } = await client.requestEnvelope<GitHubAuthorizationStartDto>(`${ROOT}/authorizations/start`, {
    method: "POST",
  });
  return data;
}

/** `complete` chỉ nhận đúng `{code, state}`; thiếu hoặc thừa key đều bị từ chối. */
export async function completeGitHubAuthorization(
  client: ApiClient,
  { code, state }: GitHubAuthorizationCompleteBody,
): Promise<GitHubAccountDto> {
  const { data } = await client.requestEnvelope<GitHubAccountDto>(`${ROOT}/authorizations/complete`, {
    method: "POST",
    body: { code, state },
  });
  return data;
}

/** Route `start` từ chối mọi body và query: KHÔNG truyền `body`. */
export async function startGitHubInstallation(client: ApiClient): Promise<GitHubInstallationStartDto> {
  const { data } = await client.requestEnvelope<GitHubInstallationStartDto>(`${ROOT}/installations/start`, {
    method: "POST",
  });
  return data;
}

/** `complete` chỉ nhận đúng `{state, installation_id, setup_action}`. */
export async function completeGitHubInstallation(
  client: ApiClient,
  { state, installation_id, setup_action }: GitHubInstallationCompleteBody,
): Promise<GitHubInstallationCompleteDto> {
  const { data } = await client.requestEnvelope<GitHubInstallationCompleteDto>(`${ROOT}/installations/complete`, {
    method: "POST",
    body: { state, installation_id, setup_action },
  });
  return data;
}

export async function listGitHubInstallations(
  client: ApiClient,
  params: GitHubPageParams = {},
): Promise<GitHubPageDto<GitHubInstallationDto>> {
  const { data } = await client.requestEnvelope<GitHubPageDto<GitHubInstallationDto>>(
    `${ROOT}/installations${pageQuery(params)}`,
  );
  return data;
}

export async function listGitHubRepositories(
  client: ApiClient,
  installationId: string,
  params: GitHubPageParams = {},
): Promise<GitHubPageDto<GitHubRepositoryDto>> {
  const { data } = await client.requestEnvelope<GitHubPageDto<GitHubRepositoryDto>>(
    `${ROOT}/installations/${encodeURIComponent(installationId)}/repositories${pageQuery(params)}`,
  );
  return data;
}
