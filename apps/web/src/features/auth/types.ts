import type { CurrentUserDto } from "@/lib/api/identity/dto";

export type AuthUser = CurrentUserDto;

/** Access token chỉ giữ trong bộ nhớ; refresh token nằm trong cookie HttpOnly. */
export interface AuthSession {
  accessToken: string;
  user: AuthUser;
}

export type AuthStatus = "restoring" | "authenticated" | "anonymous";
