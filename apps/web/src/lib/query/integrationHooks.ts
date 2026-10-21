import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useApiClient } from "@/lib/api/ApiClientProvider";
import type { GitHubAuthorizationCompleteBody, GitHubInstallationCompleteBody } from "@/lib/api/integration/dto";
import {
  completeGitHubAuthorization,
  completeGitHubInstallation,
  getGitHubAccount,
  listGitHubInstallations,
  listGitHubRepositories,
  startGitHubAuthorization,
  startGitHubInstallation,
  unlinkGitHubAccount,
} from "@/lib/api/integration/endpoints";
import { isRealService } from "@/lib/config/services";

export const integrationKeys = {
  account: ["integration", "github", "account"] as const,
  installations: ["integration", "github", "installations"] as const,
  repositories: (installationId: string) => ["integration", "github", "repositories", installationId] as const,
};

export function useGitHubAccount() {
  const client = useApiClient();
  return useQuery({
    queryKey: integrationKeys.account,
    queryFn: () => getGitHubAccount(client),
    enabled: isRealService("integration"),
  });
}

/** Chuyển cả trang sang GitHub; phiên cấp quyền hoàn tất ở route callback. */
export function useStartGitHubAuthorization() {
  const client = useApiClient();
  return useMutation({
    mutationFn: () => startGitHubAuthorization(client),
    onSuccess: (data) => window.location.assign(data.authorization_url),
  });
}

export function useCompleteGitHubAuthorization() {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: GitHubAuthorizationCompleteBody) => completeGitHubAuthorization(client, body),
    onSuccess: (data) => {
      queryClient.setQueryData(integrationKeys.account, data);
    },
  });
}

export function useUnlinkGitHubAccount() {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => unlinkGitHubAccount(client),
    onSuccess: (data) => {
      queryClient.setQueryData(integrationKeys.account, data);
      return queryClient.invalidateQueries({ queryKey: integrationKeys.installations });
    },
  });
}

export function useStartGitHubInstallation() {
  const client = useApiClient();
  return useMutation({
    mutationFn: () => startGitHubInstallation(client),
    onSuccess: (data) => window.location.assign(data.installation_url),
  });
}

export function useCompleteGitHubInstallation() {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: GitHubInstallationCompleteBody) => completeGitHubInstallation(client, body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: integrationKeys.installations }),
  });
}

/** Chỉ tải khi Integration thật được bật và quyền GitHub của tài khoản đang `ACTIVE`. */
export function useGitHubInstallations() {
  const client = useApiClient();
  const account = useGitHubAccount();
  const active = account.data?.status === "LINKED" && account.data.authorization_status === "ACTIVE";
  return useInfiniteQuery({
    queryKey: integrationKeys.installations,
    queryFn: ({ pageParam }) => listGitHubInstallations(client, { page: pageParam }),
    initialPageParam: 1,
    getNextPageParam: (page) => page.next_page ?? undefined,
    enabled: isRealService("integration") && active,
  });
}

export function useGitHubRepositories(installationId: string | null) {
  const client = useApiClient();
  return useInfiniteQuery({
    queryKey: integrationKeys.repositories(installationId ?? ""),
    queryFn: ({ pageParam }) => listGitHubRepositories(client, installationId ?? "", { page: pageParam }),
    initialPageParam: 1,
    getNextPageParam: (page) => page.next_page ?? undefined,
    enabled: installationId !== null,
  });
}
