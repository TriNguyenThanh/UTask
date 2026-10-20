import { http, type HttpHandler } from "msw";

import type { EpicDto, LabelDto, SprintDto, StateDto, TaskDto } from "@/lib/api/work/dto";
import { envelope, envelopeError } from "@/test/classroomHandlers";
import { failure, listResponse, record, type BaseWorkFixture, type WorkError } from "@/test/workHandlers.shared";

export function buildState(overrides: Partial<StateDto> = {}): StateDto {
  return {
    id: "state-todo",
    project_id: "project-1",
    name: "To Do",
    slug: "to-do",
    color: "#94a3b8",
    sequence: 1,
    group: "UNSTARTED",
    is_default: true,
    created_at: "2026-09-01T00:00:00Z",
    ...overrides,
  };
}

/** Năm trạng thái mặc định của backend (`projects/services/projects.py`). */
export function buildDefaultStates(): StateDto[] {
  return [
    buildState({ id: "state-backlog", name: "Backlog", slug: "backlog", sequence: 1, group: "BACKLOG", is_default: false }),
    buildState({ id: "state-todo", name: "To Do", slug: "to-do", sequence: 2, group: "UNSTARTED", is_default: true }),
    buildState({ id: "state-doing", name: "In Progress", slug: "in-progress", sequence: 3, group: "STARTED", is_default: false }),
    buildState({ id: "state-review", name: "Code Review", slug: "code-review", sequence: 4, group: "REVIEW", is_default: false }),
    buildState({ id: "state-done", name: "Done", slug: "done", sequence: 5, group: "COMPLETED", is_default: false }),
  ];
}

export function buildEpic(overrides: Partial<EpicDto> = {}): EpicDto {
  return {
    id: "epic-1",
    project_id: "project-1",
    name: "Xác thực",
    description: "",
    lead_user_id: null,
    status: "IN_PROGRESS",
    start_date: null,
    target_date: null,
    created_at: "2026-09-01T00:00:00Z",
    updated_at: "2026-09-01T00:00:00Z",
    deleted_at: null,
    ...overrides,
  };
}

export function buildLabel(overrides: Partial<LabelDto> = {}): LabelDto {
  return {
    id: "label-1",
    project_id: "project-1",
    name: "frontend",
    color: "#2563eb",
    description: null,
    created_at: "2026-09-01T00:00:00Z",
    deleted_at: null,
    ...overrides,
  };
}

export function buildSprint(overrides: Partial<SprintDto> = {}): SprintDto {
  return {
    id: "sprint-1",
    project_id: "project-1",
    name: "Sprint 1",
    goal: "",
    status: "ACTIVE",
    start_date: "2026-09-01",
    end_date: "2026-09-14",
    sort_order: 1,
    version: 1,
    started_at: "2026-09-01T00:00:00Z",
    closed_at: null,
    created_at: "2026-09-01T00:00:00Z",
    updated_at: "2026-09-01T00:00:00Z",
    archived_at: null,
    ...overrides,
  };
}

export function buildTask(overrides: Partial<TaskDto> = {}): TaskDto {
  return {
    id: "task-1",
    project_id: "project-1",
    sequence_id: 1,
    code: "NEXUS-1",
    epic_id: null,
    state_id: "state-todo",
    parent_id: null,
    type: "TASK",
    source: "MANUAL",
    acceptance_criteria: "",
    version: 1,
    title: "Công việc 1",
    description_html: "",
    description_stripped: "",
    priority: "MEDIUM",
    story_points: null,
    due_date: null,
    is_blocked: false,
    blocked_reason: null,
    sort_order: 10000,
    created_by_user_id: "user-1",
    completed_at: null,
    created_at: "2026-09-01T00:00:00Z",
    updated_at: "2026-09-01T00:00:00Z",
    archived_at: null,
    deleted_at: null,
    assignee_ids: [],
    label_ids: [],
    subtasks_count: 0,
    comments_count: 0,
    attachments_count: 0,
    ...overrides,
  };
}

export interface TaskFixture extends BaseWorkFixture {
  states?: StateDto[];
  epics?: EpicDto[];
  labels?: LabelDto[];
  tasks?: TaskDto[];
  sprints?: SprintDto[];
  /** `sprintId → taskId[]`: thành viên chu kỳ đang mở (task không có `sprint_id`). */
  sprintTasks?: Record<string, string[]>;
  /** Tên hiển thị theo `user_id`, để `expand=assignees` trả đúng như backend. */
  userNames?: Record<string, string>;
  statesError?: WorkError;
  tasksError?: WorkError;
  getTaskError?: WorkError;
  /** Mọi lệnh ghi task trả lỗi này (ví dụ 403 `TEACHER_MUTATION_RESTRICTED`). */
  writeError?: WorkError;
}

