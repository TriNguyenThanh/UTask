import { describe, expect, it } from "vitest";

import { rankBetween, compareByRank } from "@/features/projects/lib/rank";

describe("rankBetween", () => {
  it("both null → 1", () => {
    expect(rankBetween(null, null)).toBe(1);
  });

  it("null before → after - 1", () => {
    expect(rankBetween(null, 5000)).toBe(4999);
  });

  it("null after → before + 1", () => {
    expect(rankBetween(1000, null)).toBe(1001);
  });

  it("returns midpoint between two numbers", () => {
    expect(rankBetween(1000, 3000)).toBe(2000);
    expect(rankBetween(1000, 2000)).toBe(1500);
  });

  it("returns null when before >= after", () => {
    expect(rankBetween(2000, 1000)).toBeNull();
    expect(rankBetween(1000, 1000)).toBeNull();
  });

  it("returns null when float is exhausted (midpoint equals boundary)", () => {
    // Two adjacent floats: (a + b) / 2 === a, so result is not strictly between.
    const a = 0;
    const b = Number.MIN_VALUE;
    expect(rankBetween(a, b)).toBeNull();
  });

  it("result is strictly between its neighbours in normal cases", () => {
    const mid = rankBetween(1000, 2000)!;
    expect(mid > 1000 && mid < 2000).toBe(true);
  });
});

describe("compareByRank", () => {
  it("sorts ascending by rank number", () => {
    const items = [
      { rank: 3000, key: "C" },
      { rank: 1000, key: "A" },
      { rank: 2000, key: "B" },
    ];
    expect(items.sort(compareByRank).map((i) => i.key)).toEqual(["A", "B", "C"]);
  });

  it("breaks ties by key lexicographically", () => {
    const items = [
      { rank: 1000, key: "Z" },
      { rank: 1000, key: "A" },
    ];
    expect(items.sort(compareByRank).map((i) => i.key)).toEqual(["A", "Z"]);
  });
});
