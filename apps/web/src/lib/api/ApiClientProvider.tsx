import { createContext, useContext, useMemo, type ReactNode } from "react";

import { useAuth } from "@/features/auth/AuthProvider";
import { createApiClient, type ApiClient } from "@/lib/api/client";

const ApiClientContext = createContext<ApiClient | null>(null);

export function ApiClientProvider({
  children,
  baseUrl = import.meta.env.VITE_API_BASE_URL ?? "",
}: {
  children: ReactNode;
  baseUrl?: string;
}) {
  const { accessToken, handleUnauthorized } = useAuth();
  const client = useMemo(() => createApiClient({
    baseUrl,
    getAccessToken: () => accessToken,
    onUnauthorized: handleUnauthorized,
  }), [accessToken, baseUrl, handleUnauthorized]);

  return <ApiClientContext.Provider value={client}>{children}</ApiClientContext.Provider>;
}

export function useApiClient() {
  const client = useContext(ApiClientContext);
  if (!client) {
    throw new Error("useApiClient must be used inside ApiClientProvider");
  }
  return client;
}
