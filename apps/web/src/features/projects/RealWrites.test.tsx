import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { describe, expect, it, vi } from "vitest";

import { LEADER_ID, MEMBER_ID } from "@/mocks/data/database";
import { createMemoryRepository } from "@/mocks/data/storage";
import { createAuthHandlers } from "@/mocks/handlers/auth";
import { server } from "@/mocks/server";
import { buildClass, buildCourse, buildGroup, classroomHandlers, envelopeError } from "@/test/classroomHandlers";
import { leaderTestSession, memberTestSession, renderAppRoutes } from "@/test/render";
import {
  buildDefaultStates,
  buildEpic,
  buildProject,
  buildProjectMember,
  buildSprint,
  buildTask,
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
  const tasks = fixture.tasks ?? [];
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
      epics: [buildEpic({ id: "e1", name: "Xác thực" })],
      sprints: [buildSprint({ id: "s1", name: "Sprint 1" })],
      sprintTasks: { s1: ["t1", "t2"] },
      ...fixture,
      tasks,
      calls,
    }),
    ...classroomHandlers({
      classes: [buildClass({ id: "class-1" })],
      courses: [buildCourse({ id: "course-1" })],
      groups: { "class-1": [buildGroup({ id: "group-1", class_section: "class-1" })] },
    }),
    ...createAuthHandlers("default", createMemoryRepository("default")),
  );
  return { calls, tasks, ...renderAppRoutes(path, session) };
}

function freshTasks() {
  return [
    buildTask({ id: "t1", code: "NEXUS-1", title: "Thiết kế đăng nhập", state_id: "state-todo", sort_order: 1000, version: 2, assignee_ids: [MEMBER_ID] }),
    buildTask({ id: "t2", code: "NEXUS-2", title: "API đăng nhập", state_id: "state-doing", sort_order: 2000, version: 1 }),
    // Subtask the board never shows, yet it sits in the To Do column the server ranks against.
    buildTask({ id: "sub", code: "NEXUS-3", title: "Việc con", type: "SUBTASK", parent_id: "t1", state_id: "state-todo", sort_order: 1500, version: 1 }),
  ];
}

const writes = (calls: WorkCall[]) => calls.filter((call) => call.method !== "GET");

async function openMenu(user: ReturnType<typeof userEvent.setup>, key: string) {
  await user.click(await screen.findByRole("button", { name: `Thao tác cho ${key}` }, { timeout: 5000 }));
}

