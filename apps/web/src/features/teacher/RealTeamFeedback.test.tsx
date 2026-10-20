import { screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { RealTeamFeedback } from "@/features/teacher/components/RealTeamFeedback";
import { createMemoryRepository } from "@/mocks/data/storage";
import { createAuthHandlers } from "@/mocks/handlers/auth";
import { server } from "@/mocks/server";
import { renderApp, teacherTestSession } from "@/test/render";
import { buildProject, workHandlers } from "@/test/workHandlers";

afterEach(() => {
  vi.unstubAllEnvs();
  server.events.removeAllListeners();
});

function mount(archivedAt: string | null) {
  const urls: string[] = [];
  server.events.on("request:end", ({ request }) => urls.push(new URL(request.url).pathname));
  vi.stubEnv("VITE_REAL_SERVICES", "auth,classroom,work");
  server.use(
    ...workHandlers({ projects: [buildProject({ id: "project-1", archived_at: archivedAt })], comments: [] }),
    ...createAuthHandlers("default", createMemoryRepository("default")),
  );
  renderApp(<RealTeamFeedback projectId="project-1" members={[]} />, { session: teacherTestSession });
  return urls;
}

describe("RealTeamFeedback", () => {
  it("lets a teacher write feedback on a live project", async () => {
    mount(null);
    expect(await screen.findByLabelText("Viết bình luận", undefined, { timeout: 5000 })).toBeInTheDocument();
  });

  it("offers no composer on an archived project, where the server rejects writes", async () => {
    const urls = mount("2026-09-01T00:00:00Z");
    expect(await screen.findByText("Phản hồi", undefined, { timeout: 5000 })).toBeInTheDocument();
    await waitFor(() => expect(urls).toContain("/api/work/projects/project-1/"));
    await waitFor(() => expect(urls).toContain("/api/work/projects/project-1/comments/"));
    expect(screen.queryByLabelText("Viết bình luận")).not.toBeInTheDocument();
  });
});
