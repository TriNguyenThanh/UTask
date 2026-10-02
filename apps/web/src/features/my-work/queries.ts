import { useQuery } from "@tanstack/react-query";

import { useApiClient } from "@/lib/api/ApiClientProvider";
import { myWorkGitHubRequest, myWorkOverviewRequest } from "@/features/my-work/api/myWork";

export const myWorkKeys = {
  all: ["my-work"] as const,
  overview: ["my-work", "overview"] as const,
  github: ["my-work", "github"] as const,
};

export function useMyWorkOverview() {
  const client = useApiClient();
  return useQuery({
    queryKey: myWorkKeys.overview,
    queryFn: () => myWorkOverviewRequest(client),
  });
}

export function useMyWorkGitHub() {
  const client = useApiClient();
  return useQuery({
    queryKey: myWorkKeys.github,
    queryFn: () => myWorkGitHubRequest(client),
  });
}