import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { UserEvent } from "@testing-library/user-event";
import { delay, http, HttpResponse } from "msw";
import { vi, describe, it, expect, beforeEach } from "vitest";

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
  envelopeError,
} from "@/test/classroomHandlers";
import { buildProject, workHandlers, type WorkFixture } from "@/test/workHandlers";
import { leaderTestSession, memberTestSession, renderAppRoutes } from "@/test/render";

const TEAM_ROUTE = "/courses/class-1/team";

function baseClassroomFixture(leaderUserId: string) {
  return {
    classes: [buildClass()],
    courses: [buildCourse()],
    groups: { "class-1": [buildGroup()] },
    members: { "group-1": [buildMember({ user_id: leaderUserId, role: "LEADER" })] },
  };
}

function setupReal(workFixture: WorkFixture, leaderUserId = LEADER_ID) {
  vi.stubEnv("VITE_REAL_SERVICES", "auth,classroom,work");
  server.use(
    ...workHandlers(workFixture),
    ...classroomHandlers(baseClassroomFixture(leaderUserId)),
    ...createAuthHandlers("default", createMemoryRepository("default")),
  );
}

async function openCreateDialog(user: UserEvent) {
  const btn = await screen.findByRole("button", { name: "Tạo dự án" });
  await user.click(btn);
  await screen.findByRole("dialog", { name: "Tạo dự án mới" });
}

