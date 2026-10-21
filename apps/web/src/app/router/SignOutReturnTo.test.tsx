import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { leaderTestSession, renderAppRoutes } from "@/test/render";

const BOARD = "/projects/project-nexus/board";

describe("sign out does not carry the page to the next account", () => {
  it("signs in as another account on /teacher, not on the previous account's project page", async () => {
    const view = renderAppRoutes(BOARD, leaderTestSession);
    const user = userEvent.setup();

    await user.click((await screen.findAllByRole("button", { name: /@utask\.test/ }))[0]);
    await user.click(await screen.findByRole("menuitem", { name: /Đăng xuất/ }));
    await waitFor(() => expect(view.router.state.location.pathname).toBe("/login"));

    await user.type(await screen.findByLabelText("Email trường học"), "teacher3@utask.test");
    await user.type(screen.getByLabelText("Mật khẩu"), "demo1234");
    await user.click(screen.getByRole("button", { name: "Đăng nhập" }));

    await waitFor(() => expect(view.router.state.location.pathname).toBe("/teacher"));
  });

  it("still returns to the page after a session that ended by itself", async () => {
    const view = renderAppRoutes(BOARD, null);
    await waitFor(() => expect(view.router.state.location.pathname).toBe("/login"));
    expect(view.router.state.location.state).toEqual({ returnTo: BOARD });
  });
});
