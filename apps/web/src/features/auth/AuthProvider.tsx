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
import { ensureCsrfToken } from "@/lib/api/csrf";
import { ApiError } from "@/lib/api/errors";
import {
  getMe,
  listSessions,
  login as loginRequest,
  logoutAll as logoutAllRequest,
  refresh as refreshRequest,
  revokeSession,
} from "@/lib/api/identity/endpoints";
import { jwtExpiry } from "@/lib/api/jwt";

/** Làm mới access token sớm hơn hạn này để request đang bay không gặp token hết hạn. */
const REFRESH_LEAD_MS = 60_000;
const MIN_REFRESH_DELAY_MS = 5_000;

export interface LoginPayload {
  email: string;
  password: string;
}
type SessionEndReason = "signed-out" | "expired";

interface AuthContextValue {
  status: AuthStatus;
  user: AuthUser | null;
  accessToken: string | null;
  login(payload: LoginPayload): Promise<AuthUser>;
  /** `revoked: false` khi chưa thu hồi được phiên trên máy chủ; phiên cục bộ luôn bị xóa. */
  logout(): Promise<{ revoked: boolean }>;
  /** Đăng xuất mọi thiết bị; trả số phiên đã thu hồi. Phiên cục bộ luôn bị xóa. */
  logoutAll(): Promise<number>;
  /**
   * Làm mới access token (single-flight). `null` khi refresh token không còn hợp lệ;
   * ném lỗi khi lỗi tạm thời (mạng, 5xx) để giữ phiên.
   */
  refreshAccessToken(failedToken?: string): Promise<string | null>;
  /** Cập nhật hồ sơ đang hiển thị (sau khi sửa hồ sơ) mà không đổi phiên. */
  setUser(user: AuthUser): void;
  handleUnauthorized(): void;
  /** true khi phiên kết thúc do người dùng tự đăng xuất. */
  signedOut: boolean;
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
  const [status, setStatus] = useState<AuthStatus>(initialSession ? "authenticated" : "restoring");
  const [signedOut, setSignedOut] = useState(false);
  const sessionRef = useRef(session);
  const refreshInFlight = useRef<Promise<string | null> | null>(null);

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

  const clearSession = useCallback((reason: SessionEndReason) => {
    setSession(null);
    setStatus("anonymous");
    setSignedOut(reason === "signed-out");
    queryClient.clear();
    publishSession(null);
  }, [queryClient]);

  const refreshAccessToken = useCallback((failedToken?: string) => {
    const current = sessionRef.current;
    // Request khác đã làm mới xong trong lúc request này đang bay.
    if (failedToken && current && current.accessToken !== failedToken) {
      return Promise.resolve(current.accessToken);
    }
    refreshInFlight.current ??= (async () => {
      try {
        const csrfToken = await ensureCsrfToken(baseUrl);
        const { accessToken } = await refreshRequest(unauthenticatedClient, csrfToken);
        const latest = sessionRef.current;
        if (latest) {
          const next = { ...latest, accessToken };
          sessionRef.current = next;
          setSession(next);
          publishSession(next);
        }
        return accessToken;
      } catch (error) {
        if (error instanceof ApiError && error.status >= 400 && error.status < 500) {
          return null;
        }
        throw error;
      } finally {
        refreshInFlight.current = null;
      }
    })();
    return refreshInFlight.current;
  }, [baseUrl, unauthenticatedClient]);

  // Khôi phục phiên khi mở app: refresh token nằm trong cookie HttpOnly nên chỉ server biết có phiên hay không.
  useEffect(() => {
    if (initialSession) {
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const accessToken = await refreshAccessToken();
        if (!accessToken) {
          return null;
        }
        const meClient = createApiClient({
          baseUrl,
          getAccessToken: () => accessToken,
          onUnauthorized: () => undefined,
        });
        return { accessToken, user: await getMe(meClient) };
      } catch {
        return null;
      }
    })().then((restored) => {
      if (cancelled) {
        return;
      }
      if (restored) {
        sessionRef.current = restored;
        setSession(restored);
        setStatus("authenticated");
        publishSession(restored);
      } else {
        setStatus("anonymous");
      }
    });
    return () => {
      cancelled = true;
    };
    // Chỉ chạy một lần khi mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const accessToken = session?.accessToken ?? null;
  useEffect(() => {
    const expiry = accessToken ? jwtExpiry(accessToken) : null;
    if (expiry === null) {
      return;
    }
    const delay = Math.max(MIN_REFRESH_DELAY_MS, expiry * 1000 - Date.now() - REFRESH_LEAD_MS);
    const timer = setTimeout(() => {
      refreshAccessToken().then(
        (fresh) => {
          if (fresh === null) {
            clearSession("expired");
          }
        },
        // Lỗi tạm thời: giữ phiên, request kế tiếp sẽ thử lại qua 401.
        () => undefined,
      );
    }, delay);
    return () => clearTimeout(timer);
  }, [accessToken, clearSession, refreshAccessToken]);

  const login = useCallback(async (payload: LoginPayload) => {
    const { accessToken, user } = await loginRequest(unauthenticatedClient, {
      ...payload,
      deviceName: deviceName(),
    });
    // A new sign-in starts from an empty cache so nothing fetched for a
    // previous account (or while anonymous) can be shown to this one.
    queryClient.clear();
    setSignedOut(false);
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
      clearSession("signed-out");
    }
    return { revoked };
  }, [clearSession, sessionClient]);

  const logoutAll = useCallback(async () => {
    try {
      const csrfToken = await ensureCsrfToken(baseUrl);
      return await logoutAllRequest(sessionClient, csrfToken);
    } finally {
      clearAllDrafts();
      clearSession("signed-out");
    }
  }, [baseUrl, clearSession, sessionClient]);

  const setUser = useCallback((user: AuthUser) => {
    const current = sessionRef.current;
    if (!current) {
      return;
    }
    const next = { ...current, user };
    sessionRef.current = next;
    setSession(next);
    publishSession(next);
  }, []);

  const handleUnauthorized = useCallback(() => clearSession("expired"), [clearSession]);

  const value = useMemo<AuthContextValue>(() => ({
    status,
    user: session?.user ?? null,
    accessToken: session?.accessToken ?? null,
    login,
    logout,
    logoutAll,
    refreshAccessToken,
    setUser,
    handleUnauthorized,
    signedOut,
  }), [handleUnauthorized, login, logout, logoutAll, refreshAccessToken, session, setUser, signedOut, status]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used inside AuthProvider");
  }
  return context;
}
