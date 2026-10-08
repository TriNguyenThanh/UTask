import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { RouteObject } from "react-router-dom";
import { AuthenticatedLayout } from "@/app/layouts/AuthenticatedLayout";
import { Navigate } from "react-router-dom";
import { Component as NotFoundRoute } from "@/app/router/NotFoundRoute";
import { RequireAuth } from "@/app/router/RequireAuth";
import { Component as ProjectsRoute } from "@/features/projects/routes/ProjectsRoute";
import { Component as ProjectBacklogRoute } from "@/features/projects/routes/ProjectBacklogRoute";
import { Component as ProjectBoardRoute } from "@/features/projects/routes/ProjectBoardRoute";
import { Component as ProjectCodeRoute } from "@/features/projects/routes/ProjectCodeRoute";
import ProjectWorkspaceLayout from "@/features/projects/routes/ProjectWorkspaceLayout";
import { RequireProjectManagePermission } from "@/features/projects/routes/RequireProjectManagePermission";
import { Component as ProjectSettingsRoute } from "@/features/projects/routes/ProjectSettingsRoute";
import { createMockHandlers } from "@/mocks/handlers";
import { createMemoryRepository } from "@/mocks/data/storage";
import type { MockScenario } from "@/mocks/scenarios";
import { server } from "@/mocks/server";
import { renderApp, studentTestSession } from "@/test/render";

function useScenario(scenario: MockScenario) {
  server.use(...createMockHandlers(scenario, createMemoryRepository(scenario)));
}

function routesWithProjectsList(): RouteObject[] {
  return [
    { path: "/login", element: <h1>Trang đang nhap</h1> },
    {
      element: (
        <RequireAuth>
          <AuthenticatedLayout />
        </RequireAuth>
      ),
      children: [
        { path: "/projects", element: <ProjectsRoute /> },
        { path: "*", element: <NotFoundRoute /> },
      ],
    },
  ];
}

