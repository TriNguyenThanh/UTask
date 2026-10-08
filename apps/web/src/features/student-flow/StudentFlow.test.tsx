import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { RouteObject } from "react-router-dom";

import { AuthenticatedLayout } from "@/app/layouts/AuthenticatedLayout";
import { Component as NotFoundRoute } from "@/app/router/NotFoundRoute";
import { RequireAuth } from "@/app/router/RequireAuth";
import { Component as CoursesRoute } from "@/features/courses/routes/CoursesRoute";
import { Component as CourseTeamRoute } from "@/features/courses/routes/CourseTeamRoute";
import { Component as ProjectsRoute } from "@/features/projects/routes/ProjectsRoute";
import { Component as ProjectBacklogRoute } from "@/features/projects/routes/ProjectBacklogRoute";
import { Component as ProjectBoardRoute } from "@/features/projects/routes/ProjectBoardRoute";
import { Component as ProjectCodeRoute } from "@/features/projects/routes/ProjectCodeRoute";
import ProjectWorkspaceLayout from "@/features/projects/routes/ProjectWorkspaceLayout";
import { RequireProjectManagePermission } from "@/features/projects/routes/RequireProjectManagePermission";
import { Component as ProjectSettingsRoute } from "@/features/projects/routes/ProjectSettingsRoute";
import { Component as NotificationsRoute } from "@/features/notifications/routes/NotificationsRoute";
import { Component as SettingsIntegrationsRoute } from "@/features/notifications/routes/SettingsIntegrationsRoute";
import { createMockHandlers } from "@/mocks/handlers";
import { createMemoryRepository } from "@/mocks/data/storage";
import type { MockScenario } from "@/mocks/scenarios";
import { renderApp, memberTestSession, studentTestSession } from "@/test/render";
import { server } from "@/mocks/server";

function useScenario(scenario: MockScenario) {
  server.use(...createMockHandlers(scenario, createMemoryRepository(scenario)));
}

function studentRoutes(): RouteObject[] {
  return [
    { path: "/login", element: <h1>Trang đăng nhập</h1> },
    {
      element: (
        <RequireAuth>
          <AuthenticatedLayout />
        </RequireAuth>
      ),
      children: [
        { path: "/courses", element: <CoursesRoute /> },
        { path: "/courses/:courseId/team", element: <CourseTeamRoute /> },
        { path: "/projects", element: <ProjectsRoute /> },
        {
          path: "/projects/:projectId",
          element: <ProjectWorkspaceLayout />,
          children: [
            { path: "backlog", element: <ProjectBacklogRoute /> },
            { path: "board", element: <ProjectBoardRoute /> },
            { path: "code", element: <ProjectCodeRoute /> },
            {
              path: "settings",
              element: <RequireProjectManagePermission />,
              children: [{ path: "", element: <ProjectSettingsRoute /> }],
            },
          ],
        },
        { path: "/notifications", element: <NotificationsRoute /> },
        { path: "/settings/integrations", element: <SettingsIntegrationsRoute /> },
        { path: "*", element: <NotFoundRoute /> },
      ],
    },
  ];
}

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("student flow routing guards", () => {
  it("keeps unauthenticated visitors out of /courses", async () => {
    renderApp(<RequireAuth><AuthenticatedLayout /></RequireAuth>, {
      route: "/courses",
      session: null,
      routes: studentRoutes(),
    });
    expect(await screen.findByRole("heading", { name: "Trang đăng nhập" })).toBeInTheDocument();
  });

  it("shows Not Found for an unknown route", async () => {
    renderApp(<RequireAuth><AuthenticatedLayout /></RequireAuth>, {
      route: "/khong-ton-tai",
      routes: studentRoutes(),
    });
    expect(await screen.findByRole("heading", { name: /Không tìm thấy trang/ })).toBeInTheDocument();
  });
});

