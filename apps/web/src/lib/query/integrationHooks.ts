import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useApiClient } from "@/lib/api/ApiClientProvider";
import type { GitHubAuthorizationCompleteBody } from "@/lib/api/integration/dto";
import {
  completeGitHubAuthorization,
  getGitHubAccount,
  startGitHubAuthorization,
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
