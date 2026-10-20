import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useAuth } from "@/features/auth/AuthProvider";
import { isConflict } from "@/features/courses/lib/groupErrors";
import { useApiClient } from "@/lib/api/ApiClientProvider";
import { loadGroupProjects, loadProjectCards, loadProjectShell } from "@/lib/api/work/loaders";
import {
  createProject,
  patchProject,
  setProjectArchived,
  type CreateProjectInput,
  type PatchProjectInput,
} from "@/lib/api/work/endpoints";

/** Khóa cache gắn `userId`: dữ liệu dự án phụ thuộc người đăng nhập. */
export const workKeys = {
  all: ["work"] as const,
  projects: (userId: string) => ["work", userId, "projects"] as const,
  project: (userId: string, projectId: string) => ["work", userId, "project", projectId] as const,
  groupProjects: (userId: string) => ["work", userId, "group-projects"] as const,
};

function useUserId(): string {
  const { user } = useAuth();
  if (!user) {
    throw new Error("Hook Work chỉ dùng được khi đã đăng nhập.");
  }
  return user.id;
}

export function useWorkProjects() {
  const client = useApiClient();
  const userId = useUserId();
  return useQuery({
    queryKey: workKeys.projects(userId),
    queryFn: () => loadProjectCards(client, userId),
  });
}

export function useWorkProject(projectId: string) {
  const client = useApiClient();
  const userId = useUserId();
  return useQuery({
    queryKey: workKeys.project(userId, projectId),
    queryFn: () => loadProjectShell(client, userId, projectId),
  });
}

export function useGroupProjects() {
  const client = useApiClient();
  const userId = useUserId();
  return useQuery({
    queryKey: workKeys.groupProjects(userId),
    queryFn: () => loadGroupProjects(client),
  });
}

/**
 * Lệnh ghi Project. Không cập nhật lạc quan: sau khi thành công, và cả khi 409
 * (dữ liệu đang hiển thị đã cũ), tải lại mọi dữ liệu Work.
 */
function useWorkCommand<V, R>(run: (variables: V) => Promise<R>) {
  const queryClient = useQueryClient();
  const refetch = () => queryClient.invalidateQueries({ queryKey: workKeys.all });
  return useMutation({
    mutationFn: run,
    onSuccess: refetch,
    onError: (error) => {
      if (isConflict(error)) {
        void refetch();
      }
    },
  });
}

/** `idempotencyKey` do component sinh một lần cho mỗi ý định tạo dự án. */
export function useCreateProject() {
  const client = useApiClient();
  return useWorkCommand((input: CreateProjectInput & { idempotencyKey: string }) => createProject(client, input));
}

/**
 * Ba lệnh sửa/lưu trữ/mở lại không gửi `Idempotency-Key`: backend không đăng ký receipt cho chúng
 * (`views/projects.py` chỉ gọi `require_key` khi tạo dự án); `expected_version` chặn ghi trùng.
 */
export function usePatchProject(projectId: string) {
  const client = useApiClient();
  return useWorkCommand((input: PatchProjectInput & { expectedVersion: number }) =>
    patchProject(client, projectId, input));
}

export function useSetProjectArchived(projectId: string) {
  const client = useApiClient();
  return useWorkCommand((input: { archived: boolean; expectedVersion: number }) =>
    setProjectArchived(client, projectId, input));
}
