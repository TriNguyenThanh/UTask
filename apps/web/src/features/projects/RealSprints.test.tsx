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
  buildDashboard,
  buildDefaultStates,
  buildProgress,
  buildProject,
  buildProjectMember,
  buildSprint,
  buildTask,
  workHandlers,
  type WorkCall,
  type WorkFixture,
} from "@/test/workHandlers";

const FIND = { timeout: 5000 };

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
        buildProjectMember({ user_id: LEADER_ID, role: "LEADER", display_name: "Nguyễn Hoàng Nam", weekly_capacity: 20 }),
        buildProjectMember({ id: "pm-2", user_id: MEMBER_ID, role: "MEMBER", display_name: "Đặng Thảo Linh", weekly_capacity: 10 }),
      ],
    },
    states: buildDefaultStates(),
    userNames: { [LEADER_ID]: "Nguyễn Hoàng Nam", [MEMBER_ID]: "Đặng Thảo Linh" },
    epics: [],
    labels: [],
    sprints: [
      buildSprint({ id: "s1", name: "Sprint 1", goal: "Đăng nhập" }),
      buildSprint({ id: "s2", name: "Sprint 2", status: "DRAFT", started_at: null, sort_order: 2 }),
    ],
    sprintTasks: { s1: ["t1", "t2"] },
    tasks: [
      buildTask({ id: "t1", code: "NEXUS-1", title: "Thiết kế đăng nhập", state_id: "state-todo" }),
      buildTask({ id: "t2", code: "NEXUS-2", title: "API đăng nhập", state_id: "state-doing", sort_order: 2000 }),
      buildTask({ id: "t3", code: "NEXUS-3", title: "Việc ngoài sprint", state_id: "state-todo", sort_order: 3000 }),
    ],
    progress: { s1: buildProgress({ completion_percent: 25, blocked_task_count: 3 }, "s1") },
    burndown: {
      s1: {
        sprint_id: "s1",
        formula_version: "v1",
        captured_at: "2026-09-05T00:00:00Z",
        snapshot_version: null,
        days: [
          { date: "2026-09-01", observed_at: "2026-09-01T00:00:00Z", scope_work_item_count: 2, remaining_work_item_count: 2, remaining_estimate_points: 8, unestimated_remaining_count: 0 },
          { date: "2026-09-02", observed_at: "2026-09-02T00:00:00Z", scope_work_item_count: 2, remaining_work_item_count: 1, remaining_estimate_points: 5, unestimated_remaining_count: 0 },
        ],
        window_truncated: false,
      },
    },
    dashboard: buildDashboard({
      totals: { ...buildProgress().totals, dependency_blocked_task_count: 2 },
      assignee_distribution: [
        { user_id: MEMBER_ID, status: "ACTIVE", weekly_capacity: 10, assigned_work_item_count: 3, unestimated_work_item_count: 1, allocated_estimate_points: 9 },
      ],
    }),
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

function actionOf(call: WorkCall): unknown {
  const { body } = call;
  return body && typeof body === "object" && "action" in body ? body.action : undefined;
}
const BACKLOG = "/projects/project-1/backlog";

function sectionOf(name: string) {
  const section = screen.getByRole("heading", { name }).closest("section");
  if (!section) throw new Error(`Không thấy phần ${name}`);
  return section;
}