const TASK_QUERY_KEYS = new Set(["cursor", "page_size", "status", "fields", "expand", "sprint_id", "state_id", "epic_id", "parent_id", "type", "priority", "is_blocked", "due_date_from", "due_date_to", "assignee_id", "label_id", "search"]);

function expandTask(task: TaskDto, expand: string[], fixture: TaskFixture): TaskDto {
  const result: TaskDto = { ...task };
  if (expand.includes("state")) {
    result.state = fixture.states?.find((state) => state.id === task.state_id);
  }
  if (expand.includes("epic")) {
    result.epic = fixture.epics?.find((epic) => epic.id === task.epic_id) ?? null;
  }
  if (expand.includes("labels")) {
    result.labels = (fixture.labels ?? []).filter((label) => task.label_ids.includes(label.id));
  }
  if (expand.includes("assignees")) {
    result.assignees = task.assignee_ids.map((userId) => ({
      user_id: userId,
      display_name: fixture.userNames?.[userId] ?? "",
      avatar_url: null,
    }));
  }
  if (expand.includes("subtasks")) {
    result.subtasks = (fixture.tasks ?? []).filter((candidate) => candidate.parent_id === task.id);
  }
  return result;
}

export function taskHandlers(fixture: TaskFixture): HttpHandler[] {
  return [
    http.get("/api/work/projects/:projectId/states/", ({ request }) => {
      if (fixture.statesError) return failure(fixture.statesError);
      return listResponse(fixture.states ?? [], new URL(request.url), fixture, false);
    }),
    http.get("/api/work/projects/:projectId/epics/", ({ request }) =>
      listResponse(fixture.epics ?? [], new URL(request.url), fixture, false)),
    http.get("/api/work/projects/:projectId/labels/", ({ request }) =>
      listResponse(fixture.labels ?? [], new URL(request.url), fixture, false)),
    http.get("/api/work/projects/:projectId/sprints/", ({ request }) =>
      listResponse(fixture.sprints ?? [], new URL(request.url), fixture, false)),

    http.get("/api/work/projects/:projectId/tasks/", ({ request }) => {
      if (fixture.tasksError) return failure(fixture.tasksError);
      const url = new URL(request.url);
      // Backend từ chối khóa lạ bằng 422; mock giữ nguyên để lộ lỗi gửi thừa tham số.
      for (const key of url.searchParams.keys()) {
        if (!TASK_QUERY_KEYS.has(key)) {
          return envelopeError(422, "VALIDATION_ERROR", "Tham số truy vấn không được hỗ trợ.");
        }
      }
      let rows = (fixture.tasks ?? []).filter((task) => task.archived_at === null && task.deleted_at === null);
      const stateFilter = url.searchParams.get("state_id");
      if (stateFilter) rows = rows.filter((task) => task.state_id === stateFilter);
      const sprintId = url.searchParams.get("sprint_id");
      if (sprintId === "none") {
        const inSprint = new Set(Object.values(fixture.sprintTasks ?? {}).flat());
        rows = rows.filter((task) => !inSprint.has(task.id));
      } else if (sprintId) {
        const members = new Set(fixture.sprintTasks?.[sprintId] ?? []);
        rows = rows.filter((task) => members.has(task.id));
      }
      const expand = (url.searchParams.get("expand") ?? "").split(",").filter(Boolean);
      const fields = (url.searchParams.get("fields") ?? "").split(",").filter(Boolean);
      const shaped = rows.map((task) => {
        const expanded = expandTask(task, expand, fixture);
        if (fields.length === 0) return expanded;
        return Object.fromEntries(Object.entries(expanded).filter(([key]) => fields.includes(key)));
      });
      return listResponse(shaped, url, fixture, false);
    }),

    http.get("/api/work/tasks/:taskId/", ({ request, params }) => {
      if (fixture.getTaskError) return failure(fixture.getTaskError);
      const task = fixture.tasks?.find((candidate) => candidate.id === params.taskId);
      if (!task) return envelopeError(404, "RESOURCE_NOT_FOUND", "Không tìm thấy công việc.");
      const expand = (new URL(request.url).searchParams.get("expand") ?? "").split(",").filter(Boolean);
      return envelope(expandTask(task, expand, fixture));
    }),

    ...taskWriteHandlers(fixture),
  ];
}

