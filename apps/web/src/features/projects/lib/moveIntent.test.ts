import { describe, expect, it } from "vitest";

import { planMove, planReorderToEdge } from "@/features/projects/lib/moveIntent";
import { compareByRank, rankBetween } from "@/features/projects/lib/rank";
import type { Issue } from "@/features/projects/types";

function issue(key: string, rank: number, patch: Partial<Issue> = {}): Issue {
  return {
    id: key,
    key,
    type: "task",
    title: key,
    status: "todo",
    statusId: "state-todo",
    stateGroup: "UNSTARTED",
    priority: "medium",
    storyPoints: 1,
    epicId: null,
    sprintId: "sprint-2",
    assignee: null,
    hasPullRequest: false,
    isMine: false,
    updatedAt: "2026-01-01T00:00:00.000Z",
    rank,
    version: 1,
    blocked: false,
    blockedReason: null,
    ...patch,
  };
}

const A = issue("A", 1000);
const B = issue("B", 2000);
const C = issue("C", 3000);
const NO_ACTIVE = new Set<string>();
const ACTIVE = new Set(["sprint-2"]);

describe("rankBetween", () => {
  it("returns midpoint between two neighbours", () => {
    const middle = rankBetween(1000, 3000);
    expect(middle).toBe(2000);
    expect(middle! > 1000 && middle! < 3000).toBe(true);
  });

  it("handles null before → after - 1", () => {
    expect(rankBetween(null, 1000)).toBe(999);
  });

  it("handles null after → before + 1", () => {
    expect(rankBetween(3000, null)).toBe(3001);
  });

  it("handles both null → 1", () => {
    expect(rankBetween(null, null)).toBe(1);
  });

  it("refuses neighbours that are not in order", () => {
    expect(rankBetween(2000, 1000)).toBeNull();
    expect(rankBetween(1000, 1000)).toBeNull();
  });

  it("returns null when float is exhausted", () => {
    // Two adjacent floats: midpoint cannot be strictly between them.
    const a = 0;
    const b = Number.MIN_VALUE;
    // The midpoint b/2 === 0 === a, so it should return null.
    expect(rankBetween(a, b)).toBeNull();
  });
});

describe("compareByRank", () => {
  it("orders by rank and breaks ties by key", () => {
    expect([C, A, B].sort(compareByRank).map((i) => i.key)).toEqual(["A", "B", "C"]);
    const tie = [issue("Z", 1000), issue("Y", 1000)].sort(compareByRank);
    expect(tie.map((i) => i.key)).toEqual(["Y", "Z"]);
  });
});

describe("planMove: leader", () => {
  const base = { role: "leader" as const, activeSprintIds: NO_ACTIVE };

  it("changes status when dropped on an empty column", () => {
    const intent = planMove({ ...base, issue: A, toStatus: "done", destination: [], target: null });
    expect(intent).toMatchObject({ status: "done", needsReason: false });
    // No neighbours in the empty column, so the card keeps the rank it has.
    expect(intent?.rank).toBeUndefined();
  });

  it("returns null when dropped back in place", () => {
    expect(
      planMove({ ...base, issue: B, toStatus: "todo", destination: [A, B, C], target: { key: "B", edge: "top" } }),
    ).toBeNull();
    expect(
      planMove({ ...base, issue: B, toStatus: "todo", destination: [A, B, C], target: { key: "A", edge: "bottom" } }),
    ).toBeNull();
    // Dropped on the empty part of its own column while already last.
    expect(planMove({ ...base, issue: C, toStatus: "todo", destination: [A, B, C], target: null })).toBeNull();
  });

  it("keeps the rank when the position is not part of the move (menu status change)", () => {
    const intent = planMove({ ...base, issue: A, toStatus: "done", destination: [] });
    expect(intent).toEqual({ status: "done", needsReason: false });
    expect(planMove({ ...base, issue: A, toStatus: "todo", destination: [] })).toBeNull();
  });

  it("sets statusId when toStateId is provided", () => {
    const intent = planMove({
      ...base,
      issue: A,
      toStatus: "in-progress",
      toStateId: "state-in-progress",
      destination: [],
    });
    expect(intent?.statusId).toBe("state-in-progress");
  });

  it("omits statusId when toStateId is absent", () => {
    const intent = planMove({ ...base, issue: A, toStatus: "done", destination: [] });
    expect(intent?.statusId).toBeUndefined();
  });

  it("reorders inside a column with a rank between the new neighbours", () => {
    const intent = planMove({
      ...base,
      issue: C,
      toStatus: "todo",
      destination: [A, B, C],
      target: { key: "B", edge: "top" },
    });
    expect(intent?.status).toBeUndefined();
    // midpoint of 1000 and 2000
    expect(intent!.rank).toBe(1500);
  });

  it("puts a card above the first one and below the last one", () => {
    const top = planMove({ ...base, issue: C, toStatus: "todo", destination: [A, B, C], target: { key: "A", edge: "top" } });
    expect(top!.rank! < 1000).toBe(true);
    const bottom = planMove({ ...base, issue: A, toStatus: "todo", destination: [A, B, C], target: { key: "C", edge: "bottom" } });
    expect(bottom!.rank! > 3000).toBe(true);
  });

  it("moving to the Product Backlog from an active sprint needs a reason", () => {
    const intent = planMove({
      ...base,
      activeSprintIds: ACTIVE,
      issue: A,
      toSprintId: null,
      destination: [],
    });
    expect(intent).toMatchObject({ sprintId: null, needsReason: true });
  });

  it("moving between non-active sprints needs no reason", () => {
    const upcoming = issue("U", 5000, { sprintId: "sprint-3" });
    const intent = planMove({
      ...base,
      activeSprintIds: ACTIVE,
      issue: upcoming,
      toSprintId: null,
      destination: [],
    });
    expect(intent).toMatchObject({ sprintId: null, needsReason: false });
  });

  it("moving into an active sprint needs a reason", () => {
    const loose = issue("L", 9000, { sprintId: null });
    const intent = planMove({
      ...base,
      activeSprintIds: ACTIVE,
      issue: loose,
      toSprintId: "sprint-2",
      destination: [A],
    });
    expect(intent).toMatchObject({ sprintId: "sprint-2", needsReason: true });
  });
});

