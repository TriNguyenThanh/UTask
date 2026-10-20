import { http, type HttpHandler } from "msw";

import type { DashboardDto, SprintBurndownDto, SprintDto, SprintProgressDto } from "@/lib/api/work/dto";
import { envelope, envelopeError } from "@/test/classroomHandlers";
import { failure, record } from "@/test/workHandlers.shared";
import { buildSprint, type TaskFixture } from "@/test/workHandlers.tasks";

export function buildProgress(overrides: Partial<SprintProgressDto["totals"]> = {}, sprintId = "sprint-1"): SprintProgressDto {
  return {
    sprint_id: sprintId,
    formula_version: "v1",
    captured_at: "2026-09-05T00:00:00Z",
    snapshot_version: null,
    totals: {
      task_count: 4,
      work_item_count: 4,
      completed_task_count: 1,
      completed_work_item_count: 1,
      cancelled_task_count: 0,
      cancelled_work_item_count: 0,
      blocked_task_count: 1,
      overdue_task_count: 0,
      estimated_count: 3,
      unestimated_count: 1,
      known_estimate_points: 12,
      completed_estimate_points: 3,
      cancelled_estimate_points: 0,
      completion_percent: 25,
      ...overrides,
    },
  };
}

export function buildDashboard(overrides: Partial<DashboardDto> = {}): DashboardDto {
  return {
    project_id: "project-1",
    formula_version: "v1",
    scope: "ACTIVE_TASKS",
    computed_at: "2026-09-05T00:00:00Z",
    business_date: "2026-09-05",
    source_event_sequence: 1,
    board_revision: 1,
    totals: { ...buildProgress().totals, dependency_blocked_task_count: 0 },
    state_distribution: [{ group: "UNSTARTED", task_count: 2, work_item_count: 2 }],
    assignee_distribution: [],
    unassigned_estimate_points: 0,
    ...overrides,
  };
}

export interface SprintFixtureExtras {
  progress?: Record<string, SprintProgressDto>;
  burndown?: Record<string, SprintBurndownDto>;
  dashboard?: DashboardDto;
}

const NOT_FOUND = () => envelopeError(404, "RESOURCE_NOT_FOUND", "Không tìm thấy chu kỳ làm việc yêu cầu.");
const STALE = () => envelopeError(409, "VERSION_CONFLICT", "Dữ liệu đã được cập nhật bởi thao tác khác.");
const NEEDS_KEY = () => envelopeError(400, "IDEMPOTENCY_KEY_REQUIRED", "Thiếu Idempotency-Key.");