const PATCHABLE_KEYS = new Set([
  "expected_version", "title", "description_html", "acceptance_criteria", "priority",
  "story_points", "due_date", "epic_id", "assignee_ids", "label_ids",
]);
const CREATABLE_KEYS = new Set([...PATCHABLE_KEYS, "type", "state_id"]);

function activeColumn(fixture: TaskFixture, stateId: string, excludeId: string): TaskDto[] {
  return (fixture.tasks ?? [])
    .filter((task) => task.state_id === stateId && task.id !== excludeId && task.archived_at === null && task.deleted_at === null)
    .sort((a, b) => a.sort_order - b.sort_order || a.id.localeCompare(b.id));
}

/** Giống `rank_for_position` của backend: hàng xóm phải liền kề trong cột đầy đủ, cột có task thì không được bỏ trống cả hai. */
function rankFor(column: TaskDto[], previousId: string | null, nextId: string | null): number | WorkError {
  const conflict = (message: string): WorkError => ({ status: 409, code: "VERSION_CONFLICT", message });
  if (previousId === null && nextId === null) {
    return column.length > 0 ? conflict("Cột trạng thái đang có công việc, cần chỉ định vị trí liền kề hợp lệ.") : 10000;
  }
  const index = (id: string | null) => (id === null ? -2 : column.findIndex((task) => task.id === id));
  if ((previousId !== null && index(previousId) < 0) || (nextId !== null && index(nextId) < 0)) {
    return conflict("Vị trí liền kề không thuộc cột trạng thái đích hiện tại.");
  }
  const previousIndex = previousId === null ? -1 : index(previousId);
  const nextIndex = nextId === null ? column.length : index(nextId);
  if (nextIndex !== previousIndex + 1) return conflict("Vị trí sắp xếp liền kề không còn hợp lệ, vui lòng tải lại bảng công việc.");
  const lo = previousIndex >= 0 ? column[previousIndex].sort_order : null;
  const hi = nextIndex < column.length ? column[nextIndex].sort_order : null;
  if (lo !== null && hi !== null) return lo + (hi - lo) / 2;
  return lo === null ? (hi as number) - 10000 : lo + 10000;
}

function unknownKeys(body: Record<string, unknown>, allowed: Set<string>) {
  return Object.keys(body).filter((key) => !allowed.has(key));
}

