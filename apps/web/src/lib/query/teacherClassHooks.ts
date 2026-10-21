import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";

import { useAuth } from "@/features/auth/AuthProvider";
import { isConflict } from "@/features/courses/lib/groupErrors";
import { chunk } from "@/features/teacher/lib/importRun";
import { useApiClient } from "@/lib/api/ApiClientProvider";
import type { ApiClient } from "@/lib/api/client";
import type { ClassStatus, ImportResultDto, StudentRowInput, TeacherRole, TeacherStatus } from "@/lib/api/classroom/dto";
import {
  addStudents,
  adjustMember,
  assignTeacher,
  createClass,
  createCourse,
  createGroup,
  exitEnrollment,
  issueClassJoinCode,
  listClassActivities,
  listCourses,
  listGroupActivities,
  lockGrouping,
  MAX_STUDENTS_PER_REQUEST,
  patchClass,
  setClassState,
  transferLeader,
  type ClassFields,
} from "@/lib/api/classroom/endpoints";
import { newIdempotencyKey } from "@/lib/api/idempotency";
import { usersBatch } from "@/lib/api/identity/endpoints";
import { classroomKeys } from "@/lib/query/classroomHooks";
import { teacherKeys } from "@/lib/query/teacherFlowHooks";

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

/** Thêm một lô nhỏ (một sinh viên); danh sách lớn dùng `useStudentImport` để chia lô. */
export function useAddStudents(classId: string) {
  return useTeacherCommand((client, input: { students: StudentRowInput[]; idempotencyKey: string }) =>
    addStudents(client, classId, input.students, input.idempotencyKey),
  );
}

export function useExitEnrollment(classId: string) {
  return useTeacherCommand(
    (client, input: { enrollmentId: string; reason: string; idempotencyKey: string }) =>
      exitEnrollment(client, classId, input.enrollmentId, input),
  );
}

export function useAdjustMember(classId: string) {
  return useTeacherCommand(
    (
      client,
      input: {
        userId: string;
        targetGroupId: string | null;
        successorUserId?: string;
        reason: string;
        idempotencyKey: string;
      },
    ) => adjustMember(client, classId, input),
  );
}

/** Giảng viên tạo nhóm hộ: `leaderId` là sinh viên ACTIVE chưa có nhóm, trở thành Leader. */
export function useCreateTeam(classId: string) {
  return useTeacherCommand((client, input: { name: string; leaderId: string; idempotencyKey: string }) =>
    createGroup(client, { classId, ...input }),
  );
}

/** Giảng viên chỉ định Leader mới trong một nhóm; `version` là `Group.source_version` đang hiển thị. */
export function useTransferTeamLeader() {
  return useTeacherCommand(
    (
      client,
      input: { groupId: string; version: number; userId: string; reason: string; idempotencyKey: string },
    ) => transferLeader(client, input.groupId, input),
  );
}

/** Lịch sử thay đổi của lớp (giảng viên) hoặc của một nhóm; nằm dưới khóa `classroom` nên lệnh nào cũng làm mới nó. */
export function useActivities(scope: { classId: string } | { groupId: string }) {
  const client = useApiClient();
  const id = "classId" in scope ? scope.classId : scope.groupId;
  return useQuery({
    queryKey: [...classroomKeys.all, "activities", "classId" in scope ? "class" : "group", id],
    queryFn: () => ("classId" in scope ? listClassActivities(client, id) : listGroupActivities(client, id)),
  });
}

/** Tên người dùng theo id; id không tra được bị bỏ qua (người gọi dùng nhãn thay thế). */
export function useUserNames(userIds: readonly string[]) {
  const client = useApiClient();
  const ids = [...new Set(userIds)].sort();
  return useQuery({
    queryKey: ["identity", "user-names", ids],
    queryFn: async () => new Map((await usersBatch(client, ids)).map((user) => [user.id, user.display_name])),
    enabled: ids.length > 0,
  });
}

export interface ImportRun {
  phase: "idle" | "running" | "done" | "failed";
  totalBatches: number;
  doneBatches: number;
  /** Kết quả các lô đã xong, theo thứ tự gửi. */
  results: ImportResultDto[];
  error: unknown;
}

const IDLE_RUN: ImportRun = { phase: "idle", totalBatches: 0, doneBatches: 0, results: [], error: null };

/**
 * Gửi danh sách sinh viên theo lô tối đa 100, lần lượt từng lô. Mỗi lô có
 * Idempotency-Key riêng, sinh một lần khi bắt đầu; `start` gọi lại sau lỗi sẽ
 * tiếp tục từ lô lỗi với cùng khóa nên không ghi danh hai lần.
 */
export function useStudentImport(classId: string) {
  const client = useApiClient();
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const [run, setRun] = useState<ImportRun>(IDLE_RUN);
  const plan = useRef<{ batches: StudentRowInput[][]; keys: string[]; results: ImportResultDto[] } | null>(null);
  const busy = useRef(false);

  async function refetch() {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: classroomKeys.all }),
      user ? queryClient.invalidateQueries({ queryKey: teacherKeys.all(user.id) }) : undefined,
    ]);
  }

  async function start(rows: readonly StudentRowInput[]) {
    if (busy.current) return;
    busy.current = true;
    if (!plan.current) {
      const batches = chunk(rows, MAX_STUDENTS_PER_REQUEST);
      plan.current = { batches, keys: batches.map(() => newIdempotencyKey()), results: [] };
    }
    const current = plan.current;
    const progress = (phase: ImportRun["phase"], error: unknown = null) =>
      setRun({
        phase,
        totalBatches: current.batches.length,
        doneBatches: current.results.length,
        results: [...current.results],
        error,
      });
    progress("running");
    try {
      while (current.results.length < current.batches.length) {
        const index = current.results.length;
        current.results.push(await addStudents(client, classId, current.batches[index], current.keys[index]));
        progress("running");
      }
      progress("done");
    } catch (error) {
      progress("failed", error);
    } finally {
      busy.current = false;
      // Một phần lô đã ghi danh dù lô sau lỗi.
      if (current.results.length > 0) await refetch();
    }
  }

  function reset() {
    if (busy.current) return;
    plan.current = null;
    setRun(IDLE_RUN);
  }

  return { run, start, reset };
}
