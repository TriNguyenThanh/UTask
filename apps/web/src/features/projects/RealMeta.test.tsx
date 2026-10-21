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
  buildLabel,
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
  const full = {
    projects: [buildProject({ id: "project-1" })],
    members: {
      "project-1": [
        buildProjectMember({ user_id: LEADER_ID, role: "LEADER", display_name: "Nguyễn Hoàng Nam" }),
        buildProjectMember({ id: "pm-2", user_id: MEMBER_ID, role: "MEMBER", display_name: "Đặng Thảo Linh" }),
      ],
    },
    states: buildDefaultStates(),
    userNames: { [LEADER_ID]: "Nguyễn Hoàng Nam", [MEMBER_ID]: "Đặng Thảo Linh" },
    epics: [buildEpic({ id: "e1", name: "Xác thực", lead_user_id: MEMBER_ID })],
    labels: [buildLabel({ id: "l1", name: "frontend" })],
    sprints: [buildSprint({ id: "s1", name: "Sprint 1" })],
    sprintTasks: { s1: ["t1", "t2"] },
    tasks: [
      buildTask({ id: "t1", code: "NEXUS-1", title: "Thiết kế đăng nhập", state_id: "state-todo", version: 2, assignee_ids: [MEMBER_ID] }),
      buildTask({ id: "t2", code: "NEXUS-2", title: "API đăng nhập", state_id: "state-doing", sort_order: 2000 }),
    ],
    ...fixture,
    calls,
  } satisfies Partial<WorkFixture> & { projects: unknown[] };
  server.use(
    ...workHandlers(full as WorkFixture),
    ...classroomHandlers({
      classes: [buildClass({ id: "class-1" })],
      courses: [buildCourse({ id: "course-1" })],
      groups: { "class-1": [buildGroup({ id: "group-1", class_section: "class-1" })] },
    }),
    ...createAuthHandlers("default", createMemoryRepository("default")),
  );
  return { calls, fixture: full, ...renderAppRoutes(path, session) };
}

const writes = (calls: WorkCall[]) => calls.filter((call) => call.method !== "GET");

