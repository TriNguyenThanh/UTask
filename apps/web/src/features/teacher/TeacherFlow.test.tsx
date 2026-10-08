import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { toast } from "sonner";
import { afterEach, describe, expect, it, vi } from "vitest";

import { STUDENT_ID, TEACHER2_ID, TEACHER_ID } from "@/mocks/data/database";
import { MOCK_COURSE_META } from "@/mocks/data/directory";
import {
  buildTeacherCourseSummary,
  buildTeacherOversight,
  buildTeacherStudents,
  buildTeacherTeams,
} from "@/mocks/data/teacherFlow";
import { createMockHandlers } from "@/mocks/handlers";
import { server } from "@/mocks/server";
import { createMemoryRepository, type MockRepository } from "@/mocks/data/storage";
import type { MockScenario } from "@/mocks/scenarios";
import { teacherKeys } from "@/lib/query/teacherFlowHooks";
import {
  legacyStudentTestSession,
  renderAppRoutes,
  studentTestSession,
  teacher2TestSession,
  teacherTestSession,
} from "@/test/render";

/**
 * Phase 1 Teacher read flow, exercised through the real route table so route
 * guards, layout and lazy routes are all in play.
 */

const TAUGHT = ["course-se330", "course-se330-n2", "course-it3090"];
const NOT_TAUGHT = ["course-cs402", "course-se331", "course-does-not-exist"];

function setup(
  route: string,
  session: Parameters<typeof renderAppRoutes>[1] = teacherTestSession,
  scenario: MockScenario = "default",
  prepare?: (repository: MockRepository) => void,
) {
  const repository: MockRepository = createMemoryRepository(scenario);
  prepare?.(repository);
  server.use(...createMockHandlers(scenario, repository));
  return { repository, ...renderAppRoutes(route, session) };
}

/** A student account that the (mock) server also knows as a TEACHER. */
const dualRoleSession = {
  ...studentTestSession,
  user: { ...studentTestSession.user, roles: ["STUDENT", "TEACHER"] as ("STUDENT" | "TEACHER")[] },
};

function grantTeacherRoleToSv01(repository: MockRepository) {
  repository.db.authUsersById[STUDENT_ID] = {
    ...repository.db.authUsersById[STUDENT_ID],
    roles: ["STUDENT", "TEACHER"],
  };
}

/** Records every request path the app makes while `fn` runs. */
function trackRequests() {
  const paths: string[] = [];
  const listener = ({ request }: { request: Request }) => {
    paths.push(new URL(request.url).pathname);
  };
  server.events.on("request:start", listener);
  return { paths, stop: () => server.events.removeListener("request:start", listener) };
}

/** The page body only: the sidebar and top bar repeat class names and the user's name. */
const page = async () => within(await screen.findByRole("main"));

const pathname = (router: { state: { location: { pathname: string } } }) =>
  router.state.location.pathname;
const search = (router: { state: { location: { search: string } } }) => router.state.location.search;

afterEach(() => {
  vi.unstubAllEnvs();
  // Sign-in tests persist a mock refresh token; do not let it restore a session in the next test.
  sessionStorage.clear();
  toast.dismiss(); // sonner keeps toasts across tests
});

