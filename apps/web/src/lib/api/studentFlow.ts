import type { ApiClient } from "@/lib/api/client";
import type { CourseDetail } from "@/features/courses/types";
import type {
  ProjectCode,
  ProjectSummary,
  ProjectWorkspace,
  IssueDetail,
} from "@/features/projects/types";
import type {
  AccountSettings,
  StudentNotification,
} from "@/features/notifications/types";

const WORK_ROOT = "/api/work/api/v1";

export interface ProjectAiSettings {
  projectId: string;
  myRole: "leader" | "member";
  ai: {
    provider: string;
    keyConfigured: boolean;
    /** Masked hint, e.g. "sk-…f4a2". Never the raw key. */
    keyHint: string | null;
    lastCheckedAt: string | null;
    status:
      | "not-configured"
      | "checking"
      | "connected"
      | "invalid-key"
      | "provider-unavailable"
      | "quota-exceeded";
  };
}

export function courseDetailRequest(
  client: ApiClient,
  courseId: string,
): Promise<CourseDetail> {
  return client.request<CourseDetail>(`${WORK_ROOT}/courses/${courseId}`);
}

export function createTeamRequest(
  client: ApiClient,
  courseId: string,
  input: { teamName: string; description: string; neededSkills: string; maxMembers: number },
): Promise<void> {
  return client.request(`${WORK_ROOT}/courses/${courseId}/teams`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function projectsRequest(client: ApiClient): Promise<ProjectSummary[]> {
  return client.request<ProjectSummary[]>(`${WORK_ROOT}/projects`);
}

export function projectWorkspaceRequest(
  client: ApiClient,
  projectId: string,
): Promise<ProjectWorkspace> {
  return client.request<ProjectWorkspace>(`${WORK_ROOT}/projects/${projectId}`);
}

export function issueDetailRequest(
  client: ApiClient,
  projectId: string,
  issueKey: string,
): Promise<IssueDetail> {
  return client.request<IssueDetail>(
    `${WORK_ROOT}/projects/${projectId}/issues/${issueKey}`,
  );
}

export function projectCodeRequest(
  client: ApiClient,
  projectId: string,
): Promise<ProjectCode> {
  return client.request<ProjectCode>(`${WORK_ROOT}/projects/${projectId}/code`);
}

export function projectAiSettingsRequest(
  client: ApiClient,
  projectId: string,
): Promise<ProjectAiSettings> {
  return client.request<ProjectAiSettings>(
    `${WORK_ROOT}/projects/${projectId}/settings`,
  );
}

export function saveAiKeyRequest(
  client: ApiClient,
  projectId: string,
  provider: string,
  apiKey: string,
): Promise<void> {
  return client.request(`${WORK_ROOT}/projects/${projectId}/settings/ai-key`, {
    method: "PUT",
    body: JSON.stringify({ provider, apiKey }),
  });
}

export function notificationsRequest(
  client: ApiClient,
): Promise<StudentNotification[]> {
  return client.request<StudentNotification[]>(`${WORK_ROOT}/notifications`);
}

export function markNotificationReadRequest(
  client: ApiClient,
  id: string,
): Promise<void> {
  return client.request(`${WORK_ROOT}/notifications/${id}/read`, {
    method: "POST",
  });
}

export function markAllNotificationsReadRequest(client: ApiClient): Promise<void> {
  return client.request(`${WORK_ROOT}/notifications/read-all`, { method: "POST" });
}

export function accountSettingsRequest(
  client: ApiClient,
): Promise<AccountSettings> {
  return client.request<AccountSettings>(`${WORK_ROOT}/me/settings`);
}

export function updateAccountSettingsRequest(
  client: ApiClient,
  input: { fullName: string; cohortClass: string; faculty: string; phone: string },
): Promise<void> {
  return client.request(`${WORK_ROOT}/me/settings`, {
    method: "PATCH",
    body: JSON.stringify(input),
  });
}

export function disconnectGitHubRequest(client: ApiClient): Promise<void> {
  return client.request(`${WORK_ROOT}/me/github/disconnect`, { method: "POST" });
}