import { useQuery } from "@tanstack/react-query";

import { useAuth } from "@/features/auth/AuthProvider";
import { useApiClient } from "@/lib/api/ApiClientProvider";
import {
  teacherCourseRequest,
  teacherCoursesRequest,
  teacherOversightRequest,
  teacherStudentsRequest,
  teacherTeamsRequest,
} from "@/lib/api/teacherFlow";

/**
 * Teacher cache keys are scoped by the signed-in user AND the class, so one
 * account's data can never be served to another from the cache, and a class
 * the user lost access to can be dropped by prefix. Logout and sign-in also
 * clear the whole cache (AuthProvider); the scoping is the second layer.
 */
export const teacherKeys = {
  all: (userId: string) => ["teacher", userId] as const,
  courses: (userId: string) => [...teacherKeys.all(userId), "courses"] as const,
  course: (userId: string, courseId: string) =>
    [...teacherKeys.courses(userId), courseId] as const,
  students: (userId: string, courseId: string) =>
    [...teacherKeys.course(userId, courseId), "students"] as const,
  teams: (userId: string, courseId: string) =>
    [...teacherKeys.course(userId, courseId), "teams"] as const,
  oversight: (userId: string, courseId: string) =>
    [...teacherKeys.course(userId, courseId), "oversight"] as const,
};

function useTeacherUserId(): string | null {
  return useAuth().user?.id ?? null;
}

export function useTeacherCourses() {
  const client = useApiClient();
  const userId = useTeacherUserId();
  return useQuery({
    queryKey: teacherKeys.courses(userId ?? "anonymous"),
    queryFn: () => teacherCoursesRequest(client),
    enabled: userId !== null,
  });
}

export function useTeacherCourse(courseId: string) {
  const client = useApiClient();
  const userId = useTeacherUserId();
  return useQuery({
    queryKey: teacherKeys.course(userId ?? "anonymous", courseId),
    queryFn: () => teacherCourseRequest(client, courseId),
    enabled: userId !== null,
  });
}

export function useTeacherStudents(courseId: string) {
  const client = useApiClient();
  const userId = useTeacherUserId();
  return useQuery({
    queryKey: teacherKeys.students(userId ?? "anonymous", courseId),
    queryFn: () => teacherStudentsRequest(client, courseId),
    enabled: userId !== null,
  });
}

export function useTeacherTeams(courseId: string) {
  const client = useApiClient();
  const userId = useTeacherUserId();
  return useQuery({
    queryKey: teacherKeys.teams(userId ?? "anonymous", courseId),
    queryFn: () => teacherTeamsRequest(client, courseId),
    enabled: userId !== null,
  });
}

export function useTeacherOversight(courseId: string) {
  const client = useApiClient();
  const userId = useTeacherUserId();
  return useQuery({
    queryKey: teacherKeys.oversight(userId ?? "anonymous", courseId),
    queryFn: () => teacherOversightRequest(client, courseId),
    enabled: userId !== null,
  });
}