describe("Epics on the Backlog", () => {
  it("blocks a target date before the start date on the client, then creates the epic", async () => {
    const user = userEvent.setup();
    const { calls } = setup("/projects/project-1/backlog", {});
    await user.click(await screen.findByRole("button", { name: "Tạo Epic" }, { timeout: 5000 }));
    const dialog = await screen.findByRole("dialog");
    await user.type(within(dialog).getByLabelText("Tên epic"), "Thanh toán");
    await user.type(within(dialog).getByLabelText("Ngày bắt đầu"), "2026-09-10");
    await user.type(within(dialog).getByLabelText("Ngày mục tiêu"), "2026-09-01");
    await user.click(within(dialog).getByRole("button", { name: "Tạo Epic" }));
    expect(await within(dialog).findByText("Ngày mục tiêu không được trước ngày bắt đầu.")).toBeInTheDocument();
    expect(writes(calls)).toHaveLength(0);

    await user.clear(within(dialog).getByLabelText("Ngày mục tiêu"));
    await user.type(within(dialog).getByLabelText("Ngày mục tiêu"), "2026-09-30");
    await user.click(within(dialog).getByRole("button", { name: "Tạo Epic" }));
    await waitFor(() => expect(writes(calls)).toHaveLength(1));
    expect(writes(calls)[0]).toMatchObject({
      method: "POST",
      path: "/projects/project-1/epics/",
      idempotencyKey: null,
      body: { name: "Thanh toán", status: "PLANNED", start_date: "2026-09-10", target_date: "2026-09-30" },
    });
    expect(await screen.findByRole("button", { name: /^Thanh toán/ })).toBeInTheDocument();
  });

  it("lets the epic's lead edit name, description and status but not lead or dates", async () => {
    const user = userEvent.setup();
    const { calls } = setup("/projects/project-1/backlog", {}, memberTestSession);
    expect(screen.queryByRole("button", { name: "Tạo Epic" })).not.toBeInTheDocument();
    await user.click(await screen.findByRole("button", { name: "Sửa epic Xác thực" }, { timeout: 5000 }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByLabelText("Người phụ trách")).toBeDisabled();
    expect(within(dialog).getByLabelText("Ngày bắt đầu")).toBeDisabled();
    expect(within(dialog).queryByRole("button", { name: "Xóa epic" })).not.toBeInTheDocument();
    await user.clear(within(dialog).getByLabelText("Tên epic"));
    await user.type(within(dialog).getByLabelText("Tên epic"), "Đăng nhập");
    await user.click(within(dialog).getByRole("button", { name: "Lưu" }));
    await waitFor(() => expect(writes(calls)).toHaveLength(1));
    expect(writes(calls)[0]).toMatchObject({ method: "PATCH", path: "/projects/project-1/epics/e1/", body: { name: "Đăng nhập" } });
  });

  it("hides epic edit controls from a member who does not lead the epic", async () => {
    setup("/projects/project-1/backlog", { epics: [buildEpic({ id: "e1", name: "Xác thực", lead_user_id: LEADER_ID })] }, memberTestSession);
    await screen.findByRole("button", { name: /Xác thực/ }, { timeout: 5000 });
    await waitFor(() => expect(screen.queryByRole("button", { name: "Sửa epic Xác thực" })).not.toBeInTheDocument());
  });

  it("deletes an epic only after confirmation", async () => {
    const user = userEvent.setup();
    const { calls } = setup("/projects/project-1/backlog", {});
    await user.click(await screen.findByRole("button", { name: "Sửa epic Xác thực" }, { timeout: 5000 }));
    await user.click(await screen.findByRole("button", { name: "Xóa epic" }));
    expect(writes(calls)).toHaveLength(0);
    const confirm = (await screen.findAllByRole("dialog")).at(-1) as HTMLElement;
    await user.click(within(confirm).getByRole("button", { name: "Xóa epic" }));
    await waitFor(() => expect(writes(calls)).toHaveLength(1));
    expect(writes(calls)[0]).toMatchObject({ method: "DELETE", path: "/projects/project-1/epics/e1/" });
  });
});

describe("Labels", () => {
  it("creates a label and removes it from issues when deleted", async () => {
    const user = userEvent.setup();
    const { calls, fixture } = setup("/projects/project-1/backlog", {});
    fixture.tasks[0].label_ids = ["l1"];
    await user.click(await screen.findByRole("button", { name: "Quản lý nhãn" }, { timeout: 5000 }));
    const dialog = await screen.findByRole("dialog");
    await user.type(within(dialog).getByLabelText("Tên nhãn"), "backend");
    await user.click(within(dialog).getByRole("button", { name: "Thêm" }));
    await waitFor(() => expect(writes(calls)).toHaveLength(1));
    expect(writes(calls)[0]).toMatchObject({ method: "POST", path: "/projects/project-1/labels/", body: { name: "backend", color: "#2563eb" } });

    await user.click(await within(dialog).findByRole("button", { name: "Xóa nhãn frontend" }));
    const confirm = (await screen.findAllByRole("dialog")).at(-1) as HTMLElement;
    await user.click(within(confirm).getByRole("button", { name: "Xóa nhãn" }));
    await waitFor(() => expect(writes(calls)).toHaveLength(2));
    expect(fixture.tasks[0].label_ids).toEqual([]);
  });
});

describe("Issue panel: labels, relations, lifecycle", () => {
  async function openEditor(user: ReturnType<typeof userEvent.setup>) {
    await user.click(await screen.findByText("Chỉnh sửa issue", {}, { timeout: 5000 }));
    await screen.findByRole("form", { name: "Thêm liên kết" });
  }

  it("adds a label with the task's current version", async () => {
    const user = userEvent.setup();
    const { calls } = setup("/projects/project-1/board?issue=NEXUS-1", {});
    await openEditor(user);
    await user.click(await screen.findByRole("checkbox", { name: /frontend/ }));
    await waitFor(() => expect(writes(calls)).toHaveLength(1));
    expect(writes(calls)[0]).toMatchObject({
      path: "/tasks/t1/labels/",
      idempotencyKey: null,
      body: { expected_version: 2, action: "ADD", label_ids: ["l1"] },
    });
  });

  it("links issues and explains a blocking cycle", async () => {
    const user = userEvent.setup();
    const { calls } = setup("/projects/project-1/board?issue=NEXUS-1", {});
    await openEditor(user);
    const form = screen.getByRole("form", { name: "Thêm liên kết" });
    await user.selectOptions(within(form).getByLabelText("Issue đích"), "t2");
    await user.click(within(form).getByRole("button", { name: "Thêm" }));
    expect(await screen.findByLabelText("Gỡ liên kết với NEXUS-2")).toBeInTheDocument();
    expect(writes(calls)[0]).toMatchObject({ path: "/tasks/t1/relations/", body: { related_task_id: "t2", relation_type: "BLOCKS" } });

    await user.selectOptions(within(form).getByLabelText("Loại liên kết"), "BLOCKED_BY");
    await user.selectOptions(within(form).getByLabelText("Issue đích"), "t2");
    await user.click(within(form).getByRole("button", { name: "Thêm" }));
    expect(await screen.findByText("Liên kết này tạo vòng chặn.")).toBeInTheDocument();
    expect(screen.getAllByLabelText(/Gỡ liên kết với/)).toHaveLength(1);
  });

  it("archives an issue after confirmation, and closes the panel", async () => {
    const user = userEvent.setup();
    const { calls } = setup("/projects/project-1/board?issue=NEXUS-1", {});
    await openEditor(user);
    await user.click(screen.getByRole("button", { name: "Lưu trữ" }));
    expect(writes(calls)).toHaveLength(0);
    const confirm = (await screen.findAllByRole("dialog")).at(-1) as HTMLElement;
    await user.click(within(confirm).getByRole("button", { name: "Lưu trữ" }));
    await waitFor(() => expect(writes(calls)).toHaveLength(1));
    expect(writes(calls)[0]).toMatchObject({ method: "POST", path: "/tasks/t1/archive/", body: { expected_version: 2 } });
    await waitFor(() => expect(screen.queryByText("Chỉnh sửa issue")).not.toBeInTheDocument());
  });

  it("shows a member labels and links on their own issue but no archive or delete", async () => {
    const user = userEvent.setup();
    setup("/projects/project-1/board?issue=NEXUS-1", {}, memberTestSession);
    await openEditor(user);
    expect(screen.getByRole("checkbox", { name: /frontend/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Lưu trữ" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Xóa" })).not.toBeInTheDocument();
  });
});

describe("Archived and deleted issues on the Backlog", () => {
  const hidden = () => [
    buildTask({ id: "old", code: "NEXUS-8", title: "Việc cũ", archived_at: "2026-09-01T00:00:00Z", version: 4 }),
    buildTask({ id: "gone", code: "NEXUS-9", title: "Việc đã xóa", deleted_at: "2026-09-01T00:00:00Z", version: 6 }),
  ];

  it("lists archived issues and reopens one", async () => {
    const user = userEvent.setup();
    const { calls } = setup("/projects/project-1/backlog", { tasks: [buildTask({ id: "t1" }), ...hidden()] });
    await user.click(await screen.findByRole("button", { name: "Đã lưu trữ" }, { timeout: 5000 }));
    expect(await screen.findByText("Việc cũ")).toBeInTheDocument();
    expect(screen.queryByText("Việc đã xóa")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Mở lại" }));
    await waitFor(() => expect(writes(calls)).toHaveLength(1));
    expect(writes(calls)[0]).toMatchObject({ path: "/tasks/old/unarchive/", body: { expected_version: 4 } });
  });

  it("restores a deleted issue, and shows the server's reason when the parent is still deleted", async () => {
    const user = userEvent.setup();
    const { calls } = setup("/projects/project-1/backlog", {
      tasks: [
        buildTask({ id: "t1" }),
        buildTask({ id: "parent", code: "NEXUS-7", title: "Cha", deleted_at: "2026-09-01T00:00:00Z" }),
        buildTask({ id: "child", code: "NEXUS-8", title: "Con", type: "SUBTASK", parent_id: "parent", deleted_at: "2026-09-01T00:00:00Z" }),
      ],
    });
    await user.click(await screen.findByRole("button", { name: "Đã xóa" }, { timeout: 5000 }));
    await screen.findByText("Con");
    const row = screen.getByText("Con").closest("li") as HTMLElement;
    await user.click(within(row).getByRole("button", { name: "Khôi phục" }));
    expect(await screen.findByText("Công việc cha đang bị xóa, hãy khôi phục công việc cha trước.")).toBeInTheDocument();
    expect(writes(calls)).toHaveLength(1);
  });

  it("offers no restore button to a member", async () => {
    const user = userEvent.setup();
    setup("/projects/project-1/backlog", { tasks: [buildTask({ id: "t1" }), ...hidden()] }, memberTestSession);
    await user.click(await screen.findByRole("button", { name: "Đã lưu trữ" }, { timeout: 5000 }));
    await screen.findByText("Việc cũ");
    expect(screen.queryByRole("button", { name: "Mở lại" })).not.toBeInTheDocument();
  });
});
