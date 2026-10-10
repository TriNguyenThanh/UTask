import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { RouteObject } from "react-router-dom";

import { AuthenticatedLayout } from "@/app/layouts/AuthenticatedLayout";
import { Component as NotFoundRoute } from "@/app/router/NotFoundRoute";
import { RequireAuth } from "@/app/router/RequireAuth";
import { MyWorkPage } from "@/features/my-work/components/MyWorkPage";
import { Component as CourseTeamRoute } from "@/features/courses/routes/CourseTeamRoute";
import { Component as ProjectBacklogRoute } from "@/features/projects/routes/ProjectBacklogRoute";
import { Component as ProjectBoardRoute } from "@/features/projects/routes/ProjectBoardRoute";
import { Component as ProjectCodeRoute } from "@/features/projects/routes/ProjectCodeRoute";
import ProjectWorkspaceLayout from "@/features/projects/routes/ProjectWorkspaceLayout";
import { RequireProjectManagePermission } from "@/features/projects/routes/RequireProjectManagePermission";
import { Component as ProjectSettingsRoute } from "@/features/projects/routes/ProjectSettingsRoute";
import { renderApp, studentTestSession } from "@/test/render";

/**
 * Multi-membership access suite: SV01 (`student@utask.test`) belongs to
 * several classes at once with different roles per class —
 *   IT3090: no team          (class A)
 *   SE330 : leader, team NEXUS (class B)
 *   CS402 : member, team DELI  (class C)
 *   SE331 : pending request to team PHOENIX
 * Every flow below runs in ONE session: no logout, no second login. The
 * UI must derive the role from the opened resource, never from a global
 * account flag.
 */
