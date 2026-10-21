import { useSyncExternalStore } from "react";
import { useAuth } from "@/features/auth/AuthProvider";
import { isRealService } from "@/lib/config/services";
import { notificationPageRequest, unreadNotificationCountRequest } from "@/features/notifications/api";
import { myWorkKeys } from "@/features/my-work/queries";
import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
} from "@tanstack/react-query";
import { toast } from "sonner";

import { issueWriteErrorMessage } from "@/features/projects/lib/moveErrors";
import { applyIssuePatch, applyServerVersion, type IssuePatch } from "@/features/projects/lib/optimistic";
import type { IssueDetail, ProjectWorkspace } from "@/features/projects/types";

import { useApiClient } from "@/lib/api/ApiClientProvider";
import {
  accountSettingsRequest,
  courseDetailRequest,
  createTeamRequest,
  disconnectGitHubRequest,
  issueDetailRequest,
  markAllNotificationsReadRequest,
  markNotificationReadRequest,
  moveIssueRequest,
  setIssueBlockedRequest,
  type MoveIssueInput,
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

/** `enabled` is false for viewers who can never read project settings (not the leader). */
export function useProjectAiSettings(projectId: string, enabled = true) {
  const client = useApiClient();
  return useQuery({
    queryKey: studentFlowKeys.aiSettings(projectId),
    queryFn: () => projectAiSettingsRequest(client, projectId),
    enabled,
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

function subscribeVisibility(callback: () => void) {
  document.addEventListener("visibilitychange", callback);
  return () => document.removeEventListener("visibilitychange", callback);
}

function useVisibleTab() {
  return useSyncExternalStore(subscribeVisibility, () => document.visibilityState === "visible");
}

export function useNotifications() {
  const client = useApiClient();
  const { user } = useAuth();
  const live = isRealService("notifications");
  const visible = useVisibleTab();
  const query = useInfiniteQuery({
    queryKey: [...studentFlowKeys.notifications, user?.id, live, "list"],
    initialPageParam: "",
    queryFn: async ({ pageParam, signal }) => live
      ? notificationPageRequest(client, pageParam, signal)
      : { results: await notificationsRequest(client), next: null },
    getNextPageParam: (lastPage) => lastPage.next ?? undefined,
    enabled: !!user,
    refetchInterval: live && visible ? 30_000 : false,
    refetchIntervalInBackground: false,
  });
  return { ...query, data: query.data?.pages.flatMap((page) => page.results) };
}

export function useUnreadNotificationCount() {
  const visible = useVisibleTab();
  const client = useApiClient();
  const { user } = useAuth();
  const live = isRealService("notifications");
  return useQuery({
    queryKey: [...studentFlowKeys.notifications, user?.id, live, "unread"],
    queryFn: ({ signal }) => unreadNotificationCountRequest(client, signal),
    enabled: !!user && live,
    refetchInterval: visible ? 30_000 : false,
    refetchIntervalInBackground: false,
  });
}

export function useMarkNotificationRead() {
  const client = useApiClient();
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const live = isRealService("notifications");
  return useMutation({
    mutationFn: (id: string) => live
      ? client.request(`/api/notifications/${encodeURIComponent(id)}/read`, { method: "POST" })
      : markNotificationReadRequest(client, id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: [...studentFlowKeys.notifications, user?.id, live] });
    },
  });
}

export function useMarkAllNotificationsRead() {
  const client = useApiClient();
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const live = isRealService("notifications");
  return useMutation({
    mutationFn: () => live
      ? client.request("/api/notifications/read-all", { method: "POST" })
      : markAllNotificationsReadRequest(client),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: [...studentFlowKeys.notifications, user?.id, live] });
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
    },
  });
}
/* ------------------------------------------------------------------ */
/* Issue writes: move and blocked (Demo MSW)                           */
/* ------------------------------------------------------------------ */

interface IssueSnapshot {
  workspace: ProjectWorkspace | undefined;
  detail: IssueDetail | undefined;
}

/**
 * Shows `patch` in the cache right away and returns what to put back on
 * failure. Called from `onMutate` only, so nothing is written while a card is
 * still being dragged across columns.
 */
async function applyOptimisticIssue(
  queryClient: QueryClient,
  projectId: string,
  issueKey: string,
  patch: IssuePatch,
): Promise<IssueSnapshot> {
  const projectKey = studentFlowKeys.project(projectId);
  const issueQueryKey = studentFlowKeys.issue(projectId, issueKey);
  await Promise.all([
    queryClient.cancelQueries({ queryKey: projectKey, exact: true }),
    queryClient.cancelQueries({ queryKey: issueQueryKey, exact: true }),
  ]);
  const snapshot: IssueSnapshot = {
    workspace: queryClient.getQueryData<ProjectWorkspace>(projectKey),
    detail: queryClient.getQueryData<IssueDetail>(issueQueryKey),
  };
  queryClient.setQueryData<ProjectWorkspace>(projectKey, (current) =>
    current ? applyIssuePatch(current, issueKey, patch) : current,
  );
  queryClient.setQueryData<IssueDetail>(issueQueryKey, (current) =>
    current ? { ...current, issue: { ...current.issue, ...patch } } : current,
  );
  return snapshot;
}

