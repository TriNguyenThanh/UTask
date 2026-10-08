import { myWorkKeys } from "@/features/my-work/queries";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useApiClient } from "@/lib/api/ApiClientProvider";
import {
  accountSettingsRequest,
  courseDetailRequest,
  createTeamRequest,
  disconnectGitHubRequest,
  issueDetailRequest,
  markAllNotificationsReadRequest,
  markNotificationReadRequest,
  notificationsRequest,
  projectAiSettingsRequest,
  projectCodeRequest,
  projectsRequest,
  projectWorkspaceRequest,
  saveAiKeyRequest,
  updateAccountSettingsRequest,
} from "@/lib/api/studentFlow";

export const studentFlowKeys = {
  course: (courseId: string) => ["courses", courseId] as const,
  projects: ["projects"] as const,
  project: (projectId: string) => ["projects", projectId] as const,
  issue: (projectId: string, issueKey: string) =>
    ["projects", projectId, "issues", issueKey] as const,
  code: (projectId: string) => ["projects", projectId, "code"] as const,
  aiSettings: (projectId: string) =>
    ["projects", projectId, "settings", "ai"] as const,
  notifications: ["notifications"] as const,
  settings: ["settings", "account"] as const,
};

export function useCourseDetail(courseId: string) {
  const client = useApiClient();
  return useQuery({
    queryKey: studentFlowKeys.course(courseId),
    queryFn: () => courseDetailRequest(client, courseId),
  });
}

export function useCreateTeam(courseId: string) {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: {
      teamName: string;
      description: string;
      neededSkills: string;
      maxMembers: number;
    }) => createTeamRequest(client, courseId, input),
    onSuccess: () => {
      // Course detail, Home overview and the projects list all embed team
      // membership; refetch them together so the UI reflects the new team
      // without a reload.
      queryClient.invalidateQueries({
        queryKey: studentFlowKeys.course(courseId),
      });
      queryClient.invalidateQueries({ queryKey: myWorkKeys.overview });
      queryClient.invalidateQueries({ queryKey: studentFlowKeys.projects });
    },
  });
}

export function useProjects() {
  const client = useApiClient();
  return useQuery({
    queryKey: studentFlowKeys.projects,
    queryFn: () => projectsRequest(client),
  });
}

function isHttpErrorStatus(error: unknown, status: number): boolean {
  return (
    typeof error === "object" &&
    error !== null &&
    "status" in error &&
    typeof error.status === "number" &&
    error.status === status
  );
}

export function useProjectWorkspace(projectId: string) {
  const client = useApiClient();
  return useQuery({
    queryKey: studentFlowKeys.project(projectId),
    queryFn: () => projectWorkspaceRequest(client, projectId),
    retry: (failureCount, error) => {
      if (isHttpErrorStatus(error, 403)) return false;
      return failureCount < 1;
    },
  });
}

export function useIssueDetail(projectId: string, issueKey: string | null) {
  const client = useApiClient();
  return useQuery({
    queryKey: studentFlowKeys.issue(projectId, issueKey ?? ""),
    queryFn: () => issueDetailRequest(client, projectId, issueKey as string),
    enabled: issueKey !== null,
    retry: false,
  });
}

export function useProjectCode(projectId: string) {
  const client = useApiClient();
  return useQuery({
    queryKey: studentFlowKeys.code(projectId),
    queryFn: () => projectCodeRequest(client, projectId),
  });
}

export function useProjectAiSettings(projectId: string) {
  const client = useApiClient();
  return useQuery({
    queryKey: studentFlowKeys.aiSettings(projectId),
    queryFn: () => projectAiSettingsRequest(client, projectId),
    retry: (failureCount, error) => {
      if ((error as { status?: number }).status === 403) return false;
      return failureCount < 1;
    },
  });
}

export function useSaveAiKey(projectId: string) {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { provider: string; apiKey: string }) =>
      saveAiKeyRequest(client, projectId, input.provider, input.apiKey),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: studentFlowKeys.aiSettings(projectId),
      });
    },
  });
}

export function useNotifications() {
  const client = useApiClient();
  return useQuery({
    queryKey: studentFlowKeys.notifications,
    queryFn: () => notificationsRequest(client),
  });
}

export function useMarkNotificationRead() {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => markNotificationReadRequest(client, id),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: studentFlowKeys.notifications,
      });
    },
  });
}

export function useMarkAllNotificationsRead() {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => markAllNotificationsReadRequest(client),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: studentFlowKeys.notifications,
      });
    },
  });
}

export function useAccountSettings() {
  const client = useApiClient();
  return useQuery({
    queryKey: studentFlowKeys.settings,
    queryFn: () => accountSettingsRequest(client),
  });
}

export function useUpdateAccountSettings() {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: {
      fullName: string;
      cohortClass: string;
      faculty: string;
      phone: string;
    }) => updateAccountSettingsRequest(client, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: studentFlowKeys.settings });
    },
  });
}

export function useDisconnectGitHub() {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => disconnectGitHubRequest(client),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: studentFlowKeys.settings });
      // Home reads GitHub sync state from /my-work/github — refresh it too.
      queryClient.invalidateQueries({ queryKey: myWorkKeys.github });
    },
  });
}