describe("Sprint management on the Backlog", () => {
  it("creates a sprint after blocking an end date before the start date on the client", async () => {
    const user = userEvent.setup();
    const { calls } = setup(BACKLOG, {});
    await user.click(await screen.findByRole("button", { name: "Tạo Sprint" }, FIND));
    const dialog = await screen.findByRole("dialog");
    await user.type(within(dialog).getByLabelText("Tên sprint"), "Sprint 3");
    await user.type(within(dialog).getByLabelText("Ngày bắt đầu"), "2026-10-10");
    await user.type(within(dialog).getByLabelText("Ngày kết thúc"), "2026-10-01");
    await user.click(within(dialog).getByRole("button", { name: "Tạo sprint" }));
    expect(await within(dialog).findByText("Ngày kết thúc không được trước ngày bắt đầu.")).toBeInTheDocument();
    expect(writes(calls)).toHaveLength(0);

    await user.clear(within(dialog).getByLabelText("Ngày kết thúc"));
    await user.type(within(dialog).getByLabelText("Ngày kết thúc"), "2026-10-24");
    await user.click(within(dialog).getByRole("button", { name: "Tạo sprint" }));
    await waitFor(() => expect(writes(calls)).toHaveLength(1));
    expect(writes(calls)[0]).toMatchObject({
      method: "POST",
      path: "/projects/project-1/sprints/",
      idempotencyKey: null,
      body: { name: "Sprint 3", start_date: "2026-10-10", end_date: "2026-10-24" },
    });
    expect(await screen.findByRole("heading", { name: "Sprint 3" })).toBeInTheDocument();
  });

  it("edits a sprint with the version read just before sending", async () => {
    const user = userEvent.setup();
    const { calls } = setup(BACKLOG, { sprints: [buildSprint({ id: "s1", name: "Sprint 1", version: 4 })] });
    await user.click(await screen.findByRole("button", { name: "Sửa Sprint 1" }, FIND));
    const dialog = await screen.findByRole("dialog");
    await user.clear(within(dialog).getByLabelText("Mục tiêu"));
    await user.type(within(dialog).getByLabelText("Mục tiêu"), "Mục tiêu mới");
    await user.click(within(dialog).getByRole("button", { name: "Lưu" }));
    await waitFor(() => expect(writes(calls)).toHaveLength(1));
    expect(writes(calls)[0]).toMatchObject({ method: "PATCH", path: "/sprints/s1/", body: { expected_version: 4, goal: "Mục tiêu mới" } });
  });

  it("starts a draft sprint after confirming, and shows the server's message when another sprint is running", async () => {
    const user = userEvent.setup();
    const { calls } = setup(BACKLOG, {
      sprints: [buildSprint({ id: "s2", name: "Sprint 2", status: "DRAFT", started_at: null })],
      sprintTasks: {},
    });
    await user.click(await screen.findByRole("button", { name: "Bắt đầu Sprint" }, FIND));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Bắt đầu" }));
    await waitFor(() => expect(writes(calls)).toHaveLength(1));
    expect(writes(calls)[0]).toMatchObject({ method: "POST", path: "/projects/project-1/sprints/s2/start/", body: { expected_version: 1 } });
    expect(writes(calls)[0].idempotencyKey).toEqual(expect.any(String));
  });

  it("explains why a draft without dates cannot start", async () => {
    setup(BACKLOG, {
      sprints: [buildSprint({ id: "s2", name: "Sprint 2", status: "DRAFT", started_at: null, start_date: null, end_date: null })],
      sprintTasks: {},
    });
    const start = await screen.findByRole("button", { name: "Bắt đầu Sprint" }, FIND);
    expect(start).toBeDisabled();
    expect(start).toHaveAttribute("title", expect.stringContaining("ngày"));
  });

  it("shows progress and burndown for the running sprint", async () => {
    setup(BACKLOG, {});
    const section = await screen.findByRole("heading", { name: "Sprint 1" }, FIND).then(() => sectionOf("Sprint 1"));
    const insights = await within(section).findByLabelText("Tiến độ sprint");
    expect(await within(insights).findByText("25%")).toBeInTheDocument();
    expect(within(insights).getByText("3")).toBeInTheDocument();
    expect(await within(insights).findByRole("img", { name: /Burndown/ })).toBeInTheDocument();
    // Sprint nháp không có số liệu.
    expect(within(sectionOf("Sprint 2")).queryByLabelText("Tiến độ sprint")).not.toBeInTheDocument();
  });

  it("closes the running sprint and sends unfinished issues to the chosen draft sprint", async () => {
    const user = userEvent.setup();
    const { calls, fixture } = setup(BACKLOG, {});
    await user.click(await screen.findByRole("button", { name: "Hoàn thành Sprint" }, FIND));
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent("2 issue chưa xong");
    await user.selectOptions(within(dialog).getByLabelText("Issue chưa xong"), "s2");
    await user.click(within(dialog).getByRole("button", { name: "Hoàn thành sprint" }));
    await waitFor(() => expect(writes(calls)).toHaveLength(1));
    expect(writes(calls)[0]).toMatchObject({ method: "POST", path: "/sprints/s1/close/", body: { expected_version: 1, target_sprint_id: "s2" } });
    expect(fixture.sprintTasks).toEqual({ s1: [], s2: ["t1", "t2"] });
  });

  it("hides every sprint control from a member", async () => {
    setup(BACKLOG, {}, memberTestSession);
    await screen.findByRole("heading", { name: "Sprint 1" }, FIND);
    expect(screen.queryByRole("button", { name: "Tạo Sprint" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Hoàn thành Sprint" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Bắt đầu Sprint" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Sửa Sprint 1" })).not.toBeInTheDocument();
  });
});

describe("Moving issues between sprints from the menu", () => {
  it("adds an issue to a draft sprint with an Idempotency-Key and no reason", async () => {
    const user = userEvent.setup();
    const { calls } = setup(BACKLOG, {});
    await user.click(await screen.findByRole("button", { name: "Thao tác cho NEXUS-3" }, FIND));
    await user.click(await screen.findByRole("menuitem", { name: /^Chuyển vào Sprint 2/ }));
    await waitFor(() => expect(writes(calls)).toHaveLength(1));
    expect(writes(calls)[0]).toMatchObject({ method: "POST", path: "/sprints/s2/tasks/", body: { action: "ADD", task_ids: ["t3"] } });
    expect(writes(calls)[0].body).not.toHaveProperty("scope_change_reason");
    expect(writes(calls)[0].idempotencyKey).toEqual(expect.any(String));
    await waitFor(() => expect(within(sectionOf("Sprint 2")).getByText("NEXUS-3")).toBeInTheDocument());
  });

  it("asks for a reason before touching the running sprint, then removes the task with that reason", async () => {
    const user = userEvent.setup();
    const { calls } = setup(BACKLOG, {});
    await user.click(await screen.findByRole("button", { name: "Thao tác cho NEXUS-1" }, FIND));
    await user.click(await screen.findByRole("menuitem", { name: "Chuyển về Product Backlog" }));
    const dialog = await screen.findByRole("dialog");
    expect(writes(calls)).toHaveLength(0);
    await user.type(within(dialog).getByLabelText("Lý do"), "Khách đổi ưu tiên");
    await user.click(within(dialog).getByRole("button", { name: "Xác nhận thay đổi" }));
    await waitFor(() => expect(writes(calls)).toHaveLength(1));
    expect(writes(calls)[0]).toMatchObject({
      method: "POST",
      path: "/sprints/s1/tasks/",
      body: { action: "REMOVE", task_ids: ["t1"], scope_change_reason: "Khách đổi ưu tiên" },
    });
  });

  it("moves an issue from one sprint to another with a REMOVE then an ADD", async () => {
    const user = userEvent.setup();
    const { calls } = setup(BACKLOG, {
      sprints: [buildSprint({ id: "s1", name: "Sprint 1", status: "DRAFT", started_at: null }), buildSprint({ id: "s2", name: "Sprint 2", status: "DRAFT", started_at: null, sort_order: 2 })],
    });
    await user.click(await screen.findByRole("button", { name: "Thao tác cho NEXUS-1" }, FIND));
    await user.click(await screen.findByRole("menuitem", { name: /^Chuyển vào Sprint 2/ }));
    await waitFor(() => expect(writes(calls)).toHaveLength(2));
    expect(writes(calls).map((call) => [call.path, actionOf(call)])).toEqual([
      ["/sprints/s1/tasks/", "REMOVE"],
      ["/sprints/s2/tasks/", "ADD"],
    ]);
  });

  it("puts the issue back and reports the server's message when the add is refused", async () => {
    const user = userEvent.setup();
    const { calls } = setup(BACKLOG, { writeError: { status: 400, code: "INVALID_OPERATION", message: "Công việc phải thuộc cùng dự án và có quyền chỉnh sửa." } });
    await user.click(await screen.findByRole("button", { name: "Thao tác cho NEXUS-3" }, FIND));
    await user.click(await screen.findByRole("menuitem", { name: /^Chuyển vào Sprint 2/ }));
    expect(await screen.findByText("Công việc phải thuộc cùng dự án và có quyền chỉnh sửa.")).toBeInTheDocument();
    expect(writes(calls).length).toBeGreaterThan(0);
    await waitFor(() => expect(within(sectionOf("Product Backlog")).getByText("NEXUS-3")).toBeInTheDocument());
  });
});

describe("Dashboard and capacity on the Info page", () => {
  const INFO = "/projects/project-1/info";

  it("shows the dashboard totals and each assignee's workload", async () => {
    setup(INFO, {});
    const section = await screen.findByLabelText("Bảng điều khiển dự án", undefined, FIND);
    expect(await within(section).findByText("Bị chặn do phụ thuộc")).toBeInTheDocument();
    const row = (await within(section).findByText("Đặng Thảo Linh")).closest("tr")!;
    expect(within(row).getByText("9")).toBeInTheDocument();
  });

  it("lets the leader change weekly capacity and sends only a valid, changed value", async () => {
    const user = userEvent.setup();
    const { calls } = setup(INFO, {});
    const input = await screen.findByLabelText("Giờ/tuần của Đặng Thảo Linh", undefined, FIND);
    expect(screen.queryByRole("button", { name: "Lưu" })).not.toBeInTheDocument();
    await user.clear(input);
    await user.type(input, "-3");
    expect(screen.getByText("Nhập số nguyên ≥ 0")).toBeInTheDocument();
    await user.clear(input);
    await user.type(input, "16");
    await user.click(screen.getByRole("button", { name: "Lưu" }));
    await waitFor(() => expect(writes(calls)).toHaveLength(1));
    expect(writes(calls)[0]).toMatchObject({
      method: "PATCH",
      path: `/projects/project-1/members/${MEMBER_ID}/capacity/`,
      idempotencyKey: null,
      body: { weekly_capacity: 16 },
    });
  });

  it("shows capacity as plain text to a member", async () => {
    setup(INFO, {}, memberTestSession);
    await screen.findByLabelText("Bảng điều khiển dự án", undefined, FIND);
    await screen.findByText("Đặng Thảo Linh", { selector: "td" });
    expect(screen.queryByLabelText(/^Giờ\/tuần của/)).not.toBeInTheDocument();
  });
});
