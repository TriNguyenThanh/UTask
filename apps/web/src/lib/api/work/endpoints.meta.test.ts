import { describe, expect, it } from "vitest";

import { createApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import {
  changeTaskLifecycle,
  createEpic,
  createLabel,
  createRelation,
  deleteEpic,
  deleteLabel,
  deleteRelation,
  getTask,
  listTasks,
  listTasksInScope,
  patchEpic,
  patchLabel,
  setTaskLabels,
} from "@/lib/api/work/endpoints";
import { server } from "@/mocks/server";
import {
  buildDefaultStates,
  buildEpic,
  buildLabel,
  buildTask,
  workHandlers,
  type WorkCall,
  type WorkFixture,
} from "@/test/workHandlers";

const client = createApiClient({ baseUrl: "http://localhost", getAccessToken: () => "token", onUnauthorized: () => undefined });

function setup(fixture: Partial<WorkFixture>) {
  const calls: WorkCall[] = [];
  const full = { projects: [], states: buildDefaultStates(), calls, ...fixture };
  server.use(...workHandlers(full));
  return { calls, full };
}

describe("task lifecycle", () => {
  it("archives, unarchives, deletes and restores with expected_version and no Idempotency-Key", async () => {
    const { calls } = setup({ tasks: [buildTask({ id: "a", version: 2 })] });
    const archived = await changeTaskLifecycle(client, "a", "archive", 2);
    expect(archived.archived_at).not.toBeNull();
    await changeTaskLifecycle(client, "a", "unarchive", 3);
    await changeTaskLifecycle(client, "a", "delete", 4);
    await changeTaskLifecycle(client, "a", "restore", 5);
    expect(calls.map((call) => [call.method, call.path])).toEqual([
      ["POST", "/tasks/a/archive/"],
      ["POST", "/tasks/a/unarchive/"],
      ["DELETE", "/tasks/a/"],
      ["POST", "/tasks/a/restore/"],
    ]);
    expect(calls.every((call) => call.idempotencyKey === null)).toBe(true);
    expect(calls.map((call) => call.body)).toEqual([2, 3, 4, 5].map((expected_version) => ({ expected_version })));
  });

  it("deleting a parent soft-deletes its subtasks and restoring brings them back", async () => {
    const { full } = setup({
      tasks: [buildTask({ id: "p" }), buildTask({ id: "c", parent_id: "p", type: "SUBTASK" })],
    });
    await changeTaskLifecycle(client, "p", "delete", 1);
    expect(full.tasks?.every((task) => task.deleted_at !== null)).toBe(true);
    await changeTaskLifecycle(client, "p", "restore", 2);
    expect(full.tasks?.every((task) => task.deleted_at === null)).toBe(true);
  });

  it("rejects a stale version", async () => {
    setup({ tasks: [buildTask({ id: "a", version: 5 })] });
    const error = await changeTaskLifecycle(client, "a", "archive", 1).catch((e: unknown) => e);
    expect((error as ApiError).code).toBe("VERSION_CONFLICT");
  });

  it("listTasksInScope reads archived or deleted tasks that the default list hides", async () => {
    setup({
      tasks: [
        buildTask({ id: "live" }),
        buildTask({ id: "old", archived_at: "2026-09-01T00:00:00Z" }),
        buildTask({ id: "gone", deleted_at: "2026-09-01T00:00:00Z" }),
      ],
    });
    expect((await listTasks(client, "project-1")).map((task) => task.id)).toEqual(["live"]);
    expect((await listTasksInScope(client, "project-1", "archived")).map((task) => task.id)).toEqual(["old"]);
    expect((await listTasksInScope(client, "project-1", "deleted")).map((task) => task.id)).toEqual(["gone"]);
  });
});

describe("labels on a task", () => {
  it("ADD and REMOVE send expected_version and label_ids", async () => {
    const { calls } = setup({ tasks: [buildTask({ id: "a", version: 2 })], labels: [buildLabel({ id: "l1" })] });
    const added = await setTaskLabels(client, "a", { expectedVersion: 2, action: "ADD", labelIds: ["l1"] });
    expect(added.label_ids).toEqual(["l1"]);
    const removed = await setTaskLabels(client, "a", { expectedVersion: 3, action: "REMOVE", labelIds: ["l1"] });
    expect(removed.label_ids).toEqual([]);
    expect(calls[0]).toMatchObject({ idempotencyKey: null, body: { expected_version: 2, action: "ADD", label_ids: ["l1"] } });
  });
});

describe("relations", () => {
  const tasks = () => [buildTask({ id: "a", code: "P-1" }), buildTask({ id: "b", code: "P-2" })];

  it("shows a stored BLOCKS from the other side as BLOCKED_BY", async () => {
    setup({ tasks: tasks() });
    await createRelation(client, "a", { relatedTaskId: "b", relationType: "BLOCKS" });
    expect((await getTask(client, "a")).relations).toMatchObject([{ related_task_code: "P-2", relation_type: "BLOCKS" }]);
    expect((await getTask(client, "b")).relations).toMatchObject([{ related_task_code: "P-1", relation_type: "BLOCKED_BY" }]);
  });

  it("rejects a cycle with DAG_CYCLE_DETECTED and a duplicate with 409", async () => {
    setup({ tasks: tasks() });
    await createRelation(client, "a", { relatedTaskId: "b", relationType: "BLOCKS" });
    const cycle = await createRelation(client, "b", { relatedTaskId: "a", relationType: "BLOCKS" }).catch((e: unknown) => e);
    expect((cycle as ApiError).code).toBe("DAG_CYCLE_DETECTED");
    const duplicate = await createRelation(client, "a", { relatedTaskId: "b", relationType: "BLOCKS" }).catch((e: unknown) => e);
    expect((duplicate as ApiError).status).toBe(409);
  });

  it("deletes a relation by id", async () => {
    const { full } = setup({ tasks: tasks() });
    const created = await createRelation(client, "a", { relatedTaskId: "b", relationType: "RELATES_TO" });
    await deleteRelation(client, "a", created.id);
    expect(full.relations).toEqual([]);
  });
});

describe("epics and labels", () => {
  it("createEpic sends only the fields that were set; patchEpic can clear dates", async () => {
    const { calls, full } = setup({});
    const created = await createEpic(client, "project-1", { name: "E", status: "PLANNED", startDate: "2026-09-01" });
    expect(calls[0].body).toEqual({ name: "E", status: "PLANNED", start_date: "2026-09-01" });
    await patchEpic(client, "project-1", created.id, { startDate: null, targetDate: null });
    expect(calls[1]).toMatchObject({ method: "PATCH", body: { start_date: null, target_date: null } });
    await deleteEpic(client, "project-1", created.id);
    expect(full.epics).toEqual([]);
  });

  it("createEpic surfaces a server date-order error", async () => {
    setup({});
    const error = await createEpic(client, "project-1", { name: "E", startDate: "2026-09-10", targetDate: "2026-09-01" }).catch((e: unknown) => e);
    expect((error as ApiError).code).toBe("VALIDATION_ERROR");
  });

  it("label create/patch/delete; deleting a label strips it from tasks", async () => {
    const { calls, full } = setup({
      labels: [buildLabel({ id: "l1" })],
      tasks: [buildTask({ id: "a", label_ids: ["l1"] })],
      epics: [buildEpic({ id: "e1" })],
    });
    const created = await createLabel(client, "project-1", { name: "ui", color: "#112233" });
    expect(calls[0].body).toEqual({ name: "ui", color: "#112233" });
    await patchLabel(client, "project-1", created.id, { description: null });
    expect(calls[1].body).toEqual({ description: null });
    await deleteLabel(client, "project-1", "l1");
    expect(full.tasks?.[0].label_ids).toEqual([]);
  });
});
