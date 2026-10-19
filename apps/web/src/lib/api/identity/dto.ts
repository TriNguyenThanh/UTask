/**
 * Hợp đồng Identity Service, đối chiếu OpenAPI v1.8 ngày 19/10/2026
 * (`https://utask-api.u-code.dev/api/auth/openapi/`). Giữ snake_case như backend.
 */

export type Role = "STUDENT" | "TEACHER" | "SYSTEM_ADMIN";

export interface CurrentUserDto {
  id: string;
  email: string;
  username: string;
  student_id: string | null;
  display_name: string;
  avatar_url: string | null;
  roles: Role[];
  first_name: string;
  last_name: string;
  phone_number: string | null;
  bio: string | null;
  github_username: string | null;
  academic_year: string | null;
  faculty: string | null;
  timezone: string;
  preferences: Record<string, unknown>;
  created_at: string;
}

/** Phiên đăng nhập của một thiết bị (`Device` trong spec). */
export interface SessionDto {
  id: string;
  token_family: string;
  device_name: string;
  ip_address: string | null;
  is_current: boolean;
  created_at: string;
  expires_at: string;
}

/** `refresh` rỗng vì refresh token nằm trong cookie HttpOnly. */
export interface LoginDataDto {
  access: string;
  refresh: string;
  user: CurrentUserDto;
}

export interface RefreshDataDto {
  access: string;
  access_expiration: string;
}

export interface LogoutAllDataDto {
  revoked_sessions_count: number;
}

/** Trường `PATCH /users/me` cho phép sửa; MSSV và email chỉ đọc (gửi `student_id` bị 403). */
export interface ProfilePatchDto {
  first_name?: string;
  last_name?: string;
  phone_number?: string | null;
  bio?: string | null;
  academic_year?: string | null;
  faculty?: string | null;
  timezone?: string;
}

export interface PasswordChangeDto {
  old_password: string;
  new_password1: string;
  new_password2: string;
}