function fullRoutes(): RouteObject[] {
  return [
    { path: "/login", element: <h1>Trang đang nhap</h1> },
    {
      element: (
        <RequireAuth>
          <AuthenticatedLayout />
        </RequireAuth>
      ),
      children: [
        { path: "/projects", element: <ProjectsRoute /> },
        {
          path: "/projects/:projectId",
          element: <ProjectWorkspaceLayout />,
          children: [
            { index: true, element: <BacklogRedirect /> },
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
      ],
    },
  ];
}

function BacklogRedirect() {
  return <Navigate to="backlog" replace />;
}

describe("projects list route", () => {
  it("renders the projects list page at /projects, not 404", async () => {
    renderApp(<ProjectsRoute />, {
      route: "/projects",
      routes: routesWithProjectsList(),
    });

    expect(
      await screen.findByRole("heading", { name: "Dự án Đồ án Môn học" }),
    ).toBeInTheDocument();
    expect(screen.queryByText(/404|Không tìm thấy/)).not.toBeInTheDocument();
  });

  it("sidebar Dự án menu navigates to /projects", async () => {
    const user = userEvent.setup();
    const result = renderApp(<ProjectsRoute />, {
      route: "/projects",
      routes: routesWithProjectsList(),
    });

    await screen.findByRole("heading", { name: "Dự án Đồ án Môn học" });
    await user.click(screen.getByRole("link", { name: /^Dự án$/ }));
    await waitFor(() => {
      expect(result.router.state.location.pathname).toBe("/projects");
    });
  });

  it("does not require projectId and skips the project-detail query", async () => {
    renderApp(<ProjectsRoute />, {
      route: "/projects",
      routes: routesWithProjectsList(),
    });

    await screen.findByRole("heading", { name: "Dự án Đồ án Môn học" });
    // The workspace heading must never appear on the list page.
    expect(
      screen.queryByRole("heading", { name: "Backlog & Sprint Planning" }),
    ).not.toBeInTheDocument();
  });

  it("lists NEXUS and DELI from mock data", async () => {
    renderApp(<ProjectsRoute />, {
      route: "/projects",
      routes: routesWithProjectsList(),
    });

    await screen.findByRole("heading", { name: "Dự án Đồ án Môn học" });
    await waitFor(() => {
      expect(screen.getByText(/Smart Supply Chain/i)).toBeInTheDocument();
      expect(
        screen.getByText(/Theo dõi Sức khỏe & Dinh dưỡng/i),
      ).toBeInTheDocument();
    });
  });

  it("filters the list by search query", async () => {
    const user = userEvent.setup();
    renderApp(<ProjectsRoute />, {
      route: "/projects",
      routes: routesWithProjectsList(),
    });

    await screen.findByRole("heading", { name: "Dự án Đồ án Môn học" });
    const searchBox = screen.getByRole("searchbox", {
      name: "Tìm kiếm dự án theo tên, mã môn học hoặc project key",
    });
    await user.type(searchBox, "nexus");
    await waitFor(() => {
      expect(screen.queryByText(/Theo dõi Sức khỏe/)).not.toBeInTheDocument();
      expect(screen.getByText(/Smart Supply Chain/i)).toBeInTheDocument();
    });
  });

  it("clicking NEXUS navigates to its backlog", async () => {
    const user = userEvent.setup();
    const result = renderApp(<ProjectsRoute />, {
      route: "/projects",
      routes: fullRoutes(),
    });

    await screen.findByRole("heading", { name: "Dự án Đồ án Môn học" });
    const nexusLink = await screen.findAllByRole("link", {
      name: /Smart Supply Chain/i,
    });
    await user.click(nexusLink[0]);
    await waitFor(() => {
      expect(result.router.state.location.pathname).toBe(
        "/projects/project-nexus/backlog",
      );
    });
  });

  it("clicking DELI navigates to its backlog", async () => {
    const user = userEvent.setup();
    const result = renderApp(<ProjectsRoute />, {
      route: "/projects",
      routes: fullRoutes(),
    });

    await screen.findByRole("heading", { name: "Dự án Đồ án Môn học" });
    const deliLink = await screen.findAllByRole("link", {
      name: /Theo dõi Sức khỏe/i,
    });
    await user.click(deliLink[0]);
    await waitFor(() => {
      expect(result.router.state.location.pathname).toBe(
        "/projects/project-deli/backlog",
      );
    });
  });

  it("redirects /projects/project-nexus to its backlog", async () => {
    const result = renderApp(<ProjectsRoute />, {
      route: "/projects/project-nexus",
      routes: fullRoutes(),
    });

    await screen.findByRole("heading", { name: "Backlog & Sprint Planning" });
    expect(result.router.state.location.pathname).toBe(
      "/projects/project-nexus/backlog",
    );
  });

  it("shows Project Not Found for an invalid project id", async () => {
    renderApp(<ProjectsRoute />, {
      route: "/projects/invalid-project/backlog",
      routes: fullRoutes(),
    });

    expect(
      await screen.findByRole("heading", { name: "Không tìm thấy dự án" }, { timeout: 4000 }),
    ).toBeInTheDocument();
  });

  it("shows an empty state, not 404, when the student has no projects", async () => {
    useScenario("student-empty");
    renderApp(<ProjectsRoute />, {
      route: "/projects",
      routes: routesWithProjectsList(),
    });

    await screen.findByRole("heading", { name: "Dự án Đồ án Môn học" });
    await waitFor(() => {
      expect(
        screen.getByText(/Chưa có dự án đồ án/),
      ).toBeInTheDocument();
    });
    expect(screen.queryByText(/404/)).not.toBeInTheDocument();
  });

  it("highlights the Dự án menu item on both list and workspace pages", async () => {
    renderApp(<ProjectsRoute />, {
      route: "/projects",
      routes: routesWithProjectsList(),
    });

    await screen.findByRole("heading", { name: "Dự án Đồ án Môn học" });
    expect(screen.getByRole("link", { name: /^Dự án$/ }).className).toContain(
      "bg-accent",
    );
  });

  it("has no project card active at /projects", async () => {
    renderApp(<ProjectsRoute />, {
      route: "/projects",
      routes: routesWithProjectsList(),
    });

    await screen.findByRole("heading", { name: "Dự án Đồ án Môn học" });
    await waitFor(() => {
      expect(screen.getByText(/Smart Supply Chain/i)).toBeInTheDocument();
    });
    const nexusCard = screen
      .getByText(/Smart Supply Chain/i)
      .closest("article");
    expect(nexusCard?.className).not.toContain("ring-primary");
  });
});