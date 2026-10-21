import { http, type HttpHandler } from "msw";

import type { ProjectDto, ProjectMemberDto } from "@/lib/api/work/dto";
import { envelope, envelopeError } from "@/test/classroomHandlers";
import {
  failure,
  listResponse,
  record,
  type BaseWorkFixture,
  type WorkError,
} from "@/test/workHandlers.shared";

export function buildProject(overrides: Partial<ProjectDto> = {}): ProjectDto {
  return {
    id: "project-1",
    identifier: "NEXUS",
    name: "Hệ thống Nexus",
    description: "Mô tả dự án",
    target_goals: "Mục tiêu dự án",
    tech_stack: {},
    start_date: "2026-09-01",
    end_date: "2026-12-31",
    classroom_group_id: "group-1",
    class_id: "class-1",
    group_source_version: 1,
    version: 1,
    board_revision: 0,
    github_repo_name: null,
    github_repo_id: null,
    github_connection_status: null,
    github_synced_at: null,
    created_at: "2026-09-01T00:00:00Z",
    updated_at: "2026-09-01T00:00:00Z",
    archived_at: null,
    ...overrides,
  };
}

export function buildProjectMember(overrides: Partial<ProjectMemberDto> = {}): ProjectMemberDto {
  return {
    id: "pm-1",
    user_id: "user-1",
    display_name: "Nguyễn Văn A",
    avatar_url: null,
    role: "MEMBER",
    status: "ACTIVE",
    weekly_capacity: 10,
    github_username: null,
    github_user_id: null,
    is_github_verified: false,
    joined_at: "2026-09-01T00:00:00Z",
    left_at: null,
    updated_at: "2026-09-01T00:00:00Z",
    ...overrides,
  };
}

export interface ProjectFixture extends BaseWorkFixture {
  /** Handler ghi thẳng vào mảng này (POST/PATCH/archive), nên test đọc lại được trạng thái. */
  projects: ProjectDto[];
  members?: Record<string, ProjectMemberDto[]>;
  listError?: WorkError;
  getError?: WorkError;
  createError?: WorkError;
  patchError?: WorkError;
  archiveError?: WorkError;
  /** Ép hai route GitHub của thành viên trả lỗi này. */
  githubError?: WorkError;
}

const STATUS_FILTERS = ["active", "archived", "all"];
const MEMBER_STATUS_FILTERS = ["ACTIVE", "LEFT", "REMOVED", "all"];