/** Sprint, tiến độ, burndown, dashboard và capacity. Kiểm quyền/trạng thái trước, version sau, như backend. */
export function sprintHandlers(fixture: TaskFixture & SprintFixtureExtras): HttpHandler[] {
  const sprints = () => (fixture.sprints ??= []);
  const find = (id: unknown) => sprints().find((row) => row.id === id);
  const bump = (row: SprintDto) => {
    row.version += 1;
  };

  return [
    http.get("/api/work/sprints/:sprintId/", ({ params }) => {
      const sprint = find(params.sprintId);
      return sprint ? envelope(sprint) : NOT_FOUND();
    }),
    http.post("/api/work/projects/:projectId/sprints/", async ({ request, params }) => {
      const body = await record(request, fixture, `/projects/${String(params.projectId)}/sprints/`);
      if (fixture.writeError) return failure(fixture.writeError);
      if (typeof body.start_date === "string" && typeof body.end_date === "string" && body.start_date > body.end_date) {
        return envelopeError(422, "VALIDATION_ERROR", "Ngày kết thúc không được diễn ra trước ngày bắt đầu.");
      }
      const sprint = buildSprint({
        id: `sprint-new-${sprints().length + 1}`,
        project_id: String(params.projectId),
        name: String(body.name),
        goal: (body.goal as string | undefined) ?? "",
        status: "DRAFT",
        start_date: (body.start_date as string | null | undefined) ?? null,
        end_date: (body.end_date as string | null | undefined) ?? null,
        started_at: null,
        sort_order: sprints().length + 1,
      });
      sprints().push(sprint);
      return envelope(sprint, { status: 201 });
    }),
    http.patch("/api/work/sprints/:sprintId/", async ({ request, params }) => {
      const body = await record(request, fixture, `/sprints/${String(params.sprintId)}/`);
      if (fixture.writeError) return failure(fixture.writeError);
      const sprint = find(params.sprintId);
      if (!sprint) return NOT_FOUND();
      if (sprint.status === "COMPLETED") return envelopeError(400, "INVALID_OPERATION", "Không thể chỉnh sửa chu kỳ làm việc đã đóng.");
      if (body.expected_version !== sprint.version) return STALE();
      const { expected_version: _version, ...fields } = body;
      Object.assign(sprint, fields);
      bump(sprint);
      return envelope(sprint);
    }),
    http.post("/api/work/projects/:projectId/sprints/:sprintId/start/", async ({ request, params }) => {
      const body = await record(request, fixture, `/projects/${String(params.projectId)}/sprints/${String(params.sprintId)}/start/`);
      if (fixture.writeError) return failure(fixture.writeError);
      if (!request.headers.get("Idempotency-Key")) return NEEDS_KEY();
      const sprint = find(params.sprintId);
      if (!sprint) return NOT_FOUND();
      if (body.expected_version !== sprint.version) return STALE();
      if (sprint.status !== "DRAFT" || !sprint.start_date || !sprint.end_date) {
        return envelopeError(400, "INVALID_OPERATION", "Chỉ có thể bắt đầu chu kỳ nháp có đủ ngày bắt đầu và ngày kết thúc.");
      }
      if (sprints().some((other) => other.status === "ACTIVE" && other.id !== sprint.id)) {
        return envelopeError(409, "ACTIVE_SPRINT_EXISTS", "Dự án đã có một chu kỳ làm việc đang hoạt động.");
      }
      Object.assign(sprint, { status: "ACTIVE", started_at: "2026-09-05T00:00:00Z" });
      bump(sprint);
      return envelope(sprint);
    }),
    http.post("/api/work/sprints/:sprintId/tasks/", async ({ request, params }) => {
      const body = await record(request, fixture, `/sprints/${String(params.sprintId)}/tasks/`);
      if (fixture.writeError) return failure(fixture.writeError);
      if (!request.headers.get("Idempotency-Key")) return NEEDS_KEY();
      const sprint = find(params.sprintId);
      if (!sprint) return NOT_FOUND();
      if (body.expected_version !== sprint.version) return STALE();
      if (sprint.status === "COMPLETED") {
        return envelopeError(400, "INVALID_OPERATION", "Không thể thay đổi phạm vi công việc của chu kỳ đã đóng.");
      }
      const reason = typeof body.scope_change_reason === "string" ? body.scope_change_reason.trim() : "";
      if (sprint.status === "ACTIVE" && !reason) {
        return envelopeError(422, "SCOPE_CHANGE_REASON_REQUIRED", "Vui lòng cung cấp lý do khi thay đổi phạm vi của chu kỳ đang hoạt động.");
      }
      const members = (fixture.sprintTasks ??= {});
      const ids = body.task_ids as string[];
      const changed: string[] = [];
      for (const id of ids) {
        const owner = Object.entries(members).find(([, list]) => list.includes(id))?.[0];
        if (body.action === "ADD") {
          if (owner && owner !== sprint.id) {
            return envelopeError(400, "INVALID_OPERATION", "Công việc đang thuộc chu kỳ làm việc khác, vui lòng gỡ bỏ trước khi thêm vào chu kỳ mới.");
          }
          if (!owner) {
            (members[sprint.id] ??= []).push(id);
            changed.push(id);
          }
        } else if (owner === sprint.id) {
          members[sprint.id] = members[sprint.id].filter((taskId) => taskId !== id);
          changed.push(id);
        }
      }
      if (changed.length > 0) bump(sprint);
      return envelope({
        sprint_id: sprint.id,
        modified_task_ids: changed,
        is_scope_creep: sprint.status === "ACTIVE" && changed.length > 0,
        version: sprint.version,
      });
    }),
    http.post("/api/work/sprints/:sprintId/close/", async ({ request, params }) => {
      const body = await record(request, fixture, `/sprints/${String(params.sprintId)}/close/`);
      if (fixture.writeError) return failure(fixture.writeError);
      if (!request.headers.get("Idempotency-Key")) return NEEDS_KEY();
      const sprint = find(params.sprintId);
      if (!sprint) return NOT_FOUND();
      if (body.expected_version !== sprint.version) return STALE();
      if (sprint.status !== "ACTIVE") return envelopeError(400, "INVALID_OPERATION", "Chỉ có thể đóng chu kỳ làm việc đang hoạt động.");
      const targetId = (body.target_sprint_id as string | null | undefined) ?? null;
      const target = targetId ? find(targetId) : undefined;
      if (targetId && target?.status !== "DRAFT") {
        return envelopeError(400, "INVALID_OPERATION", "Chu kỳ đích phải là chu kỳ nháp trong cùng dự án.");
      }
      const members = (fixture.sprintTasks ??= {});
      const finished = new Set(
        (fixture.tasks ?? [])
          .filter((task) => {
            const group = fixture.states?.find((state) => state.id === task.state_id)?.group;
            return group === "COMPLETED" || group === "CANCELLED";
          })
          .map((task) => task.id),
      );
      const unfinished = (members[sprint.id] ?? []).filter((id) => !finished.has(id));
      members[sprint.id] = (members[sprint.id] ?? []).filter((id) => finished.has(id));
      if (target) (members[target.id] ??= []).push(...unfinished);
      Object.assign(sprint, { status: "COMPLETED", closed_at: "2026-09-14T00:00:00Z" });
      bump(sprint);
      return envelope({
        sprint_id: sprint.id,
        status: "COMPLETED",
        closed_at: "2026-09-14T00:00:00Z",
        snapshot_version: 1,
        target_sprint_id: target?.id ?? null,
        summary: { completed_task_count: finished.size, unfinished_task_count: unfinished.length },
      });
    }),
    http.get("/api/work/sprints/:sprintId/progress/", ({ params }) => {
      const progress = fixture.progress?.[String(params.sprintId)];
      return progress ? envelope(progress) : NOT_FOUND();
    }),
    http.get("/api/work/sprints/:sprintId/burndown/", ({ params }) => {
      const burndown = fixture.burndown?.[String(params.sprintId)];
      return burndown ? envelope(burndown) : NOT_FOUND();
    }),
    http.get("/api/work/projects/:projectId/dashboard/", ({ request }) => {
      // Backend từ chối mọi query param bằng 422; mock giữ nguyên để lộ lỗi gửi thừa.
      if ([...new URL(request.url).searchParams.keys()].length > 0) {
        return envelopeError(400, "VALIDATION_ERROR", "Tham số truy vấn không được hỗ trợ.");
      }
      return fixture.dashboard ? envelope(fixture.dashboard) : envelopeError(404, "RESOURCE_NOT_FOUND", "Không tìm thấy dự án yêu cầu.");
    }),
  ];
}
