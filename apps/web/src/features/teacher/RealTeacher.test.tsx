import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";

import { fixture, main, record, setup } from "@/features/teacher/realTeacherTestkit";
import { server } from "@/mocks/server";
import { buildClass, buildCourse, envelope, envelopeError } from "@/test/classroomHandlers";

/**
 * Teacher class management against the (simulated) real Classroom service,
 * through the real route table: reads, create, and each command card.
 */

afterEach(() => vi.unstubAllEnvs());

describe("real Teacher reads", () => {
  it("lists classes from Classroom with counts, and says plainly what it cannot know", async () => {
    setup("/teacher/courses");
    const page = await main();
    expect(await page.findByText("Đồ án phần mềm")).toBeInTheDocument();
    expect(page.getByText("Chưa có dữ liệu tín hiệu cho lớp này.")).toBeInTheDocument();
    expect(page.queryByText("Chưa phát hiện tín hiệu cần chú ý")).not.toBeInTheDocument();
  });

  it("shows an empty state for a teacher with no class", async () => {
    setup("/teacher/courses", fixture({ classes: [] }));
    expect(await (await main()).findByText("Chưa phụ trách lớp nào")).toBeInTheDocument();
  });

  it("shows the class overview with students that have no team, and no join code it cannot read", async () => {
    setup("/teacher/courses/class-1");
    const page = await main();
    const stat = async (name: string) => within(await page.findByRole("group", { name })).getByText(/^\d+$/);
    expect(await stat("Sinh viên")).toHaveTextContent("2");
    expect(await stat("Chưa có nhóm")).toHaveTextContent("1");
    expect(await stat("Nhóm")).toHaveTextContent("1");
    expect(page.getByText("Chưa có mã")).toBeInTheDocument();
  });

  it("lists the real students and teams, and states that oversight needs Work", async () => {
    const first = setup("/teacher/courses/class-1/teams");
    expect(await (await main()).findByText("Nhóm 1")).toBeInTheDocument();
    first.unmount();
    setup("/teacher/courses/class-1/oversight");
    expect(await (await main()).findByText("Giám sát tiến độ chưa khả dụng")).toBeInTheDocument();
  });

  it("shows the unavailable-class state when Classroom answers 404", async () => {
    setup("/teacher/courses/other");
    expect(await (await main()).findByText("Không tìm thấy lớp học")).toBeInTheDocument();
  });
});

