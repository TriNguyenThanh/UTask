import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http, type HttpHandler } from "msw";
import { toast } from "sonner";
import { afterEach, describe, expect, it, vi } from "vitest";

import { createMockHandlers } from "@/mocks/handlers";
import { server } from "@/mocks/server";
import { createMemoryRepository } from "@/mocks/data/storage";
import type { MockScenario } from "@/mocks/scenarios";
import { renderAppRoutes, teacher2TestSession, teacherTestSession } from "@/test/render";
import { FEEDBACK_MAX_LENGTH } from "@/features/teacher/components/FeedbackComposer";
import { MAX_IMPORT_BYTES } from "@/features/teacher/lib/csvImport";

/**
 * Phases 3–5 through the real route table: class form, settings, add student,
 * CSV import preview, team adjustment preview, feedback drafts and the
 * attention list. None of these has a write API, so a recurring check is that
 * nothing but GET requests ever leaves the page.
 */

const API = "http://localhost/api/work/api/v1";

function setup(
  route: string,
  session: Parameters<typeof renderAppRoutes>[1] = teacherTestSession,
  scenario: MockScenario = "default",
  overrides: HttpHandler[] = [],
) {
  const repository = createMemoryRepository(scenario);
  server.use(...createMockHandlers(scenario, repository));
  server.use(...overrides);
  return { repository, ...renderAppRoutes(route, session) };
}

function trackRequests() {
  const calls: string[] = [];
  const listener = ({ request }: { request: Request }) => {
    calls.push(`${request.method} ${new URL(request.url).pathname}`);
  };
  server.events.on("request:start", listener);
  return {
    calls,
    stop: () => server.events.removeListener("request:start", listener),
    writes: () => calls.filter((call) => !call.startsWith("GET ")),
  };
}

const page = async () => within(await screen.findByRole("main"));
const pathname = (router: { state: { location: { pathname: string } } }) => router.state.location.pathname;

afterEach(() => {
  vi.unstubAllEnvs();
  sessionStorage.clear();
  toast.dismiss();
});

