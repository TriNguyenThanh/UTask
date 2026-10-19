import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useAuth } from "@/features/auth/AuthProvider";
import { useApiClient } from "@/lib/api/ApiClientProvider";
import type { PasswordChangeDto, ProfilePatchDto } from "@/lib/api/identity/dto";
import {
  changePassword,
  getMe,
  listSessions,
  patchMe,
  revokeSession,
} from "@/lib/api/identity/endpoints";
import { authKeys } from "@/lib/query/keys";

export function useMe() {
  const client = useApiClient();
  return useQuery({ queryKey: authKeys.me, queryFn: () => getMe(client) });
}

/** Sửa hồ sơ rồi đọc lại bản đầy đủ từ máy chủ; không cập nhật lạc quan. */
export function usePatchMe() {
  const client = useApiClient();
  const queryClient = useQueryClient();
  const { setUser } = useAuth();
  return useMutation({
    mutationFn: async (body: ProfilePatchDto) => {
      await patchMe(client, body);
      return getMe(client);
    },
    onSuccess: (user) => {
      queryClient.setQueryData(authKeys.me, user);
      setUser(user);
    },
  });
}

export function useSessions() {
  const client = useApiClient();
  return useQuery({ queryKey: authKeys.sessions, queryFn: () => listSessions(client) });
}

export function useRevokeSession() {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (sessionId: string) => revokeSession(client, sessionId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: authKeys.sessions }),
  });
}

export function useChangePassword() {
  const client = useApiClient();
  return useMutation({ mutationFn: (body: PasswordChangeDto) => changePassword(client, body) });
}