describe("Teacher home (T01)", () => {
  it("derives every metric from the classes it lists", async () => {
    setup("/teacher");
    await screen.findByRole("heading", { name: "Bàn làm việc giảng viên" });

    const summaries = TAUGHT.map((id) => buildTeacherCourseSummary(id)!);
    const stats = await screen.findByRole("region", { name: "Chỉ số tổng quan" });
    const value = (label: string) => within(stats).getByRole("group", { name: label });

    expect(value("Lớp phụ trách")).toHaveTextContent(String(summaries.length));
    expect(value("Nhóm")).toHaveTextContent(String(summaries.reduce((n, c) => n + c.teamCount, 0)));
    expect(value("Chưa có nhóm")).toHaveTextContent(
      String(summaries.reduce((n, c) => n + c.studentsWithoutTeam, 0)),
    );
    expect(value("Nhóm chưa có project")).toHaveTextContent(
      String(summaries.reduce((n, c) => n + c.teamsWithoutProject, 0)),
    );
    // No source for task deadlines yet: say so instead of showing 0.
    expect(value("Task quá hạn")).toHaveTextContent("Chưa có dữ liệu");
    expect(value("Task quá hạn")).not.toHaveTextContent(/^\s*Task quá hạn\s*0/);
  });

  it("lists only assigned classes, with the two SE330 classes told apart", async () => {
    setup("/teacher");
    const list = await screen.findByRole("region", { name: "Danh sách lớp" });
    expect(within(list).getAllByRole("link", { name: /Đồ án/ })).toHaveLength(3);
    expect(within(list).getByText(/SE330 • Lớp 1/)).toBeInTheDocument();
    expect(within(list).getByText(/SE330 • Lớp 2/)).toBeInTheDocument();
    expect(within(list).getAllByText(/IT3090/).length).toBeGreaterThan(0);
    expect(within(list).queryByText(/CS402/)).not.toBeInTheDocument();
    expect(within(list).queryByText(/SE331/)).not.toBeInTheDocument();
  });

  it("states the last activity with its kind, or says there is none", async () => {
    setup("/teacher");
    const list = await screen.findByRole("region", { name: "Danh sách lớp" });
    expect(within(list).getAllByText(/Cập nhật issue •/)).toHaveLength(1); // SE330 only
    expect(within(list).getAllByText("Chưa ghi nhận hoạt động")).toHaveLength(2);
  });

  it("disables Tạo lớp and explains why, without linking to a missing page", async () => {
    setup("/teacher");
    await screen.findByRole("heading", { name: "Bàn làm việc giảng viên" });
    const create = screen.getByRole("button", { name: "Tạo lớp" });
    expect(create).toBeDisabled();
    expect(create).toHaveAccessibleDescription(/Tạo lớp sẽ khả dụng/);
  });

  it("keeps the term filter in the URL and distinguishes it from having no classes", async () => {
    const { router } = setup("/teacher?term=HK2%202030");
    expect(await screen.findByText("Không có lớp trong học kỳ này")).toBeInTheDocument();
    expect(screen.queryByText("Chưa phụ trách lớp nào")).not.toBeInTheDocument();

    const user = userEvent.setup();
    await user.selectOptions(screen.getByLabelText("Học kỳ"), "all");
    await waitFor(() => expect(search(router)).toBe(""));
    expect(await screen.findByRole("region", { name: "Danh sách lớp" })).toBeInTheDocument();
  });

  it("shows an empty state for a teacher with no classes", async () => {
    setup("/teacher", teacherTestSession, "teacher-empty");
    expect(await screen.findByText("Chưa phụ trách lớp nào", { selector: "h2" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Tạo lớp" })).toBeDisabled();
  });

  it("shows a loading skeleton while the classes load", async () => {
    setup("/teacher", teacherTestSession, "slow-network");
    expect(
      await screen.findByRole("status", { name: "Đang tải bàn làm việc giảng viên" }),
    ).toBeInTheDocument();
  });

  it("shows an error with retry that re-requests", async () => {
    setup("/teacher", teacherTestSession, "server-error");
    await screen.findByText("Không thể tải dữ liệu");
    const tracker = trackRequests();
    await userEvent.setup().click(screen.getAllByRole("button", { name: "Thử lại" })[0]);
    await waitFor(() => expect(tracker.paths.some((p) => p.endsWith("/teacher/courses"))).toBe(true));
    tracker.stop();
  });
});

describe("Class list (T02)", () => {
  it("filters by name or code in the URL and tells 'no match' from 'no classes'", async () => {
    const { router } = setup("/teacher/courses?q=iot");
    const user = userEvent.setup();
    expect(await (await page()).findByRole("link", { name: "Đồ án IoT" })).toBeInTheDocument();
    expect((await page()).queryByRole("link", { name: /Công nghệ Phần mềm/ })).not.toBeInTheDocument();

    const box = screen.getByLabelText("Tìm lớp");
    await user.clear(box);
    await user.type(box, "zzz");
    expect(await screen.findByText("Không có lớp khớp bộ lọc")).toBeInTheDocument();
    expect(search(router)).toBe("?q=zzz");
    expect(screen.queryByText("Chưa phụ trách lớp nào")).not.toBeInTheDocument();

    await user.clear(box);
    expect(await (await page()).findAllByRole("link", { name: /Công nghệ Phần mềm/ })).toHaveLength(2);
    expect(search(router)).toBe("");
  });

  it("searches by subject code and finds both SE330 classes", async () => {
    setup("/teacher/courses?q=se330");
    expect(await (await page()).findAllByRole("link", { name: /Công nghệ Phần mềm/ })).toHaveLength(2);
    expect((await page()).queryByRole("link", { name: "Đồ án IoT" })).not.toBeInTheDocument();
  });
});

describe("Access: role, assignment, sidebar and deep link agree", () => {
  it.each([...TAUGHT, ...NOT_TAUGHT])(
    "teacher@ opening %s by URL matches the sidebar",
    async (courseId) => {
      setup(`/teacher/courses/${courseId}`);
      const allowed = TAUGHT.includes(courseId);

      if (allowed) {
        await screen.findByRole("heading", { level: 1, name: MOCK_COURSE_META[courseId].courseName });
      } else {
        await screen.findByText("Không tìm thấy lớp học");
      }
      const sidebar = await screen.findByRole("navigation", { name: "Điều hướng giảng viên" });
      const nav = sidebar.parentElement as HTMLElement;
      await waitFor(() =>
        expect(within(nav).getAllByRole("link", { name: /sinh viên · / }).length).toBe(TAUGHT.length),
      );
      const inSidebar = within(nav)
        .getAllByRole("link", { name: /sinh viên · / })
        .some((link) => link.getAttribute("href") === `/teacher/courses/${courseId}`);
      expect(inSidebar).toBe(allowed);
    },
  );

  it("treats a class outside the assignment exactly like a class that does not exist", async () => {
    const outside = setup("/teacher/courses/course-cs402");
    await screen.findByText("Không tìm thấy lớp học");
    const outsideHtml = document.querySelector("main")!.innerHTML;
    outside.unmount();

    setup("/teacher/courses/course-does-not-exist");
    await screen.findByText("Không tìm thấy lớp học");
    expect(document.querySelector("main")!.innerHTML).toBe(outsideHtml);
    expect(screen.queryByText(/CS402/)).not.toBeInTheDocument();
  });

  it("keeps teacher2 out of teacher@'s classes and shows them their own", async () => {
    const blocked = setup("/teacher/courses/course-se330/students", teacher2TestSession);
    await screen.findByText("Không tìm thấy lớp học");
    expect(screen.queryByText("Lê Minh Khoa")).not.toBeInTheDocument();
    blocked.unmount();

    setup("/teacher/courses/course-cs402/students", teacher2TestSession);
    expect(await screen.findAllByText("Phạm Quốc Huy")).not.toHaveLength(0);
  });

  it.each([
    ["a student", studentTestSession],
    ["a session saved before roles existed", legacyStudentTestSession],
  ])("blocks %s from the Teacher area without issuing a Teacher request", async (_label, session) => {
    const tracker = trackRequests();
    for (const route of ["/teacher", "/teacher/courses", "/teacher/courses/course-se330/students"]) {
      const view = setup(route, session);
      expect(await screen.findByText("Không đủ quyền truy cập")).toBeInTheDocument();
      expect(screen.getByText("Khu vực này chỉ dành cho tài khoản giảng viên.")).toBeInTheDocument();
      // Blocked, not bounced: the page is a stable forbidden screen.
      expect(pathname(view.router)).toBe(route);
      // Student chrome, not Teacher chrome.
      expect(screen.queryByRole("navigation", { name: "Điều hướng giảng viên" })).not.toBeInTheDocument();
      view.unmount();
    }
    tracker.stop();
    expect(tracker.paths.filter((path) => path.includes("/teacher/"))).toEqual([]);
  });

  it("lets a student keep using their own area afterwards", async () => {
    const { router } = setup("/teacher", studentTestSession);
    await screen.findByText("Không đủ quyền truy cập");
    await userEvent.setup().click(screen.getByRole("link", { name: "Quay lại trang chủ" }));
    await waitFor(() => expect(pathname(router)).toBe("/my-work"));
  });

  it("does not turn the TEACHER role into access to a class the account studies in", async () => {
    // SV01 studies SE330 and now also holds the TEACHER role. The role opens the
    // Teacher space; it does not make SV01 an instructor of SE330.
    const home = setup("/teacher", dualRoleSession, "default", grantTeacherRoleToSv01);
    await screen.findByText("Chưa phụ trách lớp nào", { selector: "h2" });
    home.unmount();

    setup("/teacher/courses/course-se330", dualRoleSession, "default", grantTeacherRoleToSv01);
    expect(await screen.findByText("Không tìm thấy lớp học")).toBeInTheDocument();
  });
});

describe("Entry points", () => {
  it("sends each account to its own home from /", async () => {
    const teacher = setup("/", teacherTestSession);
    await waitFor(() => expect(pathname(teacher.router)).toBe("/teacher"));
    teacher.unmount();

    const student = setup("/", studentTestSession);
    await waitFor(() => expect(pathname(student.router)).toBe("/my-work"));
    student.unmount();

    const dual = setup("/", dualRoleSession);
    await waitFor(() => expect(pathname(dual.router)).toBe("/my-work"));
  });

  it("offers a dual-role account the Teacher space from Student navigation, and back", async () => {
    const view = setup("/my-work", dualRoleSession, "default", grantTeacherRoleToSv01);
    const link = await screen.findByRole("link", { name: "Không gian giảng viên" });
    expect(link).toHaveAttribute("href", "/teacher");
    view.unmount();

    setup("/teacher", dualRoleSession, "default", grantTeacherRoleToSv01);
    const links = await screen.findAllByRole("link", { name: "Không gian sinh viên" });
    expect(links.length).toBeGreaterThan(0);
    for (const link of links) {
      expect(link).toHaveAttribute("href", "/my-work");
    }
  });

  it("does not show the Teacher-space link to a plain student", async () => {
    setup("/my-work", studentTestSession);
    await screen.findAllByText("Lê Minh Khoa");
    expect(screen.queryByRole("link", { name: "Không gian giảng viên" })).not.toBeInTheDocument();
  });

  async function signIn(email: string) {
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Email trường học"), email);
    await user.type(screen.getByLabelText("Mật khẩu"), "demo1234");
    await user.click(screen.getByRole("button", { name: "Đăng nhập" }));
  }

  it("lands a teacher-only login on /teacher", async () => {
    const view = setup("/login", null);
    await signIn("teacher@utask.test");
    await waitFor(() => expect(pathname(view.router)).toBe("/teacher"));
    expect(await screen.findByRole("heading", { name: "Bàn làm việc giảng viên" })).toBeInTheDocument();
  });

  it("lands a student login on /my-work", async () => {
    const view = setup("/login", null);
    await signIn("student@utask.test");
    await waitFor(() => expect(pathname(view.router)).toBe("/my-work"));
  });

  it("honours a valid returnTo, and the target still checks access", async () => {
    const view = setup("/teacher/courses/course-cs402", null);
    await waitFor(() => expect(pathname(view.router)).toBe("/login"));
    await signIn("teacher@utask.test");
    await waitFor(() => expect(pathname(view.router)).toBe("/teacher/courses/course-cs402"));
    expect(await screen.findByText("Không tìm thấy lớp học")).toBeInTheDocument();
  });

  it("does not loop a student who signs in to a Teacher-only returnTo", async () => {
    const view = setup("/teacher/courses", null);
    await waitFor(() => expect(pathname(view.router)).toBe("/login"));
    await signIn("student@utask.test");
    await waitFor(() => expect(pathname(view.router)).toBe("/teacher/courses"));
    expect(await screen.findByText("Không đủ quyền truy cập")).toBeInTheDocument();
    expect(pathname(view.router)).toBe("/teacher/courses");
  });
});

describe("Class shell and overview (T04)", () => {
  it("shows name, term, lecturers and join code, with working breadcrumb links", async () => {
    setup("/teacher/courses/course-it3090");
    await screen.findByRole("heading", { level: 1, name: "Đồ án IoT" });
    expect(screen.getByText("IT3090", { selector: "span.font-mono" })).toBeInTheDocument();
    expect(screen.getByText(/HK1 2026–2027 • \d+ sinh viên • 2 nhóm/)).toBeInTheDocument();
    expect(screen.getByText(/Giảng viên: TS\. Đặng Văn Cường, TS\. Trần Minh Đức/)).toBeInTheDocument();
    expect(screen.getAllByText("IOT3090-X").length).toBeGreaterThan(0);

    const crumbs = screen.getByRole("navigation", { name: "Breadcrumb" });
    expect(within(crumbs).getByRole("link", { name: "Trang chủ" })).toHaveAttribute("href", "/teacher");
    expect(within(crumbs).getByRole("link", { name: "Lớp phụ trách" })).toHaveAttribute(
      "href",
      "/teacher/courses",
    );
  });

  it("gives the two SE330 classes their own join code and data", async () => {
    const first = setup("/teacher/courses/course-se330");
    expect((await screen.findAllByText("SE330-A1")).length).toBeGreaterThan(0);
    first.unmount();
    setup("/teacher/courses/course-se330-n2");
    expect((await screen.findAllByText("SE330-B2")).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/SE330 • Lớp 2/).length).toBeGreaterThan(0);
    expect(await screen.findByText("Lớp chưa có sinh viên")).toBeInTheDocument();
  });

  it("derives overview numbers and lists the teams without a project", async () => {
    setup("/teacher/courses/course-it3090");
    const stats = await screen.findByRole("region", { name: "Chỉ số của lớp" });
    const summary = buildTeacherCourseSummary("course-it3090")!;
    expect(within(stats).getByRole("group", { name: "Sinh viên" })).toHaveTextContent(String(summary.studentCount));
    expect(within(stats).getByRole("group", { name: "Chưa có nhóm" })).toHaveTextContent(
      String(summary.studentsWithoutTeam),
    );
    expect(within(stats).getByRole("group", { name: "Nhóm có tín hiệu cần chú ý" })).toHaveTextContent(
      String(summary.teamsWithSignals),
    );
    expect(await screen.findByText("Team VISION")).toBeInTheDocument();
    expect(screen.getByText("Team SENSE")).toBeInTheDocument();
    expect(screen.getByText(/Xem workspace của nhóm .* sẽ khả dụng ở giai đoạn sau/)).toBeInTheDocument();
  });

  it("offers only existing tabs and a disabled Cài đặt placeholder", async () => {
    setup("/teacher/courses/course-se330");
    await screen.findByRole("heading", { level: 1 });
    const tabs = screen.getByRole("navigation", { name: "Các mục của lớp" });
    expect(
      within(tabs)
        .getAllByRole("link")
        .map((l) => l.textContent?.replace(/\s*\d+$/, "")),
    ).toEqual(["Tổng quan", "Sinh viên", "Nhóm", "Giám sát"]);
    expect(within(tabs).getByText("Cài đặt")).toHaveAttribute("aria-disabled", "true");
    expect(within(tabs).queryByRole("link", { name: "Cài đặt" })).not.toBeInTheDocument();
  });

  it("navigates between tabs with real URLs", async () => {
    const { router } = setup("/teacher/courses/course-se330");
    const user = userEvent.setup();
    await screen.findByRole("heading", { level: 1 });
    const tab = (name: RegExp) =>
      within(screen.getByRole("navigation", { name: "Các mục của lớp" })).getByRole("link", { name });
    await user.click(tab(/^Sinh viên/));
    await waitFor(() => expect(pathname(router)).toBe("/teacher/courses/course-se330/students"));
    await user.click(tab(/^Nhóm/));
    await waitFor(() => expect(pathname(router)).toBe("/teacher/courses/course-se330/teams"));
    await user.click(tab(/^Giám sát/));
    await waitFor(() => expect(pathname(router)).toBe("/teacher/courses/course-se330/oversight"));
  });
});

describe("Join code copy", () => {
  function stubClipboard(writeText: (text: string) => Promise<void>) {
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
  }

  it("confirms only when the clipboard write succeeds", async () => {
    setup("/teacher/courses/course-se330");
    const user = userEvent.setup();
    const writeText = vi.fn().mockResolvedValue(undefined);
    await screen.findAllByText("SE330-A1");
    stubClipboard(writeText);
    await user.click(screen.getByRole("button", { name: "Sao chép mã tham gia" }));
    expect(writeText).toHaveBeenCalledWith("SE330-A1");
    expect(await screen.findByText("Đã sao chép mã tham gia.")).toBeInTheDocument();
  });

  it("reports failure instead of claiming success", async () => {
    setup("/teacher/courses/course-se330");
    const user = userEvent.setup();
    await screen.findAllByText("SE330-A1");
    stubClipboard(() => Promise.reject(new Error("denied")));
    await user.click(screen.getByRole("button", { name: "Sao chép mã tham gia" }));
    expect(await screen.findByText(/Không sao chép được mã/)).toBeInTheDocument();
    expect(screen.queryByText("Đã sao chép mã tham gia.")).not.toBeInTheDocument();
  });
});

describe("Students (T05)", () => {
  it("shows each student's team and role in this class, matching the Student view", async () => {
    setup("/teacher/courses/course-se330/students");
    const table = await screen.findByRole("table");
    const row = (name: string) => within(table).getByText(name).closest("tr") as HTMLElement;

    expect(row("Lê Minh Khoa")).toHaveTextContent("Team NEXUS");
    expect(row("Lê Minh Khoa")).toHaveTextContent("Leader");
    expect(row("Nguyễn Hoàng Nam")).toHaveTextContent("Leader");
    expect(row("Đặng Thảo Linh")).toHaveTextContent("Thành viên");
    expect(row("Hoàng Trọng Khang")).toHaveTextContent("Chưa có nhóm");
    // Raw ids never leak into the table.
    expect(table).not.toHaveTextContent("team-nexus");
    expect(table).toHaveTextContent("21020999");
  });

  it("shows SV01 without a team in IT3090 and never invents activation state", async () => {
    setup("/teacher/courses/course-it3090/students");
    const table = await screen.findByRole("table");
    expect(within(table).getByText("Lê Minh Khoa").closest("tr")).toHaveTextContent("Chưa có nhóm");
    expect(screen.queryByText(/kích hoạt/i)).not.toBeInTheDocument();
  });

  it("filters by team state and text, kept in the URL", async () => {
    const { router } = setup("/teacher/courses/course-se330/students?team=no-team");
    const table = await screen.findByRole("table");
    const names = within(table).getAllByRole("row").slice(1).map((r) => r.textContent);
    expect(names).toHaveLength(1);
    expect(names[0]).toContain("Hoàng Trọng Khang");

    const user = userEvent.setup();
    const noTeamChip = screen.getByRole("button", { name: /^Chưa có nhóm/ });
    expect(noTeamChip).toHaveAttribute("aria-pressed", "true");
    await user.click(screen.getByRole("button", { name: /^Đã có nhóm/ }));
    await waitFor(() => expect(search(router)).toBe("?team=has-team"));
    expect(noTeamChip).toHaveAttribute("aria-pressed", "false");
    expect(await screen.findAllByRole("row")).toHaveLength(1 + 5);

    await user.type(screen.getByLabelText("Tìm sinh viên"), "21021004");
    expect(await screen.findByText("Không có sinh viên khớp bộ lọc")).toBeInTheDocument();
    expect(search(router)).toContain("q=21021004");
  });

  it("finds a student by email or student code", async () => {
    setup("/teacher/courses/course-se330/students?q=thang.bq");
    const table = await screen.findByRole("table");
    expect(within(table).getAllByRole("row")).toHaveLength(2);
    expect(within(table).getByText("Bùi Quang Thắng")).toBeInTheDocument();
  });

  it("explains an empty class and disables add and import with a reason", async () => {
    setup("/teacher/courses/course-se330-n2/students");
    expect(await screen.findByText("Lớp chưa có sinh viên", { selector: "h2" })).toBeInTheDocument();
    for (const name of ["Thêm sinh viên", "Nhập danh sách"]) {
      const button = screen.getByRole("button", { name });
      expect(button).toBeDisabled();
      expect(button).toHaveAccessibleDescription(/giai đoạn sau/);
    }
  });

  it("falls back to cards on narrow screens with the same data", async () => {
    setup("/teacher/courses/course-se330/students");
    await screen.findByRole("table");
    const cards = screen.getAllByRole("listitem").filter((li) => li.textContent?.includes("21021004"));
    expect(cards).toHaveLength(1);
    expect(cards[0]).toHaveTextContent("Chưa có nhóm");
  });
});

describe("Teams (T07)", () => {
  it("shows leaders, headcount, project and measured progress for NEXUS", async () => {
    setup("/teacher/courses/course-se330/teams");
    const card = (await screen.findByText("Team NEXUS")).closest('[data-slot="card"]') as HTMLElement;
    const nexus = buildTeacherTeams("course-se330")[0];

    expect(card).toHaveTextContent("Trưởng nhóm: Nguyễn Hoàng Nam, Lê Minh Khoa");
    expect(card).toHaveTextContent("5/5 thành viên");
    expect(card).toHaveTextContent("NEXUS");
    expect(card).toHaveTextContent(nexus.project!.name);
    const bar = within(card).getByRole("progressbar", { name: "Tiến độ Team NEXUS" });
    expect(bar).toHaveAttribute("aria-valuenow", String(nexus.progress!.percent));
    expect(card).toHaveTextContent("theo điểm Sprint đang chạy");
    expect(card).toHaveTextContent("Cập nhật issue •");
  });

  it("treats a team with no project as valid and reports no progress, not 0%", async () => {
    setup("/teacher/courses/course-it3090/teams");
    const vision = (await screen.findByText("Team VISION")).closest('[data-slot="card"]') as HTMLElement;
    expect(vision).toHaveTextContent("Chưa có project");
    expect(vision).toHaveTextContent("Chưa có project để đo tiến độ");
    expect(vision).toHaveTextContent("Chưa ghi nhận hoạt động");
    expect(within(vision).queryByRole("progressbar")).not.toBeInTheDocument();
    expect(vision).not.toHaveTextContent("0%");
    expect(vision).toHaveTextContent("Phạm Quốc Huy");
  });

  it("links each team to its dashboard instead of a disabled button", async () => {
    setup("/teacher/courses/course-se330/teams");
    await screen.findByText("Team NEXUS");
    expect(screen.queryByRole("button", { name: /Xem chi tiết/ })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Xem chi tiết Team NEXUS" })).toHaveAttribute(
      "href",
      "/teacher/courses/course-se330/teams/team-nexus",
    );
    expect(screen.getByText(/Chuyển thành viên, phân nhóm và chỉ định Leader sẽ khả dụng/)).toBeInTheDocument();
  });

  it("lists students without a team in their own section", async () => {
    setup("/teacher/courses/course-it3090/teams");
    await screen.findByText("Team VISION");
    const section = await screen.findByRole("region", { name: "Sinh viên chưa có nhóm" });
    const expected = buildTeacherStudents("course-it3090").filter((s) => s.team === null);
    await waitFor(() => expect(within(section).getAllByRole("listitem")).toHaveLength(expected.length));
    for (const student of expected) {
      expect(within(section).getByText(student.name)).toBeInTheDocument();
    }
  });

  it("shows the headcount stats from the class and the size rule", async () => {
    setup("/teacher/courses/course-it3090/teams");
    const stats = await screen.findByRole("region", { name: "Chỉ số nhóm" });
    const summary = buildTeacherCourseSummary("course-it3090")!;
    const value = (label: string) => within(stats).getByRole("group", { name: label });
    expect(value("Tổng số sinh viên")).toHaveTextContent(String(summary.studentCount));
    expect(value("Chưa có nhóm")).toHaveTextContent(String(summary.studentsWithoutTeam));
    expect(value("Đã có nhóm")).toHaveTextContent(String(summary.studentCount - summary.studentsWithoutTeam));
    expect(value("Quy định sĩ số")).toHaveTextContent("3–5");
  });

  it("filters teams by project, kept in the URL and restored on refresh", async () => {
    const first = setup("/teacher/courses/course-it3090/teams");
    const user = userEvent.setup();
    await screen.findByText("Team VISION");
    await user.click(screen.getByRole("button", { name: /^Chưa có project/ }));
    await waitFor(() => expect(search(first.router)).toBe("?filter=no-project"));
    first.unmount();

    // All SE330 teams have a project: the same filter now matches nothing.
    setup("/teacher/courses/course-se330/teams?filter=no-project");
    expect(await screen.findByText("Không có nhóm khớp bộ lọc")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Chưa có project/ })).toHaveAttribute("aria-pressed", "true");
  });

  it("shows every member with role and student code, and says how many slots are open", async () => {
    setup("/teacher/courses/course-it3090/teams");
    const vision = (await screen.findByText("Team VISION")).closest('[data-slot="card"]') as HTMLElement;
    const team = buildTeacherTeams("course-it3090").find((t) => t.name === "Team VISION")!;
    const list = within(vision).getByRole("list", { name: "Thành viên Team VISION" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(team.members.length);
    for (const member of team.members) {
      expect(list).toHaveTextContent(member.name);
      expect(list).toHaveTextContent(`MSSV: ${member.studentCode}`);
    }
    expect(vision).toHaveTextContent(`${team.memberCount}/${team.maxMembers} thành viên`);
    if (team.memberCount < team.maxMembers) {
      expect(vision).toHaveTextContent(`còn ${team.maxMembers - team.memberCount} chỗ`);
    }
  });

  it("shows empty states for the class without teams or students", async () => {
    setup("/teacher/courses/course-se330-n2/teams");
    expect(await screen.findByText("Lớp chưa có nhóm")).toBeInTheDocument();
    expect(screen.getByText("Lớp chưa có sinh viên.")).toBeInTheDocument();
  });
});

describe("Oversight (read-only)", () => {
  it("lists every team with progress, its basis and the cause of each signal", async () => {
    setup("/teacher/courses/course-se330/oversight");
    const main = await page();
    const nexus = buildTeacherOversight("course-se330")[0];
    const table = await main.findByRole("table");
    const row = within(table).getByText("Team NEXUS").closest("tr") as HTMLElement;
    expect(row).toHaveTextContent(nexus.project!.name);
    expect(within(row).getByRole("progressbar", { name: "Tiến độ Team NEXUS" })).toHaveAttribute(
      "aria-valuenow",
      String(nexus.progress!.percent),
    );
    expect(row).toHaveTextContent("theo điểm Sprint đang chạy");
    expect(row).toHaveTextContent(`${nexus.issues!.done}/${nexus.issues!.total} issue đã hoàn thành`);
    expect(row).toHaveTextContent(nexus.sprint!.name);
    expect(row).toHaveTextContent("Chưa phát hiện tín hiệu");
  });

  it("states a missing project and missing progress instead of drawing 0%", async () => {
    setup("/teacher/courses/course-it3090/oversight");
    const main = await page();
    const table = await main.findByRole("table");
    const row = within(table).getByText("Team VISION").closest("tr") as HTMLElement;
    expect(row).toHaveTextContent("Chưa có project để đo tiến độ");
    expect(row).toHaveTextContent("Chưa ghi nhận hoạt động");
    expect(within(row).queryByRole("progressbar")).not.toBeInTheDocument();
    expect(row).not.toHaveTextContent("0%");
  });

  it("counts teams with signals in the summary and in the class summary, consistently", async () => {
    setup("/teacher/courses/course-it3090/oversight");
    const main = await page();
    const stats = await main.findByRole("region", { name: "Tóm tắt giám sát" });
    const rows = buildTeacherOversight("course-it3090");
    const flagged = rows.filter((r) => r.signals.length > 0).length;
    expect(within(stats).getByRole("group", { name: "Có tín hiệu cần chú ý" })).toHaveTextContent(String(flagged));
    expect(within(stats).getByRole("group", { name: "Tổng số nhóm" })).toHaveTextContent(String(rows.length));
    expect(buildTeacherCourseSummary("course-it3090")!.teamsWithSignals).toBe(flagged);
  });

  it("filters by signal, searches by name and sorts, all kept in the URL", async () => {
    const { router } = setup("/teacher/courses/course-it3090/oversight");
    const user = userEvent.setup();
    const main = await page();
    await main.findByRole("table");

    await user.click(main.getByRole("button", { name: /^Chưa có tín hiệu/ }));
    await waitFor(() => expect(search(router)).toBe("?filter=no-signals"));
    expect(await main.findByText("Không có nhóm khớp bộ lọc")).toBeInTheDocument();

    await user.click(main.getByRole("button", { name: /^Tất cả/ }));
    await user.type(main.getByLabelText("Tìm nhóm"), "sense");
    await waitFor(() => expect(search(router)).toContain("q=sense"));
    const table = await main.findByRole("table");
    expect(within(table).getAllByRole("row")).toHaveLength(2);
    expect(within(table).getByText("Team SENSE")).toBeInTheDocument();

    await user.selectOptions(main.getByLabelText("Sắp xếp"), "name");
    await waitFor(() => expect(search(router)).toContain("sort=name"));
  });

  it("explains the rules, with the threshold from the server, and offers no AI or grading", async () => {
    setup("/teacher/courses/course-se330/oversight");
    const main = await page();
    const rules = await main.findByRole("region", { name: "Cách tính tín hiệu" });
    expect(rules).toHaveTextContent("không dùng AI");
    expect(rules).toHaveTextContent("không quy đổi thành điểm");
    expect(rules).toHaveTextContent("7 ngày");
    expect(main.queryByRole("button", { name: /chấm điểm|AI|gemini/i })).not.toBeInTheDocument();
    expect(main.queryByRole("link", { name: /chấm điểm/i })).not.toBeInTheDocument();
  });

  it("shows an empty state for a class without teams", async () => {
    setup("/teacher/courses/course-se330-n2/oversight");
    expect(await screen.findByText("Lớp chưa có nhóm để giám sát")).toBeInTheDocument();
  });

  it("shows retry on failure and keeps the class header", async () => {
    setup("/teacher/courses/course-se330/oversight", teacherTestSession, "teacher-partial-error");
    expect(await screen.findByText("Không thể tải dữ liệu")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1, name: /Công nghệ Phần mềm/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Thử lại" })).toBeInTheDocument();
  });

  it("treats a class outside the assignment like a missing one, with no data", async () => {
    setup("/teacher/courses/course-cs402/oversight");
    expect(await screen.findByText("Không tìm thấy lớp học")).toBeInTheDocument();
    expect(screen.queryByText(/Team /)).not.toBeInTheDocument();
  });

  it("keeps a student out", async () => {
    setup("/teacher/courses/course-se330/oversight", studentTestSession);
    expect(await screen.findByText("Không đủ quyền truy cập")).toBeInTheDocument();
  });
});

describe("Teacher sidebar", () => {
  it("shows the sections of the open class and links only to existing pages", async () => {
    setup("/teacher/courses/course-se330/students");
    const nav = await screen.findByRole("list", { name: "Mục của SE330 • Lớp 1" });
    expect(
      within(nav)
        .getAllByRole("link")
        .map((link) => link.getAttribute("href")),
    ).toEqual([
      "/teacher/courses/course-se330",
      "/teacher/courses/course-se330/students",
      "/teacher/courses/course-se330/teams",
      "/teacher/courses/course-se330/oversight",
    ]);
    expect(within(nav).getByRole("link", { name: "Sinh viên" })).toHaveAttribute("aria-current", "page");
  });

  it("shows no class sections outside a class", async () => {
    setup("/teacher/courses");
    await screen.findByRole("heading", { name: "Lớp phụ trách", level: 1 });
    expect(screen.queryByRole("list", { name: /^Mục của / })).not.toBeInTheDocument();
  });
});

describe("Partial failure and access loss", () => {
  it("keeps the class header when only the student list fails, and retries", async () => {
    setup("/teacher/courses/course-se330/students", teacherTestSession, "teacher-partial-error");
    expect(await screen.findByText("Không thể tải dữ liệu")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1, name: /Công nghệ Phần mềm/ })).toBeInTheDocument();

    const tracker = trackRequests();
    await userEvent.setup().click(screen.getByRole("button", { name: "Thử lại" }));
    await waitFor(() => expect(tracker.paths.some((p) => p.endsWith("/students"))).toBe(true));
    tracker.stop();
    expect(screen.getByText("Không thể tải dữ liệu")).toBeInTheDocument();
  });

  it("drops a class's data from screen and cache when access is revoked mid-session", async () => {
    const view = setup("/teacher/courses/course-se330/students");
    await (await page()).findAllByText("Lê Minh Khoa");
    const studentsKey = teacherKeys.students(TEACHER_ID, "course-se330");
    expect(view.queryClient.getQueryData(studentsKey)).toBeDefined();

    // Assignment revoked: the server now answers 404 for this class.
    server.use(
      http.get("*/api/work/api/v1/teacher/courses/course-se330*", () =>
        HttpResponse.json({ detail: "Không tìm thấy lớp học." }, { status: 404 }),
      ),
    );
    await view.queryClient.invalidateQueries();

    // The students tab and then the class shell both report the loss; wait for the final state.
    await waitFor(() => {
      expect(screen.getByText("Không tìm thấy lớp học")).toBeInTheDocument();
      expect(screen.queryByRole("heading", { level: 1, name: /Công nghệ Phần mềm/ })).not.toBeInTheDocument();
    });
    // Nothing of the class is on screen: not the roster, not the class header or join code.
    expect((await page()).queryByText("Lê Minh Khoa")).not.toBeInTheDocument();
    expect((await page()).queryByText("SE330-A1")).not.toBeInTheDocument();
    // The cached roster and teams of that class are dropped.
    await waitFor(() => expect(view.queryClient.getQueryData(studentsKey)).toBeUndefined());
    expect(view.queryClient.getQueryData(teacherKeys.teams(TEACHER_ID, "course-se330"))).toBeUndefined();
  });
});

describe("Cache across accounts", () => {
  it("scopes every Teacher key by user and class", () => {
    expect(teacherKeys.course("a", "x")).not.toEqual(teacherKeys.course("b", "x"));
    expect(teacherKeys.students("a", "x")).toEqual(["teacher", "a", "courses", "x", "students"]);
    expect(teacherKeys.course("a", "x")).not.toEqual(teacherKeys.course("a", "y"));
  });

  it("clears the cache on logout", async () => {
    const view = setup("/teacher");
    const user = userEvent.setup();
    await screen.findByRole("region", { name: "Danh sách lớp" });
    expect(view.queryClient.getQueryCache().findAll({ queryKey: ["teacher"] }).length).toBeGreaterThan(0);

    await user.click(screen.getByRole("button", { name: /Đăng xuất/, hidden: true }));
    await waitFor(() => expect(pathname(view.router)).toBe("/login"));
    expect(view.queryClient.getQueryCache().findAll({ queryKey: ["teacher"] })).toHaveLength(0);
  });

  it("clears whatever was cached before a new sign-in", async () => {
    const view = setup("/login", null);
    view.queryClient.setQueryData(teacherKeys.courses(TEACHER2_ID), { courses: [{ stale: true }] });
    view.queryClient.setQueryData(["my-work", "overview"], { stale: true });

    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Email trường học"), "teacher@utask.test");
    await user.type(screen.getByLabelText("Mật khẩu"), "demo1234");
    await user.click(screen.getByRole("button", { name: "Đăng nhập" }));
    await screen.findByRole("heading", { name: "Bàn làm việc giảng viên" });

    expect(view.queryClient.getQueryData(teacherKeys.courses(TEACHER2_ID))).toBeUndefined();
    expect(view.queryClient.getQueryData(["my-work", "overview"])).toBeUndefined();
  });
});

describe("Teacher screens stay inside Teacher data", () => {
  it("never requests Student endpoints while browsing the Teacher space", async () => {
    const tracker = trackRequests();
    const view = setup("/teacher");
    const user = userEvent.setup();
    await screen.findByRole("region", { name: "Danh sách lớp" });
    await user.click(screen.getAllByRole("link", { name: /Công nghệ Phần mềm/ })[0]);
    await screen.findByRole("heading", { level: 1 });
    for (const tab of [/^Sinh viên/, /^Nhóm/, /^Giám sát/]) {
      await user.click(within(screen.getByRole("navigation", { name: "Các mục của lớp" })).getByRole("link", { name: tab }));
      await waitFor(() => expect(pathname(view.router)).toMatch(/\/(students|teams|oversight)$/));
    }
    await screen.findAllByText("Team NEXUS");
    tracker.stop();

    const api = tracker.paths.filter((path) => path.startsWith("/api/"));
    expect(api.length).toBeGreaterThan(0);
    expect(api.every((path) => path.startsWith("/api/work/api/v1/teacher/"))).toBe(true);
  });
});

describe("Navigation quality", () => {
  const LIVE_ROUTES = [
    /^\/teacher$/,
    /^\/teacher\/courses$/,
    /^\/teacher\/courses\/[^/]+(\/(students|teams|oversight))?$/,
    /^\/teacher\/courses\/[^/]+\/teams\/[^/]+$/,
    /^\/projects\/[^/]+\/(backlog|board|code)$/,
    /^\/notifications$/,
    /^\/settings\/profile$/,
    /^\/my-work$/,
  ];

  it.each([
    "/teacher",
    "/teacher/courses",
    "/teacher/courses/course-se330",
    "/teacher/courses/course-se330/students",
    "/teacher/courses/course-it3090/teams",
  ])("%s links only to pages that exist", async (route) => {
    setup(route);
    await screen.findByRole("heading", { level: 1 });
    await waitFor(() => expect(screen.queryByRole("status")).not.toBeInTheDocument());
    const hrefs = [...document.querySelectorAll("a[href]")]
      .map((a) => a.getAttribute("href")!)
      .filter((href) => !href.startsWith("#")); // in-page skip link
    expect(hrefs.length).toBeGreaterThan(0);
    for (const href of hrefs) {
      expect(LIVE_ROUTES.some((pattern) => pattern.test(href)), `dead link ${href}`).toBe(true);
    }
  });

  it("closes the mobile drawer when a link inside it is followed", async () => {
    const { router } = setup("/teacher");
    const user = userEvent.setup();
    await screen.findByRole("heading", { name: "Bàn làm việc giảng viên" });

    await user.click(screen.getByRole("button", { name: "Mở điều hướng" }));
    const drawer = await screen.findByRole("dialog");
    await user.click(within(drawer).getByRole("link", { name: "Lớp phụ trách" }));
    await waitFor(() => expect(pathname(router)).toBe("/teacher/courses"));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("uses a Teacher top bar without Student actions", async () => {
    setup("/teacher");
    await screen.findByRole("heading", { name: "Bàn làm việc giảng viên" });
    expect(screen.getByText("Không gian giảng viên", { selector: "p" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Tạo task mới/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Đồng bộ Git/ })).not.toBeInTheDocument();
    expect(screen.queryByText("Điểm danh QR")).not.toBeInTheDocument();
  });
});

describe("Notifications for a teacher", () => {
  it("shows only the classes they teach, and opens the Teacher class page, not a Student page", async () => {
    const { router } = setup("/notifications");
    const user = userEvent.setup();
    expect(await screen.findByText(/Lời mời ghép nhóm từ Team ORBIT/)).toBeInTheDocument();
    // Project-level items are not visible: a teacher has no project access in Phase 1.
    expect(screen.queryByText(/Sprint 2 đồ án SE330/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Bùi Quang Thắng đề nghị review PR/)).not.toBeInTheDocument();

    await user.click(screen.getAllByRole("button", { name: "Xem môn học" })[0]);
    await waitFor(() => expect(pathname(router)).toBe("/teacher/courses/course-se330"));
    expect(await screen.findByRole("heading", { level: 1, name: /Công nghệ Phần mềm/ })).toBeInTheDocument();
  });

  it("shows teacher2 nothing from SE330", async () => {
    setup("/notifications", teacher2TestSession);
    await screen.findByRole("heading", { level: 1 });
    expect(screen.queryByText(/Lời mời ghép nhóm từ Team ORBIT/)).not.toBeInTheDocument();
  });

  it("keeps the Student page for a student", async () => {
    const { router } = setup("/notifications", studentTestSession);
    const user = userEvent.setup();
    await screen.findByText(/Lời mời ghép nhóm từ Team ORBIT/);
    await user.click(screen.getAllByRole("button", { name: "Xem môn học" })[0]);
    await waitFor(() => expect(pathname(router)).toBe("/courses/course-se330/team"));
  });
});

describe("Student Flow is unchanged for students", () => {
  it("keeps SV01's four memberships and class roster on Home", async () => {
    setup("/my-work", studentTestSession);
    expect(await screen.findByText(/Team NEXUS · Leader/)).toBeInTheDocument();
    expect(screen.getByText(/Team DELI · Member/)).toBeInTheDocument();
    expect(screen.getByText(/Yêu cầu tham gia Team PHOENIX/)).toBeInTheDocument();
  });

  it("shows the unteamed IT3090 formation view with the graph's classmates", async () => {
    setup("/courses/course-it3090/team", studentTestSession);
    expect(await screen.findAllByText(/Đồ án IoT/)).not.toHaveLength(0);
    const expected = buildTeacherStudents("course-it3090").filter((s) => s.team === null);
    for (const student of expected) {
      expect((await screen.findAllByText(student.name)).length).toBeGreaterThan(0);
    }
  });

  it("does not let a student read the Teacher API even when a Teacher exists", async () => {
    const response = await fetch("http://localhost/api/work/api/v1/teacher/courses", {
      headers: { Authorization: `Bearer mock-access:${STUDENT_ID}:test` },
    });
    expect(response.status).toBe(403);
  });
});
