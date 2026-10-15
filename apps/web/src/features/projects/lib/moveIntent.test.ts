import { describe, expect, it } from "vitest";

import { planMove, planReorderToEdge } from "@/features/projects/lib/moveIntent";
import { compareByRank, rankBetween } from "@/features/projects/lib/rank";
import type { Issue } from "@/features/projects/types";

function issue(key: string, rank: string, patch: Partial<Issue> = {}): Issue {
  return {
    id: key,
    key,
    type: "task",
    title: key,
    status: "todo",
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

const A = issue("A", "a0");
const B = issue("B", "a1");
const C = issue("C", "a2");
const NO_ACTIVE = new Set<string>();
const ACTIVE = new Set(["sprint-2"]);

describe("rankBetween", () => {
  it("sorts strictly between its neighbours, and at either end", () => {
    const middle = rankBetween("a0", "a1");
    expect(middle).not.toBeNull();
    expect(middle! > "a0" && middle! < "a1").toBe(true);
    expect(rankBetween(null, "a0")! < "a0").toBe(true);
    expect(rankBetween("a2", null)! > "a2").toBe(true);
    expect(rankBetween(null, null)).toBeTypeOf("string");
  });

  it("refuses neighbours that are not in order", () => {
    expect(rankBetween("a1", "a0")).toBeNull();
    expect(rankBetween("a1", "a1")).toBeNull();
  });
});

describe("compareByRank", () => {
  it("orders by rank and breaks ties by key", () => {
    expect([C, A, B].sort(compareByRank).map((i) => i.key)).toEqual(["A", "B", "C"]);
    const tie = [issue("Z", "a0"), issue("Y", "a0")].sort(compareByRank);
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

  it("reorders inside a column with a rank between the new neighbours", () => {
    const intent = planMove({
      ...base,
      issue: C,
      toStatus: "todo",
      destination: [A, B, C],
      target: { key: "B", edge: "top" },
    });
    expect(intent?.status).toBeUndefined();
    expect(intent!.rank! > "a0" && intent!.rank! < "a1").toBe(true);
  });

  it("puts a card above the first one and below the last one", () => {
    const top = planMove({ ...base, issue: C, toStatus: "todo", destination: [A, B, C], target: { key: "A", edge: "top" } });
    expect(top!.rank! < "a0").toBe(true);
    const bottom = planMove({ ...base, issue: A, toStatus: "todo", destination: [A, B, C], target: { key: "C", edge: "bottom" } });
    expect(bottom!.rank! > "a2").toBe(true);
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
    const upcoming = issue("U", "a5", { sprintId: "sprint-3" });
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
    const loose = issue("L", "a9", { sprintId: null });
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
    const mine = issue("M", "a3", { isMine: true });
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
    expect(planMove({ ...base, issue: issue("M", "a3", { isMine: true }), toStatus: "todo" })).toBeNull();
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
    expect(planReorderToEdge({ ...base, issue: C, edge: "first" })!.rank! < "a0").toBe(true);
    expect(planReorderToEdge({ ...base, issue: A, edge: "last" })!.rank! > "a2").toBe(true);
  });

  it("is a no-op when the card is already there", () => {
    expect(planReorderToEdge({ ...base, issue: A, edge: "first" })).toBeNull();
    expect(planReorderToEdge({ ...base, issue: C, edge: "last" })).toBeNull();
  });
});
