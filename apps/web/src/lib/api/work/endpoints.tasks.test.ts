import { describe, expect, it } from "vitest";

import { createApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import {
  getTask,
  listEpics,
  listLabels,
  listSprints,
  listStates,
  listTaskIdsInSprint,
  listTasks,
} from "@/lib/api/work/endpoints";
import { server } from "@/mocks/server";
import {
  buildDefaultStates,
  buildEpic,
  buildLabel,
  buildSprint,
  buildTask,
  workHandlers,
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
