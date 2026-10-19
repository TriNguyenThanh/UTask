import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { describe, expect, it, vi } from "vitest";

import { Component as CourseTeamRoute } from "@/features/courses/routes/CourseTeamRoute";
import { LEADER_ID, MEMBER_ID } from "@/mocks/data/database";
import { createMemoryRepository } from "@/mocks/data/storage";
import { createAuthHandlers } from "@/mocks/handlers/auth";
import { server } from "@/mocks/server";
import {
  buildClass,
  buildCourse,
  buildGroup,
  buildMember,
  classroomHandlers,
  envelope,
  envelopeError,
  type ClassroomFixture,
} from "@/test/classroomHandlers";
import { leaderTestSession, memberTestSession, renderApp } from "@/test/render";

const routes = [{ path: "/courses/:courseId", element: <CourseTeamRoute /> }];
const future = () => new Date(Date.now() + 86_400_000).toISOString();

function teamFixture(overrides: Partial<ClassroomFixture> = {}): ClassroomFixture {
  return {
    classes: [buildClass()],
    courses: [buildCourse()],
    groups: { "class-1": [buildGroup({ source_version: 3, invite_expires_at: null })] },
    members: {
      "group-1": [
        buildMember({ id: "m1", user_id: LEADER_ID, role: "LEADER", profile: { display_name: "Trưởng Nhóm" } }),
        buildMember({ id: "m2", user_id: MEMBER_ID, role: "MEMBER", profile: { display_name: "Bạn Thành Viên" } }),
      ],
    },
    ...overrides,
  };
}

function setup(fixture: ClassroomFixture, session = leaderTestSession, ...overrides: Parameters<typeof server.use>) {
  vi.stubEnv("VITE_REAL_SERVICES", "auth,classroom");
  server.use(...overrides, ...classroomHandlers(fixture), ...createAuthHandlers("default", createMemoryRepository("default")));
  return renderApp(<CourseTeamRoute />, { route: "/courses/class-1", session, routes });
}

interface Call {
  key: string | null;
  body: unknown;
}

function record(path: string, calls: Call[], respond = () => envelope(buildGroup())) {
  return http.post(path, async ({ request }) => {
    calls.push({ key: request.headers.get("Idempotency-Key"), body: await request.json() });
    return respond();
  });
}

describe("create group", () => {
  it("posts class_id and the trimmed name with an Idempotency-Key", async () => {
    const calls: Call[] = [];
    const user = userEvent.setup();
    setup({ classes: [buildClass()], courses: [buildCourse()] }, leaderTestSession, record("/api/classroom/groups/", calls));

    await user.click(await screen.findByRole("button", { name: /Tạo nhóm mới/ }));
    await user.type(await screen.findByLabelText("Tên nhóm"), "  Team Alpha ");
    expect(screen.queryByLabelText(/Sĩ số tối đa/)).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Tạo nhóm" }));

    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].body).toEqual({ class_id: "class-1", name: "Team Alpha" });
    expect(calls[0].key).toMatch(/^[0-9a-f-]{36}$/);
  });

  it("shows the field error from the server and keeps the dialog open", async () => {
    const user = userEvent.setup();
    setup(
      { classes: [buildClass()], courses: [buildCourse()] },
      leaderTestSession,
      http.post("/api/classroom/groups/", () =>
        Response.json({ success: false, message: "Dữ liệu không hợp lệ", data: null, meta: null, error: { code: "VALIDATION_ERROR", details: [{ field: "name", issue: "Tên nhóm đã tồn tại." }] } }, { status: 400 })),
    );
    await user.click(await screen.findByRole("button", { name: /Tạo nhóm mới/ }));
    await user.type(await screen.findByLabelText("Tên nhóm"), "Trùng");
    await user.click(screen.getByRole("button", { name: "Tạo nhóm" }));

    expect(await screen.findByText("Tên nhóm đã tồn tại.")).toBeInTheDocument();
    expect(screen.getByLabelText("Tên nhóm")).toBeInTheDocument();
  });

  it("disables creation when grouping is locked", async () => {
    setup({ classes: [buildClass({ grouping_phase: "LOCKED" })], courses: [buildCourse()] });
    expect(await screen.findByRole("button", { name: /Tạo nhóm mới/ })).toBeDisabled();
  });
});

