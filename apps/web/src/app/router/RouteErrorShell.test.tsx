import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { leaderTestSession, renderAppRoutes } from "@/test/render";

vi.mock("@/features/my-work/routes/MyWorkRoute", () => ({
  Component: () => {
    throw new Error("boom");
  },
}));

describe("route errors keep the app shell", () => {
  it("shows the error inside the page area, with retry and a way home, while the user menu stays", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    renderAppRoutes("/my-work", leaderTestSession);

    expect(await screen.findByRole("heading", { name: "Không mở được trang này" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Thử lại" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Về trang chủ" })).toHaveAttribute("href", "/");
    expect(screen.getAllByRole("button", { name: /@utask\.test/ }).length).toBeGreaterThan(0);
  });

  it("sends the demo project's Info tab to the board instead of crashing", async () => {
    const view = renderAppRoutes("/projects/project-nexus/info", leaderTestSession);

    await waitFor(() => expect(view.router.state.location.pathname).toBe("/projects/project-nexus/board"));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
