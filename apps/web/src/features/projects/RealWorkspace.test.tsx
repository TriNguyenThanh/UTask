import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { LEADER_ID, MEMBER_ID } from "@/mocks/data/database";
import { createMemoryRepository } from "@/mocks/data/storage";
import { createAuthHandlers } from "@/mocks/handlers/auth";
import { server } from "@/mocks/server";
import { buildClass, buildCourse, buildGroup, classroomHandlers } from "@/test/classroomHandlers";
import { leaderTestSession, memberTestSession, renderAppRoutes } from "@/test/render";
import {
  buildDefaultStates,
  buildEpic,
  buildProject,
  buildProjectMember,
  buildSprint,
  buildTask,
  buildState,
  workHandlers,
  type WorkCall,
  type WorkFixture,
} from "@/test/workHandlers";

function setup(
  path: string,
  fixture: Partial<WorkFixture>,
  session: typeof leaderTestSession | typeof memberTestSession = leaderTestSession,
) {
  vi.stubEnv("VITE_REAL_SERVICES", "auth,classroom,work");
  const calls: WorkCall[] = [];
  server.use(
    ...workHandlers({
      projects: [buildProject({ id: "project-1" })],
      members: {
        "project-1": [
          buildProjectMember({ user_id: LEADER_ID, role: "LEADER", display_name: "Nguyễn Hoàng Nam" }),
          buildProjectMember({ id: "pm-2", user_id: MEMBER_ID, role: "MEMBER", display_name: "Đặng Thảo Linh" }),
        ],
      },
      states: buildDefaultStates(),
      userNames: { [LEADER_ID]: "Nguyễn Hoàng Nam", [MEMBER_ID]: "Đặng Thảo Linh" },
      ...fixture,
      calls,
    }),
    ...classroomHandlers({
      classes: [buildClass({ id: "class-1" })],
      courses: [buildCourse({ id: "course-1" })],
      groups: { "class-1": [buildGroup({ id: "group-1", class_section: "class-1" })] },
    }),
    ...createAuthHandlers("default", createMemoryRepository("default")),
  );
  return { calls, ...renderAppRoutes(path, session) };
}

const TASKS = [
  buildTask({ id: "t1", code: "NEXUS-1", title: "Thiết kế đăng nhập", state_id: "state-todo", sort_order: 1000, story_points: 3, assignee_ids: [MEMBER_ID], epic_id: "e1" }),
  buildTask({ id: "t2", code: "NEXUS-2", title: "API đăng nhập", state_id: "state-doing", sort_order: 2000, story_points: 5 }),
  buildTask({ id: "t3", code: "NEXUS-3", title: "Việc ngoài sprint", state_id: "state-backlog", sort_order: 3000 }),
  buildTask({ id: "sub", code: "NEXUS-4", title: "Việc con", type: "SUBTASK", parent_id: "t1" }),
];

const WORKSPACE: Partial<WorkFixture> = {
  epics: [buildEpic({ id: "e1", name: "Xác thực" })],
  sprints: [buildSprint({ id: "s1", name: "Sprint 1" })],
  tasks: TASKS,
  sprintTasks: { s1: ["t1", "t2"] },
};

