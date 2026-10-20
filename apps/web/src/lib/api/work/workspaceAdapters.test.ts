import { describe, expect, it } from "vitest";

import type { WorkProjectShell } from "@/lib/api/work/adapters";
import {
  buildWorkspace,
  epicColor,
  initialsOf,
  sortStates,
  toIssue,
  toIssueDetail,
  toProjectState,
  toSprint,
} from "@/lib/api/work/workspaceAdapters";
import {
  buildDefaultStates,
  buildEpic,
  buildLabel,
  buildProject,
  buildProjectMember,
  buildSprint,
  buildTask,
} from "@/test/workHandlers";

const states = buildDefaultStates().map(toProjectState);
const statesById = new Map(states.map((state) => [state.id, state]));
const context = { userId: "me", statesById, sprintByTask: new Map<string, string>() };

function shell(myRole: WorkProjectShell["myRole"]): WorkProjectShell {
  return {
    project: buildProject(),
    classCode: "SE100.A",
    className: "Lớp A",
    courseCode: "SE100",
    groupName: "Nhóm 1",
    members: [buildProjectMember()],
    myRole,
    canEdit: myRole === "LEADER",
  };
}

describe("epicColor", () => {
  it("is stable for an id and always one of the palette colours", () => {
    expect(epicColor("epic-1")).toBe(epicColor("epic-1"));
    expect(epicColor("epic-1")).toMatch(/^#[0-9a-f]{6}$/);
    expect(new Set(["a", "b", "c", "d", "e", "f"].map(epicColor)).size).toBeGreaterThan(1);
  });
});

describe("initialsOf", () => {
  it.each([
    ["Nguyễn Văn An", "NA"],
    ["an", "A"],
    ["  ", "?"],
    ["", "?"],
  ])("%j → %j", (name, initials) => {
    expect(initialsOf(name)).toBe(initials);
  });
});

describe("sortStates", () => {
  it("orders by sequence without mutating the input", () => {
    const shuffled = [states[3], states[0], states[2]];
    expect(sortStates(shuffled).map((state) => state.sequence)).toEqual([1, 3, 4]);
    expect(shuffled[0]).toBe(states[3]);
  });
});

describe("toIssue", () => {
  it("carries the task's labels and drops deleted ones", () => {
    const issue = toIssue(
      buildTask({
        labels: [
          buildLabel({ id: "l1", name: "frontend", color: "#2563eb" }),
          buildLabel({ id: "l2", name: "cũ", deleted_at: "2026-09-02T00:00:00Z" }),
        ],
      }),
      context,
    )!;
    expect(issue.labels).toEqual([{ id: "l1", name: "frontend", color: "#2563eb" }]);
    expect(toIssue(buildTask(), context)!.labels).toEqual([]);
  });

  it("maps the state to column id, group and derived status", () => {
    const issue = toIssue(buildTask({ state_id: "state-review" }), context)!;
    expect(issue).toMatchObject({ statusId: "state-review", stateGroup: "REVIEW", status: "review" });
  });

  it("maps type, priority, points, rank and due date", () => {
    const issue = toIssue(
      buildTask({ type: "STORY", priority: "URGENT", story_points: 5, sort_order: 2500.5, due_date: "2026-10-01", version: 7 }),
      context,
    )!;
    expect(issue).toMatchObject({ type: "story", priority: "high", storyPoints: 5, rank: 2500.5, dueAt: "2026-10-01", version: 7 });
    expect(toIssue(buildTask({ priority: "LOW", story_points: null }), context)).toMatchObject({ priority: "low", storyPoints: 0 });
  });

  it("leaves subtasks out", () => {
    expect(toIssue(buildTask({ type: "SUBTASK", parent_id: "x" }), context)).toBeNull();
  });

  it("takes the first assignee and flags my own tasks", () => {
    const issue = toIssue(
      buildTask({
        assignee_ids: ["other", "me"],
        assignees: [
          { user_id: "other", display_name: "Trần Thị B", avatar_url: null },
          { user_id: "me", display_name: "Tôi", avatar_url: null },
        ],
      }),
      context,
    )!;
    expect(issue.assignee).toEqual({ userId: "other", displayName: "Trần Thị B", initials: "TB" });
    expect(issue.isMine).toBe(true);
    expect(toIssue(buildTask({ assignee_ids: ["other"] }), context)!.isMine).toBe(false);
    expect(toIssue(buildTask(), context)!.assignee).toBeNull();
  });

  it("shows an assignee with a blank name when the profile is not synced", () => {
    const issue = toIssue(buildTask({ assignee_ids: ["u2"] }), context)!;
    expect(issue.assignee).toEqual({ userId: "u2", displayName: "", initials: "?" });
  });

  it("puts the task in its sprint, or in the backlog", () => {
    const withSprint = { ...context, sprintByTask: new Map([["task-1", "sprint-1"]]) };
    expect(toIssue(buildTask(), withSprint)!.sprintId).toBe("sprint-1");
    expect(toIssue(buildTask(), context)!.sprintId).toBeNull();
  });

  it("falls back to an unstarted column for an unknown state", () => {
    expect(toIssue(buildTask({ state_id: "gone" }), context)).toMatchObject({ statusId: "gone", stateGroup: "UNSTARTED", status: "todo" });
  });
});

describe("toSprint", () => {
  it("sums points and counts only completed-group tasks as done", () => {
    const issues = [
      toIssue(buildTask({ id: "a", story_points: 3, state_id: "state-done" }), { ...context, sprintByTask: new Map([["a", "s1"]]) })!,
      toIssue(buildTask({ id: "b", story_points: 2 }), { ...context, sprintByTask: new Map([["b", "s1"]]) })!,
      toIssue(buildTask({ id: "c", story_points: 9 }), context)!,
    ];
    expect(toSprint(buildSprint({ id: "s1" }), issues)).toMatchObject({ totalPoints: 5, completedPoints: 3 });
  });

  it.each([
    ["DRAFT", "upcoming"],
    ["ACTIVE", "active"],
    ["COMPLETED", "completed"],
  ] as const)("maps %s to %s", (status, state) => {
    expect(toSprint(buildSprint({ status }), []).state).toBe(state);
  });

  it("uses empty dates when the sprint has none", () => {
    expect(toSprint(buildSprint({ start_date: null, end_date: null }), [])).toMatchObject({ startDate: "", endDate: "" });
  });
});

describe("buildWorkspace", () => {
  const input = {
    userId: "me",
    states: buildDefaultStates().reverse(),
    epics: [buildEpic({ id: "e1" }), buildEpic({ id: "e2", deleted_at: "2026-10-01T00:00:00Z" })],
    tasks: [
      buildTask({ id: "b", code: "NEXUS-2", sort_order: 20000, epic_id: "e1" }),
      buildTask({ id: "a", code: "NEXUS-1", sort_order: 10000, epic_id: "e1" }),
      buildTask({ id: "s", code: "NEXUS-3", type: "SUBTASK", parent_id: "a" }),
    ],
    sprints: [
      buildSprint({ id: "s2", sort_order: 2 }),
      buildSprint({ id: "s1", sort_order: 1 }),
      buildSprint({ id: "s0", archived_at: "2026-10-01T00:00:00Z" }),
    ],
    sprintByTask: new Map<string, string>(),
  };

  it("sorts states, issues and sprints, and drops subtasks, deleted epics and archived sprints", () => {
    const workspace = buildWorkspace({ ...input, shell: shell("LEADER") });
    expect(workspace.states.map((state) => state.sequence)).toEqual([1, 2, 3, 4, 5]);
    expect(workspace.issues.map((issue) => issue.key)).toEqual(["NEXUS-1", "NEXUS-2"]);
    expect(workspace.epics.map((epic) => [epic.id, epic.issueCount])).toEqual([["e1", 2]]);
    expect(workspace.sprints.map((sprint) => sprint.id)).toEqual(["s1", "s2"]);
  });

  it("makes a project member a team member with their role", () => {
    expect(buildWorkspace({ ...input, shell: shell("LEADER") })).toMatchObject({
      viewer: { kind: "team-member", role: "leader" },
      myRole: "leader",
      projectKey: "NEXUS",
      teamName: "Nhóm 1",
    });
    expect(buildWorkspace({ ...input, shell: shell("MEMBER") }).myRole).toBe("member");
  });

  it("makes a non-member an instructor with no role", () => {
    const workspace = buildWorkspace({ ...input, shell: shell(null) });
    expect(workspace.viewer).toEqual({ kind: "course-instructor", courseId: "class-1" });
    expect(workspace.myRole).toBeUndefined();
  });
});

describe("toIssueDetail", () => {
  it("shows the stripped description, never the HTML, and splits acceptance criteria into lines", () => {
    const dto = buildTask({
      description_html: "<script>x</script><p>Mô tả</p>",
      description_stripped: "Mô tả",
      acceptance_criteria: "Một\n\n  Hai  \n",
      created_by_user_id: "user-1",
      subtasks: [buildTask({ id: "x", title: "Con 1" }), buildTask({ id: "y", title: "Con 2", completed_at: "2026-10-01T00:00:00Z" })],
    });
    const detail = toIssueDetail(dto, toIssue(dto, context)!, [{ user_id: "user-1", display_name: "Nguyễn Văn A" }]);
    expect(detail).toMatchObject({
      description: "Mô tả",
      acceptanceCriteria: ["Một", "Hai"],
      reporterName: "Nguyễn Văn A",
      comments: [],
      history: [],
      gitLinks: [],
      subtasks: [
        { id: "x", title: "Con 1", done: false },
        { id: "y", title: "Con 2", done: true },
      ],
    });
  });

  it("leaves the reporter blank when the member is unknown", () => {
    const dto = buildTask();
    expect(toIssueDetail(dto, toIssue(dto, context)!, []).reporterName).toBe("");
  });
});
