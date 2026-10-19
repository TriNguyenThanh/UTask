import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { RouteObject } from "react-router-dom";

import { AuthenticatedLayout } from "@/app/layouts/AuthenticatedLayout";
import { RequireAuth } from "@/app/router/RequireAuth";
import { MyWorkPage } from "@/features/my-work/components/MyWorkPage";
import { createMyWorkHandlers } from "@/mocks/handlers/myWork";
import { createMemoryRepository } from "@/mocks/data/storage";
import type { MockScenario } from "@/mocks/scenarios";
import { renderApp } from "@/test/render";
import { server } from "@/mocks/server";

function useMyWorkScenario(scenario: MockScenario) {
  // Runtime handlers share a repository so account-bound fixtures and
  // session mutations (read state, disconnect) behave like the demo app.
  server.use(...createMyWorkHandlers(scenario, createMemoryRepository(scenario)));
}

function myWorkRoutes(): RouteObject[] {
  return [
    { path: "/login", element: <h1>Trang đăng nhập</h1> },
    {
      element: <RequireAuth><AuthenticatedLayout /></RequireAuth>,
      children: [
        { path: "/my-work", element: <MyWorkPage /> },
      ],
    },
  ];
}

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("my-work routing", () => {
  it("redirects anonymous users away from /my-work", async () => {
    renderApp(<RequireAuth><AuthenticatedLayout /></RequireAuth>, {
      route: "/my-work",
      session: null,
      routes: myWorkRoutes(),
    });
    expect(await screen.findByRole("heading", { name: "Trang đăng nhập" })).toBeInTheDocument();
  });

  it("does not render my-work content for anonymous visitors", () => {
    renderApp(<RequireAuth><AuthenticatedLayout /></RequireAuth>, {
      route: "/my-work",
      session: null,
      routes: myWorkRoutes(),
    });
    expect(screen.queryByRole("heading", { name: /Bàn làm việc của tôi/ })).not.toBeInTheDocument();
  });
});

describe("my-work mixed scenario", () => {
  it("renders tasks, sprints and pending state together", async () => {
    useMyWorkScenario("my-work-mixed");
    renderApp(<RequireAuth><AuthenticatedLayout /></RequireAuth>, {
      route: "/my-work",
      routes: myWorkRoutes(),
    });

    expect(
      await screen.findByRole("heading", { name: /Bàn làm việc của tôi/ }),
    ).toBeInTheDocument();

    // Tasks from both assigned projects are aggregated (keys mirror real
    // workspace issues so task links stay valid).
    expect(screen.getAllByText("NEXUS-104").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/DELI-02/).length).toBeGreaterThan(0);

    // One leader course, one member course — both sprints visible.
    expect(screen.getByText(/Team NEXUS · Leader/)).toBeInTheDocument();
    expect(screen.getByText(/Team DELI · Member/)).toBeInTheDocument();

    // The latest-courses list shows each course with its own membership state.
    const courses = screen.getByRole("region", { name: "Môn học" });
    expect(within(courses).getByText("Chờ duyệt")).toBeInTheDocument();
    expect(within(courses).getByText("Cần lập nhóm")).toBeInTheDocument();
    expect(within(courses).getByRole("link", { name: "Kiểm thử Phần mềm SE331" })).toHaveAttribute(
      "href",
      "/courses/course-se331/team",
    );
  });
});

describe("my-work no-team scenario", () => {
  it("shows the no-team empty state instead of fake sprint data", async () => {
    useMyWorkScenario("my-work-no-team");
    renderApp(<RequireAuth><AuthenticatedLayout /></RequireAuth>, {
      route: "/my-work",
      routes: myWorkRoutes(),
    });

    const courses = await screen.findByRole("region", { name: "Môn học" });
    expect(within(courses).getAllByText("Cần lập nhóm")).toHaveLength(4);

    // No fabricated sprint rows.
    expect(screen.queryByText(/Tiến độ Sprint$/)).not.toBeInTheDocument();
    expect(screen.getByText(/Chưa có Sprint nào/)).toBeInTheDocument();
  });
});

describe("my-work pending membership", () => {
  it("blocks board access copy and shows request details", async () => {
    useMyWorkScenario("my-work-pending-membership");
    renderApp(<RequireAuth><AuthenticatedLayout /></RequireAuth>, {
      route: "/my-work",
      routes: myWorkRoutes(),
    });

    const courses = await screen.findByRole("region", { name: "Môn học" });
    expect(within(courses).getAllByText("Chờ duyệt").length).toBeGreaterThan(0);
    // The old pending card with its own copy is gone; Home only lists the course.
    expect(screen.queryByText(/sẽ mở sau khi Leader duyệt/i)).not.toBeInTheDocument();
    // No "Vào Board" action for a pending member.
    const boardButtons = screen.queryAllByRole("link", { name: /Vào Board/ });
    expect(boardButtons).toHaveLength(0);
  });
});

describe("task and sprint interplay", () => {
  it("keeps sprint section visible when today has no tasks", async () => {
    useMyWorkScenario("my-work-empty-tasks");
    renderApp(<RequireAuth><AuthenticatedLayout /></RequireAuth>, {
      route: "/my-work",
      routes: myWorkRoutes(),
    });
    await screen.findByText(/Không có việc gì cần làm trong hôm nay/i);
    // Sprint rows still render.
    expect(screen.getByText(/Sprint 2/)).toBeInTheDocument();
    expect(screen.getByText(/Sprint 1/)).toBeInTheDocument();
  });

  it("surfaces overdue tasks in the overdue tab with a badge count", async () => {
    useMyWorkScenario("my-work-overdue");
    renderApp(<RequireAuth><AuthenticatedLayout /></RequireAuth>, {
      route: "/my-work",
      routes: myWorkRoutes(),
    });
    const user = userEvent.setup();
    const overdueTab = await screen.findByRole("tab", { name: /Quá hạn/ });
    await user.click(overdueTab);

    // The overdue task appears with its overdue due-date text.
    expect(await screen.findByText("NEXUS-111")).toBeInTheDocument();
    expect(screen.getAllByText(/Quá hạn \d+ ngày/).length).toBeGreaterThan(0);
  });
});

describe("home without GitHub activity", () => {
  it("renders tasks and never shows or fails on the GitHub section", async () => {
    useMyWorkScenario("my-work-github-error");
    renderApp(<RequireAuth><AuthenticatedLayout /></RequireAuth>, {
      route: "/my-work",
      routes: myWorkRoutes(),
    });

    expect(await screen.findByText("NEXUS-104")).toBeInTheDocument();
    expect(screen.queryByText(/Hoạt động GitHub/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Đồng bộ Webhook tự động/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Thử lại" })).not.toBeInTheDocument();
  });
});

describe("no courses onboarding", () => {
  it("shows the onboarding empty state", async () => {
    useMyWorkScenario("my-work-no-courses");
    renderApp(<RequireAuth><AuthenticatedLayout /></RequireAuth>, {
      route: "/my-work",
      routes: myWorkRoutes(),
    });
    expect(
      await screen.findByText(/Bạn chưa có môn học trong học kỳ hiện tại/i),
    ).toBeInTheDocument();
    expect(screen.queryByText("NEXUS-12")).not.toBeInTheDocument();
  });
});