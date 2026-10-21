import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";

import { LEADER_ID } from "@/mocks/data/database";
import { createMemoryRepository } from "@/mocks/data/storage";
import { createAuthHandlers } from "@/mocks/handlers/auth";
import { server } from "@/mocks/server";
import { buildClass, buildCourse, buildGroup, classroomHandlers, envelopeError } from "@/test/classroomHandlers";
import { leaderTestSession, renderAppRoutes } from "@/test/render";
import { buildDefaultStates, buildProject, buildProjectMember, buildTask, workHandlers } from "@/test/workHandlers";

afterEach(() => vi.unstubAllEnvs());

function serve() {
  vi.stubEnv("VITE_REAL_SERVICES", "auth,classroom,work");
  server.use(
    ...workHandlers({
      projects: [buildProject({ id: "project-1", class_id: "class-1", name: "Nexus" }), buildProject({ id: "project-2", class_id: "class-1", identifier: "BAD" })],
      members: {
        "project-1": [buildProjectMember({ user_id: LEADER_ID, role: "LEADER" })],
        "project-2": [buildProjectMember({ user_id: LEADER_ID, role: "LEADER" })],
      },
      states: buildDefaultStates(),
      tasks: [buildTask({ id: "t1", code: "NEXUS-1", title: "Thiết kế đăng nhập", assignee_ids: [LEADER_ID], due_date: null })],
    }),
    ...classroomHandlers({
      classes: [buildClass({ id: "class-1", course: "course-1" })],
      courses: [buildCourse({ id: "course-1" })],
      groups: { "class-1": [buildGroup({ id: "group-1", class_section: "class-1" })] },
    }),
    ...createAuthHandlers("default", createMemoryRepository("default")),
  );
}

describe("My Work with real Work and Classroom", () => {
  it("lists my tasks gathered from my projects, with a missing due date shown plainly", async () => {
    serve();
    renderAppRoutes("/my-work", leaderTestSession);
    await userEvent.click(await screen.findByRole("tab", { name: "Chưa đặt hạn" }, { timeout: 10000 }));
    expect((await screen.findAllByText("Thiết kế đăng nhập", undefined, { timeout: 10000 })).length).toBeGreaterThan(0);
    expect(screen.queryByText("Một phần dữ liệu chưa tải được.")).not.toBeInTheDocument();
  }, 20000);

  it("still shows the page, with a note, when one project cannot be read", async () => {
    serve();
    server.use(http.get("/api/work/projects/project-2/tasks/", () => envelopeError(500, "INTERNAL_ERROR", "Lỗi")));
    renderAppRoutes("/my-work", leaderTestSession);
    await userEvent.click(await screen.findByRole("tab", { name: "Chưa đặt hạn" }, { timeout: 10000 }));
    expect(await screen.findByText("Một phần dữ liệu chưa tải được.", undefined, { timeout: 10000 })).toBeInTheDocument();
    expect(screen.getAllByText("Thiết kế đăng nhập").length).toBeGreaterThan(0);
  }, 20000);
});
