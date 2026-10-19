import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { isConflict } from "@/features/courses/lib/groupErrors";
import { useApiClient } from "@/lib/api/ApiClientProvider";
import type { ApiClient } from "@/lib/api/client";
import type { ClassStatus, TeacherRole, TeacherStatus } from "@/lib/api/classroom/dto";
import {
  assignTeacher,
  createClass,
  createCourse,
  issueClassJoinCode,
  listCourses,
  lockGrouping,
  patchClass,
  setClassState,
  type ClassFields,
} from "@/lib/api/classroom/endpoints";
import { usersBatch } from "@/lib/api/identity/endpoints";
import { classroomKeys } from "@/lib/query/classroomHooks";
import { teacherKeys } from "@/lib/query/teacherFlowHooks";
import { useAuth } from "@/features/auth/AuthProvider";

/**
 * Lệnh quản lý lớp của giảng viên. Không cập nhật lạc quan: sau khi thành
 * công, và cả khi 409 (phiên bản đang hiển thị đã cũ), tải lại dữ liệu giảng
 * viên và Classroom. `idempotencyKey` do nơi gọi sinh cho mỗi lần bấm.
 */
function useTeacherCommand<V, R>(run: (client: ApiClient, variables: V) => Promise<R>) {
  const client = useApiClient();
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const refetch = () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: classroomKeys.all }),
      user ? queryClient.invalidateQueries({ queryKey: teacherKeys.all(user.id) }) : undefined,
    ]);
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

/** Môn học hiện có (mọi vai trò đều thấy tất cả môn), để chọn khi tạo lớp. */
export function useCourseOptions() {
  const client = useApiClient();
  return useQuery({
    queryKey: ["classroom", "course-options"],
    queryFn: () => listCourses(client),
  });
}

export function useCreateCourse() {
  return useTeacherCommand((client, input: { code: string; name: string; idempotencyKey: string }) =>
    createCourse(client, input),
  );
}

export function useCreateClass() {
  return useTeacherCommand(
    (
      client,
      input: ClassFields & { courseId: string; code: string; idempotencyKey: string },
    ) => createClass(client, input),
  );
}

export function usePatchClass(classId: string) {
  return useTeacherCommand(
    (client, input: Partial<ClassFields> & { version: number; idempotencyKey: string }) =>
      patchClass(client, classId, input),
  );
}

export function useSetClassState(classId: string) {
  return useTeacherCommand(
    (client, input: { version: number; status: ClassStatus; idempotencyKey: string }) =>
      setClassState(client, classId, input),
  );
}

export function useIssueClassJoinCode(classId: string) {
  return useTeacherCommand(
    (client, input: { version: number; enabled: boolean; idempotencyKey: string }) =>
      issueClassJoinCode(client, classId, input),
  );
}

export function useLockGrouping(classId: string) {
  return useTeacherCommand((client, input: { version: number; idempotencyKey: string }) =>
    lockGrouping(client, classId, input),
  );
}

export function useAssignTeacher(classId: string) {
  return useTeacherCommand(
    (
      client,
      input: {
        version: number;
        userId: string;
        role: TeacherRole;
        status: TeacherStatus;
        idempotencyKey: string;
      },
    ) => assignTeacher(client, classId, input),
  );
}

/** Tra người dùng theo UUID để hiện tên trước khi phân công (chưa có API tra theo e-mail, B9). */
export function useUserLookup() {
  const client = useApiClient();
  return useMutation({
    mutationFn: async (userId: string) => (await usersBatch(client, [userId]))[0] ?? null,
  });
}
