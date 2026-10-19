import type { ApiClient } from "@/lib/api/client";
import type {
  CurrentUserDto,
  LoginDataDto,
  LogoutAllDataDto,
  ActivateDto,
  PasswordResetConfirmDto,
  RegisterDataDto,
  RegisterDto,
  PasswordChangeDto,
  ProfilePatchDto,
  RefreshDataDto,
  SessionDto,
} from "@/lib/api/identity/dto";

const ROOT = "/api/auth";

export interface LoginInput {
  email: string;
  password: string;
  deviceName: string;
}

export async function login(client: ApiClient, input: LoginInput) {
  const { data } = await client.requestEnvelope<LoginDataDto>(`${ROOT}/login`, {
    method: "POST",
    body: { email: input.email, password: input.password, device_name: input.deviceName },
  });
  return { accessToken: data.access, user: data.user };
}

export async function listSessions(client: ApiClient) {
  const { data } = await client.requestEnvelope<SessionDto[]>(`${ROOT}/sessions`);
  return data;
}

export async function revokeSession(client: ApiClient, sessionId: string) {
  await client.requestEnvelope<null>(`${ROOT}/sessions/${encodeURIComponent(sessionId)}`, { method: "DELETE" });
}

export async function getMe(client: ApiClient) {
  const { data } = await client.requestEnvelope<CurrentUserDto>(`${ROOT}/users/me`);
  return data;
}

function csrfHeaders(csrfToken: string | null): HeadersInit | undefined {
  return csrfToken ? { "X-CSRFToken": csrfToken } : undefined;
}

/** Cookie `refresh_token` (HttpOnly) tự đính kèm; backend bắt CSRF khi có cookie. */
export async function refresh(client: ApiClient, csrfToken: string | null) {
  const { data } = await client.requestEnvelope<RefreshDataDto>(`${ROOT}/refresh`, {
    method: "POST",
    body: {},
    headers: csrfHeaders(csrfToken),
  });
  return { accessToken: data.access };
}

export async function logoutAll(client: ApiClient, csrfToken: string | null) {
  const { data } = await client.requestEnvelope<LogoutAllDataDto>(`${ROOT}/logout-all`, {
    method: "POST",
    body: {},
    headers: csrfHeaders(csrfToken),
  });
  return data.revoked_sessions_count;
}

/** Backend chỉ trả một phần hồ sơ sau khi sửa, nên gọi `getMe` để lấy bản đầy đủ. */
export async function patchMe(client: ApiClient, body: ProfilePatchDto) {
  await client.requestEnvelope<unknown>(`${ROOT}/users/me`, { method: "PATCH", body });
}

/** Thành công thì mọi phiên của tài khoản bị thu hồi. */
export async function changePassword(client: ApiClient, body: PasswordChangeDto) {
  await client.requestEnvelope<unknown>(`${ROOT}/password-change`, { method: "POST", body });
}

export async function register(client: ApiClient, body: RegisterDto) {
  const { data } = await client.requestEnvelope<RegisterDataDto>(`${ROOT}/register`, { method: "POST", body });
  return data;
}

export async function activate(client: ApiClient, body: ActivateDto) {
  await client.requestEnvelope<unknown>(`${ROOT}/activate`, { method: "POST", body });
}

export async function resendActivation(client: ApiClient, email: string) {
  await client.requestEnvelope<unknown>(`${ROOT}/activation/resend`, { method: "POST", body: { email } });
}

export async function requestPasswordReset(client: ApiClient, email: string) {
  await client.requestEnvelope<unknown>(`${ROOT}/password-reset/request`, { method: "POST", body: { email } });
}

export async function confirmPasswordReset(client: ApiClient, body: PasswordResetConfirmDto) {
  await client.requestEnvelope<unknown>(`${ROOT}/password-reset/confirm`, { method: "POST", body });
}
