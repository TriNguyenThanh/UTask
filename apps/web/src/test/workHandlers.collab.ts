import { http, HttpResponse, type HttpHandler } from "msw";

import type { ActivityDto, AttachmentDto, CommentDto } from "@/lib/api/work/dto";
import { envelope, envelopeError } from "@/test/classroomHandlers";
import { failure, listResponse, record } from "@/test/workHandlers.shared";
import type { TaskFixture } from "@/test/workHandlers.tasks";

export const STORAGE_ORIGIN = "https://storage.test";

export function buildComment(overrides: Partial<CommentDto> = {}): CommentDto {
  return {
    id: "comment-1",
    project_id: "project-1",
    task_id: "task-1",
    user_id: "user-1",
    display_name: "Nguyễn Hoàng Nam",
    avatar_url: null,
    content_html: "Đã xem",
    content_stripped: "Đã xem",
    is_teacher_feedback: false,
    created_at: "2026-09-02T08:00:00Z",
    updated_at: "2026-09-02T08:00:00Z",
    deleted_at: null,
    mentioned_user_ids: [],
    ...overrides,
  };
}

export function buildActivity(overrides: Partial<ActivityDto> = {}): ActivityDto {
  return {
    id: "activity-1",
    actor_user_id: "user-1",
    verb: "updated",
    field: "priority",
    old_value: '"LOW"',
    new_value: '"HIGH"',
    created_at: "2026-09-02T09:00:00Z",
    ...overrides,
  };
}

export function buildAttachment(overrides: Partial<AttachmentDto> = {}): AttachmentDto {
  return {
    id: "attachment-1",
    project_id: "project-1",
    task_id: "task-1",
    file_name: "thiet-ke.png",
    file_size: 2048,
    content_type: "image/png",
    status: "CONFIRMED",
    expires_at: null,
    confirmed_at: "2026-09-02T10:00:00Z",
    deleted_at: null,
    uploaded_by_user_id: "user-1",
    created_at: "2026-09-02T10:00:00Z",
    ...overrides,
  };
}

export interface CollabFixture {
  /** Người đang đăng nhập theo mock (tác giả của bình luận mới, chủ của tệp mới). */
  actorId?: string;
  actorIsLeader?: boolean;
  /** Bình luận mới mang `is_teacher_feedback: true`. */
  actorIsTeacher?: boolean;
  comments?: CommentDto[];
  activities?: Record<string, ActivityDto[]>;
  attachments?: AttachmentDto[];
  /** Id không thuộc phạm vi dự án: bình luận nhắc tới chúng bị 422. */
  invalidMentions?: string[];
  /** `presigned-url` trả 503 (kho lưu trữ chưa sẵn sàng). */
  storageUnavailable?: boolean;
  /** `PUT` lên kho lưu trữ trả mã này. */
  storageStatus?: number;
  /** Xác nhận trả 422 như khi presign đã hết hạn. */
  presignExpired?: boolean;
}

const NOT_FOUND = () => envelopeError(404, "RESOURCE_NOT_FOUND", "Không tìm thấy tài nguyên yêu cầu.");
const FORBIDDEN = (message: string) => envelopeError(403, "PERMISSION_DENIED", message);

