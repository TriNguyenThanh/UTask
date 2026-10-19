import { useQueryClient } from "@tanstack/react-query";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { deviceName } from "@/features/auth/deviceName";
import { publishSession } from "@/features/auth/sessionEvents";
import type { AuthSession, AuthStatus, AuthUser } from "@/features/auth/types";
import { clearAllDrafts } from "@/features/teacher/lib/drafts";
import { createApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { listSessions, login as loginRequest, revokeSession } from "@/lib/api/identity/endpoints";

export interface LoginPayload {
  email: string;
  password: string;
}

interface AuthContextValue {
  status: AuthStatus;
  user: AuthUser | null;
  accessToken: string | null;
  login(payload: LoginPayload): Promise<AuthUser>;
  /** `revoked: false` khi chưa thu hồi được phiên trên máy chủ; phiên cục bộ luôn bị xóa. */
  logout(): Promise<{ revoked: boolean }>;
  handleUnauthorized(): void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

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
  const [session, setSession] = useState<AuthSession | null>(initialSession ?? null);
  const [status, setStatus] = useState<AuthStatus>(initialSession ? "authenticated" : "anonymous");
  const sessionRef = useRef(session);

  useEffect(() => {
    sessionRef.current = session;
  }, [session]);

  const unauthenticatedClient = useMemo(() => createApiClient({
    baseUrl,
    getAccessToken: () => null,
    onUnauthorized: () => undefined,
  }), [baseUrl]);
  // 401 khi đăng xuất không cần xử lý thêm: phiên cục bộ vẫn bị xóa ngay sau đó.
  const sessionClient = useMemo(() => createApiClient({
    baseUrl,
    getAccessToken: () => sessionRef.current?.accessToken ?? null,
    onUnauthorized: () => undefined,
  }), [baseUrl]);

  const clearSession = useCallback(() => {
    setSession(null);
    setStatus("anonymous");
    queryClient.clear();
    publishSession(null);
  }, [queryClient]);

  const login = useCallback(async (payload: LoginPayload) => {
    const { accessToken, user } = await loginRequest(unauthenticatedClient, {
      ...payload,
      deviceName: deviceName(),
    });
    // A new sign-in starts from an empty cache so nothing fetched for a
    // previous account (or while anonymous) can be shown to this one.
    queryClient.clear();
    setSession({ accessToken, user });
    setStatus("authenticated");
    publishSession({ accessToken, user });
    return user;
  }, [queryClient, unauthenticatedClient]);

  const logout = useCallback(async () => {
    let revoked = true;
    try {
      if (sessionRef.current) {
        const current = (await listSessions(sessionClient)).find((item) => item.is_current);
        if (current) {
          await revokeSession(sessionClient, current.id);
        }
      }
    } catch (error) {
      // Phiên đã không còn trên máy chủ nghĩa là đã thu hồi.
      revoked = error instanceof ApiError && error.code === "SESSION_NOT_FOUND";
    } finally {
      // An explicit sign-out also forgets unsent drafts; an expired session does not.
      clearAllDrafts();
      clearSession();
    }
    return { revoked };
  }, [clearSession, sessionClient]);

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
