import { http, type HttpHandler } from "msw";

import type { RelationTypeDto, TaskDto } from "@/lib/api/work/dto";
import { envelope, envelopeError } from "@/test/classroomHandlers";
import { buildEpic, buildLabel, type StoredRelation, type TaskFixture } from "@/test/workHandlers.tasks";
import { failure, record } from "@/test/workHandlers.shared";

const NOT_FOUND = () => envelopeError(404, "RESOURCE_NOT_FOUND", "Không tìm thấy công việc.");
const STALE = () => envelopeError(409, "VERSION_CONFLICT", "Dữ liệu đã được cập nhật bởi thao tác khác.");

/** Có đường `BLOCKS` từ `from` tới `to` không (kiểm vòng chặn như `check_cycle` của backend). */
function reaches(relations: StoredRelation[], from: string, to: string): boolean {
  const seen = new Set<string>();
  const stack = [from];
  while (stack.length > 0) {
    const node = stack.pop() as string;
    if (node === to) return true;
    if (seen.has(node)) continue;
    seen.add(node);
    for (const edge of relations) if (edge.relation_type === "BLOCKS" && edge.task_id === node) stack.push(edge.related_task_id);
  }
  return false;
}

function subtreeIds(tasks: TaskDto[], rootId: string): Set<string> {
  const ids = new Set([rootId]);
  let grew = true;
  while (grew) {
    grew = false;
    for (const task of tasks) {
      if (task.parent_id && ids.has(task.parent_id) && !ids.has(task.id)) {
        ids.add(task.id);
        grew = true;
      }
    }
  }
  return ids;
}

