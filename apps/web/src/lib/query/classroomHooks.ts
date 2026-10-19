import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useAuth } from "@/features/auth/AuthProvider";
import { useApiClient } from "@/lib/api/ApiClientProvider";
import { joinClass } from "@/lib/api/classroom/endpoints";
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
