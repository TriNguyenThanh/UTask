import type { AuthUser } from "@/features/auth/types";

type MockAuthUserInput = Pick<AuthUser, "id" | "email" | "display_name" | "roles">;

/** Dựng `AuthUser` đầy đủ trường Identity cho dữ liệu mock và test. */
export function buildMockAuthUser({ id, email, display_name, roles }: MockAuthUserInput): AuthUser {
  const [firstName = "", ...rest] = display_name.split(" ");
  return {
    id,
    email,
    username: email.split("@")[0],
    student_id: null,
    display_name,
    avatar_url: null,
    roles,
    first_name: firstName,
    last_name: rest.join(" "),
    phone_number: null,
    bio: null,
    github_username: null,
    academic_year: null,
    faculty: null,
    timezone: "Asia/Ho_Chi_Minh",
    preferences: {},
    created_at: "2026-01-01T00:00:00Z",
  };
}