/** Lệnh ghi task: mô phỏng đúng thứ tự kiểm của backend (quyền → version → nghiệp vụ). Sửa trực tiếp `fixture.tasks`. */
function taskWriteHandlers(fixture: TaskFixture): HttpHandler[] {
  const notFound = () => envelopeError(404, "RESOURCE_NOT_FOUND", "Không tìm thấy công việc.");
  const find = (id: unknown) => fixture.tasks?.find((task) => task.id === id);
  const stale = () => envelopeError(409, "VERSION_CONFLICT", "Dữ liệu đã được cập nhật bởi thao tác khác.");
  const nextCode = (tasks: TaskDto[]) => {
    const prefix = tasks[0]?.code.split("-")[0] ?? "NEXUS";
    const sequence = Math.max(0, ...tasks.map((task) => task.sequence_id)) + 1;
    return { sequence, code: `${prefix}-${sequence}` };
  };
  const create = (parentId: string | null, projectId: string, body: Record<string, unknown>, request: Request) => {
    if (fixture.writeError) return failure(fixture.writeError);
    if (!request.headers.get("Idempotency-Key")) return envelopeError(400, "IDEMPOTENCY_KEY_REQUIRED", "Thiếu Idempotency-Key.");
    const bad = unknownKeys(body, CREATABLE_KEYS);
    if (bad.length > 0) return envelopeError(422, "VALIDATION_ERROR", `Trường không hợp lệ: ${bad.join(", ")}`);
    if (typeof body.title !== "string" || body.title.trim() === "") return envelopeError(422, "VALIDATION_ERROR", "Tiêu đề là bắt buộc.");
    fixture.tasks ??= [];
    const defaultState = fixture.states?.find((state) => state.is_default) ?? fixture.states?.[0];
    const stateId = (body.state_id as string | undefined) ?? defaultState?.id ?? "state-todo";
    const { sequence, code } = nextCode(fixture.tasks);
    const column = activeColumn(fixture, stateId, "");
    const created = buildTask({
      id: `task-new-${sequence}`,
      project_id: projectId,
      sequence_id: sequence,
      code,
      state_id: stateId,
      parent_id: parentId,
      type: parentId ? "SUBTASK" : ((body.type as TaskDto["type"] | undefined) ?? "TASK"),
      title: body.title,
      description_html: (body.description_html as string | undefined) ?? "",
      description_stripped: (body.description_html as string | undefined) ?? "",
      acceptance_criteria: (body.acceptance_criteria as string | undefined) ?? "",
      priority: (body.priority as TaskDto["priority"] | undefined) ?? "MEDIUM",
      story_points: (body.story_points as number | null | undefined) ?? null,
      due_date: (body.due_date as string | null | undefined) ?? null,
      epic_id: (body.epic_id as string | null | undefined) ?? null,
      assignee_ids: (body.assignee_ids as string[] | undefined) ?? [],
      label_ids: (body.label_ids as string[] | undefined) ?? [],
      sort_order: (column.at(-1)?.sort_order ?? 0) + 10000,
    });
    fixture.tasks.push(created);
    if (parentId) {
      const parent = find(parentId);
      if (parent) parent.subtasks_count += 1;
    }
    return envelope(created, { status: 201 });
  };

  return [
    http.post("/api/work/projects/:projectId/tasks/", async ({ request, params }) => {
      const body = await record(request, fixture, `/projects/${String(params.projectId)}/tasks/`);
      return create(null, String(params.projectId), body, request);
    }),
    http.post("/api/work/tasks/:taskId/subtasks/", async ({ request, params }) => {
      const body = await record(request, fixture, `/tasks/${String(params.taskId)}/subtasks/`);
      const parent = find(params.taskId);
      if (!parent) return notFound();
      return create(parent.id, parent.project_id, body, request);
    }),
    http.patch("/api/work/tasks/:taskId/", async ({ request, params }) => {
      const body = await record(request, fixture, `/tasks/${String(params.taskId)}/`);
      if (fixture.writeError) return failure(fixture.writeError);
      const task = find(params.taskId);
      if (!task) return notFound();
      const bad = unknownKeys(body, PATCHABLE_KEYS);
      if (bad.length > 0) return envelopeError(422, "VALIDATION_ERROR", `Trường không hợp lệ: ${bad.join(", ")}`);
      if (body.expected_version !== task.version) return stale();
      const { expected_version: _version, ...fields } = body;
      Object.assign(task, fields, { version: task.version + 1 });
      if (typeof fields.description_html === "string") task.description_stripped = fields.description_html;
      return envelope(task);
    }),
    http.patch("/api/work/tasks/:taskId/transition/", async ({ request, params }) => {
      const body = await record(request, fixture, `/tasks/${String(params.taskId)}/transition/`);
      if (fixture.writeError) return failure(fixture.writeError);
      const task = find(params.taskId);
      if (!task) return notFound();
      if (body.expected_version !== task.version) return stale();
      const target = fixture.states?.find((state) => state.id === body.target_state_id);
      if (!target) return envelopeError(422, "VALIDATION_ERROR", "Trạng thái đích không thuộc dự án hiện tại.");
      const rank = rankFor(
        activeColumn(fixture, target.id, task.id),
        (body.previous_task_id as string | null | undefined) ?? null,
        (body.next_task_id as string | null | undefined) ?? null,
      );
      if (typeof rank !== "number") return failure(rank);
      Object.assign(task, {
        state_id: target.id,
        sort_order: rank,
        version: task.version + 1,
        completed_at: target.group === "COMPLETED" ? (task.completed_at ?? "2026-09-02T00:00:00Z") : null,
      });
      return envelope({ ...task, board_revision: task.version });
    }),
    http.patch("/api/work/tasks/:taskId/block/", async ({ request, params }) => {
      const body = await record(request, fixture, `/tasks/${String(params.taskId)}/block/`);
      if (fixture.writeError) return failure(fixture.writeError);
      const task = find(params.taskId);
      if (!task) return notFound();
      if (body.expected_version !== task.version) return stale();
      const group = fixture.states?.find((state) => state.id === task.state_id)?.group;
      if (group === "COMPLETED" || group === "CANCELLED") {
        return envelopeError(400, "INVALID_OPERATION", "Không thể đánh dấu chặn trên công việc đã ở trạng thái hoàn tất hoặc đóng.");
      }
      Object.assign(task, { is_blocked: true, blocked_reason: body.blocked_reason, version: task.version + 1 });
      return envelope(task);
    }),
    http.patch("/api/work/tasks/:taskId/unblock/", async ({ request, params }) => {
      const body = await record(request, fixture, `/tasks/${String(params.taskId)}/unblock/`);
      if (fixture.writeError) return failure(fixture.writeError);
      const task = find(params.taskId);
      if (!task) return notFound();
      if (body.expected_version !== task.version) return stale();
      Object.assign(task, { is_blocked: false, blocked_reason: null, version: task.version + 1 });
      return envelope(task);
    }),
  ];
}
