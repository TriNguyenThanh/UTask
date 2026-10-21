import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { RealActivity, RealAttachments, RealComments, type CollabActor } from "@/features/projects/components/RealCollab";
import { LEADER_ID, MEMBER_ID } from "@/mocks/data/database";
import { createMemoryRepository } from "@/mocks/data/storage";
import { createAuthHandlers } from "@/mocks/handlers/auth";
import { server } from "@/mocks/server";
import { buildClass, buildCourse, buildGroup, classroomHandlers } from "@/test/classroomHandlers";
import { leaderTestSession, memberTestSession, renderApp, renderAppRoutes } from "@/test/render";
import {
  buildActivity,
  buildAttachment,
  buildComment,
  buildDefaultStates,
  buildProject,
  buildProjectMember,
  buildSprint,
  buildTask,
  buildTaskGitHubLink,
  STORAGE_ORIGIN,
  workHandlers,
  type WorkCall,
  type WorkFixture,
} from "@/test/workHandlers";

const FIND = { timeout: 5000 };
const PEOPLE = [
  { userId: LEADER_ID, name: "Nguyễn Hoàng Nam" },
  { userId: MEMBER_ID, name: "Đặng Thảo Linh" },
];
const TASK = "task-1";

const asLeader: CollabActor = { userId: LEADER_ID, isLeader: true, canComment: true, canUpload: true };
const asMember: CollabActor = { userId: MEMBER_ID, isLeader: false, canComment: true, canUpload: true };

function serve(fixture: Partial<WorkFixture>) {
  vi.stubEnv("VITE_REAL_SERVICES", "auth,classroom,work");
  const calls: WorkCall[] = [];
  const full = {
    projects: [buildProject({ id: "project-1" })],
    states: buildDefaultStates(),
    actorId: LEADER_ID,
    ...fixture,
    calls,
  };
  server.use(
    ...workHandlers(full as WorkFixture),
    ...classroomHandlers({
      classes: [buildClass({ id: "class-1" })],
      courses: [buildCourse({ id: "course-1" })],
      groups: { "class-1": [buildGroup({ id: "group-1", class_section: "class-1" })] },
    }),
    ...createAuthHandlers("default", createMemoryRepository("default")),
  );
  return { calls, fixture: full };
}

const writes = (calls: WorkCall[]) => calls.filter((call) => call.method !== "GET");

function mountComments(actor: CollabActor, fixture: Partial<WorkFixture> = {}) {
  const served = serve({ actorId: actor.userId, actorIsLeader: actor.isLeader, ...fixture });
  renderApp(<RealComments target={{ taskId: TASK }} actor={actor} people={PEOPLE} />, {
    session: actor.userId === LEADER_ID ? leaderTestSession : memberTestSession,
  });
  return served;
}

afterEach(() => vi.unstubAllEnvs());

