import { describe, expect, it } from "vitest";

import { createApiClient } from "@/lib/api/client";
import type { WorkProjectShell } from "@/lib/api/work/adapters";
import { loadWorkspace } from "@/lib/api/work/loaders";
import { server } from "@/mocks/server";
import {
  buildDefaultStates,
  buildProject,
  buildProjectMember,
  buildSprint,
  buildTask,
  workHandlers,
} from "@/test/workHandlers";

const client = createApiClient({ baseUrl: "http://localhost", getAccessToken: () => "token", onUnauthorized: () => undefined });

const shell: WorkProjectShell = {
  project: buildProject(),
  classCode: "",
  className: "",
  courseCode: "",
  groupName: "",
  members: [buildProjectMember()],
  myRole: "LEADER",
  canEdit: true,
};

describe("loadWorkspace", () => {
  it("places tasks into their open sprint and leaves the rest in the backlog", async () => {
    server.use(
      ...workHandlers({
        projects: [],
        states: buildDefaultStates(),
        sprints: [buildSprint({ id: "s1" }), buildSprint({ id: "s2", status: "DRAFT" })],
        tasks: [buildTask({ id: "a", code: "N-1" }), buildTask({ id: "b", code: "N-2" }), buildTask({ id: "c", code: "N-3" })],
        sprintTasks: { s1: ["a"], s2: ["b"] },
      }),
    );
    const workspace = await loadWorkspace(client, "me", shell);
    expect(Object.fromEntries(workspace.issues.map((issue) => [issue.key, issue.sprintId]))).toEqual({
      "N-1": "s1",
      "N-2": "s2",
      "N-3": null,
    });
  });

  it("does not ask for the members of a completed sprint", async () => {
    const seen: string[] = [];
    server.use(
      ...workHandlers({
        projects: [],
        states: buildDefaultStates(),
        sprints: [buildSprint({ id: "done", status: "COMPLETED" })],
        tasks: [buildTask({ id: "a" })],
      }),
    );
    server.events.on("request:start", ({ request }) => seen.push(request.url));
    await loadWorkspace(client, "me", shell);
    expect(seen.some((url) => url.includes("sprint_id"))).toBe(false);
    server.events.removeAllListeners();
  });

  it("fails as a whole when a required list fails", async () => {
    server.use(
      ...workHandlers({ projects: [], statesError: { status: 500, code: "INTERNAL_ERROR", message: "Lỗi" } }),
    );
    await expect(loadWorkspace(client, "me", shell)).rejects.toMatchObject({ status: 500 });
  });
});
