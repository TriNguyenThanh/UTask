import { describe, expect, it } from "vitest";

import { LEADER_ID, MEMBER_ID, TEACHER_ID } from "@/mocks/data/database";
import { createMockHandlers } from "@/mocks/handlers";
import { server } from "@/mocks/server";
import { createMemoryRepository, type MockRepository } from "@/mocks/data/storage";

const BASE = "http://localhost/api/work/api/v1";
const PROJECT = "/projects/project-nexus";

function useRepo(): MockRepository {
  const repository = createMemoryRepository("default");
  server.use(...createMockHandlers("default", repository));
  return repository;
}

async function call(path: string, userId: string | null, body?: unknown) {
  const response = await fetch(`${BASE}${path}`, {
    method: body === undefined ? "GET" : "POST",
    headers: {
      ...(userId ? { Authorization: `Bearer mock-access:${userId}:test` } : {}),
      ...(body === undefined ? {} : { "Content-Type": "application/json" }),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const text = await response.text();
  return { status: response.status, json: text ? JSON.parse(text) : null };
}

async function workspaceIssue(userId: string, key: string) {
  const { json } = await call(PROJECT, userId);
  return json.issues.find((issue: { key: string }) => issue.key === key);
}

describe("Issue move endpoint", () => {
  it("rejects a request without a session", async () => {
    useRepo();
    expect((await call(`${PROJECT}/issues/NEXUS-101/move`, null, { version: 1 })).status).toBe(401);
  });

  it("lets the leader change status and later reads see it, with a history row", async () => {
    useRepo();
    const before = await workspaceIssue(LEADER_ID, "NEXUS-101");
    const moved = await call(`${PROJECT}/issues/NEXUS-101/move`, LEADER_ID, {
      status: "in-progress",
      version: before.version,
    });
    expect(moved.status).toBe(200);
    expect(moved.json).toMatchObject({ status: "in-progress", version: before.version + 1 });

    expect((await workspaceIssue(LEADER_ID, "NEXUS-101")).status).toBe("in-progress");
    const detail = await call(`${PROJECT}/issues/NEXUS-101`, LEADER_ID);
    expect(detail.json.history.at(-1).summary).toBe("chuyển trạng thái sang Đang làm");
  });

  it("orders issues by rank after a leader reorders them", async () => {
    useRepo();
    const first = (await call(PROJECT, LEADER_ID)).json.issues[0];
    const last = (await call(PROJECT, LEADER_ID)).json.issues.at(-1);
    const moved = await call(`${PROJECT}/issues/${last.key}/move`, LEADER_ID, {
      rank: "!",
      version: last.version,
    });
    expect(moved.status).toBe(200);
    const issues = (await call(PROJECT, LEADER_ID)).json.issues;
    expect(issues[0].key).toBe(last.key);
    expect(issues[1].key).toBe(first.key);
  });

  it("lets a member change the status of their own task only", async () => {
    useRepo();
    const own = await workspaceIssue(MEMBER_ID, "NEXUS-101");
    expect(own.isMine).toBe(true);
    expect(
      (await call(`${PROJECT}/issues/NEXUS-101/move`, MEMBER_ID, { status: "review", version: own.version }))
        .status,
    ).toBe(200);

    const other = await workspaceIssue(MEMBER_ID, "NEXUS-104");
    expect(
      (await call(`${PROJECT}/issues/NEXUS-104/move`, MEMBER_ID, { status: "review", version: other.version }))
        .status,
    ).toBe(403);
  });

  it("refuses a member who tries to reorder or change the sprint of their own task", async () => {
    useRepo();
    const own = await workspaceIssue(MEMBER_ID, "NEXUS-101");
    for (const extra of [{ rank: "!" }, { sprintId: "sprint-3" }]) {
      const response = await call(`${PROJECT}/issues/NEXUS-101/move`, MEMBER_ID, {
        version: own.version,
        ...extra,
      });
      expect(response.status).toBe(403);
    }
  });

  it("refuses an instructor of the class even though they can open the project", async () => {
    useRepo();
    expect((await call(PROJECT, TEACHER_ID)).status).toBe(200);
    expect(
      (await call(`${PROJECT}/issues/NEXUS-101/move`, TEACHER_ID, { status: "done", version: 1 })).status,
    ).toBe(403);
  });

  it("answers 404 to someone who cannot open the project", async () => {
    useRepo();
    // The DELI-only leader of nothing: use a project this account has no seat in.
    expect(
      (await call("/projects/project-legacy/issues/LEG-1/move", MEMBER_ID, { version: 1 })).status,
    ).toBe(404);
  });

  it("answers 409 with the current issue when the version is stale", async () => {
    useRepo();
    const issue = await workspaceIssue(LEADER_ID, "NEXUS-101");
    await call(`${PROJECT}/issues/NEXUS-101/move`, LEADER_ID, { status: "review", version: issue.version });
    const stale = await call(`${PROJECT}/issues/NEXUS-101/move`, LEADER_ID, {
      status: "done",
      version: issue.version,
    });
    expect(stale.status).toBe(409);
    expect(stale.json.issue).toMatchObject({ key: "NEXUS-101", status: "review" });
  });

  it("needs a reason to change the scope of the active sprint, but not an upcoming one", async () => {
    useRepo();
    const issue = await workspaceIssue(LEADER_ID, "NEXUS-110"); // backlog issue
    const missing = await call(`${PROJECT}/issues/NEXUS-110/move`, LEADER_ID, {
      sprintId: "sprint-2",
      version: issue.version,
    });
    expect(missing.status).toBe(422);
    expect(missing.json.errors.reason).toBeDefined();

    const upcoming = await call(`${PROJECT}/issues/NEXUS-110/move`, LEADER_ID, {
      sprintId: "sprint-3",
      version: issue.version,
    });
    expect(upcoming.status).toBe(200);

    const active = await call(`${PROJECT}/issues/NEXUS-110/move`, LEADER_ID, {
      sprintId: "sprint-2",
      reason: "Khách hàng đổi ưu tiên",
      version: upcoming.json.version,
    });
    expect(active.status).toBe(200);
    const detail = await call(`${PROJECT}/issues/NEXUS-110`, LEADER_ID);
    expect(detail.json.history.at(-1).summary).toContain("lý do: Khách hàng đổi ưu tiên");
  });

  it("moves sprint point totals with the issue", async () => {
    useRepo();
    const sprint2 = (await call(PROJECT, LEADER_ID)).json.sprints.find((s: { id: string }) => s.id === "sprint-2");
    const issue = await workspaceIssue(LEADER_ID, "NEXUS-110");
    await call(`${PROJECT}/issues/NEXUS-110/move`, LEADER_ID, {
      sprintId: "sprint-2",
      reason: "Bổ sung phạm vi",
      version: issue.version,
    });
    const after = (await call(PROJECT, LEADER_ID)).json.sprints.find((s: { id: string }) => s.id === "sprint-2");
    expect(after.totalPoints).toBe(sprint2.totalPoints + issue.storyPoints);
  });

  it("rejects an unknown status or sprint", async () => {
    useRepo();
    const issue = await workspaceIssue(LEADER_ID, "NEXUS-101");
    expect(
      (await call(`${PROJECT}/issues/NEXUS-101/move`, LEADER_ID, { status: "nope", version: issue.version }))
        .status,
    ).toBe(422);
    expect(
      (await call(`${PROJECT}/issues/NEXUS-101/move`, LEADER_ID, { sprintId: "sprint-1", version: issue.version }))
        .status,
    ).toBe(422);
  });
});

describe("Issue blocked endpoint", () => {
  it("needs a reason to block, stores it, and clears it when unblocked", async () => {
    useRepo();
    const issue = await workspaceIssue(LEADER_ID, "NEXUS-101");
    expect(
      (await call(`${PROJECT}/issues/NEXUS-101/blocked`, LEADER_ID, { blocked: true, version: issue.version }))
        .status,
    ).toBe(422);

    const blocked = await call(`${PROJECT}/issues/NEXUS-101/blocked`, LEADER_ID, {
      blocked: true,
      reason: "Chờ API",
      version: issue.version,
    });
    expect(blocked.json).toMatchObject({ blocked: true, blockedReason: "Chờ API" });

    const unblocked = await call(`${PROJECT}/issues/NEXUS-101/blocked`, LEADER_ID, {
      blocked: false,
      version: blocked.json.version,
    });
    expect(unblocked.json).toMatchObject({ blocked: false, blockedReason: null });
  });

  it("lets a member block their own task but not someone else's", async () => {
    useRepo();
    const own = await workspaceIssue(MEMBER_ID, "NEXUS-101");
    expect(
      (await call(`${PROJECT}/issues/NEXUS-101/blocked`, MEMBER_ID, {
        blocked: true,
        reason: "Chờ thiết kế",
        version: own.version,
      })).status,
    ).toBe(200);
    const other = await workspaceIssue(MEMBER_ID, "NEXUS-104");
    expect(
      (await call(`${PROJECT}/issues/NEXUS-104/blocked`, MEMBER_ID, {
        blocked: true,
        reason: "x",
        version: other.version,
      })).status,
    ).toBe(403);
  });

  it("refuses an instructor and a stale version", async () => {
    useRepo();
    expect(
      (await call(`${PROJECT}/issues/NEXUS-101/blocked`, TEACHER_ID, { blocked: false, version: 1 })).status,
    ).toBe(403);
    expect(
      (await call(`${PROJECT}/issues/NEXUS-101/blocked`, LEADER_ID, {
        blocked: true,
        reason: "x",
        version: 99,
      })).status,
    ).toBe(409);
  });
});
