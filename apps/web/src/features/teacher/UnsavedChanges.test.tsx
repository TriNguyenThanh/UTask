import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { createMockHandlers } from "@/mocks/handlers";
import { createMemoryRepository } from "@/mocks/data/storage";
import { server } from "@/mocks/server";
import { renderAppRoutes, teacherTestSession } from "@/test/render";
import { main, setup as setupReal } from "@/features/teacher/realTeacherTestkit";

const DISCARD_TITLE = "Bỏ thông tin đã nhập?";

afterEach(() => vi.unstubAllEnvs());

describe("Team adjustment dialog keeps what was typed", () => {
  async function openDialog() {
    server.use(...createMockHandlers("default", createMemoryRepository("default")));
    renderAppRoutes("/teacher/courses/course-it3090/teams", teacherTestSession);
    const user = userEvent.setup();
    await user.click(await (await main()).findByRole("button", { name: "Điều chỉnh nhóm" }));
    return { user, dialog: await screen.findByRole("dialog", { name: "Điều chỉnh nhóm" }) };
  }

  it("asks before Esc discards a chosen student, and Hủy on the question keeps the choice", async () => {
    const { user, dialog } = await openDialog();
    const student = await within(dialog).findByLabelText("Sinh viên");
    await user.selectOptions(student, within(dialog).getAllByRole("option")[1]);
    const chosen = (student as HTMLSelectElement).value;
    expect(chosen).not.toBe("");

    await user.keyboard("{Escape}");
    const confirm = await screen.findByRole("dialog", { name: DISCARD_TITLE });
    await user.click(within(confirm).getByRole("button", { name: "Hủy" }));

    await waitFor(() => expect(screen.queryByRole("dialog", { name: DISCARD_TITLE })).not.toBeInTheDocument());
    expect(screen.getByRole("dialog", { name: "Điều chỉnh nhóm" })).toBeInTheDocument();
    expect((screen.getByLabelText("Sinh viên") as HTMLSelectElement).value).toBe(chosen);

    await user.keyboard("{Escape}");
    await user.click(await screen.findByRole("button", { name: "Bỏ thay đổi" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("closes at once on Esc when nothing was chosen", async () => {
    const { user } = await openDialog();
    await screen.findByLabelText("Sinh viên");

    await user.keyboard("{Escape}");

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });
});

describe("Class information form warns before leaving with unsaved edits", () => {
  async function editName() {
    const view = setupReal("/teacher/courses/class-1/settings");
    const user = userEvent.setup();
    const page = await main();
    const name = await page.findByLabelText("Tên lớp");
    await user.clear(name);
    await user.type(name, "Tên đang sửa dở");
    return { view, user };
  }

  const goToStudents = () =>
    within(screen.getByRole("navigation", { name: "Các mục của lớp" })).getByRole("link", { name: /^Sinh viên/ });

  it("keeps the page when the person stays, and leaves only after confirming", async () => {
    const { view, user } = await editName();

    await user.click(goToStudents());
    const dialog = await screen.findByRole("dialog", { name: "Rời khỏi trang?" });
    await user.click(within(dialog).getByRole("button", { name: "Ở lại và tiếp tục nhập" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(view.router.state.location.pathname).toBe("/teacher/courses/class-1/settings");
    expect(screen.getByLabelText("Tên lớp")).toHaveValue("Tên đang sửa dở");

    await user.click(goToStudents());
    await user.click(within(await screen.findByRole("dialog", { name: "Rời khỏi trang?" })).getByRole("button", { name: "Rời trang" }));
    await waitFor(() => expect(view.router.state.location.pathname).toBe("/teacher/courses/class-1/students"));
  });

  it("does not interrupt navigation when nothing was edited", async () => {
    const view = setupReal("/teacher/courses/class-1/settings");
    const user = userEvent.setup();
    await (await main()).findByLabelText("Tên lớp");

    await user.click(goToStudents());

    await waitFor(() => expect(view.router.state.location.pathname).toBe("/teacher/courses/class-1/students"));
    expect(screen.queryByRole("dialog", { name: "Rời khỏi trang?" })).not.toBeInTheDocument();
  });
});
