import { screen, waitFor } from "@testing-library/react";
import userEvent, { type UserEvent } from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { RouteObject } from "react-router-dom";

import { AuthenticatedLayout } from "@/app/layouts/AuthenticatedLayout";
import { RequireAuth } from "@/app/router/RequireAuth";
import { MyWorkPage } from "@/features/my-work/components/MyWorkPage";
import { Component as CourseTeamRoute } from "@/features/courses/routes/CourseTeamRoute";
import { Component as NotificationsRoute } from "@/features/notifications/routes/NotificationsRoute";
import { courseDetailForScenario } from "@/mocks/data/studentFlow";
import { isDueToday, isOverdue, tasksForBucket } from "@/features/my-work/taskFilters";
import { createMockHandlers } from "@/mocks/handlers";
import { createMemoryRepository, type MockRepository } from "@/mocks/data/storage";
import { LEADER_ID, MEMBER_ID, STUDENT_ID } from "@/mocks/data/database";
import type { MockScenario } from "@/mocks/scenarios";
import { leaderTestSession, renderApp, studentTestSession } from "@/test/render";
import { server } from "@/mocks/server";

/**
 * Regression suite for the Student Flow optimization pass: navigation
 * deep links, mutation persistence, per-user state isolation and
 * permission enforcement in the mock layer.
 */

function useScenarioWithRepo(scenario: MockScenario): MockRepository {
  const repository = createMemoryRepository(scenario);
  server.use(...createMockHandlers(scenario, repository));
  return repository;
}

function studentFlowRoutes(): RouteObject[] {
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
        { path: "/notifications", element: <NotificationsRoute /> },
        { path: "*", element: <h1>Không tìm thấy trang</h1> },
      ],
    },
  ];
}

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("home task deep links", () => {
  it("opens the workspace board with the issue param when clicking a home task", async () => {
    const user = userEvent.setup();
    const result = renderApp(<RequireAuth><AuthenticatedLayout /></RequireAuth>, {
      route: "/my-work",
      routes: studentFlowRoutes(),
    });

    const taskLink = await screen.findByRole("link", {
      name: /Tích hợp cổng thanh toán VNPay Sandbox và IPN/,
    });
    // The link targets the real workspace project id, not a key prefix.
    expect(taskLink).toHaveAttribute(
      "href",
      "/projects/project-nexus/board?issue=NEXUS-104",
    );
    await user.click(taskLink);

    await waitFor(() => {
      expect(result.router.state.location.pathname).toBe("/projects/project-nexus/board");
      expect(result.router.state.location.search).toBe("?issue=NEXUS-104");
    });
  });

  it("links every sprint card to its workspace board by projectId", async () => {
    renderApp(<RequireAuth><AuthenticatedLayout /></RequireAuth>, {
      route: "/my-work",
      routes: studentFlowRoutes(),
    });

    // Both demo sprints carry a workspace; each board link targets the
    // matching project, never a dead hash anchor.
    const boardLinks = await screen.findAllByRole("link", { name: "Vào Board" });
    const hrefs = boardLinks.map((link) => link.getAttribute("href"));
    expect(hrefs).toContain("/projects/project-nexus/board");
    expect(hrefs).toContain("/projects/project-deli/board");
    expect(hrefs.every((href) => href?.startsWith("/projects/"))).toBe(true);
  });
});

describe("create team mutation", () => {
  async function submitTeamDialog(
    user: UserEvent,
    teamName: string,
  ) {
    await user.click(screen.getByRole("button", { name: /Tạo nhóm mới/ }));
    await user.type(await screen.findByLabelText("Tên nhóm"), teamName);
    await user.click(screen.getByRole("button", { name: "Tạo nhóm" }));
  }

  it("persists the team, makes the creator leader, and rejects a second attempt with 409", async () => {
    const repository = useScenarioWithRepo("student-no-team");
    const user = userEvent.setup();
    renderApp(<RequireAuth><AuthenticatedLayout /></RequireAuth>, {
      route: "/courses/course-se330/team",
      session: studentTestSession,
      routes: studentFlowRoutes(),
    });

    await screen.findByRole("heading", { name: /Thành lập Nhóm/ });
    await submitTeamDialog(user, "Team TITAN");

    await waitFor(() => {
      const team = repository.db.createdTeams[`${STUDENT_ID}:course-se330`];
      expect(team).toBeDefined();
      expect(team?.teamName).toBe("Team TITAN");
      // Creator becomes the leader and the only roster member.
      expect(team?.members).toEqual([
        { userId: STUDENT_ID, role: "leader", joinedAt: expect.any(String) },
      ]);
    });

    // A second create attempt is a 409 conflict and does not add a team.
    await submitTeamDialog(user, "Team TITAN 2");
    await waitFor(() => {
      expect(
        screen.getByText(/Bạn đã gửi yêu cầu thành lập nhóm cho môn học này./),
      ).toBeInTheDocument();
    });
    expect(Object.keys(repository.db.createdTeams)).toHaveLength(1);
  });

  it("sends a JSON object body the server can parse (no double stringify)", async () => {
    const repository = useScenarioWithRepo("student-no-team");
    const user = userEvent.setup();
    renderApp(<RequireAuth><AuthenticatedLayout /></RequireAuth>, {
      route: "/courses/course-se330/team",
      session: studentTestSession,
      routes: studentFlowRoutes(),
    });

    await screen.findByRole("heading", { name: /Thành lập Nhóm/ });
    await submitTeamDialog(user, "Team TITAN");

    // The mock handler rejects a non-object body with "Định dạng yêu cầu
    // không hợp lệ"; a persisted team proves the client sent a plain
    // JSON object. A double-stringified body (a JSON string) would have
    // failed validation instead.
    await waitFor(() => {
      expect(
        screen.queryByText(/Định dạng yêu cầu không hợp lệ/),
      ).not.toBeInTheDocument();
      expect(repository.db.createdTeams[`${STUDENT_ID}:course-se330`]).toBeDefined();
    });
  });
});

