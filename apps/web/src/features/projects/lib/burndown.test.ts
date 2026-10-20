import { describe, expect, it } from "vitest";

import { burndownLines, toPolyline } from "@/features/projects/lib/burndown";

const day = (remaining_estimate_points: number) => ({ remaining_estimate_points });

describe("burndownLines", () => {
  it("returns null when there are no days", () => {
    expect(burndownLines([], 100, 50)).toBeNull();
  });

  it("puts the highest remaining value at the top and 0 at the bottom, with a straight ideal line to 0", () => {
    const lines = burndownLines([day(10), day(6), day(0)], 100, 50)!;
    expect(lines.max).toBe(10);
    expect(lines.remaining).toEqual([
      { x: 0, y: 0 },
      { x: 50, y: 20 },
      { x: 100, y: 50 },
    ]);
    expect(lines.ideal).toEqual([
      { x: 0, y: 0 },
      { x: 50, y: 25 },
      { x: 100, y: 50 },
    ]);
  });

  it("draws a single day in the middle and never divides by zero when everything is 0", () => {
    const lines = burndownLines([day(0)], 100, 50)!;
    expect(lines.max).toBe(1);
    expect(lines.remaining).toEqual([{ x: 50, y: 50 }]);
  });
});

describe("toPolyline", () => {
  it("joins rounded points for an SVG polyline", () => {
    expect(toPolyline([{ x: 0, y: 1.234 }, { x: 10.55, y: 2 }])).toBe("0,1.2 10.6,2");
  });
});
