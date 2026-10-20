import { describe, expect, it } from "vitest";

import { createApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import {
  blockTask,
  createSubtask,
  createTask,
  getTask,
  listEpics,
  listLabels,
  listSprints,
  listStates,
  listTaskIdsInSprint,
  listTaskOrderInState,
  listTasks,
  patchTask,
  transitionTask,
  unblockTask,
} from "@/lib/api/work/endpoints";
import { server } from "@/mocks/server";
import {
  buildDefaultStates,
  buildEpic,
  buildLabel,
  buildSprint,
  buildTask,
  workHandlers,
  type WorkCall,
  type WorkFixture,
} from "@/test/workHandlers";

const client = createApiClient({ baseUrl: "http://localhost", getAccessToken: () => "token", onUnauthorized: () => undefined });

function use(fixture: Partial<WorkFixture>) {
  server.use(...workHandlers({ projects: [], ...fixture }));
}

describe("metadata lists", () => {
  it("merges every page of states, epics, labels and sprints", async () => {
    use({
      pageSize: 2,
      states: buildDefaultStates(),
      epics: [buildEpic({ id: "e1" }), buildEpic({ id: "e2" }), buildEpic({ id: "e3" })],
      labels: [buildLabel({ id: "l1" }), buildLabel({ id: "l2" }), buildLabel({ id: "l3" })],
      sprints: [buildSprint({ id: "s1" }), buildSprint({ id: "s2" }), buildSprint({ id: "s3" })],
    });
    expect(await listStates(client, "project-1")).toHaveLength(5);
    expect((await listEpics(client, "project-1")).map((epic) => epic.id)).toEqual(["e1", "e2", "e3"]);
    expect(await listLabels(client, "project-1")).toHaveLength(3);
    expect(await listSprints(client, "project-1")).toHaveLength(3);
  });
});

describe("listTasks", () => {
  it("expands state, epic, labels and assignees and pages through every task", async () => {
    use({
      pageSize: 1,
      states: buildDefaultStates(),
      epics: [buildEpic({ id: "e1" })],
      labels: [buildLabel({ id: "l1" })],
      userNames: { "user-1": "Nguyễn Văn A" },
      tasks: [
        buildTask({ id: "a", epic_id: "e1", label_ids: ["l1"], assignee_ids: ["user-1"] }),
        buildTask({ id: "b" }),
      ],
    });
    const tasks = await listTasks(client, "project-1");
    expect(tasks.map((task) => task.id)).toEqual(["a", "b"]);
    expect(tasks[0]).toMatchObject({
      state: { id: "state-todo" },
      epic: { id: "e1" },
      labels: [{ id: "l1" }],
      assignees: [{ user_id: "user-1", display_name: "Nguyễn Văn A" }],
    });
  });

  it("asks only for the tasks of one sprint, or for tasks outside every sprint", async () => {
    use({
      tasks: [buildTask({ id: "a" }), buildTask({ id: "b" }), buildTask({ id: "c" })],
      sprintTasks: { "sprint-1": ["a", "b"] },
    });
    expect((await listTasks(client, "project-1", { sprintId: "sprint-1" })).map((task) => task.id)).toEqual(["a", "b"]);
    expect((await listTasks(client, "project-1", { sprintId: "none" })).map((task) => task.id)).toEqual(["c"]);
  });

  it("surfaces a server error as ApiError", async () => {
    use({ tasksError: { status: 403, code: "FORBIDDEN", message: "Không có quyền." } });
    await expect(listTasks(client, "project-1")).rejects.toBeInstanceOf(ApiError);
  });
});

describe("listTaskIdsInSprint", () => {
  it("requests only ids and returns the members of that sprint", async () => {
    use({
      pageSize: 1,
      tasks: [buildTask({ id: "a" }), buildTask({ id: "b" }), buildTask({ id: "c" })],
      sprintTasks: { "sprint-1": ["a", "c"] },
    });
    expect(await listTaskIdsInSprint(client, "project-1", "sprint-1")).toEqual(["a", "c"]);
  });
});

describe("getTask", () => {
  it("expands subtasks by default", async () => {
    use({
      states: buildDefaultStates(),
      tasks: [buildTask({ id: "a" }), buildTask({ id: "sub", parent_id: "a", type: "SUBTASK" })],
    });
    const task = await getTask(client, "a");
    expect(task.subtasks?.map((subtask) => subtask.id)).toEqual(["sub"]);
  });

  it("rejects with 404 for an unknown task", async () => {
    use({ tasks: [] });
    await expect(getTask(client, "nope")).rejects.toMatchObject({ status: 404 });
  });
});

describe("task writes", () => {
  const states = buildDefaultStates();
  const KEY = "key-1";

  function setup(tasks = [buildTask({ id: "a", version: 3 })]) {
    const calls: WorkCall[] = [];
    use({ states, tasks, calls });
    return { calls, tasks };
  }

  it("createTask sends the idempotency key and only the fields that were set", async () => {
    const { calls } = setup();
    const created = await createTask(client, "project-1", { title: "Mới", priority: "HIGH", storyPoints: 3, idempotencyKey: KEY });
    expect(created.title).toBe("Mới");
    expect(calls[0]).toMatchObject({ method: "POST", idempotencyKey: KEY, body: { title: "Mới", priority: "HIGH", story_points: 3 } });
    expect(Object.keys(calls[0].body ?? {})).not.toContain("state_id");
  });

  it("patchTask sends expected_version and no Idempotency-Key, and can clear a nullable field", async () => {
    const { calls } = setup();
    await patchTask(client, "a", { expectedVersion: 3, title: "Đổi", dueDate: null });
    expect(calls[0]).toMatchObject({ method: "PATCH", idempotencyKey: null, body: { expected_version: 3, title: "Đổi", due_date: null } });
    expect(Object.keys(calls[0].body ?? {})).not.toContain("priority");
  });

  it("patchTask surfaces VERSION_CONFLICT on a stale version", async () => {
    setup();
    const error = await patchTask(client, "a", { expectedVersion: 1, title: "x" }).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).code).toBe("VERSION_CONFLICT");
  });

  it("transitionTask always sends both neighbours, null when absent", async () => {
    const { calls } = setup();
    const moved = await transitionTask(client, "a", { expectedVersion: 3, targetStateId: "state-doing", previousTaskId: null, nextTaskId: null });
    expect(moved.state_id).toBe("state-doing");
    expect(calls[0].body).toEqual({ expected_version: 3, target_state_id: "state-doing", previous_task_id: null, next_task_id: null });
    expect(calls[0].idempotencyKey).toBeNull();
  });

  it("blockTask and unblockTask use PATCH without a key", async () => {
    const { calls } = setup();
    const blocked = await blockTask(client, "a", { expectedVersion: 3, blockedReason: "Chờ API" });
    expect(blocked.is_blocked).toBe(true);
    const unblocked = await unblockTask(client, "a", { expectedVersion: blocked.version });
    expect(unblocked.is_blocked).toBe(false);
    expect(calls.map((call) => `${call.method} ${call.path}`)).toEqual(["PATCH /tasks/a/block/", "PATCH /tasks/a/unblock/"]);
    expect(calls.every((call) => call.idempotencyKey === null)).toBe(true);
  });

  it("createSubtask posts under the parent with a key", async () => {
    const { calls } = setup();
    const sub = await createSubtask(client, "a", { title: "Con", idempotencyKey: KEY });
    expect(sub.parent_id).toBe("a");
    expect(calls[0]).toMatchObject({ path: "/tasks/a/subtasks/", idempotencyKey: KEY, body: { title: "Con" } });
  });

  it("listTaskOrderInState returns every task of the state sorted by sort_order", async () => {
    setup([
      buildTask({ id: "b", sort_order: 20000 }),
      buildTask({ id: "a", sort_order: 10000 }),
      buildTask({ id: "x", state_id: "state-doing", sort_order: 5 }),
      buildTask({ id: "gone", sort_order: 1, archived_at: "2026-09-02T00:00:00Z" }),
    ]);
    expect(await listTaskOrderInState(client, "project-1", "state-todo")).toEqual(["a", "b"]);
  });
});
