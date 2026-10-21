import { describe, expect, it } from "vitest";

import { planNeighbours } from "@/features/projects/lib/transitionNeighbours";

const COLUMN = ["a", "hidden", "b", "c"];
const SIBLINGS = [
  { id: "a", rank: 10 },
  { id: "b", rank: 30 },
  { id: "c", rank: 40 },
];

describe("planNeighbours", () => {
  it("sends an empty column as both null", () => {
    expect(planNeighbours([], [], undefined)).toEqual({ previousTaskId: null, nextTaskId: null });
    expect(planNeighbours([], [], 5)).toEqual({ previousTaskId: null, nextTaskId: null });
  });

  it("appends to the column when no rank is given (move from a menu)", () => {
    expect(planNeighbours(COLUMN, SIBLINGS, undefined)).toEqual({ previousTaskId: "c", nextTaskId: null });
  });

  it("places after the closest lower card and takes the true next from the full column", () => {
    // 'hidden' (a subtask the board never shows) sits right after 'a'.
    expect(planNeighbours(COLUMN, SIBLINGS, 20)).toEqual({ previousTaskId: "a", nextTaskId: "hidden" });
  });

  it("places before the first card when nothing is lower", () => {
    expect(planNeighbours(COLUMN, SIBLINGS, 1)).toEqual({ previousTaskId: null, nextTaskId: "a" });
  });

  it("falls back to the end when the reference card is no longer in the column", () => {
    expect(planNeighbours(["b", "c"], [{ id: "a", rank: 10 }], 20)).toEqual({ previousTaskId: "c", nextTaskId: null });
  });

  it("places after the last card when the rank is higher than every card", () => {
    expect(planNeighbours(COLUMN, SIBLINGS, 99)).toEqual({ previousTaskId: "c", nextTaskId: null });
  });
});
