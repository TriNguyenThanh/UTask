import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { describe, expect, it, vi } from "vitest";

import { LEADER_ID, MEMBER_ID } from "@/mocks/data/database";
import { createMemoryRepository } from "@/mocks/data/storage";
import { createAuthHandlers } from "@/mocks/handlers/auth";
import { server } from "@/mocks/server";
import { aiHandlers, buildAiBacklogItem, buildAiSubtask, type AiCall, type AiFixture } from "@/test/aiHandlers";
import { buildClass, buildCourse, buildGroup, classroomHandlers, envelopeError } from "@/test/classroomHandlers";
import { leaderTestSession, memberTestSession, renderAppRoutes, teacherTestSession } from "@/test/render";
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

const TWO_SUBTASKS: AiFixture = {
  decomposition: {
    warnings: ["Mô tả còn ngắn"],
    subtasks: [
      buildAiSubtask({ title: "Thiết kế màn hình", estimate_points: 2.6 }),
      buildAiSubtask({ title: "Viết API", estimate_points: 3 }),
    ],
  },
};

function setup(
  fixture: Partial<WorkFixture>,
  ai: AiFixture,
  session: typeof leaderTestSession | typeof memberTestSession | typeof teacherTestSession = leaderTestSession,
  path = "/projects/project-1/board?issue=NEXUS-1",
) {
  vi.stubEnv("VITE_REAL_SERVICES", "auth,classroom,work,ai");
  const calls: WorkCall[] = [];
  const aiCalls: AiCall[] = [];
  server.use(
    ...aiHandlers({ ...ai, calls: aiCalls }),
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
      sprintTasks: { s1: ["t1"] },
      tasks: [
        buildTask({
          id: "t1",
          code: "NEXUS-1",
          title: "Thiết kế đăng nhập",
          state_id: "state-todo",
          version: 2,
          assignee_ids: [MEMBER_ID],
        }),
      ],
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
  return { calls, aiCalls, ...renderAppRoutes(path, session) };
}

const writes = (calls: WorkCall[]) => calls.filter((call) => call.method !== "GET");
const OPEN = "AI tách nhiệm vụ con";

async function openAndGenerate(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole("button", { name: OPEN }, { timeout: 5000 }));
  await user.click(await screen.findByRole("button", { name: "Tạo gợi ý" }));
}

