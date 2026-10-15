import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";

import { server } from "@/mocks/server";
import {
  leaderTestSession,
  memberTestSession,
  renderAppRoutes,
  teacherTestSession,
} from "@/test/render";

const BOARD = "/projects/project-nexus/board";

function column(name: string) {
  return screen.getByRole("region", { name });
}

async function openMenu(user: ReturnType<typeof userEvent.setup>, key: string) {
  // The first render pulls in the lazy routes, which can take longer than the 1s default.
  await user.click(
    await screen.findByRole("button", { name: `Thao tác cho ${key}` }, { timeout: 5000 }),
  );
}

describe("Kanban board: moving a card without dragging", () => {
  it("moves a card to another column from its menu, announces it and returns focus", async () => {
    const user = userEvent.setup();
    renderAppRoutes(BOARD, leaderTestSession);

    await openMenu(user, "NEXUS-101");
    await user.click(await screen.findByRole("menuitem", { name: "Chuyển sang Đang làm (In Progress)" }));

    await waitFor(() =>
      expect(within(column("Đang làm (In Progress)")).getByText("NEXUS-101")).toBeInTheDocument(),
    );
    expect(within(column("Cần làm (To Do)")).queryByText("NEXUS-101")).not.toBeInTheDocument();

    await waitFor(() =>
      expect(document.body.textContent).toContain(
        "NEXUS-101 đã chuyển từ Cần làm sang Đang làm",
      ),
    );
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Thao tác cho NEXUS-101" })).toHaveFocus(),
    );
  });

  it("keeps the move after the board reloads from the server", async () => {
    const user = userEvent.setup();
    const { queryClient } = renderAppRoutes(BOARD, leaderTestSession);

    await openMenu(user, "NEXUS-101");
    await user.click(await screen.findByRole("menuitem", { name: "Chuyển sang Hoàn thành (Done)" }));
    await waitFor(() =>
      expect(within(column("Hoàn thành (Done)")).getByText("NEXUS-101")).toBeInTheDocument(),
    );

    await queryClient.invalidateQueries();
    await waitFor(() =>
      expect(within(column("Hoàn thành (Done)")).getByText("NEXUS-101")).toBeInTheDocument(),
    );
  });

  it("puts a card back and says why when the server answers 409", async () => {
    server.use(
      http.post("/api/work/api/v1/projects/:projectId/issues/:issueKey/move", () =>
        HttpResponse.json({ detail: "stale" }, { status: 409 }),
      ),
    );
    const user = userEvent.setup();
    renderAppRoutes(BOARD, leaderTestSession);

    await openMenu(user, "NEXUS-101");
    await user.click(await screen.findByRole("menuitem", { name: "Chuyển sang Đang làm (In Progress)" }));

    expect(
      (await screen.findAllByText("Issue vừa được người khác cập nhật. Bảng đã được tải lại."))
        .length,
    ).toBeGreaterThan(0);
    await waitFor(() =>
      expect(within(column("Cần làm (To Do)")).getByText("NEXUS-101")).toBeInTheDocument(),
    );
  });

  it("reorders inside a column from the menu", async () => {
    const user = userEvent.setup();
    renderAppRoutes(BOARD, leaderTestSession);

    const titlesIn = (name: string) =>
      within(column(name))
        .getAllByRole("article")
        .map((card) => card.getAttribute("data-issue-key"));

    await waitFor(() => expect(titlesIn("Cần làm (To Do)")).toEqual(["NEXUS-101", "NEXUS-102"]));
    await openMenu(user, "NEXUS-102");
    await user.click(await screen.findByRole("menuitem", { name: "Lên đầu danh sách" }));

    await waitFor(() => expect(titlesIn("Cần làm (To Do)")).toEqual(["NEXUS-102", "NEXUS-101"]));
  });
});

describe("Kanban board: blocked flag", () => {
  it("asks for a reason, then marks the card blocked", async () => {
    const user = userEvent.setup();
    renderAppRoutes(BOARD, leaderTestSession);

    await openMenu(user, "NEXUS-101");
    await user.click(await screen.findByRole("menuitem", { name: "Đánh dấu bị chặn…" }));

    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Đánh dấu bị chặn" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Vui lòng nêu lý do");

    await user.type(within(dialog).getByLabelText("Lý do"), "Chờ thiết kế ERD");
    await user.click(within(dialog).getByRole("button", { name: "Đánh dấu bị chặn" }));

    await waitFor(() => {
      const card = within(column("Cần làm (To Do)")).getByText("NEXUS-101").closest("article")!;
      expect(within(card).getByText("Bị chặn")).toBeInTheDocument();
    });
  });

  it("shows a card that was blocked from the start and lets the leader unblock it", async () => {
    const user = userEvent.setup();
    renderAppRoutes(BOARD, leaderTestSession);

    const card = (await screen.findByText("NEXUS-102")).closest("article")!;
    expect(within(card).getByText("Bị chặn")).toBeInTheDocument();

    await openMenu(user, "NEXUS-102");
    await user.click(await screen.findByRole("menuitem", { name: "Bỏ đánh dấu bị chặn" }));
    await waitFor(() =>
      expect(
        within(screen.getByText("NEXUS-102").closest("article")!).queryByText("Bị chặn"),
      ).not.toBeInTheDocument(),
    );
  });
});

