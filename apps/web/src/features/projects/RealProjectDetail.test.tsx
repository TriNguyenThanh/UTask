import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { LEADER_ID, MEMBER_ID } from "@/mocks/data/database";
import { createMemoryRepository } from "@/mocks/data/storage";
import { createAuthHandlers } from "@/mocks/handlers/auth";
import { server } from "@/mocks/server";
import {
  buildClass,
  buildCourse,
  buildGroup,
  classroomHandlers,
  type ClassroomFixture,
} from "@/test/classroomHandlers";
import {
  buildProject,
  buildProjectMember,
  workHandlers,
  type WorkFixture,
} from "@/test/workHandlers";
import {
  leaderTestSession,
  memberTestSession,
  renderAppRoutes,
} from "@/test/render";

// Shared classroom fixture: class-1 / course-1 / group-1
const BASE_CLASS = buildClass({ id: "class-1" });
const BASE_COURSE = buildCourse({ id: "course-1" });
const BASE_GROUP = buildGroup({ id: "group-1", class_section: "class-1" });

function classroomFixture(overrides: Partial<ClassroomFixture> = {}): ClassroomFixture {
  return {
    classes: [BASE_CLASS],
    courses: [BASE_COURSE],
    groups: { "class-1": [BASE_GROUP] },
    ...overrides,
  };
}

function setup(
  wf: WorkFixture,
  session: typeof leaderTestSession | typeof memberTestSession = leaderTestSession,
  cf: ClassroomFixture = classroomFixture(),
) {
  vi.stubEnv("VITE_REAL_SERVICES", "auth,classroom,work");
  server.use(
    ...workHandlers(wf),
    ...classroomHandlers(cf),
    ...createAuthHandlers("default", createMemoryRepository("default")),
  );
  return renderAppRoutes("/projects/project-1/info", session);
}

// ────────────────────────────────────────────────────────────
// Helpers
// ────────────────────────────────────────────────────────────

function leaderMember(userId = LEADER_ID) {
  return buildProjectMember({ user_id: userId, role: "LEADER", status: "ACTIVE", display_name: "Nguyễn Hoàng Nam" });
}

function regularMember(userId = MEMBER_ID) {
  return buildProjectMember({ id: "pm-2", user_id: userId, role: "MEMBER", status: "ACTIVE", display_name: "Đặng Thảo Linh" });
}

// ────────────────────────────────────────────────────────────
// Tests
// ────────────────────────────────────────────────────────────