function multiMembershipRoutes(): RouteObject[] {
  return [
    { path: "/login", element: <h1>Trang đăng nhập</h1> },
    {
      element: (
        <RequireAuth>
          <AuthenticatedLayout />
        </RequireAuth>
      ),
      children: [
        { path: "/my-work", element: <MyWorkPage /> },
        { path: "/courses/:courseId/team", element: <CourseTeamRoute /> },
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
        { path: "*", element: <NotFoundRoute /> },
      ],
    },
  ];
}

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("multi-membership access (SV01, one session)", () => {
  it("shows all four class memberships on Home in a single glance", async () => {
    renderApp(<RequireAuth><AuthenticatedLayout /></RequireAuth>, {
      route: "/my-work",
      session: studentTestSession,
      routes: multiMembershipRoutes(),
    });

    await screen.findByRole("heading", { name: /Bàn làm việc của tôi/ });
    // Sprint cards expose the per-class role, not a global account role.
    expect(screen.getByText(/Team NEXUS · Leader/)).toBeInTheDocument();
    expect(screen.getByText(/Team DELI · Member/)).toBeInTheDocument();
    // Unteamed class A and pending request remain visible too.
    expect(screen.getByText(/Bạn chưa tham gia nhóm nào/i)).toBeInTheDocument();
    expect(screen.getByText(/Yêu cầu tham gia Team PHOENIX/)).toBeInTheDocument();
  });

  it("deep-links into NEXUS and shows the leader UI there", async () => {
    renderApp(<RequireAuth><AuthenticatedLayout /></RequireAuth>, {
      route: "/projects/project-nexus/backlog",
      session: studentTestSession,
      routes: multiMembershipRoutes(),
    });

    expect(
      await screen.findByRole("heading", { name: "Backlog & Sprint Planning" }),
    ).toBeInTheDocument();
    // SV01 leads NEXUS: leader-only workspace actions are present.
    expect(screen.getByText(/Tạo Epic/i)).toBeInTheDocument();
    expect(screen.getByText(/AI ước lượng/i)).toBeInTheDocument();
  });

  it("opens the NEXUS settings page because SV01 is its leader", async () => {
    renderApp(<RequireAuth><AuthenticatedLayout /></RequireAuth>, {
      route: "/projects/project-nexus/settings",
      session: studentTestSession,
      routes: multiMembershipRoutes(),
    });

    expect(
      await screen.findByRole("heading", { name: /Quyền hạn trong dự án/ }),
    ).toBeInTheDocument();
  });

  it("deep-links into DELI and shows the member UI there", async () => {
    renderApp(<RequireAuth><AuthenticatedLayout /></RequireAuth>, {
      route: "/projects/project-deli/backlog",
      session: studentTestSession,
      routes: multiMembershipRoutes(),
    });

    expect(await screen.findByText(/DELI-02/)).toBeInTheDocument();
    // Member in CS402: leader-only actions stay hidden in this workspace.
    expect(screen.queryByText(/Hoàn thành Sprint/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/AI ước lượng/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Tạo Epic/i)).not.toBeInTheDocument();
  });

  it("flips between leader and member UI within one session via the sidebar", async () => {
    const user = userEvent.setup();
    renderApp(<RequireAuth><AuthenticatedLayout /></RequireAuth>, {
      route: "/projects/project-nexus/backlog",
      session: studentTestSession,
      routes: multiMembershipRoutes(),
    });

    expect(
      await screen.findByRole("heading", { name: "Backlog & Sprint Planning" }),
    ).toBeInTheDocument();
    expect(screen.getByText(/Tạo Epic/i)).toBeInTheDocument();

    // Sidebar → CS402 (member workspace): leader-only actions disappear.
    await user.click(screen.getByRole("link", { name: /CS402/i }));
    await screen.findByRole("heading", { name: "Backlog & Sprint Planning" });
    await waitFor(() => {
      expect(screen.queryByText(/Tạo Epic/i)).not.toBeInTheDocument();
    });
    expect(screen.getByText(/DELI-02/)).toBeInTheDocument();

    // Back to SE330 (leader workspace) without re-logging in.
    await user.click(screen.getByRole("link", { name: /SE330/i }));
    await screen.findByRole("heading", { name: "Backlog & Sprint Planning" });
    await waitFor(() => {
      expect(screen.getByText(/Tạo Epic/i)).toBeInTheDocument();
    });
  });

  it("blocks the DELI settings page because SV01 is only a member there", async () => {
    renderApp(<RequireAuth><AuthenticatedLayout /></RequireAuth>, {
      route: "/projects/project-deli/settings",
      session: studentTestSession,
      routes: multiMembershipRoutes(),
    });

    expect(
      await screen.findByRole("heading", { name: /Không đủ quyền truy cập/ }),
    ).toBeInTheDocument();
  });

  it("opens the unteamed IT3090 course in Team Formation view", async () => {
    renderApp(<RequireAuth><AuthenticatedLayout /></RequireAuth>, {
      route: "/courses/course-it3090/team",
      session: studentTestSession,
      routes: multiMembershipRoutes(),
    });

    expect(
      await screen.findByRole("heading", { name: /Thành lập Nhóm/ }),
    ).toBeInTheDocument();
    expect(screen.getAllByText(/Đồ án IoT/).length).toBeGreaterThan(0);
  });

  it("keeps foreign and archived projects out of reach", async () => {
    renderApp(<RequireAuth><AuthenticatedLayout /></RequireAuth>, {
      route: "/projects/project-legacy/backlog",
      session: studentTestSession,
      routes: multiMembershipRoutes(),
    });
    expect(
      await screen.findByRole("heading", { name: "Không tìm thấy dự án" }, { timeout: 4000 }),
    ).toBeInTheDocument();
  });

  it("sums up Home: enrollments of all classes plus tasks from both teams", async () => {
    renderApp(<RequireAuth><AuthenticatedLayout /></RequireAuth>, {
      route: "/my-work",
      session: studentTestSession,
      routes: multiMembershipRoutes(),
    });

    await screen.findByRole("heading", { name: /Bàn làm việc của tôi/ });
    // All four enrollments surface with their per-class status.
    expect(screen.getAllByText(/IT3090/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/SE330/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/CS402/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/SE331/i).length).toBeGreaterThan(0);
    // Tasks come from both workspaces SV01 belongs to.
    expect(
      await screen.findByRole("link", { name: /Tích hợp cổng thanh toán VNPay/ }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /Đăng nhập email \+ password/ }),
    ).toBeInTheDocument();
  });
});