/** Epic, nhãn, nhãn của task, liên kết task và vòng đời task (lưu trữ/xóa). Kiểm quyền trước, version sau, như backend. */
export function metaHandlers(fixture: TaskFixture): HttpHandler[] {
  const find = (id: unknown) => fixture.tasks?.find((task) => task.id === id);
  const lifecycle = (action: string, method: "post" | "delete", path: string) =>
    http[method](path, async ({ request, params }) => {
      const body = await record(request, fixture, `/tasks/${String(params.taskId)}/${action === "delete" ? "" : `${action}/`}`);
      if (fixture.writeError) return failure(fixture.writeError);
      const task = find(params.taskId);
      if (!task || (action === "restore" ? task.deleted_at === null : task.deleted_at !== null)) return NOT_FOUND();
      if (body.expected_version !== task.version) return STALE();
      const tasks = fixture.tasks ?? [];
      if (action === "archive") Object.assign(task, { archived_at: "2026-09-03T00:00:00Z", version: task.version + 1 });
      if (action === "unarchive") Object.assign(task, { archived_at: null, version: task.version + 1 });
      if (action === "delete") {
        for (const id of subtreeIds(tasks, task.id)) {
          const row = find(id) as TaskDto;
          Object.assign(row, { deleted_at: "2026-09-03T00:00:00Z", version: row.version + 1 });
        }
      }
      if (action === "restore") {
        const parent = task.parent_id ? find(task.parent_id) : undefined;
        if (parent?.deleted_at) return envelopeError(400, "INVALID_OPERATION", "Công việc cha đang bị xóa, hãy khôi phục công việc cha trước.");
        for (const id of subtreeIds(tasks, task.id)) {
          const row = find(id) as TaskDto;
          Object.assign(row, { deleted_at: null, version: row.version + 1 });
        }
      }
      return envelope(task);
    });

  return [
    lifecycle("archive", "post", "/api/work/tasks/:taskId/archive/"),
    lifecycle("unarchive", "post", "/api/work/tasks/:taskId/unarchive/"),
    lifecycle("restore", "post", "/api/work/tasks/:taskId/restore/"),
    lifecycle("delete", "delete", "/api/work/tasks/:taskId/"),

    http.post("/api/work/tasks/:taskId/labels/", async ({ request, params }) => {
      const body = await record(request, fixture, `/tasks/${String(params.taskId)}/labels/`);
      if (fixture.writeError) return failure(fixture.writeError);
      const task = find(params.taskId);
      if (!task) return NOT_FOUND();
      if (body.expected_version !== task.version) return STALE();
      const ids = body.label_ids as string[];
      const known = new Set((fixture.labels ?? []).map((label) => label.id));
      if (ids.some((id) => !known.has(id))) return envelopeError(422, "VALIDATION_ERROR", "Nhãn công việc phải đang hoạt động trong cùng dự án.");
      const next = new Set(task.label_ids);
      for (const id of ids) (body.action === "ADD" ? next.add(id) : next.delete(id));
      Object.assign(task, { label_ids: [...next], version: task.version + 1 });
      return envelope(task);
    }),

    http.post("/api/work/tasks/:taskId/relations/", async ({ request, params }) => {
      const body = await record(request, fixture, `/tasks/${String(params.taskId)}/relations/`);
      if (fixture.writeError) return failure(fixture.writeError);
      const task = find(params.taskId);
      if (!task) return NOT_FOUND();
      const target = find(body.related_task_id);
      if (!target || target.archived_at || target.deleted_at) {
        return envelopeError(400, "INVALID_OPERATION", "Công việc mục tiêu liên kết phải thuộc cùng dự án hiện tại.");
      }
      const type = body.relation_type as RelationTypeDto;
      const reversed = type === "BLOCKED_BY";
      const stored: StoredRelation = {
        id: `relation-${(fixture.relations?.length ?? 0) + 1}`,
        task_id: reversed ? target.id : task.id,
        related_task_id: reversed ? task.id : target.id,
        relation_type: reversed ? "BLOCKS" : (type as StoredRelation["relation_type"]),
      };
      const relations = (fixture.relations ??= []);
      if (relations.some((row) => row.task_id === stored.task_id && row.related_task_id === stored.related_task_id && row.relation_type === stored.relation_type)) {
        return envelopeError(409, "INVALID_OPERATION", "Mối liên kết giữa các công việc đã tồn tại.");
      }
      if (stored.relation_type === "BLOCKS" && reaches(relations, stored.related_task_id, stored.task_id)) {
        return envelopeError(409, "DAG_CYCLE_DETECTED", "Liên kết phụ thuộc tạo thành vòng lặp không hợp lệ.");
      }
      relations.push(stored);
      return envelope({ ...stored, project_id: task.project_id, created_at: "2026-09-03T00:00:00Z" }, { status: 201 });
    }),
    http.delete("/api/work/tasks/:taskId/relations/:relationId/", async ({ request, params }) => {
      await record(request, fixture, `/tasks/${String(params.taskId)}/relations/${String(params.relationId)}/`);
      if (fixture.writeError) return failure(fixture.writeError);
      const index = fixture.relations?.findIndex((row) => row.id === params.relationId) ?? -1;
      if (index < 0) return envelopeError(404, "RESOURCE_NOT_FOUND", "Không tìm thấy mối liên kết công việc yêu cầu.");
      fixture.relations?.splice(index, 1);
      return envelope({ deleted_relation_id: String(params.relationId) });
    }),

    http.post("/api/work/projects/:projectId/epics/", async ({ request, params }) => {
      const body = await record(request, fixture, `/projects/${String(params.projectId)}/epics/`);
      if (fixture.writeError) return failure(fixture.writeError);
      if (typeof body.start_date === "string" && typeof body.target_date === "string" && body.start_date > body.target_date) {
        return envelopeError(400, "VALIDATION_ERROR", "Ngày mục tiêu không được diễn ra trước ngày bắt đầu.");
      }
      const epic = buildEpic({ ...body, id: `epic-new-${(fixture.epics?.length ?? 0) + 1}`, project_id: String(params.projectId) } as never);
      (fixture.epics ??= []).push(epic);
      return envelope(epic, { status: 201 });
    }),
    http.patch("/api/work/projects/:projectId/epics/:epicId/", async ({ request, params }) => {
      const body = await record(request, fixture, `/projects/${String(params.projectId)}/epics/${String(params.epicId)}/`);
      if (fixture.writeError) return failure(fixture.writeError);
      const epic = fixture.epics?.find((row) => row.id === params.epicId);
      if (!epic) return envelopeError(404, "RESOURCE_NOT_FOUND", "Không tìm thấy mục tiêu lớn (epic) yêu cầu.");
      Object.assign(epic, body);
      return envelope(epic);
    }),
    http.delete("/api/work/projects/:projectId/epics/:epicId/", async ({ request, params }) => {
      await record(request, fixture, `/projects/${String(params.projectId)}/epics/${String(params.epicId)}/`);
      if (fixture.writeError) return failure(fixture.writeError);
      fixture.epics = (fixture.epics ?? []).filter((row) => row.id !== params.epicId);
      for (const task of fixture.tasks ?? []) if (task.epic_id === params.epicId) task.epic_id = null;
      return envelope({ deleted_epic_id: String(params.epicId) });
    }),

    http.post("/api/work/projects/:projectId/labels/", async ({ request, params }) => {
      const body = await record(request, fixture, `/projects/${String(params.projectId)}/labels/`);
      if (fixture.writeError) return failure(fixture.writeError);
      if (typeof body.color !== "string" || !/^#[0-9A-Fa-f]{6}$/.test(body.color)) {
        return envelopeError(422, "VALIDATION_ERROR", "Màu nhãn phải gồm dấu # và 6 ký tự thập lục phân (0–9, A–F).");
      }
      const label = buildLabel({ ...body, id: `label-new-${(fixture.labels?.length ?? 0) + 1}`, project_id: String(params.projectId) } as never);
      (fixture.labels ??= []).push(label);
      return envelope(label, { status: 201 });
    }),
    http.patch("/api/work/projects/:projectId/labels/:labelId/", async ({ request, params }) => {
      const body = await record(request, fixture, `/projects/${String(params.projectId)}/labels/${String(params.labelId)}/`);
      if (fixture.writeError) return failure(fixture.writeError);
      const label = fixture.labels?.find((row) => row.id === params.labelId);
      if (!label) return envelopeError(404, "RESOURCE_NOT_FOUND", "Không tìm thấy nhãn công việc yêu cầu.");
      Object.assign(label, body);
      return envelope(label);
    }),
    http.delete("/api/work/projects/:projectId/labels/:labelId/", async ({ request, params }) => {
      await record(request, fixture, `/projects/${String(params.projectId)}/labels/${String(params.labelId)}/`);
      if (fixture.writeError) return failure(fixture.writeError);
      fixture.labels = (fixture.labels ?? []).filter((row) => row.id !== params.labelId);
      for (const task of fixture.tasks ?? []) {
        if (task.label_ids.includes(String(params.labelId))) {
          task.label_ids = task.label_ids.filter((id) => id !== params.labelId);
          task.version += 1;
        }
      }
      return envelope({ deleted_label_id: String(params.labelId) });
    }),
  ];
}