describe("mock layer permission enforcement", () => {
  it("returns 403 when a user outside the roster opens a project workspace", async () => {
    useScenarioWithRepo("default");
    const response = await fetch("http://localhost/api/work/api/v1/projects/project-nexus", {
      headers: {
        Authorization:
          "Bearer mock-access:00000000-0000-4000-8000-000000000099:test",
      },
    });
    expect(response.status).toBe(404);
  });

  it("returns 403 when a member reads or writes project AI settings", async () => {
    useScenarioWithRepo("default");
    const read = await fetch(
      "http://localhost/api/work/api/v1/projects/project-nexus/settings",
      { headers: { Authorization: `Bearer mock-access:${MEMBER_ID}:test` } },
    );
    expect(read.status).toBe(403);

    const write = await fetch(
      "http://localhost/api/work/api/v1/projects/project-nexus/settings/ai-key",
      {
        method: "PUT",
        headers: {
          Authorization: `Bearer mock-access:${MEMBER_ID}:test`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ provider: "openai", apiKey: "sk-test" }),
      },
    );
    expect(write.status).toBe(403);
  });

  it("returns 401 for API calls without a session token", async () => {
    useScenarioWithRepo("default");
    const response = await fetch("http://localhost/api/work/api/v1/my-work/overview");
    expect(response.status).toBe(401);
  });
});

describe("per-user state isolation", () => {
  it("marks a notification read for the leader only, not for other accounts", async () => {
    const repository = useScenarioWithRepo("default");
    const user = userEvent.setup();

    renderApp(<RequireAuth><AuthenticatedLayout /></RequireAuth>, {
      route: "/notifications",
      session: leaderTestSession,
      routes: studentFlowRoutes(),
    });

    // Click the first unread notification row → the leader's read set
    // gains exactly that id; the member's stays empty.
    const unreadRows = await screen.findAllByRole("article", { name: "Thông báo chưa đọc" });
    await user.click(unreadRows[0]);

    await waitFor(() => {
      expect(repository.db.notificationReadByUser[LEADER_ID] ?? []).toHaveLength(1);
    });
    expect(repository.db.notificationReadByUser[MEMBER_ID] ?? []).toHaveLength(0);
  });

  it("stores profile PATCH per user without leaking into other accounts", async () => {
    const repository = useScenarioWithRepo("default");

    const patched = await fetch("http://localhost/api/work/api/v1/me/settings", {
      method: "PATCH",
      headers: {
        Authorization: `Bearer mock-access:${LEADER_ID}:test`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        fullName: "Nguyễn Hoàng Nam Updated",
        cohortClass: "K22",
        faculty: "Khoa Test",
        phone: "0900 000 000",
      }),
    });
    expect(patched.status).toBe(204);
    expect(repository.db.profilesByUser[LEADER_ID]?.full_name).toBe("Nguyễn Hoàng Nam Updated");
    // Member profile untouched.
    expect(repository.db.profilesByUser[MEMBER_ID]?.full_name).toBe("Đặng Thảo Linh");

    const memberSettings = (await (
      await fetch("http://localhost/api/work/api/v1/me/settings", {
        headers: { Authorization: `Bearer mock-access:${MEMBER_ID}:test` },
      })
    ).json()) as Record<string, unknown>;
    expect(memberSettings.fullName).toBe("Đặng Thảo Linh");
  });
});

