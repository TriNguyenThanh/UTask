import type { ApiClient } from "@/lib/api/client";
import type { AuthUser } from "@/features/auth/types";

export interface LoginPayload {
  email: string;
  password: string;
}

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  expires_in: number;
  user: AuthUser;
}

export interface RefreshResponse {
  access_token: string;
  expires_in: number;
  user: AuthUser;
}

const AUTH_ROOT = "/api/auth/api/v1/auth";

export function loginRequest(client: ApiClient, payload: LoginPayload) {
  return client.request<LoginResponse>(`${AUTH_ROOT}/login`, {
    method: "POST",
    body: payload,
  });
}

export function refreshRequest(client: ApiClient, refreshToken: string) {
  return client.request<RefreshResponse>(`${AUTH_ROOT}/refresh`, {
    method: "POST",
    body: { refresh_token: refreshToken },
  });
}

export function logoutRequest(client: ApiClient, refreshToken: string) {
  return client.request<void>(`${AUTH_ROOT}/logout`, {
    method: "POST",
    body: { refresh_token: refreshToken },
  });
}
