import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { leaderTestSession, renderAppRoutes } from "@/test/render";

const BOARD = "/projects/project-nexus/board";
const BACKLOG = "/projects/project-nexus/backlog";

describe("issue panel and browser history", () => {
  it("opens an issue on the Backlog itself and closes with Esc without leaving it", async () => {
    const user = userEvent.setup();
    const view = renderAppRoutes(BACKLOG, leaderTestSession);

    await user.click((await screen.findAllByRole("button", { name: /^Mở issue NEXUS-104/ }, { timeout: 5000 }))[0]);

    expect(await screen.findByRole("dialog", { name: "Chi tiết issue NEXUS-104" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Quay lại Backlog" })).toBeInTheDocument();
    expect(view.router.state.location.pathname).toBe(BACKLOG);
    expect(view.router.state.location.search).toBe("?issue=NEXUS-104");

    await user.keyboard("{Escape}");
    await waitFor(() => expect(view.router.state.location.search).toBe(""));
    expect(view.router.state.location.pathname).toBe(BACKLOG);
  });

  it("leaves no extra history entry when the panel opened from the Board is closed", async () => {
    const user = userEvent.setup();
    const view = renderAppRoutes(BOARD, leaderTestSession);
    const initialKey = view.router.state.location.key;

    await user.click(await screen.findByRole("button", { name: /^Mở chi tiết issue NEXUS-101/ }, { timeout: 5000 }));
    await screen.findByRole("dialog", { name: "Chi tiết issue NEXUS-101" });
    expect(view.router.state.location.key).not.toBe(initialKey);

    await user.keyboard("{Escape}");
    await waitFor(() => expect(view.router.state.location.key).toBe(initialKey));
    expect(view.router.state.location.search).toBe("");
  });

  it("closes a deep-linked panel by replacing the URL, since there is no earlier Board entry to go back to", async () => {
    const user = userEvent.setup();
    const view = renderAppRoutes(`${BOARD}?issue=NEXUS-101`, leaderTestSession);

    await screen.findByRole("dialog", { name: "Chi tiết issue NEXUS-101" }, { timeout: 5000 });
    await user.keyboard("{Escape}");

    await waitFor(() => expect(view.router.state.location.search).toBe(""));
    expect(view.router.state.historyAction).toBe("REPLACE");
    expect(view.router.state.location.pathname).toBe(BOARD);
  });
});
