import { describe, expect, it } from "vitest";

import { createApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import {
  closeSprint,
  createSprint,
  getProjectDashboard,
  getSprint,
  getSprintBurndown,
  getSprintProgress,
  patchMemberCapacity,
  patchSprint,
  setSprintScope,
  startSprint,
} from "@/lib/api/work/endpoints";
import { server } from "@/mocks/server";
import {
  buildDashboard,
  buildDefaultStates,
  buildProgress,
  buildProject,
  buildProjectMember,
  buildSprint,
  buildTask,
  workHandlers,
  type WorkCall,
  type WorkFixture,
} from "@/test/workHandlers";

const client = createApiClient({ baseUrl: "http://localhost", getAccessToken: () => "token", onUnauthorized: () => undefined });

function setup(fixture: Partial<WorkFixture>) {
  const calls: WorkCall[] = [];
  const full = { projects: [buildProject()], states: buildDefaultStates(), calls, ...fixture };
  server.use(...workHandlers(full as WorkFixture));
  return { calls, full };
}

async function codeOf(promise: Promise<unknown>) {
  const error = await promise.then(() => null, (reason: unknown) => reason);
  expect(error).toBeInstanceOf(ApiError);
  return (error as ApiError).code;
}

describe("sprint create, patch and start", () => {
  it("creates a draft with only the given fields and no Idempotency-Key, then patches with expected_version", async () => {
    const { calls } = setup({ sprints: [] });
    const created = await createSprint(client, "project-1", { name: "Sprint A", startDate: "2026-09-01", endDate: "2026-09-14" });
    expect(created).toMatchObject({ name: "Sprint A", status: "DRAFT", version: 1 });
    expect(calls.at(-1)).toMatchObject({
      method: "POST",
      path: "/projects/project-1/sprints/",
      idempotencyKey: null,
      body: { name: "Sprint A", start_date: "2026-09-01", end_date: "2026-09-14" },
    });

    const patched = await patchSprint(client, created.id, { expectedVersion: 1, goal: "Mới", endDate: null });
    expect(patched).toMatchObject({ goal: "Mới", end_date: null, version: 2 });
    expect(calls.at(-1)?.body).toEqual({ expected_version: 1, goal: "Mới", end_date: null });
  });

  it("rejects a stale version with VERSION_CONFLICT and a closed sprint with INVALID_OPERATION", async () => {
    setup({ sprints: [buildSprint({ id: "s1", status: "DRAFT", version: 3 }), buildSprint({ id: "s2", status: "COMPLETED" })] });
    expect(await codeOf(patchSprint(client, "s1", { expectedVersion: 1, name: "x" }))).toBe("VERSION_CONFLICT");
    expect(await codeOf(patchSprint(client, "s2", { expectedVersion: 1, name: "x" }))).toBe("INVALID_OPERATION");
  });

  it("starts a dated draft with an Idempotency-Key, and refuses a second active sprint or a missing date", async () => {
    const { calls } = setup({
      sprints: [
        buildSprint({ id: "draft", status: "DRAFT" }),
        buildSprint({ id: "undated", status: "DRAFT", start_date: null }),
      ],
    });
    expect(await codeOf(startSprint(client, "project-1", "undated", { expectedVersion: 1, idempotencyKey: "k0" }))).toBe("INVALID_OPERATION");

    const started = await startSprint(client, "project-1", "draft", { expectedVersion: 1, idempotencyKey: "k1" });
    expect(started.status).toBe("ACTIVE");
    expect(calls.at(-1)).toMatchObject({ path: "/projects/project-1/sprints/draft/start/", idempotencyKey: "k1", body: { expected_version: 1 } });

    setup({ sprints: [buildSprint({ id: "running" }), buildSprint({ id: "next", status: "DRAFT" })] });
    expect(await codeOf(startSprint(client, "project-1", "next", { expectedVersion: 1, idempotencyKey: "k2" }))).toBe("ACTIVE_SPRINT_EXISTS");
  });

  it("reads one sprint", async () => {
    setup({ sprints: [buildSprint({ id: "s1", version: 7 })] });
    expect((await getSprint(client, "s1")).version).toBe(7);
  });
});

describe("sprint scope", () => {
  it("adds and removes tasks on a draft sprint without a reason and bumps the sprint version", async () => {
    const { calls, full } = setup({ sprints: [buildSprint({ id: "s1", status: "DRAFT" })], tasks: [buildTask({ id: "t1" })] });
    const added = await setSprintScope(client, "s1", { expectedVersion: 1, action: "ADD", taskIds: ["t1"], idempotencyKey: "k1" });
    expect(added).toEqual({ sprint_id: "s1", modified_task_ids: ["t1"], is_scope_creep: false, version: 2 });
    expect(calls.at(-1)).toMatchObject({ path: "/sprints/s1/tasks/", idempotencyKey: "k1", body: { expected_version: 1, action: "ADD", task_ids: ["t1"] } });
    expect(full.sprintTasks).toEqual({ s1: ["t1"] });

    const removed = await setSprintScope(client, "s1", { expectedVersion: 2, action: "REMOVE", taskIds: ["t1"], idempotencyKey: "k2" });
    expect(removed.modified_task_ids).toEqual(["t1"]);
    expect(full.sprintTasks).toEqual({ s1: [] });
  });

  it("needs a reason on an active sprint and flags the change as scope creep", async () => {
    const { calls } = setup({ sprints: [buildSprint({ id: "s1" })], tasks: [buildTask({ id: "t1" })] });
    expect(await codeOf(setSprintScope(client, "s1", { expectedVersion: 1, action: "ADD", taskIds: ["t1"], idempotencyKey: "k1" })))
      .toBe("SCOPE_CHANGE_REASON_REQUIRED");
    const result = await setSprintScope(client, "s1", {
      expectedVersion: 1,
      action: "ADD",
      taskIds: ["t1"],
      scopeChangeReason: "Khách yêu cầu",
      idempotencyKey: "k2",
    });
    expect(result.is_scope_creep).toBe(true);
    expect(calls.at(-1)?.body).toMatchObject({ scope_change_reason: "Khách yêu cầu" });
  });

  it("refuses to add a task that already sits in another sprint, and a closed sprint", async () => {
    setup({
      sprints: [buildSprint({ id: "s1", status: "DRAFT" }), buildSprint({ id: "s2", status: "DRAFT" }), buildSprint({ id: "done", status: "COMPLETED" })],
      tasks: [buildTask({ id: "t1" })],
      sprintTasks: { s2: ["t1"] },
    });
    expect(await codeOf(setSprintScope(client, "s1", { expectedVersion: 1, action: "ADD", taskIds: ["t1"], idempotencyKey: "k1" }))).toBe("INVALID_OPERATION");
    expect(await codeOf(setSprintScope(client, "done", { expectedVersion: 1, action: "ADD", taskIds: ["t1"], idempotencyKey: "k2" }))).toBe("INVALID_OPERATION");
  });
});

describe("closeSprint", () => {
  const states = buildDefaultStates();
  const doneState = states.find((state) => state.group === "COMPLETED")!;
  const todoState = states.find((state) => state.group === "UNSTARTED")!;

  it("moves unfinished tasks to the target draft sprint and keeps the finished ones", async () => {
    const { calls, full } = setup({
      sprints: [buildSprint({ id: "run" }), buildSprint({ id: "next", status: "DRAFT" })],
      tasks: [buildTask({ id: "done", state_id: doneState.id }), buildTask({ id: "open", state_id: todoState.id })],
      sprintTasks: { run: ["done", "open"] },
    });
    const result = await closeSprint(client, "run", { expectedVersion: 1, targetSprintId: "next", idempotencyKey: "k1" });
    expect(result).toMatchObject({ status: "COMPLETED", target_sprint_id: "next" });
    expect(calls.at(-1)).toMatchObject({ path: "/sprints/run/close/", idempotencyKey: "k1", body: { expected_version: 1, target_sprint_id: "next" } });
    expect(full.sprintTasks).toEqual({ run: ["done"], next: ["open"] });
  });

  it("sends null to return unfinished tasks to the backlog, and refuses a non-active sprint or a non-draft target", async () => {
    const { calls, full } = setup({
      sprints: [buildSprint({ id: "run" }), buildSprint({ id: "draft", status: "DRAFT" })],
      tasks: [buildTask({ id: "open", state_id: todoState.id })],
      sprintTasks: { run: ["open"] },
    });
    expect(await codeOf(closeSprint(client, "draft", { expectedVersion: 1, targetSprintId: null, idempotencyKey: "k0" }))).toBe("INVALID_OPERATION");
    expect(await codeOf(closeSprint(client, "run", { expectedVersion: 1, targetSprintId: "run", idempotencyKey: "k1" }))).toBe("INVALID_OPERATION");
    await closeSprint(client, "run", { expectedVersion: 1, targetSprintId: null, idempotencyKey: "k2" });
    expect(calls.at(-1)?.body).toEqual({ expected_version: 1, target_sprint_id: null });
    expect(full.sprintTasks).toEqual({ run: [] });
  });
});

describe("reports", () => {
  it("reads progress, burndown and the project dashboard", async () => {
    setup({
      progress: { s1: buildProgress({ completion_percent: 40 }, "s1") },
      burndown: {
        s1: {
          sprint_id: "s1",
          formula_version: "v1",
          captured_at: "2026-09-05T00:00:00Z",
          snapshot_version: null,
          days: [],
          window_truncated: true,
        },
      },
      dashboard: buildDashboard({ unassigned_estimate_points: 5 }),
    });
    expect((await getSprintProgress(client, "s1")).totals.completion_percent).toBe(40);
    expect((await getSprintBurndown(client, "s1")).window_truncated).toBe(true);
    expect((await getProjectDashboard(client, "project-1")).unassigned_estimate_points).toBe(5);
  });
});

describe("patchMemberCapacity", () => {
  it("sets weekly_capacity without Idempotency-Key and refuses a member who left", async () => {
    const { calls } = setup({
      members: {
        "project-1": [
          buildProjectMember({ user_id: "u1", weekly_capacity: 10 }),
          buildProjectMember({ id: "pm-2", user_id: "u2", status: "REMOVED" }),
        ],
      },
    });
    const member = await patchMemberCapacity(client, "project-1", "u1", 25);
    expect(member.weekly_capacity).toBe(25);
    expect(calls.at(-1)).toMatchObject({ method: "PATCH", path: "/projects/project-1/members/u1/capacity/", idempotencyKey: null, body: { weekly_capacity: 25 } });
    expect(await codeOf(patchMemberCapacity(client, "project-1", "u2", 5))).toBe("MEMBER_NOT_ACTIVE");
  });
});