describe("AI task decomposition", () => {
  it("lets a leader pick and rename suggestions, then creates only the chosen subtask with points", async () => {
    const user = userEvent.setup();
    const { calls, aiCalls } = setup({}, TWO_SUBTASKS);
    await openAndGenerate(user);

    expect(await screen.findByDisplayValue("Thiết kế màn hình")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Viết API")).toBeInTheDocument();
    expect(screen.getByText("Mô tả còn ngắn")).toBeInTheDocument();
    expect(aiCalls[0]).toMatchObject({
      method: "POST",
      idempotencyKey: expect.any(String),
      body: { intent: "task_decomposition", target: { type: "task", id: "t1" } },
    });

    await user.click(screen.getByRole("checkbox", { name: "Chọn đề xuất 2" }));
    const title = screen.getByRole("textbox", { name: "Tiêu đề đề xuất 1" });
    await user.clear(title);
    await user.type(title, "X");
    await user.click(screen.getByRole("button", { name: "Tạo 1 nhiệm vụ con" }));

    await waitFor(() => expect(writes(calls)).toHaveLength(1));
    expect(writes(calls)[0]).toMatchObject({
      method: "POST",
      path: "/tasks/t1/subtasks/",
      body: { title: "X", story_points: 3 },
    });
    expect(writes(calls)[0].idempotencyKey).toBeTruthy();
    expect(await screen.findByText("Đã tạo 1 nhiệm vụ con.")).toBeInTheDocument();
  });

  it("sends no story points for an assignee who is not the leader", async () => {
    const user = userEvent.setup();
    const { calls } = setup({}, TWO_SUBTASKS, memberTestSession);
    await openAndGenerate(user);
    expect(await screen.findByText("Nhiệm vụ con sẽ được giao cho bạn; điểm ước lượng do Leader đặt.")).toBeInTheDocument();
    await user.click(await screen.findByRole("button", { name: "Tạo 2 nhiệm vụ con" }));

    await waitFor(() => expect(writes(calls)).toHaveLength(2));
    for (const call of writes(calls)) {
      expect(call.body).not.toHaveProperty("story_points");
      expect(call.body).toHaveProperty("title");
    }
  });

  it("does not offer the button to a teacher or on an archived project", async () => {
    setup({}, TWO_SUBTASKS, teacherTestSession);
    await screen.findByLabelText("Trạng thái", {}, { timeout: 5000 });
    expect(screen.queryByRole("button", { name: OPEN })).not.toBeInTheDocument();
  });

  it("does not offer the button when the project is archived", async () => {
    setup({ projects: [buildProject({ id: "project-1", archived_at: "2026-10-01T00:00:00Z" })] }, TWO_SUBTASKS);
    await screen.findByLabelText("Trạng thái", {}, { timeout: 5000 });
    expect(screen.queryByRole("button", { name: OPEN })).not.toBeInTheDocument();
  });

  it("polls an asynchronous request until the suggestions arrive", async () => {
    const user = userEvent.setup();
    // Một lần chờ thật (2 giây); nhánh `running` và giãn khoảng chờ được kiểm ở endpoints.test.ts.
    const { aiCalls } = setup({}, { ...TWO_SUBTASKS, mode: "async", pendingPolls: 0 });
    await openAndGenerate(user);

    expect(await screen.findByDisplayValue("Viết API", {}, { timeout: 8000 })).toBeInTheDocument();
    expect(aiCalls.map((call) => call.method)).toEqual(["POST", "GET"]);
  });

  it("shows how long to wait when the AI rate limits the request", async () => {
    const user = userEvent.setup();
    setup({}, { failWith: { status: 429, code: "RATE_LIMITED", message: "x", retryAfter: "7" } });
    await openAndGenerate(user);

    expect(await screen.findByText("Bạn đã gửi quá nhiều yêu cầu AI. Thử lại sau 7 giây.")).toBeInTheDocument();
  });

  it("says so when the AI suggests nothing", async () => {
    const user = userEvent.setup();
    setup({}, { decomposition: { subtasks: [], warnings: [] } });
    await openAndGenerate(user);

    expect(await screen.findByText("AI không đề xuất nhiệm vụ con nào.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Tạo 0 nhiệm vụ con" })).toBeDisabled();
  });

  it("keeps what was created when a later item fails and retries only the rest with the same key", async () => {
    const user = userEvent.setup();
    const posts: { key: string | null; title: unknown }[] = [];
    const { calls } = setup({}, TWO_SUBTASKS);
    let attempt = 0;
    server.use(
      http.post("/api/work/tasks/:taskId/subtasks/", async ({ request }) => {
        const body = (await request.clone().json()) as { title: string };
        posts.push({ key: request.headers.get("Idempotency-Key"), title: body.title });
        attempt += 1;
        if (attempt === 2) return envelopeError(500, "INTERNAL_ERROR", "Lỗi máy chủ");
        return undefined;
      }),
    );
    await openAndGenerate(user);
    await user.click(await screen.findByRole("button", { name: "Tạo 2 nhiệm vụ con" }));

    expect(await screen.findByText(/Đã tạo 1\/2\. Lỗi:/)).toBeInTheDocument();
    const failedKey = posts[1].key;
    expect(failedKey).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "Thử lại phần còn lại" }));
    await waitFor(() => expect(posts).toHaveLength(3));
    expect(posts[2]).toEqual({ key: failedKey, title: "Viết API" });
    expect(writes(calls).filter((call) => call.path === "/tasks/t1/subtasks/")).toHaveLength(2);
  });
});

