import type { AuthUser } from "@/features/auth/types";

/** `null` khi phiên bị xóa (đăng xuất, hết hạn). */
export type SessionEvent = { accessToken: string; user: AuthUser } | null;

type SessionListener = (event: SessionEvent) => void;

const listeners = new Set<SessionListener>();

/**
 * Phát thay đổi phiên cho tầng không thuộc luồng sản phẩm (cầu nối persona của MSW)
 * mà không để mã production import `src/mocks`.
 */
export function publishSession(event: SessionEvent): void {
  for (const listener of listeners) {
    listener(event);
  }
}

export function subscribeSession(listener: SessionListener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}