describe("RealProjectDetail — /projects/:projectId/info", () => {
  it("Leader sees 'Sửa thông tin' button", async () => {
    const project = buildProject({ id: "project-1" });
    setup(
      { projects: [project], members: { "project-1": [leaderMember()] } },
      leaderTestSession,
    );
    expect(await screen.findByRole("button", { name: "Sửa thông tin" })).toBeInTheDocument();
  });

  it("Member does not see 'Sửa thông tin' button", async () => {
    const project = buildProject({ id: "project-1" });
    setup(
      { projects: [project], members: { "project-1": [leaderMember(), regularMember()] } },
      memberTestSession,
    );
    await screen.findByRole("heading", { name: "Thông tin dự án" });
    expect(screen.queryByRole("button", { name: "Sửa thông tin" })).not.toBeInTheDocument();
  });

  it("PATCH uses correct expected_version and shows new name after success", async () => {
    const calls: Parameters<typeof workHandlers>[0]["calls"] = [];
    const project = buildProject({ id: "project-1", name: "Cũ", version: 3 });
    const user = userEvent.setup();
    setup(
      { projects: [project], members: { "project-1": [leaderMember()] }, calls },
      leaderTestSession,
    );

    await user.click(await screen.findByRole("button", { name: "Sửa thông tin" }));
    const nameInput = await screen.findByLabelText("Tên dự án");
    await user.clear(nameInput);
    await user.type(nameInput, "Mới");
    await user.click(screen.getByRole("button", { name: "Lưu" }));

    await waitFor(() =>
      expect(calls.some((c) => c.method === "PATCH" && c.body?.expected_version === 3)).toBe(true),
    );
    await waitFor(() => expect(screen.getAllByText("Mới").length).toBeGreaterThan(0));
  });

  it("VERSION_CONFLICT shows the correct message", async () => {
    const project = buildProject({ id: "project-1", version: 1 });
    const user = userEvent.setup();
    // Pre-inject a newer version so the handler returns VERSION_CONFLICT
    setup(
      {
        projects: [project],
        members: { "project-1": [leaderMember()] },
        patchError: { status: 409, code: "VERSION_CONFLICT", message: "Xung đột" },
      },
      leaderTestSession,
    );

    await user.click(await screen.findByRole("button", { name: "Sửa thông tin" }));
    const nameInput = await screen.findByLabelText("Tên dự án");
    await user.clear(nameInput);
    await user.type(nameInput, "Bất kỳ");
    await user.click(screen.getByRole("button", { name: "Lưu" }));

    expect(
      await screen.findByText(/Dự án đã được cập nhật bởi thao tác khác/),
    ).toBeInTheDocument();
  });

  it("Archived project has no edit button but shows 'Mở lại dự án'", async () => {
    const project = buildProject({
      id: "project-1",
      archived_at: "2026-10-01T00:00:00Z",
    });
    setup(
      { projects: [project], members: { "project-1": [leaderMember()] } },
      leaderTestSession,
    );

    await screen.findByRole("heading", { name: "Thông tin dự án" });
    expect(screen.queryByRole("button", { name: "Sửa thông tin" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Mở lại dự án" })).toBeInTheDocument();
  });

  it("/projects/x redirects to /projects/x/info in real mode", async () => {
    const project = buildProject({ id: "x" });
    vi.stubEnv("VITE_REAL_SERVICES", "auth,classroom,work");
    server.use(
      ...workHandlers({ projects: [project], members: { x: [leaderMember()] } }),
      ...classroomHandlers(classroomFixture()),
      ...createAuthHandlers("default", createMemoryRepository("default")),
    );
    renderAppRoutes("/projects/x", leaderTestSession);
    // /projects/x/info should load and show project info heading
    expect(await screen.findByText("Thông tin dự án")).toBeInTheDocument();
  });

  it("404 shows 'Không tìm thấy dự án'", async () => {
    vi.stubEnv("VITE_REAL_SERVICES", "auth,classroom,work");
    server.use(
      ...workHandlers({ projects: [] }),
      ...classroomHandlers(classroomFixture()),
      ...createAuthHandlers("default", createMemoryRepository("default")),
    );
    renderAppRoutes("/projects/does-not-exist/info", leaderTestSession);
    expect(await screen.findByText("Không tìm thấy dự án")).toBeInTheDocument();
  });

  it("client validation: end_date before start_date shows error", async () => {
    const project = buildProject({ id: "project-1", start_date: "2026-10-01", end_date: "2026-12-01" });
    const user = userEvent.setup();
    setup(
      { projects: [project], members: { "project-1": [leaderMember()] } },
      leaderTestSession,
    );

    await user.click(await screen.findByRole("button", { name: "Sửa thông tin" }));
    const endInput = await screen.findByLabelText("Ngày kết thúc");
    await user.clear(endInput);
    await user.type(endInput, "2026-09-01");
    await user.click(screen.getByRole("button", { name: "Lưu" }));

    expect(
      await screen.findByText("Ngày kết thúc không được trước ngày bắt đầu."),
    ).toBeInTheDocument();
  });

  it("reloads the form after VERSION_CONFLICT so untouched fields do not overwrite someone else's change", async () => {
    const project = buildProject({ id: "project-1", version: 1, description: "Mô tả cũ" });
    const calls: NonNullable<WorkFixture["calls"]> = [];
    const user = userEvent.setup();
    setup({ projects: [project], members: { "project-1": [leaderMember()] }, calls }, leaderTestSession);

    await user.click(await screen.findByRole("button", { name: "Sửa thông tin" }));
    // Người khác sửa mô tả trong lúc form đang mở.
    Object.assign(project, { description: "Mô tả của người khác", version: 2 });
    const nameInput = await screen.findByLabelText("Tên dự án");
    await user.clear(nameInput);
    await user.type(nameInput, "Tên A");
    await user.click(screen.getByRole("button", { name: "Lưu" }));

    expect(await screen.findByText(/Dự án đã được cập nhật bởi thao tác khác/)).toBeInTheDocument();
    await waitFor(() => expect(screen.getByLabelText("Mô tả")).toHaveValue("Mô tả của người khác"));

    await user.clear(screen.getByLabelText("Tên dự án"));
    await user.type(screen.getByLabelText("Tên dự án"), "Tên B");
    await user.click(screen.getByRole("button", { name: "Lưu" }));

    await waitFor(() => expect(calls.filter((c) => c.method === "PATCH")).toHaveLength(2));
    expect(calls.filter((c) => c.method === "PATCH")[1].body).toEqual({ expected_version: 2, name: "Tên B" });
    expect(project.description).toBe("Mô tả của người khác");
  });

  it("closes the confirm dialog and shows the archive error where it is visible", async () => {
    const user = userEvent.setup();
    setup(
      {
        projects: [buildProject({ id: "project-1" })],
        members: { "project-1": [leaderMember()] },
        archiveError: { status: 409, code: "VERSION_CONFLICT", message: "Xung đột" },
      },
      leaderTestSession,
    );

    await user.click(await screen.findByRole("button", { name: "Lưu trữ dự án" }));
    const dialog = await screen.findByRole("dialog", { name: "Lưu trữ dự án" });
    await user.click(within(dialog).getByRole("button", { name: "Lưu trữ" }));

    expect(await screen.findByText(/Dự án đã được cập nhật bởi thao tác khác/)).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});

describe("RealProjectDetail — GitHub column", () => {
  it("lets a member declare their own username and shows it as unverified", async () => {
    const calls: Parameters<typeof workHandlers>[0]["calls"] = [];
    const user = userEvent.setup();
    setup(
      { projects: [buildProject({ id: "project-1" })], members: { "project-1": [leaderMember(), regularMember()] }, calls },
      memberTestSession,
    );

    const input = await screen.findByLabelText("Username GitHub của bạn");
    await user.type(input, "@octocat");
    await user.click(screen.getByRole("button", { name: "Lưu" }));

    await waitFor(() =>
      expect(calls.some((c) => c.method === "PATCH" && c.path.endsWith(`/members/${MEMBER_ID}/github/`))).toBe(true),
    );
    expect(calls.find((c) => c.path.endsWith("/github/"))?.body).toEqual({ github_username: "octocat" });
    await waitFor(() => expect(screen.getByLabelText("Username GitHub của bạn")).toHaveValue("octocat"));
    expect(screen.getByText("Chưa xác minh")).toBeInTheDocument();
  });

  it("shows the server message when the declaration is rejected", async () => {
    const user = userEvent.setup();
    setup(
      {
        projects: [buildProject({ id: "project-1" })],
        members: { "project-1": [leaderMember(), regularMember()] },
        githubError: { status: 400, code: "INVALID_OPERATION", message: "Dự án đang ở chế độ chỉ đọc." },
      },
      memberTestSession,
    );

    await user.type(await screen.findByLabelText("Username GitHub của bạn"), "octocat");
    await user.click(screen.getByRole("button", { name: "Lưu" }));

    expect(await screen.findByText("Dự án đang ở chế độ chỉ đọc.")).toBeInTheDocument();
  });

  it("lets the leader request verification for an unverified member, once", async () => {
    const calls: Parameters<typeof workHandlers>[0]["calls"] = [];
    const user = userEvent.setup();
    setup(
      {
        projects: [buildProject({ id: "project-1" })],
        members: { "project-1": [leaderMember(), { ...regularMember(), github_username: "linh-dev" }] },
        calls,
      },
      leaderTestSession,
    );

    expect(await screen.findByText("@linh-dev")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Yêu cầu xác minh" }));

    expect(await screen.findByRole("button", { name: "Đã gửi yêu cầu" })).toBeDisabled();
    expect(calls.filter((c) => c.path.endsWith("/request-verification/"))).toHaveLength(1);
  });

  it("hides the verification button from members and for verified usernames", async () => {
    const view = setup(
      {
        projects: [buildProject({ id: "project-1" })],
        members: { "project-1": [{ ...leaderMember(), github_username: "lead" }, regularMember()] },
      },
      memberTestSession,
    );

    expect(await screen.findByText("@lead")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Yêu cầu xác minh" })).not.toBeInTheDocument();
    view.unmount();

    setup(
      {
        projects: [buildProject({ id: "project-1" })],
        members: { "project-1": [leaderMember(), { ...regularMember(), github_username: "linh", is_github_verified: true }] },
      },
      leaderTestSession,
    );

    expect(await screen.findByText("@linh")).toBeInTheDocument();
    expect(screen.getByText("Đã xác minh")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Yêu cầu xác minh" })).not.toBeInTheDocument();
  });
});
