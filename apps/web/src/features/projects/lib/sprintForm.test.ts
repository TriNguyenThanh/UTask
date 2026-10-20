import { describe, expect, it } from "vitest";

import {
  canStartSprint,
  EMPTY_SPRINT_FORM,
  toCreateSprintInput,
  toPatchSprintInput,
  validateSprintForm,
} from "@/features/projects/lib/sprintForm";

const BASE = { name: "Sprint 1", goal: "Mục tiêu", startDate: "2026-09-01", endDate: "2026-09-14" };

describe("validateSprintForm", () => {
  it("accepts a name with ordered dates, or with no dates at all", () => {
    expect(validateSprintForm(BASE)).toEqual({});
    expect(validateSprintForm({ ...EMPTY_SPRINT_FORM, name: "S" })).toEqual({});
    expect(validateSprintForm({ ...BASE, endDate: BASE.startDate })).toEqual({});
  });

  it("rejects a blank or over-long name and an end date before the start date", () => {
    expect(validateSprintForm({ ...BASE, name: "   " }).name).toBeDefined();
    expect(validateSprintForm({ ...BASE, name: "x".repeat(201) }).name).toBeDefined();
    expect(validateSprintForm({ ...BASE, endDate: "2026-08-31" }).endDate).toBeDefined();
  });
});

describe("toCreateSprintInput", () => {
  it("trims the name and leaves out blank optional fields", () => {
    expect(toCreateSprintInput({ ...EMPTY_SPRINT_FORM, name: "  S1 " })).toEqual({ name: "S1" });
    expect(toCreateSprintInput(BASE)).toEqual({
      name: "Sprint 1",
      goal: "Mục tiêu",
      startDate: "2026-09-01",
      endDate: "2026-09-14",
    });
  });
});

describe("toPatchSprintInput", () => {
  it("returns null when nothing changed", () => {
    expect(toPatchSprintInput(BASE, { ...BASE, name: " Sprint 1 " })).toBeNull();
  });

  it("sends only the changed keys, and null for a cleared date", () => {
    expect(toPatchSprintInput(BASE, { ...BASE, goal: "Mới", endDate: "" })).toEqual({ goal: "Mới", endDate: null });
  });
});

describe("canStartSprint", () => {
  it("needs a draft sprint with both dates", () => {
    expect(canStartSprint({ status: "DRAFT", start_date: "2026-09-01", end_date: "2026-09-14" })).toBe(true);
    expect(canStartSprint({ status: "DRAFT", start_date: null, end_date: "2026-09-14" })).toBe(false);
    expect(canStartSprint({ status: "ACTIVE", start_date: "2026-09-01", end_date: "2026-09-14" })).toBe(false);
  });
});
