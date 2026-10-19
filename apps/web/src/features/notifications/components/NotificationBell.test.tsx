import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { renderAppRoutes, studentTestSession, teacherTestSession } from "@/test/render";

describe("NotificationBell", () => {
  it("shows the unread count, at most 5 latest items, and clears the badge on 'mark all read'", async () => {
    renderAppRoutes("/my-work", studentTestSession);
    const user = userEvent.setup();

    const bell = await screen.findByRole("button", { name: /^Thông báo \(\d+ chưa đọc\)$/ });
    await user.click(bell);

    const popover = await screen.findByRole("dialog");
    expect(within(popover).getAllByRole("listitem").length).toBeLessThanOrEqual(5);
    expect(within(popover).getByRole("link", { name: "Xem tất cả thông báo" })).toHaveAttribute(
      "href",
      "/notifications",
    );

    await user.click(within(popover).getByRole("button", { name: "Đánh dấu tất cả đã đọc" }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Thông báo" })).toBeInTheDocument(),
    );
  });

  it("is absent from the Teacher top bar, which must not call Student endpoints", async () => {
    renderAppRoutes("/teacher", teacherTestSession);
    await screen.findByRole("heading", { name: "Bàn làm việc giảng viên" });
    expect(screen.queryByRole("button", { name: /^Thông báo/ })).not.toBeInTheDocument();
  });
});
