import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { DisabledAction } from "@/components/feedback/DisabledAction";

const REASON = "Chưa có API tạo Epic";

describe("DisabledAction", () => {
  it("is announced as disabled, stays focusable, and describes why", async () => {
    render(<DisabledAction reason={REASON}>Tạo Epic</DisabledAction>);
    const button = screen.getByRole("button", { name: "Tạo Epic" });

    expect(button).toHaveAttribute("aria-disabled", "true");
    expect(button).not.toHaveAttribute("disabled");
    expect(button).toHaveAccessibleDescription(REASON);

    await userEvent.setup().tab();
    expect(button).toHaveFocus();
  });

  it("shows the reason on click and closes it with Escape", async () => {
    const user = userEvent.setup();
    render(<DisabledAction reason={REASON}>Tạo Epic</DisabledAction>);

    await user.click(screen.getByRole("button", { name: "Tạo Epic" }));
    expect(await screen.findByRole("dialog")).toHaveTextContent(REASON);

    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("opens from the keyboard", async () => {
    const user = userEvent.setup();
    render(<DisabledAction reason={REASON}>Tạo Epic</DisabledAction>);

    await user.tab();
    await user.keyboard("{Enter}");
    expect(await screen.findByRole("dialog")).toHaveTextContent(REASON);
  });

  it("never submits the form it sits in", async () => {
    const onSubmit = vi.fn((event: { preventDefault: () => void }) => event.preventDefault());
    const user = userEvent.setup();
    render(
      <form onSubmit={onSubmit}>
        <DisabledAction reason={REASON}>Tạo Epic</DisabledAction>
      </form>,
    );

    await user.click(screen.getByRole("button", { name: "Tạo Epic" }));
    await user.keyboard("{Enter}");
    expect(onSubmit).not.toHaveBeenCalled();
  });
});
