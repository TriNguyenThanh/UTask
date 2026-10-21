import { describe, expect, it } from "vitest";

import {
  backlogFormFromProject,
  buildBacklogBody,
  EMPTY_BACKLOG_FORM,
  splitLines,
  validateBacklogForm,
} from "@/features/projects/lib/aiBacklogForm";

describe("splitLines", () => {
  it("trims and drops blank lines", () => {
    expect(splitLines("  a \n\n b\n   \n")).toEqual(["a", "b"]);
  });
});

describe("backlogFormFromProject", () => {
  it("prefills the description and goals", () => {
    expect(backlogFormFromProject({ name: "Tên", description: " Mô tả ", target_goals: "G1\nG2" })).toMatchObject({
      description: "Mô tả",
      goals: "G1\nG2",
      techStack: "",
    });
  });

  it("falls back to the project name when the description is blank", () => {
    expect(backlogFormFromProject({ name: "Tên", description: "  ", target_goals: "" }).description).toBe("Tên");
  });
});

describe("validateBacklogForm", () => {
  it("requires a description", () => {
    expect(validateBacklogForm({ ...EMPTY_BACKLOG_FORM, description: "  " })).toEqual({ description: "Nhập mô tả dự án." });
  });

  it("accepts exactly 30 lines and rejects 31, per list", () => {
    const lines = (count: number) => Array.from({ length: count }, (_, i) => `m${i}`).join("\n");
    expect(validateBacklogForm({ ...EMPTY_BACKLOG_FORM, description: "x", goals: lines(30) })).toEqual({});
    expect(validateBacklogForm({ ...EMPTY_BACKLOG_FORM, description: "x", goals: lines(31), constraints: lines(31) })).toEqual({
      goals: "Tối đa 30 mục.",
      constraints: "Tối đa 30 mục.",
    });
  });

  it("does not count blank lines toward the limit", () => {
    const padded = `${"a\n".repeat(30)}\n\n\n`;
    expect(validateBacklogForm({ ...EMPTY_BACKLOG_FORM, description: "x", techStack: padded })).toEqual({});
  });
});

describe("buildBacklogBody", () => {
  it("sends only the description when nothing else is filled", () => {
    expect(buildBacklogBody("p1", { ...EMPTY_BACKLOG_FORM, description: " Mô tả " }, null)).toEqual({
      intent: "backlog_generation",
      target: { type: "project", id: "p1" },
      input: { description: "Mô tả" },
    });
  });

  it("adds lists, a Vietnam-time deadline and the extra instruction", () => {
    const body = buildBacklogBody(
      "p1",
      { description: "D", goals: "g1\ng2", techStack: "React", constraints: "Không DB", extra: " Ưu tiên API " },
      "2026-12-31",
    );

    expect(body.input).toEqual({
      description: "D",
      goals: ["g1", "g2"],
      tech_stack: ["React"],
      constraints: ["Không DB"],
      deadline: "2026-12-31T23:59:59+07:00",
      additional_instruction: "Ưu tiên API",
    });
  });

  it("cuts a description over 12000 characters", () => {
    const body = buildBacklogBody("p1", { ...EMPTY_BACKLOG_FORM, description: "x".repeat(13_000) }, null);
    expect(body.input.description).toHaveLength(12_000);
  });
});