describe("Kanban board: who may do what", () => {
  it("gives a member menus only on their own tasks, with no ordering items", async () => {
    const user = userEvent.setup();
    renderAppRoutes(BOARD, memberTestSession);

    await screen.findByText("NEXUS-104");
    expect(screen.getByRole("button", { name: "Thao tác cho NEXUS-101" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Thao tác cho NEXUS-105" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Thao tác cho NEXUS-104" })).not.toBeInTheDocument();

    await openMenu(user, "NEXUS-101");
    expect(await screen.findByRole("menuitem", { name: "Chuyển sang Đang làm (In Progress)" })).toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: "Lên đầu danh sách" })).not.toBeInTheDocument();
  });

  it("gives an instructor no way to change anything", async () => {
    renderAppRoutes(BOARD, teacherTestSession);

    await screen.findByText("NEXUS-104");
    expect(screen.queryByRole("button", { name: /^Thao tác cho/ })).not.toBeInTheDocument();
  });

  it("is read-only when the demo writes are off", async () => {
    vi.stubEnv("VITE_ENABLE_MOCKS", "false");
    renderAppRoutes(BOARD, leaderTestSession);

    await screen.findByText("NEXUS-104");
    expect(screen.queryByRole("button", { name: /^Thao tác cho/ })).not.toBeInTheDocument();
  });
});

function isDraggable(key: string) {
  return screen.getByText(key).closest("article")!.parentElement!.getAttribute("draggable") === "true";
}

describe("Kanban board: drag registration follows the permissions", () => {
  it("makes every card draggable for the leader, with a grip on each", async () => {
    renderAppRoutes(BOARD, leaderTestSession);

    await screen.findByText("NEXUS-104");
    for (const key of ["NEXUS-101", "NEXUS-104", "NEXUS-98"]) expect(isDraggable(key)).toBe(true);
    expect(screen.getAllByTitle("Kéo để di chuyển").length).toBe(
      screen.getAllByRole("article").length,
    );
  });

  it("makes only a member's own cards draggable", async () => {
    renderAppRoutes(BOARD, memberTestSession);

    await screen.findByText("NEXUS-104");
    expect(isDraggable("NEXUS-101")).toBe(true);
    expect(isDraggable("NEXUS-105")).toBe(true);
    expect(isDraggable("NEXUS-104")).toBe(false);
    expect(screen.getAllByTitle("Kéo để di chuyển")).toHaveLength(2);
  });

  it("makes nothing draggable for an instructor or when the demo writes are off", async () => {
    const { unmount } = renderAppRoutes(BOARD, teacherTestSession);
    await screen.findByText("NEXUS-104");
    expect(isDraggable("NEXUS-104")).toBe(false);
    expect(screen.queryByTitle("Kéo để di chuyển")).not.toBeInTheDocument();
    unmount();

    vi.stubEnv("VITE_ENABLE_MOCKS", "false");
    renderAppRoutes(BOARD, leaderTestSession);
    await screen.findByText("NEXUS-104");
    expect(isDraggable("NEXUS-104")).toBe(false);
  });
});

describe("Kanban board: filters live in the URL", () => {
  it("applies the filters found in the address", async () => {
    renderAppRoutes(`${BOARD}?blocked=1`, leaderTestSession);

    await screen.findByText("NEXUS-102");
    expect(screen.queryByText("NEXUS-101")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Bị chặn" })).toHaveAttribute("aria-pressed", "true");
  });

  it("writes a chosen filter to the address and keeps the open issue", async () => {
    const user = userEvent.setup();
    const { router } = renderAppRoutes(`${BOARD}?issue=NEXUS-104`, leaderTestSession);

    await screen.findByRole("dialog", { name: "Chi tiết issue NEXUS-104" });
    await user.click(screen.getByRole("button", { name: "Quá hạn" }));

    await waitFor(() => expect(router.state.location.search).toContain("overdue=1"));
    expect(router.state.location.search).toContain("issue=NEXUS-104");
  });

  it("filters overdue cards: only unfinished ones past their due date", async () => {
    renderAppRoutes(`${BOARD}?overdue=1`, leaderTestSession);

    await screen.findByText("NEXUS-102");
    expect(screen.getByText("NEXUS-98")).toBeInTheDocument();
    expect(screen.queryByText("NEXUS-101")).not.toBeInTheDocument();
  });
});

describe("Issue panel status", () => {
  it("lets the leader change the status from the panel", async () => {
    const user = userEvent.setup();
    renderAppRoutes(`${BOARD}?issue=NEXUS-101`, leaderTestSession);

    const select = await screen.findByLabelText("Trạng thái");
    await waitFor(() => expect(select).toBeEnabled());
    await user.selectOptions(select, "review");

    await waitFor(() =>
      expect(within(column("Chờ Review (In Review)")).getByText("NEXUS-101")).toBeInTheDocument(),
    );
  });

  it("keeps the status read-only for an instructor", async () => {
    renderAppRoutes(`${BOARD}?issue=NEXUS-101`, teacherTestSession);

    const select = await screen.findByLabelText("Trạng thái");
    expect(select).toBeDisabled();
  });
});
