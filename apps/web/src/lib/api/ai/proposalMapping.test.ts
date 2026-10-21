import { describe, expect, it } from "vitest";

import { backlogItemToCreateInput, subtaskToCreateInput } from "@/lib/api/ai/proposalMapping";
import { buildAiBacklogItem, buildAiSubtask } from "@/test/aiHandlers";

describe("subtaskToCreateInput", () => {
  it("gives a leader rounded story points and trimmed text", () => {
    const input = subtaskToCreateInput(
      buildAiSubtask({ description: "  Mô tả  ", acceptance_criteria: [" a ", "", "b"], estimate_points: 2.6 }),
      "  Tiêu đề ",
      true,
    );

    expect(input).toEqual({ title: "Tiêu đề", descriptionHtml: "Mô tả", acceptanceCriteria: "a\nb", storyPoints: 3 });
  });

  it("sends a non-leader only title, description and criteria", () => {
    const input = subtaskToCreateInput(buildAiSubtask(), "Việc", false);

    expect(Object.keys(input).sort()).toEqual(["acceptanceCriteria", "descriptionHtml", "title"]);
  });

  it("omits empty description and criteria", () => {
    const input = subtaskToCreateInput(buildAiSubtask({ description: "  ", acceptance_criteria: ["", " "] }), "Việc", false);

    expect(input).toEqual({ title: "Việc" });
  });

  it("cuts a 400-character title to 300", () => {
    expect(subtaskToCreateInput(buildAiSubtask(), "x".repeat(400), false).title).toHaveLength(300);
  });
});

describe("backlogItemToCreateInput", () => {
  it("maps critical to URGENT and always creates a TASK with points", () => {
    const input = backlogItemToCreateInput(buildAiBacklogItem({ priority: "critical", estimate_points: 4.4 }), "Việc");

    expect(input).toMatchObject({ type: "TASK", priority: "URGENT", storyPoints: 4, title: "Việc" });
  });

  it.each([
    ["low", "LOW"],
    ["medium", "MEDIUM"],
    ["high", "HIGH"],
  ] as const)("maps %s to %s", (ai, work) => {
    expect(backlogItemToCreateInput(buildAiBacklogItem({ priority: ai }), "Việc").priority).toBe(work);
  });
});
