import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useAuth } from "@/features/auth/AuthProvider";
import { useApiClient } from "@/lib/api/ApiClientProvider";
import { uploadTaskAttachment } from "@/lib/api/work/attachmentUpload";
import {
  createComment,
  deleteAttachment,
  deleteComment,
  getAttachmentDownloadUrl,
  listProjectComments,
  listTaskActivities,
  listTaskAttachments,
  listTaskComments,
  patchComment,
  type CommentInput,
  type CommentTarget,
} from "@/lib/api/work/endpoints";

function useUserId(): string {
  const { user } = useAuth();
  if (!user) throw new Error("Hook Work chỉ dùng được khi đã đăng nhập.");
  return user.id;
}

/** Nằm dưới `["work", userId]` nên cũng bị `invalidateQueries(workKeys.all)` làm mới. */
export const workCollabKeys = {
  comments: (userId: string) => ["work", userId, "comments"] as const,
  commentsOf: (userId: string, target: CommentTarget) =>
    ["work", userId, "comments", "taskId" in target ? `task:${target.taskId}` : `project:${target.projectId}`] as const,
  activities: (userId: string, taskId: string) => ["work", userId, "activities", taskId] as const,
  attachments: (userId: string, taskId: string) => ["work", userId, "attachments", taskId] as const,
};

export function useComments(target: CommentTarget, enabled = true) {
  const client = useApiClient();
  const userId = useUserId();
  return useQuery({
    queryKey: workCollabKeys.commentsOf(userId, target),
    queryFn: () => ("taskId" in target ? listTaskComments(client, target.taskId) : listProjectComments(client, target.projectId)),
    enabled,
  });
}

export function useTaskActivities(taskId: string) {
  const client = useApiClient();
  const userId = useUserId();
  return useQuery({
    queryKey: workCollabKeys.activities(userId, taskId),
    queryFn: () => listTaskActivities(client, taskId),
  });
}

export function useTaskAttachments(taskId: string) {
  const client = useApiClient();
  const userId = useUserId();
  return useQuery({
    queryKey: workCollabKeys.attachments(userId, taskId),
    queryFn: () => listTaskAttachments(client, taskId),
  });
}

/** Chỉ làm mới các khóa cộng tác: bình luận/tệp không đổi workspace nên không tải lại cả dự án. */
function useCollabMutation<V, R>(run: (variables: V) => Promise<R>, scopes: ReadonlyArray<"comments" | "activities" | "attachments">) {
  const queryClient = useQueryClient();
  const userId = useUserId();
  return useMutation({
    mutationFn: run,
    onSuccess: () => Promise.all(scopes.map((scope) => queryClient.invalidateQueries({ queryKey: ["work", userId, scope] }))),
  });
}

export function useCreateComment(target: CommentTarget) {
  const client = useApiClient();
  return useCollabMutation((input: CommentInput) => createComment(client, target, input), ["comments", "activities"]);
}

export function usePatchComment() {
  const client = useApiClient();
  return useCollabMutation((input: CommentInput & { commentId: string }) =>
    patchComment(client, input.commentId, input), ["comments", "activities"]);
}

export function useDeleteComment() {
  const client = useApiClient();
  return useCollabMutation((commentId: string) => deleteComment(client, commentId), ["comments", "activities"]);
}

export function useUploadAttachment(taskId: string) {
  const client = useApiClient();
  return useCollabMutation((file: File) => uploadTaskAttachment(client, taskId, file), ["attachments"]);
}

export function useDeleteAttachment(taskId: string) {
  const client = useApiClient();
  return useCollabMutation((attachmentId: string) => deleteAttachment(client, taskId, attachmentId), ["attachments"]);
}

/** Không cache: liên kết tải chỉ có hạn 300 giây. */
export function useAttachmentDownload(taskId: string) {
  const client = useApiClient();
  return useMutation({ mutationFn: (attachmentId: string) => getAttachmentDownloadUrl(client, taskId, attachmentId) });
}
