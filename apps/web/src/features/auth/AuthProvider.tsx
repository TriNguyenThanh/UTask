import { useQueryClient } from "@tanstack/react-query";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { loginRequest, logoutRequest, refreshRequest } from "@/features/auth/api/auth";
import type { LoginPayload } from "@/features/auth/api/auth";
import type { AuthSession, AuthStatus, AuthUser } from "@/features/auth/types";
import { createApiClient } from "@/lib/api/client";

const MOCK_REFRESH_TOKEN_KEY = "utask.mock.refresh-token";

interface AuthContextValue {
  status: AuthStatus;
  user: AuthUser | null;
  accessToken: string | null;
  login(payload: LoginPayload): Promise<AuthUser>;
  logout(): Promise<void>;
  handleUnauthorized(): void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

function mocksEnabled() {
  // Mirror mocks/enableMocking.ts: run in any build when explicitly
  // enabled, so a deployed mock demo also restores its session.
  return import.meta.env.VITE_ENABLE_MOCKS === "true";
}

function readRefreshToken(): string | null {
  try {
    return sessionStorage.getItem(MOCK_REFRESH_TOKEN_KEY);
  } catch {
    return null;
  }
}

function writeRefreshToken(token: string | null) {
  try {
    if (token) {
      sessionStorage.setItem(MOCK_REFRESH_TOKEN_KEY, token);
    } else {
      sessionStorage.removeItem(MOCK_REFRESH_TOKEN_KEY);
    }
  } catch {
    // In-memory auth remains functional when browser storage is unavailable.
  }
}

export function AuthProvider({
  children,
  initialSession,
  baseUrl = import.meta.env.VITE_API_BASE_URL ?? "",
}: {
  children: ReactNode;
  initialSession?: AuthSession | null;
  baseUrl?: string;
}) {
  const queryClient = useQueryClient();
  const unauthenticatedClient = useMemo(() => createApiClient({
    baseUrl,
    getAccessToken: () => null,
    onUnauthorized: () => undefined,
  }), [baseUrl]);
  const [session, setSession] = useState<AuthSession | null>(initialSession ?? null);
  const [status, setStatus] = useState<AuthStatus>(initialSession ? "authenticated" : "restoring");

  const clearSession = useCallback(() => {
    writeRefreshToken(null);
    setSession(null);
    setStatus("anonymous");
    queryClient.clear();
  }, [queryClient]);

  useEffect(() => {
    if (initialSession) {
      return;
    }
    if (!mocksEnabled()) {
      setStatus("anonymous");
      return;
    }

    const refreshToken = readRefreshToken();
    if (!refreshToken) {
      setStatus("anonymous");
      return;
    }

    let active = true;
    void refreshRequest(unauthenticatedClient, refreshToken)
      .then((response) => {
        if (!active) {
          return;
        }
        setSession({
          accessToken: response.access_token,
          refreshToken,
          user: response.user,
        });
        setStatus("authenticated");
      })
      .catch(() => {
        if (active) {
          clearSession();
        }
      });

    return () => {
      active = false;
    };
  }, [clearSession, initialSession, unauthenticatedClient]);

  const login = useCallback(async (payload: LoginPayload) => {
    const response = await loginRequest(unauthenticatedClient, payload);
    const nextSession: AuthSession = {
      accessToken: response.access_token,
      refreshToken: response.refresh_token,
      user: response.user,
    };
    if (mocksEnabled()) {
      writeRefreshToken(response.refresh_token);
    }
    setSession(nextSession);
    setStatus("authenticated");
    return response.user;
  }, [unauthenticatedClient]);

  const logout = useCallback(async () => {
    const refreshToken = session?.refreshToken;
    try {
      if (refreshToken) {
        await logoutRequest(unauthenticatedClient, refreshToken);
      }
    } catch {
      // Logout is local-authoritative after best-effort token revocation.
    } finally {
      clearSession();
    }
  }, [clearSession, session?.refreshToken, unauthenticatedClient]);

  const value = useMemo<AuthContextValue>(() => ({
    status,
    user: session?.user ?? null,
    accessToken: session?.accessToken ?? null,
    login,
    logout,
    handleUnauthorized: clearSession,
  }), [clearSession, login, logout, session, status]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used inside AuthProvider");
  }
  return context;
}