describe("Real Board writes", () => {
  it("moves a card from its menu: ranks against the full column, keeps the new column after the server accepts", async () => {
    const user = userEvent.setup();
    const { calls, tasks } = setup("/projects/project-1/board", { tasks: freshTasks() });
    await openMenu(user, "NEXUS-2");
    await user.click(await screen.findByRole("menuitem", { name: "Chuyển sang To Do" }));

    await waitFor(() => expect(writes(calls)).toHaveLength(1));
    expect(writes(calls)[0]).toMatchObject({
      method: "PATCH",
      path: "/tasks/t2/transition/",
      idempotencyKey: null,
      // Appended after the hidden subtask (last in the column), not after the last card the board shows.
      body: { expected_version: 1, target_state_id: "state-todo", previous_task_id: "sub", next_task_id: null },
    });
    expect(within(await screen.findByRole("region", { name: "To Do" })).getByText("API đăng nhập")).toBeInTheDocument();
    expect(tasks.find((task) => task.id === "t2")?.state_id).toBe("state-todo");
  });

  it("rolls the card back and explains when the server rejects the move with VERSION_CONFLICT", async () => {
    const user = userEvent.setup();
    setup("/projects/project-1/board", { tasks: freshTasks(), writeError: { status: 409, code: "VERSION_CONFLICT", message: "x" } });
    await openMenu(user, "NEXUS-2");
    await user.click(await screen.findByRole("menuitem", { name: "Chuyển sang To Do" }));

    expect(await screen.findByText("Issue vừa được người khác cập nhật. Bảng đã được tải lại.")).toBeInTheDocument();
    await waitFor(() =>
      expect(within(screen.getByRole("region", { name: "In Progress" })).getByText("API đăng nhập")).toBeInTheDocument(),
    );
  });

  it("blocks and unblocks with PATCH and the reason", async () => {
    const user = userEvent.setup();
    const { calls } = setup("/projects/project-1/board", { tasks: freshTasks() });
    await openMenu(user, "NEXUS-2");
    await user.click(await screen.findByRole("menuitem", { name: "Đánh dấu bị chặn…" }));
    await user.type(await screen.findByLabelText("Lý do"), "Chờ API ngoài");
    await user.click(screen.getByRole("button", { name: /Đánh dấu bị chặn|Xác nhận|Chặn/ }));

    await waitFor(() => expect(writes(calls)).toHaveLength(1));
    expect(writes(calls)[0]).toMatchObject({
      method: "PATCH",
      path: "/tasks/t2/block/",
      body: { expected_version: 1, blocked_reason: "Chờ API ngoài" },
    });
  });

  it("gives a member the menu on their own card only and moves it", async () => {
    const user = userEvent.setup();
    const { calls } = setup("/projects/project-1/board", { tasks: freshTasks() }, memberTestSession);
    await openMenu(user, "NEXUS-1");
    expect(screen.queryByRole("button", { name: "Thao tác cho NEXUS-2" })).not.toBeInTheDocument();
    await user.click(await screen.findByRole("menuitem", { name: "Chuyển sang In Progress" }));
    await waitFor(() => expect(writes(calls)).toHaveLength(1));
    expect(writes(calls)[0].body).toMatchObject({ target_state_id: "state-doing", previous_task_id: "t2", next_task_id: null });
  });
});

