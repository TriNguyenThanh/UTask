import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useAuth } from "@/features/auth/AuthProvider";
import { isConflict } from "@/features/courses/lib/groupErrors";
import { useApiClient } from "@/lib/api/ApiClientProvider";
import type { ApiClient } from "@/lib/api/client";
import {
  createGroup,
  issueGroupInviteCode,
  joinClass,
  joinGroup,
  leaveGroup,
  removeMember,
  transferLeader,
} from "@/lib/api/classroom/endpoints";
import { loadCourseDetail, loadCourseEnrollments } from "@/lib/api/classroom/loaders";

/** Khóa cache gắn `userId`: dữ liệu lớp phụ thuộc người đăng nhập. */
export const classroomKeys = {
  all: ["classroom"] as const,
  courses: (userId: string) => ["classroom", userId, "courses"] as const,
  course: (userId: string, classId: string) => ["classroom", userId, "course", classId] as const,
};

function useUserId(): string {
  const { user } = useAuth();
  if (!user) {
    throw new Error("Hook Classroom chỉ dùng được khi đã đăng nhập.");
  }
  return user.id;
}

/** Lớp của tôi (cho `/courses`) từ Classroom thật. */
export function useClassroomCourses() {
  const client = useApiClient();
  const userId = useUserId();
  return useQuery({
    queryKey: classroomKeys.courses(userId),
    queryFn: () => loadCourseEnrollments(client, userId),
  });
}

export function useClassroomCourseDetail(classId: string) {
  const client = useApiClient();
  const userId = useUserId();
  return useQuery({
    queryKey: classroomKeys.course(userId, classId),
    queryFn: () => loadCourseDetail(client, userId, classId),
  });
}

/** `idempotencyKey` do component sinh một lần cho mỗi lần mở hộp thoại. */
export function useJoinClass() {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ code, idempotencyKey }: { code: string; idempotencyKey: string }) =>
      joinClass(client, code.trim(), idempotencyKey),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: classroomKeys.all }),
  });
}

/**
 * Lệnh nhóm: không cập nhật lạc quan; chỉ refetch sau thành công, và cả khi 409
 * (dữ liệu đang hiển thị có thể đã cũ). `idempotencyKey` do nơi gọi sinh cho mỗi lần bấm.
 */
function useGroupMutation<V, R>(run: (client: ApiClient, variables: V) => Promise<R>) {
  const client = useApiClient();
  const queryClient = useQueryClient();
  const refetch = () => queryClient.invalidateQueries({ queryKey: classroomKeys.all });
  return useMutation({
    mutationFn: (variables: V) => run(client, variables),
    onSuccess: refetch,
    onError: (error) => {
      if (isConflict(error)) {
        void refetch();
      }
    },
  });
}

export function useCreateGroup(classId: string) {
  return useGroupMutation((client, input: { name: string; idempotencyKey: string }) =>
    createGroup(client, { classId, ...input }));
}

export function useJoinGroup() {
  return useGroupMutation((client, input: { code: string; idempotencyKey: string }) =>
    joinGroup(client, { ...input, code: input.code.trim() }));
}

export function useIssueInviteCode(groupId: string) {
  return useGroupMutation((client, input: { version: number; enabled: boolean; idempotencyKey: string }) =>
    issueGroupInviteCode(client, groupId, input));
}

export function useLeaveGroup(groupId: string) {
  return useGroupMutation((client, input: { version: number; reason: string; idempotencyKey: string }) =>
    leaveGroup(client, groupId, input));
}

export function useTransferLeader(groupId: string) {
  return useGroupMutation(
    (client, input: { version: number; reason: string; userId: string; idempotencyKey: string }) =>
      transferLeader(client, groupId, input),
  );
}

export function useRemoveMember(groupId: string) {
  return useGroupMutation(
    (client, input: { version: number; reason: string; userId: string; idempotencyKey: string }) =>
      removeMember(client, groupId, input),
  );
}
