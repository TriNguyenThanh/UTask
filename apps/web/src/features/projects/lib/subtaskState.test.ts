import { describe, expect, it } from "vitest";

import { stateForSubtask } from "@/features/projects/lib/subtaskState";
import type { ProjectState } from "@/features/projects/types";

const state = (id: string, group: ProjectState["group"], sequence: number): ProjectState =>
  ({ id, name: id, group, sequence }) as ProjectState;

const STATES = [state("done-b", "COMPLETED", 5), state("todo", "UNSTARTED", 2), state("done-a", "COMPLETED", 4), state("backlog", "UNSTARTED", 1)];

describe("stateForSubtask", () => {
  it("picks the first COMPLETED state by sequence when done", () => {
    expect(stateForSubtask(STATES, true)?.id).toBe("done-a");
  });
  it("picks the first UNSTARTED state by sequence when undone", () => {
    expect(stateForSubtask(STATES, false)?.id).toBe("backlog");
  });
  it("returns null when the project has no such state", () => {
    expect(stateForSubtask([state("todo", "UNSTARTED", 1)], true)).toBeNull();
  });
});