describe("planMove: member and instructor", () => {
  it("lets a member change the status of their own task, and never the rank", () => {
    const mine = issue("M", 3000, { isMine: true });
    const intent = planMove({
      issue: mine,
      role: "member",
      toStatus: "review",
      destination: [A, B],
      target: { key: "A", edge: "top" },
      activeSprintIds: ACTIVE,
    });
    expect(intent).toEqual({ status: "review", needsReason: false });
  });

  it("does nothing for a member on a task that is not theirs, or on the same status", () => {
    const base = { role: "member" as const, destination: [], activeSprintIds: NO_ACTIVE };
    expect(planMove({ ...base, issue: A, toStatus: "review" })).toBeNull();
    expect(planMove({ ...base, issue: issue("M", 3000, { isMine: true }), toStatus: "todo" })).toBeNull();
  });

  it("does nothing for an instructor", () => {
    expect(
      planMove({ issue: A, role: null, toStatus: "done", destination: [], activeSprintIds: NO_ACTIVE }),
    ).toBeNull();
  });
});

describe("planReorderToEdge", () => {
  const base = { role: "leader" as const, destination: [A, B, C], activeSprintIds: NO_ACTIVE };

  it("sends a card to the top or the bottom of its list", () => {
    expect(planReorderToEdge({ ...base, issue: C, edge: "first" })!.rank! < 1000).toBe(true);
    expect(planReorderToEdge({ ...base, issue: A, edge: "last" })!.rank! > 3000).toBe(true);
  });

  it("is a no-op when the card is already there", () => {
    expect(planReorderToEdge({ ...base, issue: A, edge: "first" })).toBeNull();
    expect(planReorderToEdge({ ...base, issue: C, edge: "last" })).toBeNull();
  });
});

describe("planMove: states that share a group", () => {
  it("treats Backlog -> To Do as a move when the target state id differs", () => {
    const intent = planMove({
      issue: A, role: "leader", toStatus: "todo", toStateId: "state-other-todo", destination: [], activeSprintIds: NO_ACTIVE,
    });
    expect(intent).toEqual({ status: "todo", statusId: "state-other-todo", needsReason: false });
  });

  it("is a no-op when the target state id is the issue's own state", () => {
    expect(
      planMove({ issue: A, role: "leader", toStatus: "todo", toStateId: "state-todo", destination: [], activeSprintIds: NO_ACTIVE }),
    ).toBeNull();
  });

  it("keeps the state id for a member moving their own task", () => {
    const mine = issue("M", 3000, { isMine: true });
    const intent = planMove({
      issue: mine, role: "member", toStatus: "todo", toStateId: "state-other-todo", destination: [], activeSprintIds: NO_ACTIVE,
    });
    expect(intent).toEqual({ status: "todo", statusId: "state-other-todo", needsReason: false });
  });
});