describe("Create issue", () => {
  it("creates with an idempotency key, and reuses the key for a retry with the same content", async () => {
    const user = userEvent.setup();
    const keys: (string | null)[] = [];
    const { calls } = setup("/projects/project-1/board", { tasks: freshTasks() });
    server.use(
      http.post(
        "/api/work/projects/:projectId/tasks/",
        ({ request }) => {
          keys.push(request.headers.get("Idempotency-Key"));
          return envelopeError(500, "INTERNAL_ERROR", "Lỗi máy chủ");
        },
        { once: true },
      ),
    );
    await user.click(await screen.findByRole("button", { name: "Tạo Issue" }, { timeout: 5000 }));
    const dialog = await screen.findByRole("dialog");
    // Chỉ kiểm khóa của lệnh tạo: không thêm vào Sprint đang chạy.
    await user.click(within(dialog).getByLabelText("Thêm vào Sprint đang chạy (Sprint 1)"));
    await user.type(within(dialog).getByLabelText("Tiêu đề"), "Việc mới");
    await user.click(within(dialog).getByRole("button", { name: "Tạo Issue" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Không thể cập nhật issue");

    await user.click(within(dialog).getByRole("button", { name: "Tạo Issue" }));
    await waitFor(() => expect(writes(calls)).toHaveLength(1));
    expect(writes(calls)[0]).toMatchObject({ path: "/projects/project-1/tasks/", body: { title: "Việc mới", type: "TASK", priority: "MEDIUM" } });
    expect(writes(calls)[0].idempotencyKey).toBe(keys[0]);
    expect(keys[0]).toBeTruthy();
  });

  it("does not offer the button to a member", async () => {
    setup("/projects/project-1/board", { tasks: freshTasks() }, memberTestSession);
    await screen.findByText("Thiết kế đăng nhập");
    expect(screen.queryByRole("button", { name: "Tạo Issue" })).not.toBeInTheDocument();
  });

  it("adds a new issue to the active sprint with the reason, so it shows on the board", async () => {
    const user = userEvent.setup();
    const { calls } = setup("/projects/project-1/board", { tasks: freshTasks() });
    await user.click(await screen.findByRole("button", { name: "Tạo Issue" }, { timeout: 5000 }));
    const dialog = await screen.findByRole("dialog");
    await user.type(within(dialog).getByLabelText("Tiêu đề"), "Việc phát sinh");
    await user.type(within(dialog).getByLabelText("Lý do thêm vào Sprint"), "Khách hàng yêu cầu gấp");
    await user.click(within(dialog).getByRole("button", { name: "Tạo Issue" }));

    await waitFor(() => expect(writes(calls)).toHaveLength(2));
    expect(writes(calls)[0].path).toBe("/projects/project-1/tasks/");
    expect(writes(calls)[1]).toMatchObject({
      path: "/sprints/s1/tasks/",
      body: { action: "ADD", scope_change_reason: "Khách hàng yêu cầu gấp" },
    });
    expect(await screen.findByText(/trong Sprint 1\.$/)).toBeInTheDocument();
    expect(await within(await screen.findByRole("region", { name: "To Do" })).findByText("Việc phát sinh")).toBeInTheDocument();
  });

  it("asks for a reason before adding to the active sprint and sends nothing without it", async () => {
    const user = userEvent.setup();
    const { calls } = setup("/projects/project-1/board", { tasks: freshTasks() });
    await user.click(await screen.findByRole("button", { name: "Tạo Issue" }, { timeout: 5000 }));
    const dialog = await screen.findByRole("dialog");
    await user.type(within(dialog).getByLabelText("Tiêu đề"), "Việc phát sinh");
    await user.click(within(dialog).getByRole("button", { name: "Tạo Issue" }));

    expect(await within(dialog).findByText("Nhập lý do thêm issue vào Sprint đang chạy.")).toBeInTheDocument();
    expect(writes(calls)).toHaveLength(0);
  });

  it("keeps the created issue and does not create it again when adding to the sprint fails", async () => {
    const user = userEvent.setup();
    const { calls } = setup("/projects/project-1/board", { tasks: freshTasks() });
    server.use(
      http.post("/api/work/sprints/:sprintId/tasks/", () => envelopeError(500, "INTERNAL_ERROR", "Lỗi máy chủ"), { once: true }),
    );
    await user.click(await screen.findByRole("button", { name: "Tạo Issue" }, { timeout: 5000 }));
    const dialog = await screen.findByRole("dialog");
    await user.type(within(dialog).getByLabelText("Tiêu đề"), "Việc phát sinh");
    await user.type(within(dialog).getByLabelText("Lý do thêm vào Sprint"), "Gấp");
    await user.click(within(dialog).getByRole("button", { name: "Tạo Issue" }));

    expect(await screen.findByText(/chưa thêm được vào Sprint.*Issue đang ở Product Backlog\./)).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(writes(calls).filter((call) => call.path === "/projects/project-1/tasks/")).toHaveLength(1);
  });
});

describe("Board with an empty active sprint", () => {
  it("says the sprint has no issues instead of blaming filters, and points to the backlog", async () => {
    setup("/projects/project-1/board", { tasks: freshTasks(), sprintTasks: { s1: [] } });
    expect(await screen.findByText("Sprint chưa có issue", {}, { timeout: 5000 })).toBeInTheDocument();
    expect(screen.getByText(/Bấm "Tạo Issue" để tạo issue ngay trong Sprint/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Mở Backlog" })).toHaveAttribute("href", "/projects/project-1/backlog");
    expect(screen.queryByText("Không có issue khớp bộ lọc")).not.toBeInTheDocument();
  });

  it("does not tell a member to create issues", async () => {
    setup("/projects/project-1/board", { tasks: freshTasks(), sprintTasks: { s1: [] } }, memberTestSession);
    expect(await screen.findByText(/Thêm issue vào Sprint từ trang Backlog\./, {}, { timeout: 5000 })).toBeInTheDocument();
  });
});

describe("Issue panel edits", () => {
  it("sends only the changed field with expected_version, and reloads the form after a VERSION_CONFLICT", async () => {
    const user = userEvent.setup();
    const { calls, tasks } = setup("/projects/project-1/board?issue=NEXUS-1", { tasks: freshTasks() });
    await user.click(await screen.findByText("Chỉnh sửa issue", {}, { timeout: 5000 }));
    const title = await screen.findByLabelText("Tiêu đề");
    await user.clear(title);
    await user.type(title, "Tên mới");
    await user.click(screen.getByRole("button", { name: "Lưu thay đổi" }));
    await waitFor(() => expect(writes(calls)).toHaveLength(1));
    expect(writes(calls)[0]).toMatchObject({ method: "PATCH", path: "/tasks/t1/", idempotencyKey: null, body: { expected_version: 2, title: "Tên mới" } });
    expect(Object.keys(writes(calls)[0].body ?? {}).sort()).toEqual(["expected_version", "title"]);

    // Someone else edits: the server version moves on, so the next save is stale.
    const t1 = tasks.find((task) => task.id === "t1")!;
    t1.version += 5;
    t1.title = "Người khác sửa";
    await user.clear(screen.getByLabelText("Tiêu đề"));
    await user.type(screen.getByLabelText("Tiêu đề"), "Tên thứ hai");
    await user.click(screen.getByRole("button", { name: "Lưu thay đổi" }));
    expect(await screen.findByText(/Dữ liệu đã được cập nhật bởi thao tác khác/)).toBeInTheDocument();
    await waitFor(() => expect(screen.getByLabelText("Tiêu đề")).toHaveValue("Người khác sửa"));
  });

  it("limits a member to the text fields of their own task", async () => {
    const user = userEvent.setup();
    setup("/projects/project-1/board?issue=NEXUS-1", { tasks: freshTasks() }, memberTestSession);
    await user.click(await screen.findByText("Chỉnh sửa issue", {}, { timeout: 5000 }));
    await screen.findByLabelText("Tiêu đề");
    expect(screen.getByLabelText("Tiêu đề")).toHaveAttribute("readonly");
    expect(screen.getByLabelText("Tiêu chí nghiệm thu")).toHaveAttribute("readonly");
    expect(screen.queryByLabelText("Độ ưu tiên")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Epic")).not.toBeInTheDocument();
  });

  it("offers no edit form on a card the member does not own", async () => {
    setup("/projects/project-1/board?issue=NEXUS-2", { tasks: freshTasks() }, memberTestSession);
    await screen.findByLabelText("Trạng thái");
    expect(screen.queryByText("Chỉnh sửa issue")).not.toBeInTheDocument();
  });

  it("creates a subtask under the parent with an idempotency key", async () => {
    const user = userEvent.setup();
    const { calls } = setup("/projects/project-1/board?issue=NEXUS-1", { tasks: freshTasks() });
    await user.type(await screen.findByLabelText("Tiêu đề nhiệm vụ con", {}, { timeout: 5000 }), "Việc con mới");
    await user.click(within(screen.getByRole("form", { name: "Thêm nhiệm vụ con" })).getByRole("button", { name: "Thêm" }));
    await waitFor(() => expect(writes(calls)).toHaveLength(1));
    expect(writes(calls)[0]).toMatchObject({ method: "POST", path: "/tasks/t1/subtasks/", body: { title: "Việc con mới" } });
    expect(writes(calls)[0].idempotencyKey).toBeTruthy();
  });

  it("completes a subtask by moving it to the Done state at the end of that column", async () => {
    const user = userEvent.setup();
    const { calls } = setup("/projects/project-1/board?issue=NEXUS-1", { tasks: freshTasks() });
    await user.click(await screen.findByRole("checkbox", { name: /Việc con/ }, { timeout: 5000 }));
    await waitFor(() => expect(writes(calls)).toHaveLength(1));
    expect(writes(calls)[0]).toMatchObject({
      method: "PATCH",
      path: "/tasks/sub/transition/",
      body: { expected_version: 1, target_state_id: "state-done", previous_task_id: null, next_task_id: null },
    });
  });
});
