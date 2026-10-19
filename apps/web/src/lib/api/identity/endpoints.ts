import type { ApiClient } from "@/lib/api/client";
import type { CurrentUserDto, LoginDataDto, SessionDto } from "@/lib/api/identity/dto";

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