describe("real class creation", () => {
  async function fillClass(user: ReturnType<typeof userEvent.setup>, page: Awaited<ReturnType<typeof main>>) {
    await user.type(page.getByLabelText("Mã lớp"), "SE330.P11");
    await user.type(page.getByLabelText("Học kỳ"), "HK1 2026–2027");
    await user.type(page.getByLabelText("Tên lớp"), "Đồ án chuyên ngành");
    await user.type(page.getByLabelText("Ngày bắt đầu"), "2026-09-01");
    await user.type(page.getByLabelText("Ngày kết thúc"), "2027-01-15");
  }

  async function openCreate(user: ReturnType<typeof userEvent.setup>, fx?: ReturnType<typeof fixture>) {
    if (fx) setup("/teacher/courses", fx);
    else setup("/teacher/courses");
    await user.click(await (await main()).findByRole("button", { name: "Tạo lớp" }));
    return within(await screen.findByRole("dialog", { name: "Tạo lớp" }));
  }

  it("opens a dialog on the class list instead of leaving the page, and explains course vs class", async () => {
    const user = userEvent.setup();
    const page = await openCreate(user);
    expect(screen.getByRole("heading", { name: "Lớp phụ trách", hidden: true })).toBeInTheDocument();
    expect(page.getByText("Thông tin lớp học")).toBeInTheDocument();
    expect(page.queryByText("Thông tin môn học")).not.toBeInTheDocument();
    expect(page.queryByText(/Bước \d/)).not.toBeInTheDocument();
    await user.selectOptions(await page.findByLabelText("Môn học"), "course-1");
    expect(await page.findByText(/^Lớp mới thuộc môn /)).toBeInTheDocument();
  });

  it("closes with Hủy without sending anything, and starts empty when reopened", async () => {
    const seen = record("post", "/api/classroom/classes/", () => envelope(buildClass(), { status: 201 }));
    const user = userEvent.setup();
    const page = await openCreate(user);
    await user.type(page.getByLabelText("Tên lớp"), "Dở dang");
    await user.click(page.getByRole("button", { name: "Hủy" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    await user.click(await (await main()).findByRole("button", { name: "Tạo lớp" }));
    expect(await within(await screen.findByRole("dialog")).findByLabelText("Tên lớp")).toHaveValue("");
    expect(seen).toHaveLength(0);
  });

  it("creates the class under an existing course, with one idempotency key, then opens it", async () => {
    const created = buildClass({ id: "class-new", name: "Đồ án chuyên ngành" });
    const seen = record("post", "/api/classroom/classes/", () => envelope(created, { status: 201 }));
    const user = userEvent.setup();
    const page = await openCreate(user, fixture({ classes: [created] }));
    await user.selectOptions(await page.findByLabelText("Môn học"), "course-2");
    await fillClass(user, page);
    await user.click(page.getByRole("button", { name: "Tạo lớp" }));

    await waitFor(() => expect(seen).toHaveLength(1));
    expect(seen[0].key).toMatch(/^[0-9a-f-]{36}$/);
    expect(seen[0].body).toMatchObject({ course_id: "course-2", code: "SE330.P11", group_min_size: 1, group_max_size: 6 });
    expect(await screen.findByRole("heading", { name: "Đồ án chuyên ngành" })).toBeInTheDocument();
  });

  it("creates a new course first when asked, then the class under it", async () => {
    const order: string[] = [];
    server.use(
      http.post("/api/classroom/courses/", async ({ request }) => {
        order.push(`course:${JSON.stringify(await request.json())}`);
        return envelope(buildCourse({ id: "course-new", code: "NEW1", name: "Môn mới" }), { status: 201 });
      }),
    );
    const seen = record("post", "/api/classroom/classes/", () => {
      order.push("class");
      return envelope(buildClass({ id: "class-new" }), { status: 201 });
    });
    const user = userEvent.setup();
    const page = await openCreate(user);
    await user.selectOptions(await page.findByLabelText("Môn học"), "new");
    await user.type(page.getByLabelText("Mã môn mới"), "new1");
    await user.type(page.getByLabelText("Tên môn mới"), "Môn mới");
    await fillClass(user, page);
    await user.click(page.getByRole("button", { name: "Tạo lớp" }));

    await waitFor(() => expect(seen).toHaveLength(1));
    expect(order).toEqual(['course:{"code":"new1","name":"Môn mới"}', "class"]);
    expect(seen[0].body.course_id).toBe("course-new");
  });

  it("puts a server field error next to the field", async () => {
    server.use(
      http.post("/api/classroom/classes/", () =>
        HttpResponse.json(
          { success: false, message: "Dữ liệu không hợp lệ", data: null, meta: null, error: { code: "VALIDATION_ERROR", details: [{ field: "code", issue: "Mã lớp đã tồn tại." }] } },
          { status: 422 },
        ),
      ),
    );
    const user = userEvent.setup();
    const page = await openCreate(user);
    await user.selectOptions(await page.findByLabelText("Môn học"), "course-1");
    await fillClass(user, page);
    await user.click(page.getByRole("button", { name: "Tạo lớp" }));

    expect(await page.findByText("Mã lớp đã tồn tại.")).toBeInTheDocument();
    expect(page.getByText("Còn thông tin chưa hợp lệ, xem các thông báo cạnh từng ô.")).toBeInTheDocument();
  });

  it("refuses to submit an invalid form without calling the server", async () => {
    const seen = record("post", "/api/classroom/classes/", () => envelope(buildClass(), { status: 201 }));
    const user = userEvent.setup();
    const page = await openCreate(user);
    await user.click(await page.findByRole("button", { name: "Tạo lớp" }));
    expect(await page.findByText("Chọn môn học hoặc tạo môn mới.")).toBeInTheDocument();
    expect(seen).toHaveLength(0);
  });

  it("shows the server's refusal when the account is not a teacher", async () => {
    server.use(http.post("/api/classroom/classes/", () => envelopeError(403, "PERMISSION_DENIED", "Chỉ giảng viên mới được tạo lớp.")));
    const user = userEvent.setup();
    const page = await openCreate(user);
    await user.selectOptions(await page.findByLabelText("Môn học"), "course-1");
    await fillClass(user, page);
    await user.click(page.getByRole("button", { name: "Tạo lớp" }));
    expect(await page.findByText("Chỉ giảng viên mới được tạo lớp.")).toBeInTheDocument();
  });
});

describe("real class settings", () => {
  it("saves edits with the displayed version", async () => {
    const seen = record("patch", "/api/classroom/classes/class-1/", () => envelope(buildClass({ version: 2, name: "Tên mới" })));
    setup("/teacher/courses/class-1/settings");
    const user = userEvent.setup();
    const page = await main();
    const name = await page.findByLabelText("Tên lớp");
    await user.clear(name);
    await user.type(name, "Tên mới");
    await user.click(page.getByRole("button", { name: "Lưu thay đổi" }));
    await waitFor(() => expect(seen).toHaveLength(1));
    expect(seen[0].body).toMatchObject({ version: 1, name: "Tên mới", group_min_size: 3, group_max_size: 5 });
    expect(seen[0].key).toBeTruthy();
  });

  it("shows the stale-class message on a version conflict", async () => {
    server.use(http.patch("/api/classroom/classes/class-1/", () => envelopeError(409, "VERSION_CONFLICT", "Lớp học đã thay đổi.")));
    setup("/teacher/courses/class-1/settings");
    const user = userEvent.setup();
    const page = await main();
    const name = await page.findByLabelText("Tên lớp");
    await user.type(name, "!");
    await user.click(page.getByRole("button", { name: "Lưu thay đổi" }));
    expect(await page.findByText("Lớp học đã thay đổi, hãy xem lại dữ liệu mới rồi thử lại.")).toBeInTheDocument();
  });

  it("shows a new join code exactly once and never reads it back", async () => {
    const seen = record("post", "/api/classroom/classes/class-1/join-code/", () =>
      envelope({ id: "class-1", version: 2, code: "ABCD1234", expires_at: "2099-01-01T00:00:00Z", enabled: true }),
    );
    const first = setup("/teacher/courses/class-1/settings");
    const user = userEvent.setup();
    let page = await main();
    await user.click(await page.findByRole("button", { name: "Tạo mã mới" }));
    expect(await page.findByLabelText("Mã tham gia vừa cấp")).toHaveTextContent("ABCD1234");
    expect(seen[0].body).toEqual({ version: 1, enabled: true });
    first.unmount();

    // Open again: the class now has an active code, but the raw value is gone.
    setup("/teacher/courses/class-1/settings", fixture({ classes: [buildClass({ version: 2, join_code_expires_at: "2099-01-01T00:00:00Z" })] }));
    page = await main();
    expect(await page.findByText("Đang bật")).toBeInTheDocument();
    expect(screen.queryByText("ABCD1234")).not.toBeInTheDocument();
  });

  it("asks before replacing or disabling an active code, and sends nothing on cancel", async () => {
    const seen = record("post", "/api/classroom/classes/class-1/join-code/", () => envelope({ id: "class-1", version: 2, expires_at: null, enabled: false }));
    setup("/teacher/courses/class-1/settings", fixture({ classes: [buildClass({ join_code_expires_at: "2099-01-01T00:00:00Z" })] }));
    const user = userEvent.setup();
    const page = await main();
    await user.click(await page.findByRole("button", { name: "Tắt mã" }));
    const dialog = within(await screen.findByRole("dialog"));
    await user.click(dialog.getByRole("button", { name: "Hủy" }));
    expect(seen).toHaveLength(0);

    await user.click(page.getByRole("button", { name: "Tắt mã" }));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Tắt mã" }));
    await waitFor(() => expect(seen).toHaveLength(1));
    expect(seen[0].body).toEqual({ version: 1, enabled: false });
  });

  it("locks grouping only after an irreversible-action confirmation", async () => {
    const seen = record("post", "/api/classroom/classes/class-1/lock-grouping/", () => envelope(buildClass({ version: 2, grouping_phase: "LOCKED" })));
    setup("/teacher/courses/class-1/settings");
    const user = userEvent.setup();
    const page = await main();
    await user.click(await page.findByRole("button", { name: "Chốt lập nhóm" }));
    const dialog = within(await screen.findByRole("dialog"));
    expect(dialog.getByText(/không có cách mở lại/)).toBeInTheDocument();
    expect(seen).toHaveLength(0);
    await user.click(dialog.getByRole("button", { name: "Chốt lập nhóm" }));
    await waitFor(() => expect(seen).toHaveLength(1));
    expect(seen[0].body).toEqual({ version: 1 });
  });

  it("offers no lock button and no reopen once grouping is locked and the class archived", async () => {
    setup(
      "/teacher/courses/class-1/settings",
      fixture({ classes: [buildClass({ grouping_phase: "LOCKED", grouping_locked_at: "2026-10-01T00:00:00Z", status: "ARCHIVED" })] }),
    );
    const page = await main();
    expect(await page.findByText("Đã chốt")).toBeInTheDocument();
    expect(page.queryByRole("button", { name: "Chốt lập nhóm" })).not.toBeInTheDocument();
    expect(page.getByText("Lớp đã lưu trữ không thể mở lại.")).toBeInTheDocument();
    expect(page.queryByRole("button", { name: "Mở lại lớp" })).not.toBeInTheDocument();
  });

  it("closes the class after confirmation and reports the server's refusal when the teacher lost access", async () => {
    const seen = record("post", "/api/classroom/classes/class-1/state/", () =>
      envelopeError(403, "PERMISSION_DENIED", "Bạn không có quyền quản lý lớp học này."),
    );
    setup("/teacher/courses/class-1/settings");
    const user = userEvent.setup();
    const page = await main();
    await user.click(await page.findByRole("button", { name: "Đóng lớp" }));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Đóng lớp" }));
    await waitFor(() => expect(seen).toHaveLength(1));
    expect(seen[0].body).toEqual({ version: 1, status: "CLOSED" });
    expect(await screen.findByText("Bạn không có quyền quản lý lớp học này.")).toBeInTheDocument();
  });

  it("adds a co-teacher only after looking the person up and confirming their name", async () => {
    const seen = record("post", "/api/classroom/classes/class-1/teachers/assign/", () => envelope(buildClass({ version: 2 })));
    setup("/teacher/courses/class-1/settings");
    const user = userEvent.setup();
    const page = await main();
    const input = await page.findByLabelText("Thêm giảng viên đồng phụ trách");

    await user.type(input, "không-phải-uuid");
    await user.click(page.getByRole("button", { name: "Tra cứu" }));
    expect(await page.findByText("Mã người dùng phải là UUID hợp lệ.")).toBeInTheDocument();

    await user.clear(input);
    await user.type(input, "22222222-2222-4222-8222-222222222222");
    await user.click(page.getByRole("button", { name: "Tra cứu" }));
    expect(await page.findByText("Không tìm thấy người dùng với mã này.")).toBeInTheDocument();

    await user.clear(input);
    await user.type(input, "11111111-1111-4111-8111-111111111111");
    await user.click(page.getByRole("button", { name: "Tra cứu" }));
    const dialog = within(await screen.findByRole("dialog"));
    expect(dialog.getByText(/ThS\. Mai \(mai@utask\.test\)/)).toBeInTheDocument();
    expect(seen).toHaveLength(0);
    await user.click(dialog.getByRole("button", { name: "Thêm giảng viên" }));
    await waitFor(() => expect(seen).toHaveLength(1));
    expect(seen[0].body).toEqual({ version: 1, user_id: "11111111-1111-4111-8111-111111111111", role: "CO_TEACHER", status: "ACTIVE" });
  });

  it("shows the server's reason when the chosen account cannot teach", async () => {
    record("post", "/api/classroom/classes/class-1/teachers/assign/", () =>
      envelopeError(422, "INVALID_TEACHER", "Hãy chọn giảng viên có tài khoản đang hoạt động."),
    );
    setup("/teacher/courses/class-1/settings");
    const user = userEvent.setup();
    const page = await main();
    await user.type(await page.findByLabelText("Thêm giảng viên đồng phụ trách"), "11111111-1111-4111-8111-111111111111");
    await user.click(page.getByRole("button", { name: "Tra cứu" }));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Thêm giảng viên" }));
    expect(await screen.findByText("Hãy chọn giảng viên có tài khoản đang hoạt động.")).toBeInTheDocument();
  });
});
