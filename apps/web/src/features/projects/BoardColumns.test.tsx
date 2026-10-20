import { screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { DEMO_STATES, statusForGroup } from "@/features/projects/issueMeta";
import type { ProjectState, StateGroup } from "@/features/projects/types";
import { server } from "@/mocks/server";
import { LEADER_ID } from "@/mocks/data/database";
import { leaderTestSession, renderAppRoutes } from "@/test/render";

const BOARD = "/projects/project-nexus/board";

// ── statusForGroup ────────────────────────────────────────────────────────────

describe("statusForGroup", () => {
  const cases: [StateGroup, string][] = [
    ["BACKLOG", "todo"],
    ["UNSTARTED", "todo"],
    ["STARTED", "in-progress"],
    ["REVIEW", "review"],
    ["COMPLETED", "done"],
    ["CANCELLED", "done"],
  ];

  for (const [group, expected] of cases) {
    it(`${group} → "${expected}"`, () => {
      expect(statusForGroup(group)).toBe(expected);
    });
  }
});

// ── Board columns from workspace.states ──────────────────────────────────────

/** Overrides the project workspace endpoint to return custom states only. */
function patchStates(states: ProjectState[]) {
  server.use(
    http.get("/api/work/api/v1/projects/project-nexus", async () => {
      // Build a minimal workspace response with the custom states.
      // The full workspace from studentFlow already provides issues/sprints/epics;
      // here we just need the board to load. Re-use the mock via a direct call.
      const res = await fetch(`http://localhost/api/work/api/v1/projects/project-nexus`, {
        headers: { Authorization: `Bearer mock-access:${LEADER_ID}:test` },
      });
      const data = await res.json();
      return HttpResponse.json({ ...data, states });
    }),
  );
}

describe("Board columns from workspace.states", () => {
  it("renders one column per non-CANCELLED state using default DEMO_STATES", async () => {
    renderAppRoutes(BOARD, leaderTestSession);

    for (const state of DEMO_STATES) {
      expect(await screen.findByRole("region", { name: state.name }, { timeout: 5000 })).toBeInTheDocument();
    }
    // Exactly 4 columns (no CANCELLED in DEMO_STATES).
    expect(screen.getAllByRole("region").filter((el) => DEMO_STATES.some((s) => s.name === el.getAttribute("aria-label")))).toHaveLength(4);
  });

  it("places a card in the column whose state id matches issue.statusId", async () => {
    renderAppRoutes(BOARD, leaderTestSession);

    const todoColumn = await screen.findByRole("region", { name: "Cần làm (To Do)" }, { timeout: 5000 });
    expect(within(todoColumn).getByText("NEXUS-101")).toBeInTheDocument();
    expect(within(todoColumn).getByText("NEXUS-102")).toBeInTheDocument();

    const inProgressColumn = screen.getByRole("region", { name: "Đang làm (In Progress)" });
    expect(within(inProgressColumn).getByText("NEXUS-104")).toBeInTheDocument();
  });

  it("hides a CANCELLED state column", async () => {
    const statesWithCancelled: ProjectState[] = [
      ...DEMO_STATES,
      { id: "state-cancelled", name: "Đã huỷ", color: "#ef4444", sequence: 5, group: "CANCELLED", isDefault: false },
    ];
    // Inject into MSW - replace default workspace states only.
    server.use(
      http.get("/api/work/api/v1/projects/project-nexus", () => {
        // Return minimal workspace — board only needs states and issues.
        // Issues already have statusId matching DEMO_STATES, so they'll show correctly.
        return HttpResponse.json({
          projectId: "project-nexus",
          projectKey: "NEXUS",
          name: "Smart Supply Chain",
          courseCode: "SE330",
          courseName: "Đồ án",
          instructorName: "TS. Trần Minh Đức",
          teamName: "Team NEXUS",
          courseId: "course-se330",
          teamId: "team-nexus",
          viewer: { kind: "team-member", role: "leader" },
          myRole: "leader",
          repository: null,
          epics: [],
          sprints: [
            {
              id: "sprint-2",
              name: "Sprint 2",
              state: "active",
              startDate: "2026-10-01T00:00:00.000Z",
              endDate: "2026-11-01T00:00:00.000Z",
              goal: "",
              completedPoints: 0,
              totalPoints: 0,
            },
          ],
          issues: [
            {
              id: "i1",
              key: "NEXUS-101",
              type: "task",
              title: "Test issue",
              status: "todo",
              statusId: "state-todo",
              stateGroup: "UNSTARTED",
              priority: "medium",
              storyPoints: 1,
              epicId: null,
              sprintId: "sprint-2",
              assignee: null,
              hasPullRequest: false,
              isMine: true,
              updatedAt: "2026-10-01T00:00:00.000Z",
              rank: 1000,
              version: 1,
              blocked: false,
              blockedReason: null,
            },
          ],
          states: statesWithCancelled,
        });
      }),
    );

    renderAppRoutes(BOARD, leaderTestSession);
    await screen.findByRole("region", { name: "Cần làm (To Do)" }, { timeout: 5000 });
    expect(screen.queryByRole("region", { name: "Đã huỷ" })).not.toBeInTheDocument();
  });
});
