import type { AuthUser } from "@/features/auth/types";
import { isSafeInternalPath } from "@/lib/navigation/safeInternalPath";

/**
 * Whether the account may open the Teacher space (`/teacher/*`).
 *
 * This is a capability check only. It decides which navigation and routes
 * are available; it grants NO access to any class. Reading a class needs an
 * assignment for that class, which only the server (or the demo mock)
 * decides. Sessions created before `roles` existed carry no roles and are
 * treated as plain students.
 */
export function canUseTeacherSpace(user: AuthUser | null | undefined): boolean {
  return user?.roles?.includes("TEACHER") ?? false;
}

export function isStudentAccount(user: AuthUser | null | undefined): boolean {
  return user?.roles?.includes("STUDENT") ?? false;
}

/**
 * Where a user lands when no valid `returnTo` exists. Teacher-only accounts
 * go to the Teacher space; anyone who is also a student keeps the Student
 * home and reaches the Teacher space through the sidebar link.
 */
export function defaultLandingPath(user: AuthUser | null | undefined): string {
  return canUseTeacherSpace(user) && !isStudentAccount(user) ? "/teacher" : "/my-work";
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