describe("TeamProjectSection — Leader", () => {
  it("creates ZP9T, fires exactly one POST, then navigates to /projects/<id>/info", async () => {
    const calls: WorkFixture["calls"] = [];
    setupReal({ projects: [], calls });
    const user = userEvent.setup();
    const { router } = renderAppRoutes(TEAM_ROUTE, leaderTestSession);

    await openCreateDialog(user);

    await user.type(screen.getByLabelText("Mã dự án"), "ZP9T");
    await user.type(screen.getByLabelText("Tên dự án"), "Dự án kiểm thử");
    await user.click(screen.getByRole("button", { name: "Tạo dự án" }));

    await waitFor(() => expect(calls?.filter((c) => c.method === "POST").length).toBe(1));
    await waitFor(() => expect(router.state.location.pathname).toMatch(/^\/projects\/project-1\/info$/));
  });

  it("shows DUPLICATE_IDENTIFIER error on the identifier field", async () => {
    // Project is in a different group → group-1 shows empty (dialog opens),
    // but POST with same identifier triggers 409 from workHandlers duplicate check.
    setupReal({ projects: [buildProject({ identifier: "ZP9T", classroom_group_id: "other-group" })] });
    const user = userEvent.setup();
    renderAppRoutes(TEAM_ROUTE, leaderTestSession);

    await openCreateDialog(user);
    await user.type(screen.getByLabelText("Mã dự án"), "ZP9T");
    await user.type(screen.getByLabelText("Tên dự án"), "Dự án kiểm thử");
    await user.click(screen.getByRole("button", { name: "Tạo dự án" }));

    expect(await screen.findByText("Mã dự án đã được dùng. Hãy chọn mã khác.")).toBeInTheDocument();
    expect(screen.getByRole("dialog", { name: "Tạo dự án mới" })).toBeInTheDocument();
  });

  it("retry unchanged after failure reuses the SAME Idempotency-Key", async () => {
    vi.stubEnv("VITE_REAL_SERVICES", "auth,classroom,work");
    const callsArr: { key: string | null }[] = [];
    let callCount = 0;
    // Custom POST handler must come before workHandlers so it wins; workHandlers still handles GET.
    server.use(
      http.post("/api/work/projects/", async ({ request }) => {
        callsArr.push({ key: request.headers.get("Idempotency-Key") });
        callCount += 1;
        if (callCount === 1) {
          return envelopeError(503, "CLASSROOM_UNAVAILABLE", "Classroom không khả dụng.");
        }
        const body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(
          {
            success: true,
            message: "OK",
            data: buildProject({ identifier: String(body.identifier), name: String(body.name) }),
            meta: null,
            error: null,
          },
          { status: 201 },
        );
      }),
      ...workHandlers({ projects: [] }),
      ...classroomHandlers(baseClassroomFixture(LEADER_ID)),
      ...createAuthHandlers("default", createMemoryRepository("default")),
    );

    const user = userEvent.setup();
    renderAppRoutes(TEAM_ROUTE, leaderTestSession);

    await openCreateDialog(user);
    await user.type(screen.getByLabelText("Mã dự án"), "ZP9T");
    await user.type(screen.getByLabelText("Tên dự án"), "Dự án kiểm thử");

    await user.click(screen.getByRole("button", { name: "Tạo dự án" }));
    expect(await screen.findByText("Chưa xác minh được nhóm lớp học. Hãy thử lại sau ít phút.")).toBeInTheDocument();

    // Retry without any field change — same key
    await user.click(screen.getByRole("button", { name: "Tạo dự án" }));
    await waitFor(() => expect(callsArr).toHaveLength(2));

    expect(callsArr[0]!.key).toBeTruthy();
    expect(callsArr[0]!.key).toBe(callsArr[1]!.key);
  });

  it("changed field after failure generates a NEW Idempotency-Key", async () => {
    vi.stubEnv("VITE_REAL_SERVICES", "auth,classroom,work");
    const callsArr: { key: string | null }[] = [];
    let callCount = 0;
    server.use(
      http.post("/api/work/projects/", async ({ request }) => {
        callsArr.push({ key: request.headers.get("Idempotency-Key") });
        callCount += 1;
        if (callCount === 1) {
          return envelopeError(503, "CLASSROOM_UNAVAILABLE", "Classroom không khả dụng.");
        }
        const body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(
          {
            success: true,
            message: "OK",
            data: buildProject({ identifier: String(body.identifier), name: String(body.name) }),
            meta: null,
            error: null,
          },
          { status: 201 },
        );
      }),
      ...workHandlers({ projects: [] }),
      ...classroomHandlers(baseClassroomFixture(LEADER_ID)),
      ...createAuthHandlers("default", createMemoryRepository("default")),
    );

    const user = userEvent.setup();
    renderAppRoutes(TEAM_ROUTE, leaderTestSession);

    await openCreateDialog(user);
    await user.type(screen.getByLabelText("Mã dự án"), "ZP9T");
    await user.type(screen.getByLabelText("Tên dự án"), "Tên ban đầu");

    await user.click(screen.getByRole("button", { name: "Tạo dự án" }));
    expect(await screen.findByText("Chưa xác minh được nhóm lớp học. Hãy thử lại sau ít phút.")).toBeInTheDocument();

    // Change the name field → triggers new key generation
    await user.clear(screen.getByLabelText("Tên dự án"));
    await user.type(screen.getByLabelText("Tên dự án"), "Tên đã đổi");

    await user.click(screen.getByRole("button", { name: "Tạo dự án" }));
    await waitFor(() => expect(callsArr).toHaveLength(2));

    expect(callsArr[0]!.key).toBeTruthy();
    expect(callsArr[1]!.key).toBeTruthy();
    expect(callsArr[0]!.key).not.toBe(callsArr[1]!.key);
  });
});

