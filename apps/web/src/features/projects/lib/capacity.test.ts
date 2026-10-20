import { describe, expect, it } from "vitest";

import { CAPACITY_MAX, parseCapacity } from "@/features/projects/lib/capacity";

describe("parseCapacity", () => {
  it("accepts whole numbers from 0 to the backend limit, ignoring surrounding spaces", () => {
    expect(parseCapacity("0")).toBe(0);
    expect(parseCapacity(" 20 ")).toBe(20);
    expect(parseCapacity(String(CAPACITY_MAX))).toBe(CAPACITY_MAX);
  });

  it("rejects blank, negative, fractional, non-numeric and over-limit input", () => {
    for (const bad of ["", "  ", "-1", "2.5", "abc", "1e3", String(CAPACITY_MAX + 1)]) {
      expect(parseCapacity(bad)).toBeNull();
    }
  });
});
