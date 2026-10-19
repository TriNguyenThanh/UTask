import { z } from "zod";

import type { AuthUser } from "@/features/auth/types";
import { isSafeInternalPath } from "@/lib/navigation/safeInternalPath";

/**
 * Whether the account may open the Teacher space (`/teacher/*`).
 *
 * This is a capability check only. It decides which navigation and routes
 * are available; it grants NO access to any class. Reading a class needs an
 * assignment for that class, which only the server (or the demo mock)
 * decides.
 */
export function canUseTeacherSpace(user: AuthUser | null | undefined): boolean {
  return user?.roles.includes("TEACHER") ?? false;
}

export function isStudentAccount(user: AuthUser | null | undefined): boolean {
  return user?.roles.includes("STUDENT") ?? false;
}

/**
 * Where a user lands when no valid `returnTo` exists. Teacher-only accounts
 * go to the Teacher space; anyone who is also a student keeps the Student
 * home and reaches the Teacher space through the sidebar link.
 */
export function defaultLandingPath(user: AuthUser | null | undefined): string {
  if (canUseTeacherSpace(user) && !isStudentAccount(user)) {
    return "/teacher";
  }
  // Chưa có khu quản trị: tài khoản chỉ có SYSTEM_ADMIN không có dữ liệu sinh viên để hiển thị.
  if (user?.roles.length === 1 && user.roles[0] === "SYSTEM_ADMIN") {
    return "/settings/profile";
  }
  return "/my-work";
}

/**
 * Where to send a user who is signed in on the login page: a valid internal
 * `returnTo` from the router state, otherwise the account's home. The target
 * still authorizes itself, so a `returnTo` never widens access.
 */
export function resolveLoginTarget(state: unknown, user: AuthUser | null | undefined): string {
  if (state && typeof state === "object" && "returnTo" in state && isSafeInternalPath(state.returnTo)) {
    return state.returnTo;
  }
  return defaultLandingPath(user);
}

const loginNoticeSchema = z.object({ notice: z.string().min(1) });

/** Thông báo một lần truyền qua router state khi chuyển về `/login` (ví dụ sau khi đổi mật khẩu). */
export function readLoginNotice(state: unknown): string | null {
  const parsed = loginNoticeSchema.safeParse(state);
  return parsed.success ? parsed.data.notice : null;
}
