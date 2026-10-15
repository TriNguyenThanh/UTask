import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import {
  leaderTestSession,
  memberTestSession,
  renderAppRoutes,
  teacherTestSession,
} from "@/test/render";

const BACKLOG = "/projects/project-nexus/backlog";

function section(heading: RegExp) {
  return screen.getByRole("heading", { name: heading }).closest("section")!;
}

function keysIn(heading: RegExp) {
  return [...section(heading).querySelectorAll("[data-issue-key]")].map((row) =>
    row.getAttribute("data-issue-key"),
  );
}

async function openMenu(user: ReturnType<typeof userEvent.setup>, key: string) {
  // The first render pulls in the lazy routes, which can take longer than the 1s default.
  await user.click(
    await screen.findByRole("button", { name: `Thao tác cho ${key}` }, { timeout: 5000 }),
  );
}

describe("Backlog: moving issues between sprints without dragging", () => {
  it("moves an issue into an upcoming sprint without asking for a reason", async () => {
    const user = userEvent.setup();
    renderAppRoutes(BACKLOG, leaderTestSession);

    await openMenu(user, "NEXUS-110");
    await user.click(await screen.findByRole("menuitem", { name: /^Chuyển vào Sprint 3/ }));

    await waitFor(() => expect(keysIn(/^Sprint 3/)).toContain("NEXUS-110"));
    expect(keysIn(/^Product Backlog/)).not.toContain("NEXUS-110");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("asks for a reason before changing the running sprint, and cancelling changes nothing", async () => {
    const user = userEvent.setup();
    renderAppRoutes(BACKLOG, leaderTestSession);

    await openMenu(user, "NEXUS-110");
    await user.click(await screen.findByRole("menuitem", { name: /^Chuyển vào Sprint 2/ }));

    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent("Thay đổi phạm vi Sprint đang chạy");
    await user.click(within(dialog).getByRole("button", { name: "Hủy" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(keysIn(/^Product Backlog/)).toContain("NEXUS-110");
    expect(keysIn(/^Sprint 2/)).not.toContain("NEXUS-110");

    await openMenu(user, "NEXUS-110");
    await user.click(await screen.findByRole("menuitem", { name: /^Chuyển vào Sprint 2/ }));
    const again = await screen.findByRole("dialog");
    await user.click(within(again).getByRole("button", { name: "Xác nhận thay đổi" }));
    expect(await within(again).findByRole("alert")).toHaveTextContent("Vui lòng nêu lý do");

    await user.type(within(again).getByLabelText("Lý do"), "Khách hàng đổi ưu tiên");
    await user.click(within(again).getByRole("button", { name: "Xác nhận thay đổi" }));

    await waitFor(() => expect(keysIn(/^Sprint 2/)).toContain("NEXUS-110"));
    expect(keysIn(/^Product Backlog/)).not.toContain("NEXUS-110");
  });

  it("sends an issue back to the Product Backlog", async () => {
    const user = userEvent.setup();
    renderAppRoutes(BACKLOG, leaderTestSession);

    // Sprint 3 is upcoming and empty: first put an issue there, then bring it back.
    await openMenu(user, "NEXUS-111");
    await user.click(await screen.findByRole("menuitem", { name: /^Chuyển vào Sprint 3/ }));
    await waitFor(() => expect(keysIn(/^Sprint 3/)).toContain("NEXUS-111"));

    await openMenu(user, "NEXUS-111");
    await user.click(await screen.findByRole("menuitem", { name: "Chuyển về Product Backlog" }));
    await waitFor(() => expect(keysIn(/^Product Backlog/)).toContain("NEXUS-111"));
    expect(keysIn(/^Sprint 3/)).not.toContain("NEXUS-111");
  });

  it("reorders the Product Backlog from the menu", async () => {
    const user = userEvent.setup();
    renderAppRoutes(BACKLOG, leaderTestSession);

    await screen.findByRole("button", { name: "Thao tác cho NEXUS-113" }, { timeout: 5000 });
    const before = keysIn(/^Product Backlog/);
    expect(before.at(-1)).toBe("NEXUS-113");

    await openMenu(user, "NEXUS-113");
    await user.click(await screen.findByRole("menuitem", { name: "Lên đầu danh sách" }));

    await waitFor(() => expect(keysIn(/^Product Backlog/)[0]).toBe("NEXUS-113"));
    expect(keysIn(/^Product Backlog/)).toHaveLength(before.length);
  });
});

describe("Backlog: who may do what", () => {
  it("registers drag only for the leader", async () => {
    const { unmount } = renderAppRoutes(BACKLOG, leaderTestSession);
    await screen.findByRole("button", { name: "Thao tác cho NEXUS-110" }, { timeout: 5000 });
    const row = (key: string) => document.querySelector(`[data-issue-key="${key}"]`)!;
    expect(row("NEXUS-110").getAttribute("draggable")).toBe("true");
    unmount();

    renderAppRoutes(BACKLOG, memberTestSession);
    await screen.findByText("NEXUS-110", {}, { timeout: 5000 });
    expect(row("NEXUS-110").getAttribute("draggable")).not.toBe("true");
    expect(row("NEXUS-101").getAttribute("draggable")).not.toBe("true");
    expect(screen.queryByTitle("Kéo để di chuyển")).not.toBeInTheDocument();
  });

  it("gives a member a menu only on their own issues, without sprint or ordering items", async () => {
    const user = userEvent.setup();
    renderAppRoutes(BACKLOG, memberTestSession);

    await screen.findByText("NEXUS-110", {}, { timeout: 5000 });
    expect(screen.queryByRole("button", { name: "Thao tác cho NEXUS-110" })).not.toBeInTheDocument();

    await openMenu(user, "NEXUS-101");
    expect(await screen.findByRole("menuitem", { name: "Đánh dấu bị chặn…" })).toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: /^Chuyển vào/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: "Lên đầu danh sách" })).not.toBeInTheDocument();
  });

  it("gives an instructor nothing to change", async () => {
    renderAppRoutes(BACKLOG, teacherTestSession);

    await screen.findByText("NEXUS-110", {}, { timeout: 5000 });
    expect(screen.queryByRole("button", { name: /^Thao tác cho/ })).not.toBeInTheDocument();
    expect(screen.queryByTitle("Kéo để di chuyển")).not.toBeInTheDocument();
  });
});
