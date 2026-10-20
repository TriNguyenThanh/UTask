import { http, type HttpHandler } from "msw";

import type { EpicDto, LabelDto, SprintDto, StateDto, TaskDto } from "@/lib/api/work/dto";
import { envelope, envelopeError } from "@/test/classroomHandlers";
import { failure, listResponse, type BaseWorkFixture, type WorkError } from "@/test/workHandlers.shared";

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
      let rows = [...(fixture.tasks ?? [])];
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
  ];
}