describe("TeamProjectSection — Member (non-leader)", () => {
  beforeEach(() => {
    vi.stubEnv("VITE_REAL_SERVICES", "auth,classroom,work");
    server.use(
      ...workHandlers({ projects: [] }),
      ...classroomHandlers({
        classes: [buildClass()],
        courses: [buildCourse()],
        groups: { "class-1": [buildGroup()] },
        members: { "group-1": [buildMember({ user_id: MEMBER_ID, role: "MEMBER" })] },
      }),
      ...createAuthHandlers("default", createMemoryRepository("default")),
    );
  });

  it("shows the non-leader sentence and no create button", async () => {
    renderAppRoutes(TEAM_ROUTE, memberTestSession);

    expect(
      await screen.findByText("Nhóm chưa có dự án. Trưởng nhóm là người tạo dự án."),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Tạo dự án" })).not.toBeInTheDocument();
  });
});

describe("TeamProjectSection — existing projects", () => {
  it("lists projects with Vào dự án links and archived badge", async () => {
    setupReal({
      projects: [
        buildProject({ id: "p1", identifier: "NEXUS", name: "Hệ thống Nexus", archived_at: null }),
        buildProject({ id: "p2", identifier: "ARCH", name: "Dự án cũ", archived_at: "2026-10-01T00:00:00Z" }),
      ],
    });
    renderAppRoutes(TEAM_ROUTE, leaderTestSession);

    expect(await screen.findByText("Hệ thống Nexus")).toBeInTheDocument();
    expect(screen.getByText("Dự án cũ")).toBeInTheDocument();
    expect(screen.getByText("Đã lưu trữ")).toBeInTheDocument();

    const links = screen.getAllByRole("link", { name: "Vào dự án" });
    expect(links[0]).toHaveAttribute("href", "/projects/p1/info");
    expect(links[1]).toHaveAttribute("href", "/projects/p2/info");
  });

  it("does not show create button when group already has projects", async () => {
    setupReal({ projects: [buildProject({ classroom_group_id: "group-1" })] });
    renderAppRoutes(TEAM_ROUTE, leaderTestSession);

    await screen.findByText("Hệ thống Nexus");
    expect(screen.queryByRole("button", { name: "Tạo dự án" })).not.toBeInTheDocument();
  });
});

describe("TeamProjectSection — query failure", () => {
  it("shows error line but does not break the team page", async () => {
    vi.stubEnv("VITE_REAL_SERVICES", "auth,classroom,work");
    server.use(
      http.get("/api/work/projects/", () => envelopeError(503, "CLASSROOM_UNAVAILABLE", "Classroom lỗi.")),
      ...classroomHandlers(baseClassroomFixture(LEADER_ID)),
      ...createAuthHandlers("default", createMemoryRepository("default")),
    );
    renderAppRoutes(TEAM_ROUTE, leaderTestSession);

    expect(await screen.findByText("Nguyễn Văn An")).toBeInTheDocument();
    expect(await screen.findByText("Chưa tải được dự án của nhóm.")).toBeInTheDocument();
  });

  it("does not offer 'Tạo dự án' while the group's projects are still loading", async () => {
    setupReal({ projects: [] });
    server.use(http.get("/api/work/projects/", () => delay("infinite")));
    renderAppRoutes(TEAM_ROUTE, leaderTestSession);

    expect(await screen.findByText("Đang tải dự án của nhóm…")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Tạo dự án" })).not.toBeInTheDocument();
  });

  it("shows LEADER_PERMISSION_REQUIRED at the top of the form", async () => {
    setupReal({
      projects: [],
      createError: { status: 403, code: "LEADER_PERMISSION_REQUIRED", message: "Forbidden" },
    });
    const user = userEvent.setup();
    renderAppRoutes(TEAM_ROUTE, leaderTestSession);

    await openCreateDialog(user);
    await user.type(screen.getByLabelText("Mã dự án"), "ZP9T");
    await user.type(screen.getByLabelText("Tên dự án"), "Dự án");
    await user.click(screen.getByRole("button", { name: "Tạo dự án" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Chỉ trưởng nhóm mới tạo được dự án.");
  });

  it("does not drop a VALIDATION_ERROR for a field the form has no slot for", async () => {
    setupReal({ projects: [] });
    server.use(
      http.post("/api/work/projects/", () =>
        HttpResponse.json(
          {
            success: false,
            message: "Dữ liệu không hợp lệ.",
            data: null,
            meta: null,
            error: { code: "VALIDATION_ERROR", details: [{ field: "description", issue: "Quá dài." }] },
          },
          { status: 400 },
        )),
    );
    const user = userEvent.setup();
    renderAppRoutes(TEAM_ROUTE, leaderTestSession);

    await openCreateDialog(user);
    await user.type(screen.getByLabelText("Mã dự án"), "ZP9T");
    await user.type(screen.getByLabelText("Tên dự án"), "Dự án");
    await user.click(screen.getByRole("button", { name: "Tạo dự án" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Dữ liệu không hợp lệ.");
  });
});