describe("join group by code", () => {
  it("sends the trimmed code and shows the server message for an expired code", async () => {
    const calls: Call[] = [];
    const user = userEvent.setup();
    setup(
      { classes: [buildClass()], courses: [buildCourse()] },
      leaderTestSession,
      http.post("/api/classroom/groups/join/", async ({ request }) => {
        calls.push({ key: request.headers.get("Idempotency-Key"), body: await request.json() });
        return envelopeError(409, "ACCESS_CODE_EXPIRED", "Mã mời nhóm không còn hiệu lực. Hãy xin mã mới.");
      }),
    );
    await user.click(await screen.findByRole("button", { name: /Tham gia nhóm bằng mã/ }));
    await user.type(await screen.findByLabelText("Mã mời nhóm"), " CODE1 ");
    await user.click(screen.getByRole("button", { name: "Tham gia" }));

    expect(await screen.findByText(/Mã mời nhóm không còn hiệu lực/)).toBeInTheDocument();
    expect(calls[0].body).toEqual({ code: "CODE1" });
    expect(calls[0].key).toMatch(/^[0-9a-f-]{36}$/);
  });
});

describe("invite code", () => {
  it("shows the raw code once with a one-time warning, using the current group version", async () => {
    const calls: Call[] = [];
    const user = userEvent.setup();
    setup(
      teamFixture(),
      leaderTestSession,
      record("/api/classroom/groups/group-1/invite-code/", calls, () =>
        envelope({ id: "group-1", version: 4, code: "SECRET99", expires_at: future(), enabled: true })),
    );
    expect(await screen.findByText("Mã mời đang tắt hoặc đã hết hạn.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Bật mã mời" }));

    expect(await screen.findByText("SECRET99")).toBeInTheDocument();
    expect(screen.getByText(/Mã chỉ hiển thị một lần/)).toBeInTheDocument();
    expect(calls[0].body).toEqual({ version: 3, enabled: true });
  });

  it("offers to disable an active code and never shows a code it was not just given", async () => {
    const calls: Call[] = [];
    const user = userEvent.setup();
    setup(
      teamFixture({ groups: { "class-1": [buildGroup({ source_version: 3, invite_expires_at: future() })] } }),
      leaderTestSession,
      record("/api/classroom/groups/group-1/invite-code/", calls, () => envelope({ id: "group-1", version: 4, expires_at: null, enabled: false })),
    );
    expect(await screen.findByText(/Mã đang bật, hết hạn/)).toBeInTheDocument();
    expect(screen.queryByText(/Mã chỉ hiển thị một lần/)).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Tắt mã" }));

    await waitFor(() => expect(calls[0].body).toEqual({ version: 3, enabled: false }));
  });

  it("is hidden for non-leaders", async () => {
    setup(teamFixture(), memberTestSession);
    await screen.findByText("Bạn Thành Viên");
    expect(screen.queryByText("Mã mời nhóm")).not.toBeInTheDocument();
  });
});

