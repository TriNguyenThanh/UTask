import { ApiError } from "@/lib/api/errors";
import type { ApiClient } from "@/lib/api/client";
import { collectAllPages } from "@/lib/api/pagination";
import type {
  ActivityDto,
  AttachmentDownloadDto,
  AttachmentDto,
  AttachmentPresignDto,
  CommentDto,
} from "@/lib/api/work/dto";
import { fetchPage, ROOT } from "@/lib/api/work/endpoints.shared";

const task = (taskId: string) => `/tasks/${encodeURIComponent(taskId)}`;

/** Bình luận gắn đúng một đối tượng: task hoặc dự án (backend từ chối cả hai hoặc không có). */
export type CommentTarget = { taskId: string } | { projectId: string };

export interface CommentInput {
  /** Văn bản thuần; `content_html` được gửi đúng bằng chuỗi này (app không có bộ lọc HTML). */
  content: string;
  mentionedUserIds: readonly string[];
}

export function listTaskComments(client: ApiClient, taskId: string) {
  return collectAllPages((cursor) => fetchPage<CommentDto>(client, `${task(taskId)}/comments/`, { cursor }));
}

export function listProjectComments(client: ApiClient, projectId: string) {
  return collectAllPages((cursor) =>
    fetchPage<CommentDto>(client, `/projects/${encodeURIComponent(projectId)}/comments/`, { cursor }));
}

/** Không gửi `Idempotency-Key`: backend không đăng ký receipt cho bình luận. */
export async function createComment(client: ApiClient, target: CommentTarget, input: CommentInput) {
  const { data } = await client.requestEnvelope<CommentDto>(`${ROOT}/comments/`, {
    method: "POST",
    body: {
      ...("taskId" in target ? { task_id: target.taskId } : { project_id: target.projectId }),
      content_html: input.content,
      mentioned_user_ids: input.mentionedUserIds,
    },
  });
  return data;
}

export async function patchComment(client: ApiClient, commentId: string, input: CommentInput) {
  const { data } = await client.requestEnvelope<CommentDto>(`${ROOT}/comments/${encodeURIComponent(commentId)}/`, {
    method: "PATCH",
    body: { content_html: input.content, mentioned_user_ids: input.mentionedUserIds },
  });
  return data;
}

export async function deleteComment(client: ApiClient, commentId: string) {
  const { data } = await client.requestEnvelope<CommentDto>(`${ROOT}/comments/${encodeURIComponent(commentId)}/`, {
    method: "DELETE",
  });
  return data;
}

export function listTaskActivities(client: ApiClient, taskId: string) {
  return collectAllPages((cursor) => fetchPage<ActivityDto>(client, `${task(taskId)}/activities/`, { cursor }));
}

export function listTaskAttachments(client: ApiClient, taskId: string) {
  return collectAllPages((cursor) => fetchPage<AttachmentDto>(client, `${task(taskId)}/attachments/`, { cursor }));
}

export interface PresignInput {
  fileName: string;
  fileSize: number;
  contentType: string;
}

export async function presignAttachment(client: ApiClient, taskId: string, input: PresignInput) {
  const { data } = await client.requestEnvelope<AttachmentPresignDto>(
    `${ROOT}${task(taskId)}/attachments/presigned-url/`,
    {
      method: "POST",
      body: { file_name: input.fileName, file_size: input.fileSize, content_type: input.contentType },
    },
  );
  return data;
}

/** `PUT` thẳng lên kho lưu trữ (không qua `ApiClient`, không gửi token). Lỗi mạng/CORS → `ApiError` status 0. */
export async function uploadToStorage(
  presign: Pick<AttachmentPresignDto, "presigned_url" | "headers">,
  file: Blob,
  fetchImpl: typeof fetch = fetch,
) {
  let response: Response;
  try {
    response = await fetchImpl(presign.presigned_url, { method: "PUT", headers: presign.headers, body: file });
  } catch {
    throw new ApiError({ status: 0, message: "Không tải được tệp lên kho lưu trữ. Hãy thử lại." });
  }
  if (!response.ok) {
    throw new ApiError({ status: response.status, code: "STORAGE_REJECTED", message: "Kho lưu trữ từ chối tệp. Hãy chọn lại tệp và thử lại." });
  }
}

/** `Idempotency-Key` bắt buộc. Xác nhận muộn quá hạn presign → 422, phải xin presign mới. */
export async function confirmAttachment(
  client: ApiClient,
  taskId: string,
  input: { attachmentId: string; idempotencyKey: string },
) {
  const { data } = await client.requestEnvelope<AttachmentDto>(`${ROOT}${task(taskId)}/attachments/`, {
    method: "POST",
    body: { attachment_id: input.attachmentId },
    idempotencyKey: input.idempotencyKey,
  });
  return data;
}

/** Liên kết tải có hạn 300 giây: gọi ngay trước khi mở, không cache. */
export async function getAttachmentDownloadUrl(client: ApiClient, taskId: string, attachmentId: string) {
  const { data } = await client.requestEnvelope<AttachmentDownloadDto>(
    `${ROOT}${task(taskId)}/attachments/${encodeURIComponent(attachmentId)}/download/`,
  );
  return data.download_url;
}

export async function deleteAttachment(client: ApiClient, taskId: string, attachmentId: string) {
  const { data } = await client.requestEnvelope<AttachmentDto>(
    `${ROOT}${task(taskId)}/attachments/${encodeURIComponent(attachmentId)}/`,
    { method: "DELETE" },
  );
  return data;
}
