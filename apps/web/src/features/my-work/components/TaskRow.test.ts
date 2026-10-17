import { describe, expect, it } from "vitest";

import { formatDue } from "@/features/my-work/components/TaskRow";

/**
 * Regression for the bug fixed 2026-10-17: the day-count diffed full
 * timestamps (due at a fixed hour vs. "now" at whatever hour the clock
 * showed), so a task due "yesterday" rounded to 0 days overdue whenever now
 * and the due hour were under 12h apart on the clock — the overdue badge
 * then never rendered. `MyWork.test.tsx`'s "surfaces overdue tasks" test hit
 * this for real between roughly 00:00 and 05:00 local time. See
 * docs/web/teacher-flow.md §16.10 for the original report.
 *
 * `now` is swept across every hour of the day to prove the result no longer
 * depends on wall time.
 */
function at(year: number, month: number, day: number, hour: number): Date {
  return new Date(year, month, day, hour, 0, 0, 0);
}

const ALL_HOURS = Array.from({ length: 24 }, (_, hour) => hour);

describe("formatDue: days overdue is a calendar-day count, not a clock-sensitive one", () => {
  it.each(ALL_HOURS)("reports 1 day overdue at every hour (hour=%i)", (hour) => {
    const due = at(2026, 9, 16, 17); // yesterday, 17:00 — the fixture's own due hour
    const now = at(2026, 9, 17, hour);
    expect(formatDue(due.toISOString(), now)).toBe("Quá hạn 1 ngày");
  });

  it.each(ALL_HOURS)("reports 2 days overdue at every hour (hour=%i)", (hour) => {
    const due = at(2026, 9, 15, 9);
    const now = at(2026, 9, 17, hour);
    expect(formatDue(due.toISOString(), now)).toBe("Quá hạn 2 ngày");
  });

  it.each(ALL_HOURS)("never reports overdue for a task due later today (hour=%i)", (hour) => {
    const due = at(2026, 9, 17, 23);
    const now = at(2026, 9, 17, hour);
    expect(formatDue(due.toISOString(), now)).not.toMatch(/Quá hạn/);
  });
});

describe("formatDue: other branches untouched by the fix", () => {
  it("shows today's time for a same-day due date", () => {
    expect(formatDue(at(2026, 9, 17, 18).toISOString(), at(2026, 9, 17, 8))).toBe("Hôm nay, 18:00");
  });

  it("shows 'Mai' for tomorrow", () => {
    expect(formatDue(at(2026, 9, 18, 9).toISOString(), at(2026, 9, 17, 8))).toBe("Mai, 09:00");
  });

  it("shows a formatted date further in the future", () => {
    expect(formatDue(at(2026, 9, 20, 9).toISOString(), at(2026, 9, 17, 8))).toBe("20/10/2026");
  });
});