describe("RealComments", () => {
  it("lists comments oldest first with the server name, a placeholder for an unknown author and the teacher badge", async () => {
    mountComments(asLeader, {
      comments: [
        buildComment({ id: "late", created_at: "2026-09-03T08:00:00Z", content_stripped: "Làm tốt", user_id: "teacher-1", display_name: "TS. Trần Minh Đức", is_teacher_feedback: true }),
        buildComment({ id: "early", created_at: "2026-09-02T08:00:00Z", content_stripped: "Đã xem", user_id: "ghost", display_name: "", mentioned_user_ids: [MEMBER_ID] }),
      ],
    });
    const items = await screen.findAllByRole("listitem", undefined, FIND);
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent("Chưa rõ tên");
    expect(items[0]).toHaveTextContent("Đã xem");
    expect(items[0]).toHaveTextContent("@Đặng Thảo Linh");
    expect(items[1]).toHaveTextContent("TS. Trần Minh Đức");
    expect(items[1]).toHaveTextContent("Phản hồi giảng viên");
  });

  it("blocks a blank comment, then posts with the chosen mention and clears the box", async () => {
    const user = userEvent.setup();
    const { calls } = mountComments(asLeader);
    const box = await screen.findByLabelText("Viết bình luận", undefined, FIND);
    await user.click(screen.getByRole("button", { name: "Gửi bình luận" }));
    expect(await screen.findByText("Nhập nội dung bình luận.")).toBeInTheDocument();
    expect(writes(calls)).toHaveLength(0);

    await user.type(box, "Nhờ bạn xem giúp");
    await user.click(screen.getByRole("button", { name: "Nhắc Đặng Thảo Linh" }));
    await user.click(screen.getByRole("button", { name: "Gửi bình luận" }));
    await waitFor(() => expect(writes(calls)).toHaveLength(1));
    expect(writes(calls)[0]).toMatchObject({
      method: "POST",
      path: "/comments/",
      idempotencyKey: null,
      body: { task_id: TASK, content_html: "Nhờ bạn xem giúp", mentioned_user_ids: [MEMBER_ID] },
    });
    expect(await screen.findByText("Nhờ bạn xem giúp")).toBeInTheDocument();
    expect(screen.getByLabelText("Viết bình luận")).toHaveValue("");
  });

  it("does not offer yourself as a mention", async () => {
    mountComments(asLeader);
    await screen.findByLabelText("Viết bình luận", undefined, FIND);
    expect(screen.queryByRole("button", { name: "Nhắc Nguyễn Hoàng Nam" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Nhắc Đặng Thảo Linh" })).toBeInTheDocument();
  });

  it("keeps the text and shows the server's message when a mention is outside the project", async () => {
    const user = userEvent.setup();
    mountComments(asLeader, { invalidMentions: [MEMBER_ID] });
    await user.type(await screen.findByLabelText("Viết bình luận", undefined, FIND), "Xin chào");
    await user.click(screen.getByRole("button", { name: "Nhắc Đặng Thảo Linh" }));
    await user.click(screen.getByRole("button", { name: "Gửi bình luận" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Người nhận thông báo không thuộc phạm vi của dự án.");
    expect(screen.getByLabelText("Viết bình luận")).toHaveValue("Xin chào");
  });

  it("lets an author edit their own comment but not someone else's", async () => {
    const user = userEvent.setup();
    const { calls } = mountComments(asMember, {
      comments: [
        buildComment({ id: "mine", user_id: MEMBER_ID, content_stripped: "Bản cũ", created_at: "2026-09-02T08:00:00Z" }),
        buildComment({ id: "theirs", user_id: LEADER_ID, content_stripped: "Của trưởng nhóm", created_at: "2026-09-03T08:00:00Z" }),
      ],
    });
    await screen.findByText("Bản cũ", undefined, FIND);
    expect(screen.getAllByRole("button", { name: "Sửa bình luận" })).toHaveLength(1);
    expect(screen.getAllByRole("button", { name: "Xóa bình luận" })).toHaveLength(1);

    await user.click(screen.getByRole("button", { name: "Sửa bình luận" }));
    const box = screen.getByLabelText("Nội dung bình luận");
    await user.clear(box);
    await user.type(box, "Bản mới");
    await user.click(screen.getByRole("button", { name: "Lưu" }));
    await waitFor(() => expect(writes(calls)).toHaveLength(1));
    expect(writes(calls)[0]).toMatchObject({ method: "PATCH", path: "/comments/mine/", body: { content_html: "Bản mới" } });
    expect(await screen.findByText("Bản mới")).toBeInTheDocument();
  });

  it("lets the leader delete another member's comment after confirming", async () => {
    const user = userEvent.setup();
    const { calls } = mountComments(asLeader, { comments: [buildComment({ id: "theirs", user_id: MEMBER_ID, content_stripped: "Cần xóa" })] });
    await screen.findByText("Cần xóa", undefined, FIND);
    expect(screen.queryByRole("button", { name: "Sửa bình luận" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Xóa bình luận" }));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Xóa bình luận" }));
    await waitFor(() => expect(writes(calls)).toHaveLength(1));
    expect(writes(calls)[0]).toMatchObject({ method: "DELETE", path: "/comments/theirs/" });
    await waitFor(() => expect(screen.queryByText("Cần xóa")).not.toBeInTheDocument());
    expect(screen.getByText("Chưa có bình luận nào.")).toBeInTheDocument();
  });

  it("hides the composer and every action when commenting is not allowed", async () => {
    mountComments({ ...asLeader, canComment: false }, { comments: [buildComment({ user_id: LEADER_ID, content_stripped: "Chỉ xem" })] });
    await screen.findByText("Chỉ xem", undefined, FIND);
    expect(screen.queryByLabelText("Viết bình luận")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Sửa bình luận" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Xóa bình luận" })).not.toBeInTheDocument();
  });
});

describe("RealActivity", () => {
  it("shows who changed what, resolving the actor from the project's people", async () => {
    serve({ activities: { [TASK]: [buildActivity({ actor_user_id: MEMBER_ID })] } });
    renderApp(<RealActivity taskId={TASK} people={PEOPLE} />);
    const line = await screen.findByText("đã đổi độ ưu tiên: LOW → HIGH", undefined, FIND);
    expect(line.parentElement).toHaveTextContent("Đặng Thảo Linh");
  });

  it("says so when there is no history", async () => {
    serve({});
    renderApp(<RealActivity taskId={TASK} people={PEOPLE} />);
    expect(await screen.findByText("Chưa có hoạt động nào.", undefined, FIND)).toBeInTheDocument();
  });
});

describe("RealAttachments", () => {
  function mountAttachments(actor: CollabActor, fixture: Partial<WorkFixture> = {}) {
    const served = serve({ actorId: actor.userId, ...fixture });
    renderApp(<RealAttachments taskId={TASK} actor={actor} />);
    return served;
  }

  it("refuses an unsupported file before asking the server for anything", async () => {
    const user = userEvent.setup({ applyAccept: false });
    const { calls } = mountAttachments(asLeader);
    const input = await screen.findByLabelText("Chọn tệp đính kèm", undefined, FIND);
    await user.upload(input, new File(["x"], "virus.exe", { type: "application/x-msdownload" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Chỉ nhận");
    expect(calls.filter((call) => call.path.includes("presigned"))).toHaveLength(0);
  });

  it("uploads through presign, storage and confirm, then lists the file", async () => {
    const user = userEvent.setup();
    const { calls } = mountAttachments(asLeader);
    const input = await screen.findByLabelText("Chọn tệp đính kèm", undefined, FIND);
    await user.upload(input, new File([new Uint8Array(2048)], "thiet-ke.png", { type: "image/png" }));
    expect(await screen.findByText("thiet-ke.png", undefined, FIND)).toBeInTheDocument();
    expect(calls.map((call) => call.method)).toEqual(["POST", "PUT", "POST"]);
    expect(calls[0].body).toMatchObject({ file_name: "thiet-ke.png", file_size: 2048, content_type: "image/png" });
    expect(calls[2].idempotencyKey).toEqual(expect.any(String));
  });

  it.each([
    [{ storageUnavailable: true }, "Kho lưu trữ chưa sẵn sàng, hãy thử lại."],
    [{ presignExpired: true }, "Phiên tải lên đã hết hạn."],
    [{ storageStatus: 403 }, "Kho lưu trữ từ chối tệp."],
  ] satisfies [Partial<WorkFixture>, string][])("explains a failed upload (%o)", async (fixture, message) => {
    const user = userEvent.setup();
    mountAttachments(asLeader, fixture);
    const input = await screen.findByLabelText("Chọn tệp đính kèm", undefined, FIND);
    await user.upload(input, new File(["abc"], "ghi-chu.txt", { type: "text/plain" }));
    expect(await screen.findByRole("alert", undefined, FIND)).toHaveTextContent(message);
    expect(screen.queryByText("ghi-chu.txt")).not.toBeInTheDocument();
  });

  it("opens a fresh download link in a new tab", async () => {
    const user = userEvent.setup();
    const open = vi.spyOn(window, "open").mockReturnValue(null);
    mountAttachments(asLeader, { attachments: [buildAttachment({ id: "att-1", file_name: "bao-cao.pdf", content_type: "application/pdf" })] });
    await user.click(await screen.findByRole("button", { name: "Tải bao-cao.pdf" }, FIND));
    await waitFor(() => expect(open).toHaveBeenCalledWith(`${STORAGE_ORIGIN}/download/att-1`, "_blank", "noopener,noreferrer"));
    open.mockRestore();
  });

  it("deletes after confirming", async () => {
    const user = userEvent.setup();
    const { calls } = mountAttachments(asLeader, { attachments: [buildAttachment({ id: "att-1", file_name: "bao-cao.pdf" })] });
    await user.click(await screen.findByRole("button", { name: "Xóa bao-cao.pdf" }, FIND));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Xóa tệp" }));
    await waitFor(() => expect(writes(calls)).toHaveLength(1));
    expect(writes(calls)[0]).toMatchObject({ method: "DELETE", path: "/tasks/task-1/attachments/att-1/" });
    await waitFor(() => expect(screen.queryByText("bao-cao.pdf")).not.toBeInTheDocument());
  });

  it("is read-only for someone who cannot upload", async () => {
    mountAttachments({ ...asLeader, canUpload: false }, { attachments: [buildAttachment({ file_name: "bao-cao.pdf" })] });
    await screen.findByText("bao-cao.pdf", undefined, FIND);
    expect(screen.queryByLabelText("Chọn tệp đính kèm")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Xóa bao-cao.pdf" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Tải bao-cao.pdf" })).toBeInTheDocument();
  });
});

describe("Issue panel on the real Board", () => {
  it("shows the task's server comments, history and attachments, and posts a comment", async () => {
    const user = userEvent.setup();
    const { calls } = serve({
      members: {
        "project-1": [
          buildProjectMember({ user_id: LEADER_ID, role: "LEADER", display_name: "Nguyễn Hoàng Nam" }),
          buildProjectMember({ id: "pm-2", user_id: MEMBER_ID, role: "MEMBER", display_name: "Đặng Thảo Linh" }),
        ],
      },
      userNames: { [LEADER_ID]: "Nguyễn Hoàng Nam", [MEMBER_ID]: "Đặng Thảo Linh" },
      epics: [],
      sprints: [buildSprint({ id: "s1", name: "Sprint 1" })],
      sprintTasks: { s1: ["t1"] },
      tasks: [buildTask({ id: "t1", code: "NEXUS-1", title: "Thiết kế đăng nhập", state_id: "state-todo" })],
      comments: [buildComment({ id: "c1", task_id: "t1", user_id: MEMBER_ID, display_name: "Đặng Thảo Linh", content_stripped: "Đã làm xong phần UI" })],
      activities: { t1: [buildActivity({ actor_user_id: LEADER_ID })] },
      attachments: [buildAttachment({ task_id: "t1", file_name: "wireframe.png" })],
    });
    renderAppRoutes("/projects/project-1/board?issue=NEXUS-1", leaderTestSession);

    expect(await screen.findByText("Đã làm xong phần UI", undefined, { timeout: 15000 })).toBeInTheDocument();
    expect(await screen.findByText("đã đổi độ ưu tiên: LOW → HIGH")).toBeInTheDocument();
    expect(await screen.findByText("wireframe.png")).toBeInTheDocument();

    await user.type(screen.getByLabelText("Viết bình luận"), "Cảm ơn");
    await user.click(screen.getByRole("button", { name: "Gửi bình luận" }));
    await waitFor(() => expect(writes(calls).some((call) => call.path === "/comments/" && call.body?.task_id === "t1")).toBe(true));
  }, 30000);

  it("replaces the demo GitHub block with the task's server links", async () => {
    serve({
      members: { "project-1": [buildProjectMember({ user_id: LEADER_ID, role: "LEADER", display_name: "Nguyễn Hoàng Nam" })] },
      userNames: { [LEADER_ID]: "Nguyễn Hoàng Nam" },
      epics: [],
      sprints: [buildSprint({ id: "s1", name: "Sprint 1" })],
      sprintTasks: { s1: ["t1"] },
      tasks: [buildTask({ id: "t1", code: "NEXUS-1", title: "Thiết kế đăng nhập", state_id: "state-todo" })],
      githubLinks: [buildTaskGitHubLink({ id: "l1", task_id: "t1", github_ref_id: "feature/login" })],
    });
    renderAppRoutes("/projects/project-1/board?issue=NEXUS-1", leaderTestSession);

    expect(await screen.findByText("feature/login", undefined, { timeout: 15000 })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Thêm liên kết" })).toBeInTheDocument();
  }, 30000);

  it("lets an active member manage links on a task assigned to someone else", async () => {
    serve({
      members: {
        "project-1": [
          buildProjectMember({ user_id: LEADER_ID, role: "LEADER", display_name: "Nguyễn Hoàng Nam" }),
          buildProjectMember({ id: "pm-2", user_id: MEMBER_ID, role: "MEMBER", display_name: "Đặng Thảo Linh" }),
        ],
      },
      userNames: { [LEADER_ID]: "Nguyễn Hoàng Nam", [MEMBER_ID]: "Đặng Thảo Linh" },
      epics: [],
      sprints: [buildSprint({ id: "s1", name: "Sprint 1" })],
      sprintTasks: { s1: ["t1"] },
      tasks: [buildTask({ id: "t1", code: "NEXUS-1", title: "Thiết kế đăng nhập", state_id: "state-todo", assignee_ids: [LEADER_ID] })],
      githubLinks: [buildTaskGitHubLink({ id: "l1", task_id: "t1", github_ref_id: "feature/login" })],
    });
    renderAppRoutes("/projects/project-1/board?issue=NEXUS-1", memberTestSession);

    expect(await screen.findByText("feature/login", undefined, { timeout: 15000 })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Thêm liên kết" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Xóa liên kết feature/login" })).toBeInTheDocument();
  }, 30000);
});

describe("RealComments on a project (teacher feedback)", () => {
  it("lists project-level feedback with the teacher badge and posts with project_id", async () => {
    const user = userEvent.setup();
    const served = serve({
      actorId: LEADER_ID,
      comments: [buildComment({ id: "p1", task_id: null, project_id: "project-1", content_stripped: "Cần thêm test", user_id: "teacher-1", display_name: "TS. Trần Minh Đức", is_teacher_feedback: true })],
    });
    renderApp(
      <RealComments target={{ projectId: "project-1" }} title="Phản hồi" actor={{ ...asLeader, isLeader: false }} people={PEOPLE} />,
    );
    expect(await screen.findByText("Cần thêm test", undefined, FIND)).toBeInTheDocument();
    expect(screen.getByText("Phản hồi giảng viên")).toBeInTheDocument();
    await user.type(screen.getByLabelText("Viết bình luận"), "Đã xem");
    await user.click(screen.getByRole("button", { name: "Gửi bình luận" }));
    await waitFor(() => expect(writes(served.calls)).toHaveLength(1));
    expect(writes(served.calls)[0].body).toMatchObject({ project_id: "project-1", content_html: "Đã xem" });
    expect(writes(served.calls)[0].body).not.toHaveProperty("task_id");
  });
});
