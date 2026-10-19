import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import { leaderTestSession, renderAppRoutes } from "@/test/render";

const PINNED_KEY = "utask.sidebar.pinned";

function courseListShell() {
  return screen.getByText("Học kỳ hiện tại").closest("div[aria-hidden]");
}

describe("AuthenticatedLayout sidebar", () => {
  beforeEach(() => localStorage.clear());

  it("moves Settings and Notifications into the profile menu and drops the quick tools", async () => {
    renderAppRoutes("/my-work", leaderTestSession);
    const user = userEvent.setup();
    const nav = await screen.findByRole("navigation", { name: "Điều hướng chính" });

    expect(within(nav).queryByRole("link", { name: "Cài đặt" })).not.toBeInTheDocument();
    expect(within(nav).queryByRole("link", { name: "Thông báo" })).not.toBeInTheDocument();
    expect(screen.queryByText("Tiện ích nhanh")).not.toBeInTheDocument();

    await user.click(screen.getAllByRole("button", { name: /@utask\.test/ })[0]);
    expect(await screen.findByRole("menuitem", { name: /Cài đặt tài khoản/ })).toHaveAttribute(
      "href",
      "/settings/profile",
    );
    expect(screen.getByRole("menuitem", { name: /Thông báo/ })).toHaveAttribute("href", "/notifications");
    expect(screen.getByRole("menuitem", { name: /Đăng xuất/ })).toBeInTheDocument();
  });

  it("is pinned open by default and has no collapse button", async () => {
    renderAppRoutes("/my-work", leaderTestSession);
    const pin = await screen.findByRole("button", { name: "Bỏ ghim thanh điều hướng" });
    expect(pin).toHaveAttribute("aria-pressed", "true");
    expect(screen.queryByRole("button", { name: /Thu gọn/ })).not.toBeInTheDocument();
    expect(courseListShell()).toHaveAttribute("aria-hidden", "false");
  });

  it("unpinned: shrinks to a rail, opens while hovered, shrinks back, and remembers the choice", async () => {
    const first = renderAppRoutes("/my-work", leaderTestSession);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Bỏ ghim thanh điều hướng" }));
    expect(localStorage.getItem(PINNED_KEY)).toBe("0");

    // The click left the pointer and focus inside the sidebar, which keeps it open.
    const aside = screen.getByRole("complementary");
    expect(courseListShell()).toHaveAttribute("aria-hidden", "false");
    await user.unhover(aside);
    (document.activeElement as HTMLElement).blur();
    await waitFor(() => expect(courseListShell()).toHaveAttribute("aria-hidden", "true"));

    await user.hover(aside);
    expect(courseListShell()).toHaveAttribute("aria-hidden", "false");
    await user.unhover(aside);
    expect(courseListShell()).toHaveAttribute("aria-hidden", "true");

    first.unmount();
    renderAppRoutes("/my-work", leaderTestSession);
    const pin = await screen.findByRole("button", { name: "Ghim thanh điều hướng" });
    expect(pin).toHaveAttribute("aria-pressed", "false");
    await user.hover(screen.getByRole("complementary"));
    await user.click(pin);
    expect(localStorage.getItem(PINNED_KEY)).toBe("1");
  });
});
