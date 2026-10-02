import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { RouteObject } from "react-router-dom";

import { AuthenticatedLayout } from "@/app/layouts/AuthenticatedLayout";
import { Component as NotFoundRoute } from "@/app/router/NotFoundRoute";
import { RequireAuth } from "@/app/router/RequireAuth";
import { Component as ProjectBacklogRoute } from "@/features/projects/routes/ProjectBacklogRoute";
import { Component as ProjectBoardRoute } from "@/features/projects/routes/ProjectBoardRoute";
import { Component as ProjectCodeRoute } from "@/features/projects/routes/ProjectCodeRoute";
import ProjectWorkspaceLayout from "@/features/projects/routes/ProjectWorkspaceLayout";
import { RequireProjectManagePermission } from "@/features/projects/routes/RequireProjectManagePermission";
import { Component as ProjectSettingsRoute } from "@/features/projects/routes/ProjectSettingsRoute";
import { renderApp, memberTestSession } from "@/test/render";

function workspaceRoutes(): RouteObject[] {
  return [
    {
      element: (
        <RequireAuth>
          <AuthenticatedLayout />
        </RequireAuth>
      ),
      children: [
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

describe("project workspace layout", () => {
  it("shows the shared header and navigation on backlog", async () => {
    renderApp(<ProjectWorkspaceLayout />, {
      route: "/projects/project-nexus/backlog",
      routes: workspaceRoutes(),
    });
    expect(
      await screen.findByRole("heading", { name: "Backlog & Sprint Planning" }),
    ).toBeInTheDocument();
    expect(screen.getByText(/GVHD: TS\. Trần Minh Đức/)).toBeInTheDocument();
    expect(
      screen.getByRole("navigation", { name: "Project navigation" }),
    ).toBeInTheDocument();
  });

  it("shows the same header and navigation on board with board heading", async () => {
    renderApp(<ProjectWorkspaceLayout />, {
      route: "/projects/project-nexus/board",
      routes: workspaceRoutes(),
    });

    expect(
      await screen.findByRole("heading", { name: "Bảng công việc Sprint" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("navigation", { name: "Project navigation" }),
    ).toBeInTheDocument();
  });

  it("shows the same header and navigation on code", async () => {
    renderApp(<ProjectWorkspaceLayout />, {
      route: "/projects/project-nexus/code",
      routes: workspaceRoutes(),
    });

    expect(
      await screen.findByRole("heading", { name: "Mã nguồn & GitHub" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("navigation", { name: "Project navigation" }),
    ).toBeInTheDocument();
  });

  it("renders navigation exactly once per route", async () => {
    renderApp(<ProjectWorkspaceLayout />, {
      route: "/projects/project-nexus/backlog",
      routes: workspaceRoutes(),
    });

    await screen.findByRole("heading", { name: "Backlog & Sprint Planning" });
    expect(
      screen.getAllByRole("navigation", { name: "Project navigation" }),
    ).toHaveLength(1);
  });

  it("marks the active tab from the pathname", async () => {
    renderApp(<ProjectWorkspaceLayout />, {
      route: "/projects/project-nexus/code",
      routes: workspaceRoutes(),
    });

    await screen.findByRole("heading", { name: "Mã nguồn & GitHub" });
    const activeTab = screen.getByRole("link", { name: "Mã nguồn" });
    expect(activeTab).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Backlog" })).not.toHaveAttribute(
      "aria-current",
    );
  });

  it("navigates client-side from backlog to board keeping projectId", async () => {
    const user = userEvent.setup();
    const result = renderApp(<ProjectWorkspaceLayout />, {
      route: "/projects/project-nexus/backlog",
      routes: workspaceRoutes(),
    });

    await screen.findByRole("heading", { name: "Backlog & Sprint Planning" });
    await user.click(screen.getByRole("link", { name: "Bảng công việc" }));

    expect(
      await screen.findByRole("heading", { name: "Bảng công việc Sprint" }),
    ).toBeInTheDocument();
    expect(result.router.state.location.pathname).toBe(
      "/projects/project-nexus/board",
    );
  });

  it("navigates from board to code keeping projectId", async () => {
    const user = userEvent.setup();
    const result = renderApp(<ProjectWorkspaceLayout />, {
      route: "/projects/project-nexus/board",
      routes: workspaceRoutes(),
    });

    await screen.findByRole("heading", { name: "Bảng công việc Sprint" });
    await user.click(screen.getByRole("link", { name: "Mã nguồn" }));

    expect(
      await screen.findByRole("heading", { name: "Mã nguồn & GitHub" }),
    ).toBeInTheDocument();
    expect(result.router.state.location.pathname).toBe(
      "/projects/project-nexus/code",
    );
  });

  it("hides the settings tab from a member", async () => {
    renderApp(<ProjectWorkspaceLayout />, {
      route: "/projects/project-deli/backlog",
      session: memberTestSession,
      routes: workspaceRoutes(),
    });

    await screen.findByRole("heading", { name: "Backlog & Sprint Planning" });
    expect(
      screen.queryByRole("link", { name: "Cài đặt dự án" }),
    ).not.toBeInTheDocument();
  });

  it("shows Forbidden when a member opens settings directly", async () => {
    renderApp(<ProjectWorkspaceLayout />, {
      route: "/projects/project-deli/settings",
      session: memberTestSession,
      routes: workspaceRoutes(),
    });

    expect(
      await screen.findByRole("heading", { name: /Không đủ quyền truy cập/ }),
    ).toBeInTheDocument();
  });

  it("keeps project navigation visible under the issue panel", async () => {
    renderApp(<ProjectWorkspaceLayout />, {
      route: "/projects/project-nexus/board?issue=NEXUS-104",
      routes: workspaceRoutes(),
    });

    await screen.findByRole("heading", { name: "Bảng công việc Sprint" });
    // Panel opens without unmounting the layout navigation.
    expect(
      screen.getByRole("navigation", { name: "Project navigation" }),
    ).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText(/VNPay/i)).toBeInTheDocument();
    });
  });

  it("keeps the global Dự án nav active inside a project", async () => {
    renderApp(<ProjectWorkspaceLayout />, {
      route: "/projects/project-nexus/board",
      routes: workspaceRoutes(),
    });

    const projectsNav = await screen.findByRole("link", { name: /Dự án/ });
    expect(projectsNav.className).toContain("bg-accent");
  });
});

describe("sidebar project destination", () => {
  it("links a ready project course to its backlog", async () => {
    renderApp(<ProjectWorkspaceLayout />, {
      route: "/projects/project-nexus/backlog",
      routes: workspaceRoutes(),
    });

    await screen.findByRole("heading", { name: "Backlog & Sprint Planning" });
    const sidebarLink = screen.getByRole("link", {
      name: /SE330 — Đồ án Chuyên ngành SE330/i,
    });
    expect(sidebarLink).toHaveAttribute("href", "/projects/project-nexus/backlog");
  });

  it("links an unteamed course to the course team page", async () => {
    renderApp(<ProjectWorkspaceLayout />, {
      route: "/projects/project-nexus/backlog",
      routes: workspaceRoutes(),
    });

    await screen.findByRole("heading", { name: "Backlog & Sprint Planning" });
    const sidebarLink = screen.getByRole("link", {
      name: /IT3090/i,
    });
    expect(sidebarLink).toHaveAttribute(
      "href",
      "/courses/course-it3090/team",
    );
  });

  it("links a pending course to the course team page", async () => {
    renderApp(<ProjectWorkspaceLayout />, {
      route: "/projects/project-nexus/backlog",
      routes: workspaceRoutes(),
    });

    await screen.findByRole("heading", { name: "Backlog & Sprint Planning" });
    const sidebarLink = screen.getByRole("link", {
      name: /SE331/i,
    });
    expect(sidebarLink).toHaveAttribute(
      "href",
      "/courses/course-se331/team",
    );
  });

  it("keeps the project course active across every project module", async () => {
    for (const modulePath of ["board", "code"]) {
      const { unmount } = renderApp(<ProjectWorkspaceLayout />, {
        route: `/projects/project-nexus/${modulePath}`,
        routes: workspaceRoutes(),
      });
      await screen.findByRole("heading", { name: /Sprint|GitHub/ });
      const sidebarLink = screen.getByRole("link", {
        name: /SE330 — Đồ án Chuyên ngành SE330/i,
      });
      expect(sidebarLink.className).toContain("border-primary");
      unmount();
    }
  });
});