describe("leave group", () => {
  it("asks for a reason, then posts version and reason", async () => {
    const calls: Call[] = [];
    const user = userEvent.setup();
    setup(teamFixture(), memberTestSession, record("/api/classroom/groups/group-1/leave/", calls));
    await user.click(await screen.findByRole("button", { name: "Rời nhóm" }));

    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Rời nhóm" }));
    expect(await within(dialog).findByRole("alert")).toBeInTheDocument();
    expect(calls).toHaveLength(0);

    await user.type(within(dialog).getByLabelText("Lý do"), "Chuyển sang nhóm khác");
    await user.click(within(dialog).getByRole("button", { name: "Rời nhóm" }));

    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].body).toEqual({ version: 3, reason: "Chuyển sang nhóm khác" });
    expect(calls[0].key).toMatch(/^[0-9a-f-]{36}$/);
  });

  it("is disabled for the leader, who must transfer leadership first", async () => {
    setup(teamFixture());
    expect(await screen.findByRole("button", { name: "Rời nhóm" })).toBeDisabled();
  });

  it("on a version conflict shows the stale-data message and refetches the group", async () => {
    let fetches = 0;
    const user = userEvent.setup();
    setup(
      teamFixture(),
      memberTestSession,
      http.get("/api/classroom/classes/class-1/groups/", () => {
        fetches += 1;
        return envelope([buildGroup({ source_version: 3 })]);
      }),
      http.post("/api/classroom/groups/group-1/leave/", () => envelopeError(409, "VERSION_CONFLICT", "Nhóm học tập đã thay đổi. Vui lòng tải lại dữ liệu.")),
    );
    await user.click(await screen.findByRole("button", { name: "Rời nhóm" }));
    await user.type(await screen.findByLabelText("Lý do"), "Đổi nhóm");
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Rời nhóm" }));

    expect(await screen.findByText("Dữ liệu nhóm đã thay đổi, hãy thử lại.")).toBeInTheDocument();
    await waitFor(() => expect(fetches).toBeGreaterThan(1));
  });

  it("shows the server message when leaving is forbidden", async () => {
    const user = userEvent.setup();
    setup(
      teamFixture(),
      memberTestSession,
      http.post("/api/classroom/groups/group-1/leave/", () => envelopeError(409, "GROUPING_LOCKED", "Lớp đã chốt nhóm; hãy liên hệ giảng viên phụ trách.")),
    );
    await user.click(await screen.findByRole("button", { name: "Rời nhóm" }));
    await user.type(await screen.findByLabelText("Lý do"), "Đổi nhóm");
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Rời nhóm" }));

    expect(await screen.findByText(/Lớp đã chốt nhóm/)).toBeInTheDocument();
  });
});

describe("leader member management", () => {
  it("transfers leadership to the chosen member with user_id and reason", async () => {
    const calls: Call[] = [];
    const user = userEvent.setup();
    setup(teamFixture(), leaderTestSession, record("/api/classroom/groups/group-1/transfer-leader/", calls));
    await user.click(await screen.findByRole("button", { name: "Chuyển quyền" }));
    await user.type(await screen.findByLabelText("Lý do"), "Bàn giao công việc");
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Chuyển quyền" }));

    await waitFor(() => expect(calls[0]?.body).toEqual({ version: 3, reason: "Bàn giao công việc", user_id: MEMBER_ID }));
  });

  it("removes the chosen member", async () => {
    const calls: Call[] = [];
    const user = userEvent.setup();
    setup(teamFixture(), leaderTestSession, record("/api/classroom/groups/group-1/remove-member/", calls));
    await user.click(await screen.findByRole("button", { name: "Loại" }));
    await user.type(await screen.findByLabelText("Lý do"), "Không hoạt động");
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Loại khỏi nhóm" }));

    await waitFor(() => expect(calls[0]?.body).toEqual({ version: 3, reason: "Không hoạt động", user_id: MEMBER_ID }));
  });

  it("shows no management buttons to a regular member, and none on the leader's own row", async () => {
    setup(teamFixture(), memberTestSession);
    await screen.findByText("Bạn Thành Viên");
    expect(screen.queryByRole("button", { name: "Chuyển quyền" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Loại" })).not.toBeInTheDocument();
  });

  it("does not offer actions on rows of the leader themself", async () => {
    setup({ ...teamFixture(), members: { "group-1": [buildMember({ user_id: LEADER_ID, role: "LEADER" })] } });
    await screen.findByText("Nguyễn Văn An");
    expect(screen.queryByRole("button", { name: "Loại" })).not.toBeInTheDocument();
  });
});