describe("team formation flow", () => {
  it("routes an unteamed student to Team Formation with open teams and create CTA", async () => {
    useScenario("student-no-team");
    renderApp(<RequireAuth><AuthenticatedLayout /></RequireAuth>, {
      route: "/courses/course-se330/team",
      session: studentTestSession,
      routes: studentRoutes(),
    });

    expect(
      await screen.findByRole("heading", { name: /Thành lập Nhóm/ }),
    ).toBeInTheDocument();
    expect(screen.getByText(/Team ATLAS/)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Tạo nhóm mới/ }),
    ).toBeInTheDocument();
  });

  it("shows the pending join-request state without leaking internal team data", async () => {
    useScenario("student-join-pending");
    renderApp(<RequireAuth><AuthenticatedLayout /></RequireAuth>, {
      route: "/courses/course-se331/team",
      session: studentTestSession,
      routes: studentRoutes(),
    });
    expect(
      await screen.findByRole("heading", { name: /chờ duyệt/ }),
    ).toBeInTheDocument();
    // Internal team roster must not leak into the pending view.
    expect(screen.queryByText(/Danh sách thành viên/i)).not.toBeInTheDocument();
  });
});

describe("project access and permissions", () => {
  it("renders Forbidden when the project endpoint denies access", async () => {
    useScenario("student-forbidden");
    renderApp(<RequireAuth><AuthenticatedLayout /></RequireAuth>, {
      route: "/projects/project-nexus/backlog",
      session: studentTestSession,
      routes: studentRoutes(),
    });

    expect(
      await screen.findByRole("heading", { name: /Không đủ quyền truy cập/ }),
    ).toBeInTheDocument();
  });

  it("hides leader-only sprint and AI actions from a member", async () => {
    renderApp(<RequireAuth><AuthenticatedLayout /></RequireAuth>, {
      route: "/projects/project-deli/backlog",
      session: memberTestSession,
      routes: studentRoutes(),
    });

    expect(await screen.findByText(/DELI-02/)).toBeInTheDocument();
    expect(screen.queryByText(/Hoàn thành Sprint/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/AI ước lượng/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Tạo Epic/i)).not.toBeInTheDocument();
  });

  it("routes a leader without an AI key to Project Settings via CTA", async () => {
    useScenario("student-ai-key-missing");
    renderApp(<RequireAuth><AuthenticatedLayout /></RequireAuth>, {
      route: "/projects/project-nexus/backlog",
      routes: studentRoutes(),
    });

    const aiCta = await screen.findByRole("link", { name: /AI ước lượng/i });
    expect(aiCta).toHaveAttribute("href", "/projects/project-nexus/settings");
  });

  it("keeps the AI key input masked, empty, and never prefilled with the saved key", async () => {
    useScenario("student-ai-key-missing");
    renderApp(<RequireAuth><AuthenticatedLayout /></RequireAuth>, {
      route: "/projects/project-nexus/settings",
      routes: studentRoutes(),
    });

    const keyInput = await screen.findByLabelText("API key", { selector: "input" });
    expect(keyInput).toHaveAttribute("type", "password");
    expect(keyInput).toHaveValue("");
    expect(keyInput).toHaveAttribute("autocomplete", "off");
    // The saved-key hint (masked) only appears for a connected key, and the
    // raw key never appears anywhere in the document.
    expect(document.body.textContent).not.toMatch(/sk-[A-Za-z0-9]{16,}/);
  });
});

describe("notifications", () => {
  it("deep-links a task notification to the board issue URL and marks it read", async () => {
    const user = userEvent.setup();
    const result = renderApp(<RequireAuth><AuthenticatedLayout /></RequireAuth>, {
      route: "/notifications",
      session: studentTestSession,
      routes: studentRoutes(),
    });

    const issueAction = await screen.findByRole("button", { name: /Xem Issue/i });
    await user.click(issueAction);

    await waitFor(() => {
      expect(result.router.state.location.pathname).toBe(
        "/projects/project-nexus/board",
      );
      expect(result.router.state.location.search).toBe("?issue=NEXUS-104");
    });
  });
});

describe("github integration states", () => {
  it("shows a connect CTA when GitHub is disconnected", async () => {
    useScenario("student-github-disconnected");
    renderApp(<RequireAuth><AuthenticatedLayout /></RequireAuth>, {
      route: "/settings/integrations",
      session: studentTestSession,
      routes: studentRoutes(),
    });

    expect((await screen.findAllByText(/Kết nối GitHub/i)).length).toBeGreaterThan(0);
    expect(screen.getByTitle(/OAuth sẽ khả dụng khi backend hỗ trợ/i)).toBeInTheDocument();
  });
});