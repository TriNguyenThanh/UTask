import { screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { RealTeamProgress } from "@/features/teacher/components/RealTeamProgress";
import { createMemoryRepository } from "@/mocks/data/storage";
import { createAuthHandlers } from "@/mocks/handlers/auth";
import { server } from "@/mocks/server";
import { renderApp, teacherTestSession } from "@/test/render";
import { buildDashboard, buildProgress, buildProject, workHandlers } from "@/test/workHandlers";

afterEach(() => vi.unstubAllEnvs());

function mount(dashboard?: ReturnType<typeof buildDashboard>) {
  vi.stubEnv("VITE_REAL_SERVICES", "auth,classroom,work");
  server.use(
    ...workHandlers({ projects: [buildProject({ id: "project-1" })], dashboard }),
    ...createAuthHandlers("default", createMemoryRepository("default")),
  );
  renderApp(<RealTeamProgress projectId="project-1" />, { session: teacherTestSession });
}

describe("RealTeamProgress", () => {
  it("shows the server's totals as given", async () => {
    const base = buildDashboard();
    mount({ ...base, totals: { ...base.totals, ...buildProgress({ task_count: 12, overdue_task_count: 3, blocked_task_count: 1, completion_percent: 25 }).totals } });
    expect(await screen.findByText("25%")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
  });

  it("says there is no work yet instead of 0% when there is nothing to divide", async () => {
    const base = buildDashboard();
    mount({ ...base, totals: { ...base.totals, completion_percent: null } });
    expect(await screen.findByText("Chưa có việc")).toBeInTheDocument();
  });

  it("reports a load failure in the card only", async () => {
    mount(undefined);
    expect(await screen.findByRole("alert")).toHaveTextContent("Không tải được tiến độ dự án.");
  });
});
