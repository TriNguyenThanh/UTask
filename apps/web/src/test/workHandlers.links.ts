import { http, type HttpHandler } from "msw";

import type { TaskGitHubLinkDto } from "@/lib/api/work/dto";
import { envelope, envelopeError } from "@/test/classroomHandlers";
import { failure, record, type BaseWorkFixture, type WorkError } from "@/test/workHandlers.shared";

export function buildTaskGitHubLink(overrides: Partial<TaskGitHubLinkDto> = {}): TaskGitHubLinkDto {
  return {
    id: "link-1",
    task_id: "task-1",
    github_repo_id: "42",
    connection_generation: 1,
    source_version: 1,
    confirmation_status: "PENDING",
    confirmed_by_user_id: null,
    confirmed_at: null,
    deleted_at: null,
    link_type: "BRANCH",
    github_ref_id: "feature/login",
    github_title: null,
    github_status: null,
    github_url: null,
    is_verified: false,
    created_by_user_id: "user-1",
    synced_at: null,
    ...overrides,
  };
}

export interface LinkFixture extends BaseWorkFixture {
  /** Handler ghi thẳng vào mảng này, nên test đọc lại được trạng thái. */
  githubLinks?: TaskGitHubLinkDto[];
  /** Ép mọi route link trả lỗi này. */
  githubLinksError?: WorkError;
  /** Dự án chưa nối repo: tạo/xác nhận trả 400 `INVALID_OPERATION` như `require_connection`. */
  repositoryNotConnected?: boolean;
}

const LINK_TYPES = ["BRANCH", "COMMIT", "PULL_REQUEST"];

/** `LinkInputSerializer`: PR là số nguyên dương, tự bỏ `#` đầu và chuẩn hóa số. */
function normalizeRef(type: string, ref: string): string | null {
  if (type !== "PULL_REQUEST") return ref;
  const digits = ref.replace(/^#/, "");
  return /^[0-9]+$/.test(digits) && Number(digits) >= 1 ? String(Number(digits)) : null;
}

export function linkHandlers(fixture: LinkFixture): HttpHandler[] {
  const rows = () => (fixture.githubLinks ??= []);
  const find = (taskId: unknown, linkId: unknown) =>
    rows().find((row) => row.task_id === taskId && row.id === linkId && row.deleted_at === null);
  const NOT_FOUND = () => envelopeError(404, "RESOURCE_NOT_FOUND", "Không tìm thấy liên kết GitHub.");
  const NOT_CONNECTED = () =>
    envelopeError(400, "INVALID_OPERATION", "Dự án chưa được kết nối với kho lưu trữ mã nguồn nào.");

  return [
    http.get("/api/work/tasks/:taskId/github-links/", async ({ request, params }) => {
      await record(request, fixture, `/tasks/${String(params.taskId)}/github-links/`);
      if (fixture.githubLinksError) return failure(fixture.githubLinksError);
      return envelope(rows().filter((row) => row.task_id === params.taskId));
    }),
    http.post("/api/work/tasks/:taskId/github-links/", async ({ request, params }) => {
      const body = await record(request, fixture, `/tasks/${String(params.taskId)}/github-links/`);
      if (fixture.githubLinksError) return failure(fixture.githubLinksError);
      if (fixture.repositoryNotConnected) return NOT_CONNECTED();
      const type = String(body.link_type);
      const ref = normalizeRef(type, String(body.github_ref_id ?? ""));
      if (!LINK_TYPES.includes(type) || ref === null || ref === "") {
        return envelopeError(400, "VALIDATION_ERROR", "Dữ liệu đầu vào không hợp lệ.");
      }
      const link = buildTaskGitHubLink({
        id: `link-new-${rows().length + 1}`,
        task_id: String(params.taskId),
        link_type: type as TaskGitHubLinkDto["link_type"],
        github_ref_id: ref,
      });
      rows().push(link);
      return envelope(link, { status: 201 });
    }),
    http.post("/api/work/tasks/:taskId/github-links/:linkId/confirm/", async ({ request, params }) => {
      await record(request, fixture, `/tasks/${String(params.taskId)}/github-links/${String(params.linkId)}/confirm/`);
      if (fixture.githubLinksError) return failure(fixture.githubLinksError);
      if (!request.headers.get("Idempotency-Key")) {
        return envelopeError(400, "IDEMPOTENCY_KEY_REQUIRED", "Thiếu Idempotency-Key.");
      }
      const link = find(params.taskId, params.linkId);
      if (!link) return NOT_FOUND();
      if (fixture.repositoryNotConnected) return NOT_CONNECTED();
      if (!link.is_verified) return envelopeError(400, "INVALID_OPERATION", "Chưa thể xác minh đề xuất liên kết GitHub này.");
      link.confirmation_status = "CONFIRMED";
      link.confirmed_at = "2026-10-01T00:00:00Z";
      return envelope(link);
    }),
    http.delete("/api/work/tasks/:taskId/github-links/:linkId/", async ({ request, params }) => {
      await record(request, fixture, `/tasks/${String(params.taskId)}/github-links/${String(params.linkId)}/`);
      if (fixture.githubLinksError) return failure(fixture.githubLinksError);
      const link = find(params.taskId, params.linkId);
      if (!link) return NOT_FOUND();
      link.deleted_at = "2026-10-01T00:00:00Z";
      return envelope({ unlinked_id: link.id });
    }),
  ];
}
