import { describe, expect, it } from "vitest";

import {
  EMPTY_EPIC_FORM,
  epicEditAccess,
  formValuesOfEpic,
  toCreateEpicInput,
  toPatchEpicInput,
  validateEpicForm,
} from "@/features/projects/lib/epicForm";
import { buildEpic } from "@/test/workHandlers";

describe("validateEpicForm", () => {
  it("requires a name and caps its length", () => {
    expect(validateEpicForm(EMPTY_EPIC_FORM).name).toBeDefined();
    expect(validateEpicForm({ ...EMPTY_EPIC_FORM, name: "x".repeat(201) }).name).toBeDefined();
    expect(validateEpicForm({ ...EMPTY_EPIC_FORM, name: "ok" })).toEqual({});
  });

  it("rejects a target date before the start date but allows equal or one-sided dates", () => {
    const base = { ...EMPTY_EPIC_FORM, name: "ok" };
    expect(validateEpicForm({ ...base, startDate: "2026-09-10", targetDate: "2026-09-01" }).targetDate).toBeDefined();
    expect(validateEpicForm({ ...base, startDate: "2026-09-10", targetDate: "2026-09-10" })).toEqual({});
    expect(validateEpicForm({ ...base, startDate: "2026-09-10" })).toEqual({});
  });
});

describe("toCreateEpicInput", () => {
  it("sends only the fields that were filled", () => {
    expect(toCreateEpicInput({ ...EMPTY_EPIC_FORM, name: " E " })).toEqual({ name: "E", status: "PLANNED" });
    expect(toCreateEpicInput({ ...EMPTY_EPIC_FORM, name: "E", leadUserId: "u1", targetDate: "2026-09-30" })).toEqual({
      name: "E",
      status: "PLANNED",
      leadUserId: "u1",
      targetDate: "2026-09-30",
    });
  });
});

describe("toPatchEpicInput", () => {
  const initial = formValuesOfEpic(buildEpic({ lead_user_id: "u1", start_date: "2026-09-01", target_date: "2026-09-30" }));

  it("returns null when nothing changed", () => {
    expect(toPatchEpicInput(initial, { ...initial })).toBeNull();
  });

  it("clears a lead and a date with null", () => {
    expect(toPatchEpicInput(initial, { ...initial, leadUserId: "", startDate: "" })).toEqual({ leadUserId: null, startDate: null });
  });

  it("limited access drops lead and date changes", () => {
    const changed = { ...initial, name: "Mới", leadUserId: "u2", targetDate: "2026-10-01" };
    expect(toPatchEpicInput(initial, changed, "limited")).toEqual({ name: "Mới" });
    expect(toPatchEpicInput(initial, { ...initial, leadUserId: "u2" }, "limited")).toBeNull();
  });
});

describe("epicEditAccess", () => {
  const epic = { lead_user_id: "u1" };
  it("gives the leader everything, the epic lead a limited form, others nothing", () => {
    expect(epicEditAccess("leader", "u9", epic)).toBe("all");
    expect(epicEditAccess("member", "u1", epic)).toBe("limited");
    expect(epicEditAccess("member", "u2", epic)).toBeNull();
    expect(epicEditAccess("none", "u1", epic)).toBeNull();
  });
});