export function projectHandlers(fixture: ProjectFixture): HttpHandler[] {
  const find = (id: unknown) => fixture.projects.find((project) => project.id === id);
  const notFound = () => envelopeError(404, "RESOURCE_NOT_FOUND", "Không tìm thấy dự án.");

  return [
    http.get("/api/work/projects/", ({ request }) => {
      if (fixture.listError) return failure(fixture.listError);
      const url = new URL(request.url);
      const status = url.searchParams.get("status") ?? "active";
      if (!STATUS_FILTERS.includes(status)) {
        return envelopeError(400, "VALIDATION_ERROR", "Dữ liệu không hợp lệ.");
      }
      const projects = fixture.projects.filter(
        (project) => status === "all" || (status === "archived") === (project.archived_at !== null),
      );
      return listResponse(projects, url, fixture, true);
    }),

    http.post("/api/work/projects/", async ({ request }) => {
      const body = await record(request, fixture, "/projects/");
      if (!request.headers.get("Idempotency-Key")) {
        return envelopeError(400, "IDEMPOTENCY_KEY_REQUIRED", "Thiếu Idempotency-Key.");
      }
      if (fixture.createError) return failure(fixture.createError);
      if (fixture.projects.some((project) => project.identifier === body.identifier)) {
        return envelopeError(409, "DUPLICATE_IDENTIFIER", "Dữ liệu xung đột với thay đổi hiện hành.");
      }
      const project = buildProject({
        id: `project-${fixture.projects.length + 1}`,
        identifier: String(body.identifier),
        name: String(body.name),
        description: String(body.description ?? ""),
        target_goals: String(body.target_goals ?? ""),
        start_date: (body.start_date as string | null) ?? null,
        end_date: (body.end_date as string | null) ?? null,
        classroom_group_id: String(body.classroom_group_id),
      });
      fixture.projects.push(project);
      return envelope(project, { status: 201 });
    }),

    http.get("/api/work/projects/:projectId/", ({ params }) => {
      if (fixture.getError) return failure(fixture.getError);
      const project = find(params.projectId);
      return project ? envelope(project) : notFound();
    }),

    http.patch("/api/work/projects/:projectId/", async ({ request, params }) => {
      const body = await record(request, fixture, `/projects/${String(params.projectId)}/`);
      if (fixture.patchError) return failure(fixture.patchError);
      const project = find(params.projectId);
      if (!project) return notFound();
      // Backend kiểm quyền ghi (đã lưu trữ → INVALID_OPERATION) trước khi so version.
      if (project.archived_at !== null) {
        return envelopeError(400, "INVALID_OPERATION", "Dự án đã lưu trữ.");
      }
      if (body.expected_version !== project.version) {
        return envelopeError(409, "VERSION_CONFLICT", "Dữ liệu xung đột với thay đổi hiện hành.");
      }
      for (const key of ["name", "description", "target_goals", "start_date", "end_date"] as const) {
        if (key in body) Object.assign(project, { [key]: body[key] });
      }
      project.version += 1;
      return envelope(project);
    }),

    ...(["archive", "unarchive"] as const).map((action) =>
      http.post(`/api/work/projects/:projectId/${action}/`, async ({ request, params }) => {
        const body = await record(request, fixture, `/projects/${String(params.projectId)}/${action}/`);
        if (fixture.archiveError) return failure(fixture.archiveError);
        const project = find(params.projectId);
        if (!project) return notFound();
        if (body.expected_version !== project.version) {
          return envelopeError(409, "VERSION_CONFLICT", "Dữ liệu xung đột với thay đổi hiện hành.");
        }
        const archived = action === "archive";
        // Gọi khi trạng thái đã đúng: 200 nhưng `version` không tăng, như backend.
        if ((project.archived_at !== null) !== archived) {
          project.archived_at = archived ? "2026-10-01T00:00:00Z" : null;
          project.version += 1;
        }
        return envelope(project);
      })),

    http.get("/api/work/projects/:projectId/members/", ({ request, params }) => {
      if (!find(params.projectId)) return notFound();
      const url = new URL(request.url);
      const status = url.searchParams.get("status") ?? "ACTIVE";
      if (!MEMBER_STATUS_FILTERS.includes(status)) {
        return envelopeError(400, "VALIDATION_ERROR", "Dữ liệu không hợp lệ.");
      }
      const members = (fixture.members?.[String(params.projectId)] ?? []).filter(
        (member) => status === "all" || member.status === status,
      );
      return listResponse(members, url, fixture, false);
    }),
    http.patch("/api/work/projects/:projectId/members/:userId/capacity/", async ({ request, params }) => {
      const body = await record(request, fixture, `/projects/${String(params.projectId)}/members/${String(params.userId)}/capacity/`);
      if (!find(params.projectId)) return notFound();
      const member = fixture.members?.[String(params.projectId)]?.find((row) => row.user_id === params.userId);
      if (!member || member.status !== "ACTIVE") {
        return envelopeError(422, "MEMBER_NOT_ACTIVE", "Thành viên không còn hoạt động.");
      }
      member.weekly_capacity = body.weekly_capacity as number;
      return envelope(member);
    }),
    http.patch("/api/work/projects/:projectId/members/:userId/github/", async ({ request, params }) => {
      const body = await record(request, fixture, `/projects/${String(params.projectId)}/members/${String(params.userId)}/github/`);
      if (fixture.githubError) return failure(fixture.githubError);
      const project = find(params.projectId);
      if (!project) return notFound();
      const member = fixture.members?.[String(params.projectId)]?.find((row) => row.user_id === params.userId);
      if (!member || member.status !== "ACTIVE") {
        return envelopeError(422, "MEMBER_NOT_ACTIVE", "Thành viên không còn hoạt động.");
      }
      if (project.archived_at !== null) return envelopeError(400, "INVALID_OPERATION", "Dự án đang ở chế độ chỉ đọc.");
      const username = typeof body.github_username === "string" ? body.github_username : "";
      if (username === "") {
        return envelopeError(400, "VALIDATION_ERROR", "Vui lòng nhập tên tài khoản GitHub của bạn.");
      }
      if (member.is_github_verified && member.github_username !== username) {
        return envelopeError(400, "INVALID_OPERATION", "Liên kết tài khoản đã xác thực chỉ có thể thay đổi thông qua cổng ủy quyền OAuth.");
      }
      member.github_username = username;
      return envelope({ user_id: member.user_id, github_username: username, is_github_verified: member.is_github_verified });
    }),
    http.post("/api/work/projects/:projectId/members/:userId/github/request-verification/", async ({ request, params }) => {
      await record(request, fixture, `/projects/${String(params.projectId)}/members/${String(params.userId)}/github/request-verification/`);
      if (fixture.githubError) return failure(fixture.githubError);
      if (!find(params.projectId)) return notFound();
      return envelope({ project_id: String(params.projectId), user_id: String(params.userId), requested_by_user_id: "leader" });
    }),
  ];
}
