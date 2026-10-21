/** DTO của Integration Service (gateway `/api/integrations/`). Giữ nguyên tên field snake_case của backend. */

export type GitHubAccountStatus = "LINKED" | "UNLINKED" | "REVOKED";
export type GitHubAuthorizationStatus = "ACTIVE" | "REAUTH_REQUIRED" | "REVOKED" | "NOT_AUTHORIZED";

export interface GitHubAccountDto {
  user_id: string;
  status: GitHubAccountStatus;
  authorization_status: GitHubAuthorizationStatus;
  github_user_id: string | null;
  github_username: string | null;
  verified_at: string | null;
  linked_at: string | null;
  revoked_at: string | null;
  source_version: number;
}

export interface GitHubAuthorizationStartDto {
  authorization_url: string;
  expires_at: string;
}

export interface GitHubInstallationStartDto {
  installation_url: string;
  expires_at: string;
}

export interface GitHubInstallationDto {
  installation_id: string;
  app_id: string;
  account: { id: string; login: string; type: string };
  repository_selection: string;
  suspended_at: string | null;
}

export type GitHubInstallationCompleteDto =
  | { status: "PENDING_APPROVAL"; installation_id: string }
  | ({ status: "ACTIVE" } & GitHubInstallationDto);

export interface GitHubRepositoryDto {
  repository_id: string;
  name: string;
  full_name: string;
  private: boolean;
}

export interface GitHubPageDto<T> {
  items: T[];
  next_page: number | null;
}

export interface GitHubAuthorizationCompleteBody {
  code: string;
  state: string;
}

export interface GitHubInstallationCompleteBody {
  state: string;
  installation_id: string;
  setup_action: string;
}
