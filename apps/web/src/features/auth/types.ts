export interface AuthUser {
  id: string;
  email: string;
  display_name: string;
  global_role: "USER";
  capabilities: string[];
}

export interface AuthSession {
  accessToken: string;
  refreshToken: string;
  user: AuthUser;
}

export type AuthStatus = "restoring" | "authenticated" | "anonymous";