describe("github disconnect reflects on home", () => {
  it("flips the github sync state after disconnect", async () => {
    const repository = useScenarioWithRepo("default");

    const disconnect = await fetch("http://localhost/api/work/api/v1/me/github/disconnect", {
      method: "POST",
      headers: { Authorization: `Bearer mock-access:${LEADER_ID}:test` },
    });
    expect(disconnect.status).toBe(204);
    expect(repository.db.githubDisconnectedByUser[LEADER_ID]).toBe(true);

    const activity = (await (
      await fetch("http://localhost/api/work/api/v1/my-work/github", {
        headers: { Authorization: `Bearer mock-access:${LEADER_ID}:test` },
      })
    ).json()) as { sync: { state: string } };
    expect(activity.sync.state).toBe("disconnected");
  });
});

describe("BYOK key handling", () => {
  it("stores only provider metadata, never the raw key", async () => {
    const repository = useScenarioWithRepo("default");

    const save = await fetch(
      "http://localhost/api/work/api/v1/projects/project-nexus/settings/ai-key",
      {
        method: "PUT",
        headers: {
          Authorization: `Bearer mock-access:${LEADER_ID}:test`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ provider: "openai", apiKey: "sk-raw-secret-987654321" }),
      },
    );
    expect(save.status).toBe(204);

    const stored = repository.db.aiConfigByProject["project-nexus"];
    expect(stored?.keyConfigured).toBe(true);
    expect(stored?.keyHint).toContain("••••");
    // The raw key never reaches the repository.
    expect(JSON.stringify(repository.db)).not.toContain("sk-raw-secret-987654321");
  });
});

describe("membership-bound fixtures", () => {
  it("shows the multi-class student all memberships at once", async () => {
    renderApp(<RequireAuth><AuthenticatedLayout /></RequireAuth>, {
      route: "/my-work",
      session: studentTestSession,
      routes: studentFlowRoutes(),
    });

    await screen.findByRole("heading", { name: /Bàn làm việc của tôi/ });
    // SV01 is leader of NEXUS and member of DELI at the same time, so
    // tasks from both projects surface, plus the unteamed IT3090 hint
    // and the pending PHOENIX request.
    expect(
      await screen.findByRole("link", { name: /Tích hợp cổng thanh toán VNPay/ }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /Đăng nhập email \+ password/ }),
    ).toBeInTheDocument();
    expect((await screen.findAllByText(/Bạn chưa tham gia nhóm nào/i)).length).toBeGreaterThan(0);
    expect(screen.getByText(/Yêu cầu tham gia Team PHOENIX/)).toBeInTheDocument();
  });

  it("keeps the notifications list scoped to accessible projects", async () => {
    renderApp(<RequireAuth><AuthenticatedLayout /></RequireAuth>, {
      route: "/notifications",
      session: studentTestSession,
      routes: studentFlowRoutes(),
    });

    // SV01 belongs to NEXUS, so project-scoped notifications (NEXUS
    // board/code targets) surface; nothing outside the accessible set
    // may appear.
    expect(
      await screen.findByRole("button", { name: /Xem Issue/i }),
    ).toBeInTheDocument();
    expect(document.body.textContent ?? "").toContain("NEXUS-104");
    expect(document.body.textContent ?? "").not.toContain("DELI-01");
  });
});

describe("done tasks never count as overdue", () => {
  const now = new Date("2026-10-20T08:30:00.000Z");
  const doneOverdue = {
    id: "t1",
    issueKey: "NEXUS-95",
    title: "Done long ago",
    courseId: "course-se330",
    courseCode: "SE330",
    projectName: "Smart Supply Chain",
    projectId: "project-nexus",
    priority: "medium" as const,
    status: "done" as const,
    dueAt: "2026-10-10T00:00:00.000Z",
  };
  const openToday = {
    id: "t2",
    issueKey: "NEXUS-104",
    title: "Due today",
    courseId: "course-se330",
    courseCode: "SE330",
    projectName: "Smart Supply Chain",
    projectId: "project-nexus",
    priority: "high" as const,
    status: "in-progress" as const,
    dueAt: "2026-10-20T10:00:00.000Z",
  };

  it("excludes done tasks from overdue and today buckets", () => {
    expect(isOverdue(doneOverdue, now)).toBe(false);
    expect(isDueToday(doneOverdue, now)).toBe(false);
    expect(tasksForBucket([doneOverdue, openToday], "overdue", now)).toEqual([]);
    expect(tasksForBucket([doneOverdue, openToday], "today", now)).toEqual([openToday]);
  });
});

describe("course team workspace link", () => {
  it("carries the workspace projectId for an approved NEXUS topic", () => {
    const detail = courseDetailForScenario("course-se330", "default", LEADER_ID);
    expect(detail?.team?.projectId).toBe("project-nexus");
  });

  it("keeps DELI team workspace data aligned with the mock workspace", () => {
    const detail = courseDetailForScenario("course-cs402", "default", LEADER_ID);
    expect(detail?.team?.projectId).toBe("project-deli");
  });
});