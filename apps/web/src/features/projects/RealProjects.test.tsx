import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { createMemoryRepository } from "@/mocks/data/storage";
import { createAuthHandlers } from "@/mocks/handlers/auth";
import { server } from "@/mocks/server";
import { classroomHandlers, buildClass, buildCourse, buildGroup, buildMember } from "@/test/classroomHandlers";
import { buildProject, buildProjectMember, workHandlers, type WorkFixture } from "@/test/workHandlers";
import { renderAppRoutes, studentTestSession } from "@/test/render";
import { STUDENT_ID } from "@/mocks/data/database";

afterEach(() => vi.unstubAllEnvs());

function setupWork(workFixture: WorkFixture = { projects: [] }) {
  vi.stubEnv("VITE_REAL_SERVICES", "auth,classroom,work");
  const classFixture = {
    classes: [buildClass({ id: "class-1" })],
    courses: [buildCourse({ id: "course-1", code: "SE100" })],
    groups: { "class-1": [buildGroup({ id: "group-1", name: "Nhóm 1" })] },
    members: { "group-1": [buildMember({ group_id: "group-1", user_id: STUDENT_ID, role: "MEMBER" })] },
  };
  server.use(
    ...workHandlers(workFixture),
    ...classroomHandlers(classFixture),
    ...createAuthHandlers("default", createMemoryRepository("default")),
  );
  return renderAppRoutes("/projects", studentTestSession);
}

describe("/projects at real Work service", () => {
  it("shows empty state when the user has no projects", async () => {
    setupWork({ projects: [] });
    expect(await screen.findByText("Chưa có dự án")).toBeInTheDocument();
    expect(screen.getByText(/Trưởng nhóm tạo dự án/)).toBeInTheDocument();
  });

  it("tab active shows active project, tab archived shows archived project", async () => {
    const active = buildProject({ id: "p1", name: "Dự án Alpha", archived_at: null });
    const archived = buildProject({
      id: "p2",
      name: "Dự án Beta",
      identifier: "BETA",
      archived_at: "2026-10-01T00:00:00Z",
    });
    setupWork({
      projects: [active, archived],
      members: {
        p1: [buildProjectMember({ user_id: STUDENT_ID, role: "MEMBER", status: "ACTIVE" })],
        p2: [buildProjectMember({ id: "pm-2", user_id: STUDENT_ID, role: "MEMBER", status: "ACTIVE" })],
      },
    });

    const user = userEvent.setup();
    await screen.findByText("Dự án Alpha");
    expect(screen.queryByText("Dự án Beta")).not.toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: "Đã lưu trữ" }));
    await screen.findByText("Dự án Beta");
    expect(screen.queryByText("Dự án Alpha")).not.toBeInTheDocument();
  });

  it("shows partial warning banner when meta.scope.partial is true", async () => {
    setupWork({ projects: [buildProject()], partial: true });
    expect(await screen.findByText(/Danh sách có thể thiếu dự án/)).toBeInTheDocument();
  });

  it("shows ErrorState with server message on 503", async () => {
    setupWork({
      projects: [],
      listError: { status: 503, code: "CLASSROOM_UNAVAILABLE", message: "Dịch vụ lớp học tạm thời không khả dụng." },
    });
    expect(await screen.findByText("Dịch vụ lớp học tạm thời không khả dụng.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Thử lại" })).toBeInTheDocument();
  });

  it("search filters by identifier", async () => {
    const p1 = buildProject({ id: "p1", identifier: "ALPHA", name: "Dự án Alpha" });
    const p2 = buildProject({ id: "p2", identifier: "BETA", name: "Dự án Beta" });
    setupWork({
      projects: [p1, p2],
      members: {
        p1: [buildProjectMember({ user_id: STUDENT_ID, status: "ACTIVE" })],
        p2: [buildProjectMember({ id: "pm-2", user_id: STUDENT_ID, status: "ACTIVE" })],
      },
    });

    const user = userEvent.setup();
    await screen.findByText("Dự án Alpha");
    await screen.findByText("Dự án Beta");

    await user.type(screen.getByPlaceholderText(/Tìm theo mã/), "BETA");
    await waitFor(() => expect(screen.queryByText("Dự án Alpha")).not.toBeInTheDocument());
    expect(screen.getByText("Dự án Beta")).toBeInTheDocument();
  });
});