/** Bình luận, lịch sử, tệp đính kèm. Kiểm quyền/trạng thái trước, rồi mới đến nội dung, như backend. */
export function collabHandlers(fixture: TaskFixture & CollabFixture): HttpHandler[] {
  const actor = () => fixture.actorId ?? "user-1";
  const comments = () => (fixture.comments ??= []);
  const attachments = () => (fixture.attachments ??= []);
  const pending = new Map<string, AttachmentDto>();
  let sequence = 0;

  const commentError = (content: unknown, mentions: unknown) => {
    if (typeof content !== "string" || content.trim() === "" || content.length > 100000) {
      return envelopeError(422, "VALIDATION_ERROR", "Nội dung bình luận không hợp lệ.");
    }
    const ids = Array.isArray(mentions) ? mentions.map(String) : [];
    if (ids.some((id) => fixture.invalidMentions?.includes(id))) {
      return envelopeError(422, "VALIDATION_ERROR", "Người nhận thông báo không thuộc phạm vi của dự án.");
    }
    return null;
  };

  const commentsOf = (match: (comment: CommentDto) => boolean, url: URL) =>
    listResponse(comments().filter((comment) => comment.deleted_at === null && match(comment)), url, fixture, false);

  return [
    http.get("/api/work/tasks/:taskId/comments/", ({ request, params }) =>
      commentsOf((comment) => comment.task_id === params.taskId, new URL(request.url))),
    http.get("/api/work/projects/:projectId/comments/", ({ request, params }) =>
      commentsOf((comment) => comment.task_id === null && comment.project_id === params.projectId, new URL(request.url))),

    http.post("/api/work/comments/", async ({ request }) => {
      const body = await record(request, fixture, "/comments/");
      if (fixture.writeError) return failure(fixture.writeError);
      if (("task_id" in body) === ("project_id" in body)) {
        return envelopeError(422, "VALIDATION_ERROR", "Bình luận phải gắn với chính xác một công việc hoặc dự án.");
      }
      const invalid = commentError(body.content_html, body.mentioned_user_ids);
      if (invalid) return invalid;
      const content = String(body.content_html);
      const created = buildComment({
        id: `comment-new-${++sequence}`,
        task_id: typeof body.task_id === "string" ? body.task_id : null,
        project_id: typeof body.project_id === "string" ? body.project_id : "project-1",
        user_id: actor(),
        display_name: "",
        content_html: content,
        content_stripped: content,
        is_teacher_feedback: fixture.actorIsTeacher ?? false,
        created_at: "2026-09-03T08:00:00Z",
        mentioned_user_ids: Array.isArray(body.mentioned_user_ids) ? body.mentioned_user_ids.map(String) : [],
      });
      comments().push(created);
      return HttpResponse.json({ success: true, message: "OK", data: created, meta: null, error: null }, { status: 201 });
    }),

    http.patch("/api/work/comments/:commentId/", async ({ request, params }) => {
      const body = await record(request, fixture, `/comments/${String(params.commentId)}/`);
      const comment = comments().find((row) => row.id === params.commentId && row.deleted_at === null);
      if (!comment) return NOT_FOUND();
      if (comment.user_id !== actor()) return FORBIDDEN("Chỉ tác giả được sửa bình luận.");
      const invalid = commentError(body.content_html, body.mentioned_user_ids);
      if (invalid) return invalid;
      Object.assign(comment, {
        content_html: String(body.content_html),
        content_stripped: String(body.content_html),
        mentioned_user_ids: Array.isArray(body.mentioned_user_ids) ? body.mentioned_user_ids.map(String) : [],
      });
      return envelope(comment);
    }),

    http.delete("/api/work/comments/:commentId/", async ({ request, params }) => {
      await record(request, fixture, `/comments/${String(params.commentId)}/`);
      const comment = comments().find((row) => row.id === params.commentId && row.deleted_at === null);
      if (!comment) return NOT_FOUND();
      if (comment.user_id !== actor() && !fixture.actorIsLeader) {
        return FORBIDDEN("Chỉ tác giả hoặc trưởng nhóm được xóa bình luận.");
      }
      comment.deleted_at = "2026-09-03T09:00:00Z";
      return envelope(comment);
    }),

    http.get("/api/work/tasks/:taskId/activities/", ({ request, params }) =>
      listResponse(fixture.activities?.[String(params.taskId)] ?? [], new URL(request.url), fixture, false)),

    http.get("/api/work/tasks/:taskId/attachments/", ({ request, params }) =>
      listResponse(
        attachments().filter((row) => row.task_id === params.taskId && row.status === "CONFIRMED" && row.deleted_at === null),
        new URL(request.url),
        fixture,
        false,
      )),

    http.post("/api/work/tasks/:taskId/attachments/presigned-url/", async ({ request, params }) => {
      const body = await record(request, fixture, `/tasks/${String(params.taskId)}/attachments/presigned-url/`);
      if (fixture.writeError) return failure(fixture.writeError);
      if (fixture.storageUnavailable) return envelopeError(503, "SERVICE_UNAVAILABLE", "Kho lưu trữ chưa sẵn sàng.");
      const id = `attachment-new-${++sequence}`;
      pending.set(
        id,
        buildAttachment({
          id,
          task_id: String(params.taskId),
          file_name: String(body.file_name),
          file_size: Number(body.file_size),
          content_type: String(body.content_type),
          status: "PENDING",
          confirmed_at: null,
          uploaded_by_user_id: actor(),
        }),
      );
      return envelope({
        attachment_id: id,
        presigned_url: `${STORAGE_ORIGIN}/upload/${id}`,
        headers: { "Content-Type": String(body.content_type) },
        expires_in: 900,
      });
    }),

    http.put(`${STORAGE_ORIGIN}/upload/:attachmentId`, ({ params }) => {
      fixture.calls?.push({
        method: "PUT",
        path: `/storage/upload/${String(params.attachmentId)}`,
        idempotencyKey: null,
        body: null,
      });
      return new HttpResponse(null, { status: fixture.storageStatus ?? 200 });
    }),

    http.post("/api/work/tasks/:taskId/attachments/", async ({ request, params }) => {
      const body = await record(request, fixture, `/tasks/${String(params.taskId)}/attachments/`);
      if (fixture.writeError) return failure(fixture.writeError);
      if (!request.headers.get("Idempotency-Key")) {
        return envelopeError(400, "IDEMPOTENCY_KEY_REQUIRED", "Thiếu Idempotency-Key.");
      }
      const row = pending.get(String(body.attachment_id));
      if (!row) return NOT_FOUND();
      if (fixture.presignExpired) return envelopeError(422, "VALIDATION_ERROR", "Phiên tải lên đã hết hạn.");
      Object.assign(row, { status: "CONFIRMED", confirmed_at: "2026-09-03T10:00:00Z" });
      pending.delete(row.id);
      attachments().push(row);
      return envelope(row);
    }),

    http.get("/api/work/tasks/:taskId/attachments/:attachmentId/download/", ({ params }) => {
      const row = attachments().find((item) => item.id === params.attachmentId);
      if (!row) return NOT_FOUND();
      return envelope({ download_url: `${STORAGE_ORIGIN}/download/${row.id}`, expires_in: 300 });
    }),

    http.delete("/api/work/tasks/:taskId/attachments/:attachmentId/", async ({ request, params }) => {
      await record(request, fixture, `/tasks/${String(params.taskId)}/attachments/${String(params.attachmentId)}/`);
      if (fixture.writeError) return failure(fixture.writeError);
      const row = attachments().find((item) => item.id === params.attachmentId && item.deleted_at === null);
      if (!row) return NOT_FOUND();
      row.deleted_at = "2026-09-03T11:00:00Z";
      return envelope(row);
    }),
  ];
}
