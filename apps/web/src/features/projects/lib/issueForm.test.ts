import { describe, expect, it } from "vitest";

import {
  EMPTY_ISSUE_FORM,
  formValuesOfTask,
  toCreateInput,
  toPatchInput,
  validateIssueForm,
} from "@/features/projects/lib/issueForm";
import { buildTask } from "@/test/workHandlers";

describe("validateIssueForm", () => {
  it("requires a title within 300 characters", () => {
    expect(validateIssueForm({ ...EMPTY_ISSUE_FORM, title: "  " }).title).toBeDefined();
    expect(validateIssueForm({ ...EMPTY_ISSUE_FORM, title: "x".repeat(301) }).title).toBeDefined();
    expect(validateIssueForm({ ...EMPTY_ISSUE_FORM, title: "x".repeat(300) })).toEqual({});
  });

  it("accepts empty or whole-number story points only", () => {
    const base = { ...EMPTY_ISSUE_FORM, title: "a" };
    expect(validateIssueForm({ ...base, storyPoints: "" })).toEqual({});
    expect(validateIssueForm({ ...base, storyPoints: "5" })).toEqual({});
    for (const bad of ["-1", "1.5", "abc", "1234567890"]) {
      expect(validateIssueForm({ ...base, storyPoints: bad }).storyPoints).toBeDefined();
    }
  });
});

describe("toCreateInput", () => {
  it("sends only the title, type and priority for an untouched form", () => {
    expect(toCreateInput({ ...EMPTY_ISSUE_FORM, title: " Việc " })).toEqual({ title: "Việc", type: "TASK", priority: "MEDIUM" });
  });

  it("includes every filled field", () => {
    const input = toCreateInput({
      type: "BUG", title: "Lỗi", description: "mô tả", acceptanceCriteria: "tiêu chí", priority: "URGENT",
      storyPoints: "3", dueDate: "2026-10-01", epicId: "e1", assigneeIds: ["u1"],
    });
    expect(input).toEqual({
      title: "Lỗi", type: "BUG", priority: "URGENT", descriptionHtml: "mô tả", acceptanceCriteria: "tiêu chí",
      storyPoints: 3, dueDate: "2026-10-01", epicId: "e1", assigneeIds: ["u1"],
    });
  });
});

describe("formValuesOfTask / toPatchInput", () => {
  const task = buildTask({ title: "Cũ", story_points: 2, due_date: "2026-10-01", epic_id: "e1", assignee_ids: ["u1", "u2"], priority: "HIGH" });
  const initial = formValuesOfTask(task);

  it("maps a task into form values", () => {
    expect(initial).toMatchObject({ title: "Cũ", storyPoints: "2", dueDate: "2026-10-01", epicId: "e1", priority: "HIGH" });
  });

  it("returns null when nothing changed, even if assignees are reordered", () => {
    expect(toPatchInput(initial, { ...initial, assigneeIds: ["u2", "u1"] }, 4)).toBeNull();
  });

  it("sends only changed keys and clears nullable fields with null", () => {
    const patch = toPatchInput(initial, { ...initial, title: " Mới ", storyPoints: "", dueDate: "", epicId: "" }, 4);
    expect(patch).toEqual({ expectedVersion: 4, title: "Mới", storyPoints: null, dueDate: null, epicId: null });
  });

  it("limits a non-leader to the description, the only field the backend lets them change", () => {
    const patch = toPatchInput(
      initial,
      { ...initial, title: "Mới", acceptanceCriteria: "Khác", description: "Mô tả mới", priority: "LOW", assigneeIds: [] },
      4,
      "text",
    );
    expect(patch).toEqual({ expectedVersion: 4, descriptionHtml: "Mô tả mới" });
    expect(toPatchInput(initial, { ...initial, title: "Mới", priority: "LOW" }, 4, "text")).toBeNull();
  });
});
