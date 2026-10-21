import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { createMockHandlers } from "@/mocks/handlers";
import { createMemoryRepository } from "@/mocks/data/storage";
import type { MockScenario } from "@/mocks/scenarios";
import { server } from "@/mocks/server";
import { leaderTestSession, renderAppRoutes } from "@/test/render";

function openTeam(scenario: MockScenario) {
  server.use(...createMockHandlers(scenario, createMemoryRepository(scenario)));
  renderAppRoutes("/courses/course-se330/team", leaderTestSession);
}

describe("topic section without a registration API", () => {
  it("tells a leader with a draft topic that topics cannot be composed yet, and offers no form", async () => {
    openTeam("student-team-leader-topic-draft");

    expect(await screen.findByText(/Chưa soạn đề tài trên UTask được/, {}, { timeout: 5000 })).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: "Tên đề tài" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Soạn đề tài" })).not.toBeInTheDocument();
  });

  it("keeps the notice away from a topic that is not a draft", async () => {
    openTeam("student-topic-revision-required");

    expect(await screen.findByRole("button", { name: "Chỉnh sửa lại" }, { timeout: 5000 })).toHaveAttribute(
      "aria-disabled",
      "true",
    );
    expect(screen.queryByText(/Chưa soạn đề tài trên UTask được/)).not.toBeInTheDocument();
  });
});