function restoreIssue(
  queryClient: QueryClient,
  projectId: string,
  issueKey: string,
  snapshot: IssueSnapshot | undefined,
) {
  if (!snapshot) return;
  queryClient.setQueryData(studentFlowKeys.project(projectId), snapshot.workspace);
  queryClient.setQueryData(studentFlowKeys.issue(projectId, issueKey), snapshot.detail);
}

/** Keeps the version the server just assigned, so a queued write after this one is not stale. */
function recordServerVersion(
  queryClient: QueryClient,
  projectId: string,
  issueKey: string,
  version: number,
) {
  queryClient.setQueryData<ProjectWorkspace>(studentFlowKeys.project(projectId), (current) =>
    current ? applyServerVersion(current, issueKey, version) : current,
  );
  queryClient.setQueryData<IssueDetail>(studentFlowKeys.issue(projectId, issueKey), (current) =>
    current ? { ...current, issue: { ...current.issue, version } } : current,
  );
}

function currentIssueVersion(
  queryClient: QueryClient,
  projectId: string,
  issueKey: string,
): number {
  const workspace = queryClient.getQueryData<ProjectWorkspace>(studentFlowKeys.project(projectId));
  return workspace?.issues.find((issue) => issue.key === issueKey)?.version ?? 0;
}

function invalidateAfterIssueWrite(queryClient: QueryClient, projectId: string, issueKey: string) {
  void queryClient.invalidateQueries({ queryKey: studentFlowKeys.project(projectId), exact: true });
  void queryClient.invalidateQueries({
    queryKey: studentFlowKeys.issue(projectId, issueKey),
    exact: true,
  });
  void queryClient.invalidateQueries({ queryKey: myWorkKeys.overview });
}

export type MoveIssueVariables = { issueKey: string } & Omit<MoveIssueInput, "version">;

/**
 * Moves an issue (status, sprint, position). Writes queue per project so two
 * drops in a row reach the server in order, and the version is read when the
 * request actually goes out, after the previous write has bumped it.
 */
export function useMoveIssue(projectId: string) {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    scope: { id: `issue-write:${projectId}` },
    mutationFn: ({ issueKey, ...input }: MoveIssueVariables) =>
      moveIssueRequest(client, projectId, issueKey, {
        ...input,
        version: currentIssueVersion(queryClient, projectId, issueKey),
      }),
    onMutate: ({ issueKey, status, statusId, sprintId, rank }: MoveIssueVariables) =>
      applyOptimisticIssue(queryClient, projectId, issueKey, {
        ...(status !== undefined ? { status } : {}),
        ...(statusId !== undefined ? { statusId } : {}),
        ...(sprintId !== undefined ? { sprintId } : {}),
        ...(rank !== undefined ? { rank } : {}),
      }),
    onSuccess: (issue, { issueKey }) =>
      recordServerVersion(queryClient, projectId, issueKey, issue.version),
    onError: (error, { issueKey }, snapshot) => {
      restoreIssue(queryClient, projectId, issueKey, snapshot);
      toast.error(issueWriteErrorMessage(error));
    },
    onSettled: (_data, _error, { issueKey }) =>
      invalidateAfterIssueWrite(queryClient, projectId, issueKey),
  });
}

export interface SetBlockedVariables {
  issueKey: string;
  blocked: boolean;
  reason?: string;
}

export function useSetIssueBlocked(projectId: string) {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    scope: { id: `issue-write:${projectId}` },
    mutationFn: ({ issueKey, ...input }: SetBlockedVariables) =>
      setIssueBlockedRequest(client, projectId, issueKey, {
        ...input,
        version: currentIssueVersion(queryClient, projectId, issueKey),
      }),
    onMutate: ({ issueKey, blocked, reason }: SetBlockedVariables) =>
      applyOptimisticIssue(queryClient, projectId, issueKey, {
        blocked,
        blockedReason: blocked ? (reason?.trim() ?? null) : null,
      }),
    onSuccess: (issue, { issueKey }) =>
      recordServerVersion(queryClient, projectId, issueKey, issue.version),
    onError: (error, { issueKey }, snapshot) => {
      restoreIssue(queryClient, projectId, issueKey, snapshot);
      toast.error(issueWriteErrorMessage(error));
    },
    onSettled: (_data, _error, { issueKey }) =>
      invalidateAfterIssueWrite(queryClient, projectId, issueKey),
  });
}
