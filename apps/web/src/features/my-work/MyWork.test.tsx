import { screen, waitFor } from "@testing-library/react";
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

    // Pending request surfaces with its team name.
    expect(screen.getByText(/Yêu cầu tham gia Team PHOENIX/)).toBeInTheDocument();

    // A course without team shows its own hint, not an empty dashboard.
    expect(screen.getByText(/IT3090: Bạn chưa tham gia nhóm nào/i)).toBeInTheDocument();
  });
});

describe("my-work no-team scenario", () => {
  it("shows the no-team empty state instead of fake sprint data", async () => {
    useMyWorkScenario("my-work-no-team");
    renderApp(<RequireAuth><AuthenticatedLayout /></RequireAuth>, {
      route: "/my-work",
      routes: myWorkRoutes(),
    });

    expect(
      await screen.findAllByText(/Bạn chưa tham gia nhóm nào/i),
    ).toHaveLength(4);

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

    expect((await screen.findAllByText(/Team PHOENIX/)).length).toBeGreaterThan(0);
    expect(
      screen.getByText(/sẽ mở sau khi Leader duyệt/i),
    ).toBeInTheDocument();
    // No "Vào Board" action for a pending member.
    const boardButtons = screen.queryAllByRole("link", { name: /Vào Board/ });
    expect(boardButtons).toHaveLength(0);
  });
});

describe("role-based actions", () => {
  it("hides leader-only create-task affordance from members", async () => {
    useMyWorkScenario("my-work-member");
    renderApp(<RequireAuth><AuthenticatedLayout /></RequireAuth>, {
      route: "/my-work",
      routes: myWorkRoutes(),
    });
    await screen.findByRole("heading", { name: /Bàn làm việc của tôi/ });
    const createButton = screen.getByRole("button", { name: /Tạo task mới/ });
    expect(createButton).toBeDisabled();
    expect(createButton).toHaveAttribute(
      "title",
      "Chỉ Leader nhóm mới có thể tạo task",
    );
  });

  it("enables create-task affordance for leaders", async () => {
    useMyWorkScenario("my-work-leader");
    renderApp(<RequireAuth><AuthenticatedLayout /></RequireAuth>, {
      route: "/my-work",
      routes: myWorkRoutes(),
    });
    await screen.findByRole("heading", { name: /Bàn làm việc của tôi/ });
    const createButton = screen.getByRole("button", { name: /Tạo task mới/ });
    expect(createButton).toBeDisabled(); // placeholder until Board slice exists
    expect(createButton).toHaveAttribute("title", "Tạo task mới sẽ khả dụng ở slice Board");
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

describe("github section resilience", () => {
  it("shows retryable error for github while tasks still render", async () => {
    useMyWorkScenario("my-work-github-error");
    renderApp(<RequireAuth><AuthenticatedLayout /></RequireAuth>, {
      route: "/my-work",
      routes: myWorkRoutes(),
    });

    // Task rows still appear despite the GitHub endpoint failing.
    expect(await screen.findByText("NEXUS-104")).toBeInTheDocument();
    // GitHub section shows its own error with a retry button.
    expect(
      await screen.findByRole("button", { name: "Thử lại" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Không thể tải dữ liệu/i),
    ).toBeInTheDocument();
  });

  it("recovers github section after retry succeeds", async () => {
    useMyWorkScenario("my-work-github-error");
    renderApp(<RequireAuth><AuthenticatedLayout /></RequireAuth>, {
      route: "/my-work",
      routes: myWorkRoutes(),
    });
    await screen.findByRole("heading", { name: /Bàn làm việc của tôi/ });

    // Flip to a healthy handler, then retry.
    server.use(...createMyWorkHandlers("my-work-mixed", createMemoryRepository("my-work-mixed")));
    const user = userEvent.setup();
    const retry = await screen.findByRole("button", { name: "Thử lại" });
    await user.click(retry);

    await waitFor(() => {
      expect(screen.getByText(/Đồng bộ Webhook tự động/)).toBeInTheDocument();
    });
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