describe("Create class form (T03)", () => {
  it("is reachable from Home and from the class list", async () => {
    const first = setup("/teacher/courses");
    expect(await screen.findByRole("link", { name: "Tạo lớp" })).toHaveAttribute("href", "/teacher/courses/new");
    first.unmount();
    setup("/teacher");
    expect(await screen.findByRole("link", { name: "Tạo lớp" })).toHaveAttribute("href", "/teacher/courses/new");
  });

  it("says plainly that the class cannot be created yet, with the button disabled and described", async () => {
    setup("/teacher/courses/new");
    const main = await page();
    expect(await main.findByText("Chưa thể tạo lớp")).toBeInTheDocument();
    const create = main.getByRole("button", { name: "Tạo lớp" });
    expect(create).toBeDisabled();
    expect(create).toHaveAccessibleDescription(/chưa có hợp đồng API tạo lớp/);
  });

  it("validates dates and team size next to the field, as the person types", async () => {
    setup("/teacher/courses/new");
    const user = userEvent.setup();
    const main = await page();
    await user.type(await main.findByLabelText("Ngày bắt đầu"), "2026-09-10");
    await user.type(main.getByLabelText("Ngày kết thúc"), "2026-09-01");
    expect(await main.findByText("Ngày kết thúc phải sau hoặc cùng ngày bắt đầu.")).toBeInTheDocument();

    const min = main.getByLabelText("Sĩ số nhóm tối thiểu");
    const max = main.getByLabelText("Sĩ số nhóm tối đa");
    await user.clear(min);
    await user.type(min, "6");
    await user.clear(max);
    await user.type(max, "4");
    expect(await main.findByText("Sĩ số tối đa phải lớn hơn hoặc bằng sĩ số tối thiểu.")).toBeInTheDocument();
  });

  it("reports a valid form as valid but still not creatable, and sends nothing", async () => {
    const tracker = trackRequests();
    setup("/teacher/courses/new");
    const user = userEvent.setup();
    const main = await page();
    await user.type(await main.findByLabelText("Tên lớp"), "Đồ án mới");
    await user.type(main.getByLabelText("Học kỳ"), "HK2 2026-2027");
    await user.type(main.getByLabelText("Ngày bắt đầu"), "2027-02-01");
    await user.type(main.getByLabelText("Ngày kết thúc"), "2027-06-01");
    await user.click(main.getByRole("button", { name: "Kiểm tra thông tin" }));
    expect(await main.findByText("Thông tin đúng định dạng. Việc tạo lớp vẫn chưa khả dụng.")).toBeInTheDocument();
    tracker.stop();
    expect(tracker.writes()).toEqual([]);
  });

  it("asks before leaving a form that has been edited, and lets the person stay or leave", async () => {
    const view = setup("/teacher/courses/new");
    const user = userEvent.setup();
    const main = await page();
    await user.type(await main.findByLabelText("Tên lớp"), "Đang nhập dở");

    await user.click(main.getByRole("link", { name: "Hủy" }));
    const dialog = await screen.findByRole("dialog", { name: "Rời khỏi trang?" });
    expect(pathname(view.router)).toBe("/teacher/courses/new");
    await user.click(within(dialog).getByRole("button", { name: /Ở lại/ }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(pathname(view.router)).toBe("/teacher/courses/new");
    expect(main.getByLabelText("Tên lớp")).toHaveValue("Đang nhập dở");

    await user.click(main.getByRole("link", { name: "Hủy" }));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Rời trang" }));
    await waitFor(() => expect(pathname(view.router)).toBe("/teacher/courses"));
  });

  it("also asks when the tab is closed or refreshed, but only for an edited form", async () => {
    setup("/teacher/courses/new");
    const user = userEvent.setup();
    const main = await page();
    const fire = () => {
      const event = new Event("beforeunload", { cancelable: true });
      window.dispatchEvent(event);
      return event.defaultPrevented;
    };
    await main.findByLabelText("Tên lớp");
    expect(fire()).toBe(false);
    await user.type(main.getByLabelText("Tên lớp"), "Dở dang");
    expect(fire()).toBe(true);
    await user.clear(main.getByLabelText("Tên lớp"));
    await waitFor(() => expect(fire()).toBe(false));
  });

  it("leaves without asking when nothing was typed", async () => {
    const view = setup("/teacher/courses/new");
    const main = await page();
    await userEvent.setup().click(await main.findByRole("link", { name: "Hủy" }));
    await waitFor(() => expect(pathname(view.router)).toBe("/teacher/courses"));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("keeps a student out of the form", async () => {
    // The guard is the Teacher space guard; covered for every /teacher route, spot-checked here.
    const { studentTestSession } = await import("@/test/render");
    setup("/teacher/courses/new", studentTestSession);
    expect(await screen.findByText("Không đủ quyền truy cập")).toBeInTheDocument();
  });
});

describe("Class settings (T10)", () => {
  it("shows class information and the join code, read-only, with no edit or delete control", async () => {
    setup("/teacher/courses/course-se330/settings");
    const main = await page();
    expect(await main.findByText("Thông tin lớp")).toBeInTheDocument();
    expect(main.getByLabelText("Mã tham gia hiện tại")).toHaveTextContent("SE330-A1");
    expect(main.getByText("Phụ trách chính")).toBeInTheDocument();
    expect(main.queryByRole("button", { name: /Xóa|Sửa|Lưu/ })).not.toBeInTheDocument();
    expect(main.getByText(/Không có thao tác xóa lớp/)).toBeInTheDocument();
  });

  it("disables changing and disabling the code, each with its reason and the confirmation it will need", async () => {
    setup("/teacher/courses/course-se330/settings");
    const main = await page();
    const change = await main.findByRole("button", { name: "Đổi mã" });
    const disable = main.getByRole("button", { name: "Vô hiệu mã" });
    for (const button of [change, disable]) expect(button).toBeDisabled();
    expect(change).toHaveAccessibleDescription(/chưa có hợp đồng API đổi mã.*cần xác nhận/);
    expect(disable).toHaveAccessibleDescription(/chưa có hợp đồng API.*cần xác nhận/);
  });

  it("copies the code only when the clipboard write succeeds", async () => {
    setup("/teacher/courses/course-se330/settings");
    const user = userEvent.setup();
    const main = await page();
    await main.findByLabelText("Mã tham gia hiện tại");

    const writeText = vi.fn().mockRejectedValue(new Error("denied"));
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    const copy = () => main.getAllByRole("button", { name: "Sao chép mã tham gia" })[0];
    await user.click(copy());
    expect(await screen.findByText(/Không sao chép được mã/)).toBeInTheDocument();
    expect(screen.queryByText("Đã sao chép mã tham gia.")).not.toBeInTheDocument();

    writeText.mockResolvedValue(undefined);
    await user.click(copy());
    expect(await screen.findByText("Đã sao chép mã tham gia.")).toBeInTheDocument();
    expect(writeText).toHaveBeenLastCalledWith("SE330-A1");
  });

  it("treats a class outside the assignment like a missing one", async () => {
    setup("/teacher/courses/course-cs402/settings");
    expect(await screen.findByText("Không tìm thấy lớp học")).toBeInTheDocument();
    expect(screen.queryByText("CS402-MOB")).not.toBeInTheDocument();
  });
});

describe("Add one student (dialog)", () => {
  async function openDialog() {
    setup("/teacher/courses/course-se330/students");
    const user = userEvent.setup();
    const main = await page();
    await user.click(await main.findByRole("button", { name: "Thêm sinh viên" }));
    return { user, dialog: await screen.findByRole("dialog", { name: "Thêm sinh viên vào lớp" }) };
  }

  it("checks the format of what is typed and needs an email or a student code", async () => {
    const { user, dialog } = await openDialog();
    await user.type(within(dialog).getByLabelText("Email"), "khong-hop-le");
    expect(await within(dialog).findByText("Email sai định dạng.")).toBeInTheDocument();
    await user.clear(within(dialog).getByLabelText("Email"));
    await user.type(within(dialog).getByLabelText("Họ và tên đệm"), "Nguyễn Văn");
    expect(
      await within(dialog).findByText("Nhập email hoặc mã sinh viên để xác định người cần thêm."),
    ).toBeInTheDocument();
  });

  it("cannot be submitted, says no account is created, and sends nothing", async () => {
    const tracker = trackRequests();
    const { user, dialog } = await openDialog();
    await user.type(within(dialog).getByLabelText("Email"), "sv@truong.edu.vn");
    const submit = within(dialog).getByRole("button", { name: "Thêm vào lớp" });
    expect(submit).toBeDisabled();
    expect(submit).toHaveAccessibleDescription(/không có tài khoản nào được tạo/);
    expect(within(dialog).queryByLabelText(/mật khẩu/i)).not.toBeInTheDocument();
    expect(within(dialog).queryByLabelText(/nhóm/i)).not.toBeInTheDocument();
    tracker.stop();
    expect(tracker.writes()).toEqual([]);
  });

  it("closes and forgets what was typed", async () => {
    const { user, dialog } = await openDialog();
    await user.type(within(dialog).getByLabelText("Email"), "sv@truong.edu.vn");
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "Thêm sinh viên" }));
    expect(within(await screen.findByRole("dialog")).getByLabelText("Email")).toHaveValue("");
  });
});

describe("Import preview (T06)", () => {
  const csv = (text: string, name = "ds.csv") => new File([text], name, { type: "text/csv" });

  async function choose(file: File) {
    setup("/teacher/courses/course-se330/students/import");
    const user = userEvent.setup();
    const main = await page();
    await user.upload(await main.findByLabelText(/File danh sách/), file);
    return { user, main };
  }

  it("opens from the students page and states up front that it only checks format", async () => {
    const view = setup("/teacher/courses/course-se330/students");
    await userEvent.setup().click(await screen.findByRole("link", { name: "Nhập danh sách" }));
    await waitFor(() => expect(pathname(view.router)).toBe("/teacher/courses/course-se330/students/import"));
    expect(await screen.findByText("Chỉ kiểm tra định dạng, chưa nhập được")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Sinh viên 6" })).toBeInTheDocument();
  });

  it("previews rows with their file row numbers and the format result, without sending the file", async () => {
    const tracker = trackRequests();
    const { main } = await choose(
      csv("student_id,email,last_name,first_name\n21000001,a@x.vn,Nguyễn Văn,A\n,khong-hop-le,Lê,B\n,,Trần,C\n21000001,d@x.vn,Phạm,D\n"),
    );
    const table = await main.findByRole("table");
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows.map((row) => within(row).getAllByRole("cell")[0].textContent)).toEqual(["2", "3", "4", "5"]);
    expect(rows[0]).toHaveTextContent("Đúng định dạng");
    expect(rows[1]).toHaveTextContent("Email sai định dạng");
    expect(rows[2]).toHaveTextContent("không xác định được người cần thêm");
    expect(rows[3]).toHaveTextContent("Trùng với dòng 2");

    const summary = main.getByRole("list", { hidden: true, name: "Các loại kết quả theo dòng" });
    expect(summary).toBeInTheDocument();
    const totals = main.getByLabelText("Tóm tắt kiểm tra");
    expect(totals).toHaveTextContent("Tổng số dòng4");
    expect(totals).toHaveTextContent("Dòng lỗi2");
    expect(totals).toHaveTextContent("Dòng trùng trong file1");
    tracker.stop();
    expect(tracker.calls.some((call) => call.includes("import"))).toBe(false);
    expect(tracker.writes()).toEqual([]);
  });

  it("keeps 'Xác nhận nhập' disabled with the reason, and shows no outcome", async () => {
    const { main } = await choose(csv("email\na@x.vn\n"));
    const confirm = await main.findByRole("button", { name: "Xác nhận nhập" });
    expect(confirm).toBeDisabled();
    expect(confirm).toHaveAccessibleDescription(/chưa có hợp đồng API nhập danh sách.*multipart/);
    expect(main.getByText(/Chưa có kết quả nào: file chưa được gửi/)).toBeInTheDocument();
    expect(main.queryByText(/nhập thành công|nhập xong/i)).not.toBeInTheDocument();
  });

  it("lists the kinds of per-row result the backend is described to report, as a legend only", async () => {
    setup("/teacher/courses/course-se330/students/import");
    const legend = await screen.findByRole("list", { name: "Các loại kết quả theo dòng" });
    for (const title of [
      "Tạo tài khoản mới, chờ kích hoạt",
      "Dùng tài khoản có sẵn",
      "Đã thuộc lớp",
      "Cần kiểm tra",
      "Xung đột danh tính",
      "Lỗi từng dòng",
    ]) {
      expect(within(legend).getByText(title)).toBeInTheDocument();
    }
    expect(within(legend).getByText(/Không ai đặt hộ mật khẩu/)).toBeInTheDocument();
  });

  it("filters to the rows that need attention", async () => {
    const { user, main } = await choose(csv("email\na@x.vn\nxấu\nb@x.vn\n"));
    await main.findByRole("table");
    await user.click(main.getByLabelText("Chỉ hiện dòng có lỗi hoặc lưu ý"));
    const rows = within(await main.findByRole("table")).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(1);
    expect(rows[0]).toHaveTextContent("xấu");
  });

  it("refuses a spreadsheet or an oversized file without ever reading it", async () => {
    const read = vi.spyOn(FileReader.prototype, "readAsText");
    try {
      const { user, main } = await choose(csv("binary", "ds.xlsx"));
      await main.findByText("Không dùng được file này");
      const huge = new File([new Uint8Array(MAX_IMPORT_BYTES + 1)], "lon.csv", { type: "text/csv" });
      await user.upload(main.getByLabelText(/File danh sách/), huge);
      expect(await main.findByText(/vượt giới hạn mà giao diện đặt/)).toBeInTheDocument();
      expect(read).not.toHaveBeenCalled();
      // A normal file is still read.
      await user.upload(main.getByLabelText(/File danh sách/), csv("email\na@x.vn\n"));
      expect(await main.findByRole("table")).toBeInTheDocument();
      expect(read).toHaveBeenCalledTimes(1);
    } finally {
      read.mockRestore();
    }
  });

  it("explains why an Excel file cannot be read, and offers CSV instead", async () => {
    const { main } = await choose(csv("binary", "ds.xlsx"));
    expect(await main.findByText("Không dùng được file này")).toBeInTheDocument();
    expect(main.getByText(/chưa có thư viện đọc Excel/)).toBeInTheDocument();
    expect(main.queryByRole("table")).not.toBeInTheDocument();
  });

  it("reports a file with a missing identity column", async () => {
    const { main } = await choose(csv("ten,lop\nAn,1\n"));
    expect(await main.findByText(/Thiếu cột định danh/)).toBeInTheDocument();
  });

  it("lets the person pick another file after a good or a bad one", async () => {
    const { user, main } = await choose(csv("ten,lop\nAn,1\n"));
    await main.findByText(/Thiếu cột định danh/);
    await user.upload(main.getByLabelText(/File danh sách/), csv("email\na@x.vn\n"));
    expect(await main.findByRole("table")).toBeInTheDocument();
    expect(main.queryByText(/Thiếu cột định danh/)).not.toBeInTheDocument();
    await user.click(main.getByRole("button", { name: "Chọn file khác" }));
    expect(main.queryByRole("table")).not.toBeInTheDocument();
  });

  it("does not open for a class the teacher does not teach", async () => {
    setup("/teacher/courses/course-cs402/students/import");
    expect(await screen.findByText("Không tìm thấy lớp học")).toBeInTheDocument();
    expect(screen.queryByLabelText(/File danh sách/)).not.toBeInTheDocument();
  });
});

describe("Team adjustment preview (T07)", () => {
  async function open(route = "/teacher/courses/course-it3090/teams") {
    setup(route);
    const user = userEvent.setup();
    const main = await page();
    await user.click(await main.findByRole("button", { name: "Điều chỉnh nhóm" }));
    return { user, dialog: await screen.findByRole("dialog", { name: "Điều chỉnh nhóm" }) };
  }

  it("never lets the change be confirmed, and sends nothing", async () => {
    const tracker = trackRequests();
    const { user, dialog } = await open();
    const confirm = await within(dialog).findByRole("button", { name: "Xác nhận thay đổi" });
    expect(confirm).toBeDisabled();
    expect(confirm).toHaveAccessibleDescription(/chưa có hợp đồng API.*chính sách sĩ số/);
    await user.selectOptions(within(dialog).getByLabelText("Sinh viên"), within(dialog).getAllByRole("option")[1]);
    tracker.stop();
    expect(tracker.writes()).toEqual([]);
  });

  it("blocks a move into a full team and does not let the limit be bypassed", async () => {
    // SE330's NEXUS has 5 of 5 seats; the unteamed student cannot be seated there.
    const { user, dialog } = await open("/teacher/courses/course-se330/teams");
    await user.selectOptions(await within(dialog).findByLabelText("Sinh viên"), "00000000-0000-4000-8000-000000000006");
    await user.selectOptions(within(dialog).getByLabelText("Nhóm đích"), "team-nexus");
    expect(await within(dialog).findByText(/đã đủ sĩ số tối đa \(5\/5\)/)).toBeInTheDocument();
    expect(within(dialog).getByText("Chưa đủ điều kiện để xác nhận.")).toBeInTheDocument();
  });

  it("requires a replacement Leader when the only Leader would leave, and keeps history in view", async () => {
    // IT3090's VISION has one Leader (Phạm Quốc Huy) and one member.
    const { user, dialog } = await open();
    const roster = await within(dialog).findByLabelText("Sinh viên");
    const huy = within(roster).getByRole("option", { name: /Phạm Quốc Huy/ });
    await user.selectOptions(roster, huy);
    await user.selectOptions(within(dialog).getByLabelText("Nhóm đích"), "team-iot-sense");
    expect(await within(dialog).findByText(/sẽ mất Leader/)).toBeInTheDocument();

    await user.selectOptions(within(dialog).getByLabelText(/Leader mới của Team VISION/), within(dialog).getByRole("option", { name: "Vũ Ngọc Diệp" }));
    expect(await within(dialog).findByText(/Lịch sử thành viên và đóng góp cũ được giữ nguyên/)).toBeInTheDocument();
    expect(within(dialog).queryByText(/sẽ mất Leader/)).not.toBeInTheDocument();
    expect(within(dialog).getByText("Đúng điều kiện cơ bản, nhưng việc xác nhận vẫn chưa khả dụng.")).toBeInTheDocument();
  });

  it("checks a new team's name and first Leader", async () => {
    const { user, dialog } = await open();
    await user.click(within(dialog).getByRole("button", { name: "Tạo nhóm mới" }));
    await user.type(await within(dialog).findByLabelText("Tên nhóm"), "team vision");
    expect(await within(dialog).findByText("Đã có nhóm trùng tên trong lớp.")).toBeInTheDocument();
    expect(within(dialog).getByText(/nhóm không được thiếu Leader/)).toBeInTheDocument();
  });
});

describe("Feedback drafts", () => {
  const open = async (route: string, session = teacherTestSession) => {
    const view = setup(route, session);
    const main = await page();
    return { main, unmount: view.unmount, box: await main.findByRole("textbox", { name: /Soạn phản hồi cho nhóm/ }) };
  };

  it("keeps a draft across a reload of the page, per account", async () => {
    const first = await open("/teacher/courses/course-se330/teams/team-nexus");
    await userEvent.setup().type(first.box, "Nhóm cần làm rõ phạm vi Sprint 3");
    expect(first.main.getByText(/Đã lưu nháp trong tab này/)).toBeInTheDocument();
    first.unmount();

    const again = await open("/teacher/courses/course-se330/teams/team-nexus");
    await waitFor(() => expect(again.box).toHaveValue("Nhóm cần làm rõ phạm vi Sprint 3"));
  });

  it("does not show one account's draft to another", async () => {
    const mine = await open("/teacher/courses/course-se330/teams/team-nexus");
    await userEvent.setup().type(mine.box, "riêng tư");
    mine.unmount();
    // teacher2 has a different class; use their own team page and check the storage key is theirs.
    const other = await open("/teacher/courses/course-cs402/teams/team-deli", teacher2TestSession);
    expect(other.box).toHaveValue("");
    const keys = Object.keys(sessionStorage);
    expect(keys.some((key) => key.includes("00000000-0000-4000-8000-0000000000f1"))).toBe(true);
  });

  it("validates length, disables send with the reason, and clears the draft on request", async () => {
    const { main, box } = await open("/teacher/courses/course-se330/teams/team-nexus");
    const user = userEvent.setup();
    await user.click(box);
    await user.paste("x".repeat(FEEDBACK_MAX_LENGTH + 1));
    expect(await main.findByRole("alert")).toHaveTextContent(`vượt giới hạn ${FEEDBACK_MAX_LENGTH}`);
    const send = main.getByRole("button", { name: "Gửi phản hồi" });
    expect(send).toBeDisabled();
    expect(send).toHaveAccessibleDescription(/chưa có hợp đồng API bình luận\/phản hồi.*chưa gửi cho ai.*không nhận được thông báo/);
    await user.click(main.getByRole("button", { name: "Xóa nháp" }));
    expect(box).toHaveValue("");
    expect(main.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("forgets unsent drafts on an explicit sign-out", async () => {
    const { box } = await open("/teacher/courses/course-se330/teams/team-nexus");
    await userEvent.setup().type(box, "nháp chưa gửi");
    expect(Object.keys(sessionStorage).some((key) => key.startsWith("utask.draft."))).toBe(true);
    await userEvent.setup().click(screen.getAllByRole("button", { name: /Đăng xuất/ })[0]);
    await waitFor(() =>
      expect(Object.keys(sessionStorage).some((key) => key.startsWith("utask.draft."))).toBe(false),
    );
  });

  it("says there is no history to read instead of showing an empty fake list", async () => {
    const { main } = await open("/teacher/courses/course-it3090/teams/team-iot-vision");
    expect(main.getByText(/Chưa có phản hồi nào để hiển thị/)).toBeInTheDocument();
    expect(main.getByText(/lịch sử chưa có nguồn dữ liệu/)).toBeInTheDocument();
  });

  it("states that feedback never changes tasks and never sends anything", async () => {
    const tracker = trackRequests();
    const { main, box } = await open("/teacher/courses/course-se330/teams/team-nexus");
    await userEvent.setup().type(box, "ok");
    expect(main.getByText(/không tự đổi task, hạn chót hay người được giao/)).toBeInTheDocument();
    tracker.stop();
    expect(tracker.writes()).toEqual([]);
  });
});

describe("Attention list and signals (Phase 5)", () => {
  it("lists flagged teams on Home with category, evidence time and a link to the source", async () => {
    setup("/teacher");
    const panel = await screen.findByRole("region", { name: "Cần chú ý" });
    const vision = (await within(panel).findAllByText("Team VISION"))[0].closest("li") as HTMLElement;
    expect(vision).toHaveTextContent("Chưa ánh xạ");
    expect(vision).toHaveTextContent("Chưa có project");
    expect(vision).toHaveTextContent("Nguồn không cho biết thời điểm");
    expect(within(vision).getAllByRole("link", { name: /^Trang nhóm \(Team VISION, IT3090\)$/ })[0]).toHaveAttribute(
      "href",
      "/teacher/courses/course-it3090/teams/team-iot-vision",
    );
    expect(panel).toHaveTextContent("không dùng AI và không quy ra điểm");
    expect(panel).toHaveTextContent("Không có tín hiệu không có nghĩa là nhóm đang tốt");
  });

  it("gives every source link a name that says which team it is about", async () => {
    setup("/teacher");
    const panel = await screen.findByRole("region", { name: "Cần chú ý" });
    await within(panel).findAllByText("Team VISION");
    const names = within(panel)
      .getAllByRole("link")
      .map((link) => link.getAttribute("aria-label") ?? link.textContent);
    const sourceLinks = names.filter((name) => /^Trang nhóm/.test(name ?? ""));
    expect(sourceLinks.length).toBeGreaterThan(2);
    // The same label on two teams must still be told apart.
    expect(sourceLinks).toContain("Trang nhóm (Team VISION, IT3090)");
    expect(sourceLinks).toContain("Trang nhóm (Team SENSE, IT3090)");
    expect(new Set(sourceLinks.filter((name) => !/\(.*\)$/.test(name ?? ""))).size).toBe(0);
  });

  it("does not list a team that no rule flagged", async () => {
    setup("/teacher");
    const panel = await screen.findByRole("region", { name: "Cần chú ý" });
    await within(panel).findAllByText("Team VISION");
    expect(within(panel).queryByText("Team NEXUS")).not.toBeInTheDocument();
  });

  it("reports a class whose signals failed to load without hiding the others", async () => {
    setup("/teacher", teacherTestSession, "default", [
      http.get(`${API}/teacher/courses/course-it3090/oversight`, () =>
        HttpResponse.json({ detail: "Lỗi hệ thống, vui lòng thử lại sau." }, { status: 500 }),
      ),
    ]);
    const panel = await screen.findByRole("region", { name: "Cần chú ý" });
    expect(await within(panel).findByRole("alert", {}, { timeout: 8000 })).toHaveTextContent("Không tải được tín hiệu của 1 lớp");
    expect(within(panel).getByRole("button", { name: "Thử lại" })).toBeInTheDocument();
    // The other classes still answered; the list is not replaced by the error.
    expect(within(panel).queryByText("Team VISION")).not.toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Chỉ số tổng quan" })).toBeInTheDocument();
  }, 15000);

  it("tells a broken GitHub connection from a project that was never mapped, and links to the code page", async () => {
    setup("/teacher/courses/course-se330/oversight", teacherTestSession, "teacher-github-error");
    const main = await page();
    const row = within(await main.findByRole("table")).getByText("Team NEXUS").closest("tr") as HTMLElement;
    expect(row).toHaveTextContent("Kết nối GitHub");
    expect(row).toHaveTextContent("Mất kết nối đồng bộ GitHub (webhook lỗi)");
    expect(within(row).getByRole("link", { name: "Mã nguồn của nhóm (Team NEXUS)" })).toHaveAttribute(
      "href",
      "/projects/project-nexus/code",
    );
  });

  it("reports a project without a repository as not mapped, not as an error", async () => {
    setup("/teacher/courses/course-cs402/oversight", teacher2TestSession);
    const main = await page();
    const row = within(await main.findByRole("table")).getByText("Team DELI").closest("tr") as HTMLElement;
    expect(row).toHaveTextContent("Chưa ánh xạ");
    expect(row).toHaveTextContent("chưa gắn repository GitHub");
    expect(row).not.toHaveTextContent("Mất kết nối");
  });

  it("separates 'old data' from 'no data' and keeps both from scoring anyone", async () => {
    setup("/teacher/courses/course-se330/oversight");
    const main = await page();
    const rules = await main.findByRole("region", { name: "Cách tính tín hiệu" });
    expect(rules).toHaveTextContent("thiếu dữ liệu, dữ liệu cũ, kết nối, chưa ánh xạ, cơ cấu nhóm");
    expect(rules).toHaveTextContent("không quy đổi thành điểm");
    expect(main.queryByRole("button", { name: /AI|chạy|quét/i })).not.toBeInTheDocument();
  });
});