const BACKLOG = "/projects/project-1/backlog";

const BACKLOG_ITEMS: AiFixture = {
  backlog: {
    warnings: [],
    items: [
      buildAiBacklogItem({ title: "Thiết lập CI", priority: "critical", estimate_points: 2.6 }),
      buildAiBacklogItem({ title: "Trang đăng nhập", priority: "medium", estimate_points: 3 }),
    ],
  },
};

async function openBacklogDialog(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole("button", { name: "AI gợi ý backlog" }, { timeout: 5000 }));
}

describe("AI backlog generation", () => {
  it("prefills the description from the project and creates the chosen issues with mapped priority", async () => {
    const user = userEvent.setup();
    const { calls, aiCalls } = setup(
      { projects: [buildProject({ id: "project-1", description: "Mô tả A", target_goals: "Mục tiêu 1\nMục tiêu 2" })] },
      BACKLOG_ITEMS,
      leaderTestSession,
      BACKLOG,
    );
    await openBacklogDialog(user);
    expect(await screen.findByLabelText("Mô tả dự án")).toHaveValue("Mô tả A");
    await user.click(screen.getByRole("button", { name: "Tạo gợi ý" }));

    expect(await screen.findByDisplayValue("Thiết lập CI")).toBeInTheDocument();
    expect(aiCalls[0].body).toMatchObject({
      intent: "backlog_generation",
      target: { type: "project", id: "project-1" },
      input: { description: "Mô tả A", goals: ["Mục tiêu 1", "Mục tiêu 2"], deadline: "2026-12-31T23:59:59+07:00" },
    });

    await user.click(screen.getByRole("button", { name: "Tạo 2 issue" }));

    await waitFor(() => expect(writes(calls).filter((call) => call.path === "/projects/project-1/tasks/")).toHaveLength(2));
    const created = writes(calls).filter((call) => call.path === "/projects/project-1/tasks/");
    expect(created[0]).toMatchObject({ body: { title: "Thiết lập CI", type: "TASK", priority: "URGENT", story_points: 3 } });
    expect(created[1]).toMatchObject({ body: { title: "Trang đăng nhập", priority: "MEDIUM" } });
    expect(created[0].idempotencyKey).not.toBe(created[1].idempotencyKey);
    expect(await screen.findByText("Đã tạo 2 issue trong Product Backlog.")).toBeInTheDocument();
  });

  it("does not offer the button to a member", async () => {
    setup({}, BACKLOG_ITEMS, memberTestSession, BACKLOG);
    await screen.findByText("Product Backlog", {}, { timeout: 5000 });
    expect(screen.queryByRole("button", { name: "AI gợi ý backlog" })).not.toBeInTheDocument();
  });

  it("blocks a goals list over 30 lines and sends nothing", async () => {
    const user = userEvent.setup();
    const { aiCalls } = setup({}, BACKLOG_ITEMS, leaderTestSession, BACKLOG);
    await openBacklogDialog(user);
    const goals = await screen.findByLabelText("Mục tiêu (mỗi dòng một mục)");
    await user.clear(goals);
    await user.click(goals);
    await user.paste(Array.from({ length: 31 }, (_, i) => `mục ${i}`).join("\n"));

    expect(await screen.findByText("Tối đa 30 mục.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Tạo gợi ý" })).toBeDisabled();
    expect(aiCalls).toHaveLength(0);
  });

  it("will not generate without a description", async () => {
    const user = userEvent.setup();
    setup({}, BACKLOG_ITEMS, leaderTestSession, BACKLOG);
    await openBacklogDialog(user);
    await user.clear(await screen.findByLabelText("Mô tả dự án"));

    expect(screen.getByText("Nhập mô tả dự án.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Tạo gợi ý" })).toBeDisabled();
  });
});