describe("Real Board — /projects/:id/board", () => {
  it("builds columns from the project states, in sequence order, and puts each task in its state", async () => {
    setup("/projects/project-1/board", WORKSPACE);
    const todo = await screen.findByRole("region", { name: "To Do" });
    expect(within(todo).getByText("Thiết kế đăng nhập")).toBeInTheDocument();
    const names = screen.getAllByRole("heading", { level: 2 }).map((heading) => heading.textContent);
    expect(names).toEqual(["Backlog", "To Do", "In Progress", "Code Review", "Done"]);
    expect(within(screen.getByRole("region", { name: "In Progress" })).getByText("API đăng nhập")).toBeInTheDocument();
  });

  it("shows only the active sprint, and no subtasks", async () => {
    setup("/projects/project-1/board", WORKSPACE);
    await screen.findByText("Thiết kế đăng nhập");
    expect(screen.queryByText("Việc ngoài sprint")).not.toBeInTheDocument();
    expect(screen.queryByText("Việc con")).not.toBeInTheDocument();
  });

  it("hides a CANCELLED state column", async () => {
    setup("/projects/project-1/board", {
      ...WORKSPACE,
      states: [...buildDefaultStates(), buildState({ id: "state-cancel", name: "Đã hủy", sequence: 6, group: "CANCELLED", is_default: false })],
    });
    await screen.findByRole("region", { name: "To Do" });
    expect(screen.queryByRole("region", { name: "Đã hủy" })).not.toBeInTheDocument();
  });

  it("tells a viewer there is no running sprint", async () => {
    setup("/projects/project-1/board", { ...WORKSPACE, sprints: [buildSprint({ id: "s1", status: "DRAFT" })] });
    expect(await screen.findByText("Chưa có Sprint đang chạy")).toBeInTheDocument();
  });

  it("gives a member the action menu only on their own cards", async () => {
    setup("/projects/project-1/board", WORKSPACE, memberTestSession);
    await screen.findByText("Thiết kế đăng nhập");
    expect(screen.getAllByRole("button", { name: /Thao tác cho/ })).toHaveLength(1);
  });

  it("makes no write request just by viewing the board", async () => {
    const { calls } = setup("/projects/project-1/board", WORKSPACE);
    await screen.findByText("Thiết kế đăng nhập");
    expect(calls.filter((call) => call.method !== "GET")).toEqual([]);
  });

  it("opens the issue panel from ?issue= with the stripped description and subtasks", async () => {
    setup("/projects/project-1/board?issue=NEXUS-1", {
      ...WORKSPACE,
      tasks: [
        buildTask({ ...TASKS[0], description_html: "<script>alert(1)</script><p>Mô tả</p>", description_stripped: "Mô tả ngắn" }),
        ...TASKS.slice(1),
      ],
    });
    expect((await screen.findAllByText("Mô tả ngắn")).length).toBeGreaterThan(0);
    expect(screen.queryByText(/alert\(1\)/)).not.toBeInTheDocument();
    expect(await screen.findByText("Việc con")).toBeInTheDocument();
  });

  it("locks the status field and subtasks on a card the member does not own, with no AI key link", async () => {
    setup("/projects/project-1/board?issue=NEXUS-2", { ...WORKSPACE, tasks: [...TASKS.slice(0, 1), buildTask({ ...TASKS[1] }), TASKS[2], buildTask({ ...TASKS[3], parent_id: "t2" })] }, memberTestSession);
    const select = await screen.findByLabelText("Trạng thái");
    expect(select).toBeDisabled();
    expect(select).toHaveDisplayValue("In Progress");
    expect(screen.queryByText(/Cấu hình AI key/)).not.toBeInTheDocument();
    expect(await screen.findByRole("checkbox", { name: /Việc con/ })).toBeDisabled();
  });

  it("shows not-found in the panel for a key that is not in the project", async () => {
    setup("/projects/project-1/board?issue=NEXUS-99", WORKSPACE);
    expect(await screen.findByText(/không tìm thấy/i)).toBeInTheDocument();
  });

  it("shows an error with retry when tasks fail to load", async () => {
    setup("/projects/project-1/board", { ...WORKSPACE, tasksError: { status: 500, code: "INTERNAL_ERROR", message: "Lỗi máy chủ" } });
    expect(await screen.findByRole("button", { name: /thử lại/i })).toBeInTheDocument();
  });
});

describe("Real Backlog — /projects/:id/backlog", () => {
  it("lists sprint tasks under the sprint and the rest under the backlog, with epics", async () => {
    setup("/projects/project-1/backlog", WORKSPACE);
    const sprint = (await screen.findByRole("heading", { name: "Sprint 1" })).closest("section")!;
    expect(within(sprint).getByText("Thiết kế đăng nhập")).toBeInTheDocument();
    expect(within(sprint).getByText("API đăng nhập")).toBeInTheDocument();
    expect(screen.getByText("Việc ngoài sprint")).toBeInTheDocument();
    expect(screen.queryByText("Việc con")).not.toBeInTheDocument();
    expect(screen.getAllByText("Xác thực").length).toBeGreaterThan(0);
  });

  it("hides the AI toolbar and makes no write request", async () => {
    const { calls } = setup("/projects/project-1/backlog", WORKSPACE);
    await screen.findByText("Thiết kế đăng nhập");
    expect(screen.queryByText("Trợ lý AI Scrum Copilot")).not.toBeInTheDocument();
    expect(calls.filter((call) => call.method !== "GET")).toEqual([]);
  });
});

describe("Real project tabs", () => {
  it("navigates between Backlog, Board and Info", async () => {
    const user = userEvent.setup();
    setup("/projects/project-1/backlog", WORKSPACE);
    const nav = await screen.findByRole("navigation", { name: "Project navigation" });
    expect(within(nav).getByRole("link", { name: "Backlog" })).toHaveAttribute("aria-current", "page");
    await user.click(within(nav).getByRole("link", { name: "Bảng công việc" }));
    await screen.findByRole("region", { name: "To Do" });
    expect(within(screen.getByRole("navigation", { name: "Project navigation" })).getByRole("link", { name: "Bảng công việc" })).toHaveAttribute("aria-current", "page");
    await user.click(within(screen.getByRole("navigation", { name: "Project navigation" })).getByRole("link", { name: "Thông tin" }));
    await waitFor(() => expect(screen.getByRole("heading", { name: "Thông tin dự án" })).toBeInTheDocument());
  });
});
