import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http, type HttpHandler } from "msw";
import { toast } from "sonner";
import { afterEach, describe, expect, it, vi } from "vitest";

import { TEACHER_ID } from "@/mocks/data/database";
import { mockAnchorDate, projectWorkspaceFor } from "@/mocks/data/studentFlow";
import { buildTeacherTeamDetail } from "@/mocks/data/teacherFlow";
import { createMockHandlers } from "@/mocks/handlers";
import { server } from "@/mocks/server";
import { createMemoryRepository, type MockRepository } from "@/mocks/data/storage";
import type { MockScenario } from "@/mocks/scenarios";
import {
  leaderTestSession,
  memberTestSession,
  renderAppRoutes,
  studentTestSession,
  teacher2TestSession,
  teacherTestSession,
} from "@/test/render";

/**
 * Phase 2: team dashboard (T08) and the read-only workspace for an
 * instructor, through the real route table. The workspace pages are the
 * shared Student ones; these tests prove they behave differently only by
 * viewer, never by a separate copy.
 */

const API = "http://localhost/api/work/api/v1";

function setup(
  route: string,
  session: Parameters<typeof renderAppRoutes>[1] = teacherTestSession,
  scenario: MockScenario = "default",
  overrides: HttpHandler[] = [],
) {
  const repository: MockRepository = createMemoryRepository(scenario);
  server.use(...createMockHandlers(scenario, repository));
  // Registered after the defaults, so they win; and before the first render.
  server.use(...overrides);
  return { repository, ...renderAppRoutes(route, session) };
}

/** Records "METHOD /path" for every request made while the test runs. */
function trackRequests() {
  const calls: string[] = [];
  const listener = ({ request }: { request: Request }) => {
    calls.push(`${request.method} ${new URL(request.url).pathname}`);
  };
  server.events.on("request:start", listener);
  return { calls, stop: () => server.events.removeListener("request:start", listener) };
}

const page = async () => within(await screen.findByRole("main"));
const pathname = (router: { state: { location: { pathname: string } } }) =>
  router.state.location.pathname;

afterEach(() => {
  vi.unstubAllEnvs();
  sessionStorage.clear();
  toast.dismiss();
});

describe("Team dashboard (T08)", () => {
  it("shows members, measured progress, issue counts and the overdue figure with its basis", async () => {
    setup("/teacher/courses/course-se330/teams/team-nexus");
    const main = await page();
    const detail = buildTeacherTeamDetail("course-se330", "team-nexus")!;

    expect(await main.findByRole("heading", { level: 2, name: "Team NEXUS" })).toBeInTheDocument();
    const members = main.getByRole("list", { name: "Thành viên Team NEXUS" });
    expect(within(members).getAllByRole("listitem")).toHaveLength(detail.members.length);
    expect(members).toHaveTextContent("Lê Minh Khoa");
    expect(members).toHaveTextContent("MSSV: 21020999");

    expect(main.getByRole("progressbar", { name: "Tiến độ Team NEXUS" })).toHaveAttribute(
      "value",
      String(detail.progress!.percent),
    );
    expect(main.getByText(/theo điểm Sprint đang chạy/)).toBeInTheDocument();

    const overdue = main.getByLabelText("Issue quá hạn");
    expect(overdue).toHaveTextContent("2/4 issue có hạn chót");
    expect(overdue).toHaveTextContent("chưa hoàn thành");
  });

  it("does not rank or score members", async () => {
    setup("/teacher/courses/course-se330/teams/team-nexus");
    const main = await page();
    await main.findByRole("heading", { level: 2, name: "Team NEXUS" });
    expect(main.queryByText(/xếp hạng:|điểm số|chấm điểm/i)).not.toBeInTheDocument();
    expect(main.getByText(/không được xếp hạng hay quy ra điểm/)).toBeInTheDocument();
  });

  it("states 'no data' for a team without a project, with no workspace links and no GitHub block", async () => {
    setup("/teacher/courses/course-it3090/teams/team-iot-vision");
    const main = await page();
    expect(await main.findByRole("heading", { level: 2, name: "Team VISION" })).toBeInTheDocument();
    expect(main.getByText(/Nhóm chưa có project nên chưa có tiến độ/)).toBeInTheDocument();
    expect(main.queryByRole("progressbar")).not.toBeInTheDocument();
    expect(main.queryByText("GitHub")).not.toBeInTheDocument();
    expect(main.queryByRole("link", { name: /Backlog|Bảng công việc|Mã nguồn/ })).not.toBeInTheDocument();
    expect(main.getByText("Tín hiệu cần chú ý")).toBeInTheDocument();
  });

  it("keeps task data when only the GitHub block fails, and retries just that block", async () => {
    setup("/teacher/courses/course-se330/teams/team-nexus", teacherTestSession, "default", [
      http.get(`${API}/projects/project-nexus/code`, () =>
        HttpResponse.json({ detail: "Lỗi hệ thống, vui lòng thử lại sau." }, { status: 500 }),
      ),
    ]);
    const main = await page();
    await main.findByRole("heading", { level: 2, name: "Team NEXUS" });
    // The GitHub block reports its own failure …
    expect(await main.findByText("Không thể tải dữ liệu", {}, { timeout: 8000 })).toBeInTheDocument();
    // … while members, progress and issue counts stay on screen.
    expect(main.getByRole("progressbar", { name: "Tiến độ Team NEXUS" })).toBeInTheDocument();
    expect(main.getByLabelText("Issue quá hạn")).toBeInTheDocument();
    expect(main.getByRole("list", { name: "Thành viên Team NEXUS" })).toBeInTheDocument();
    expect(main.getByRole("button", { name: "Thử lại" })).toBeInTheDocument();
  }, 15000);

  it("shows GitHub facts with the sync state, and says when the sync time is unknown", async () => {
    setup("/teacher/courses/course-se330/teams/team-nexus");
    const main = await page();
    expect(await main.findByText("nexus-team/smart-supply-chain")).toBeInTheDocument();
    expect(main.getByText("Đã đồng bộ")).toBeInTheDocument();
    const sync = main.getByText("Thời điểm đồng bộ gần nhất").closest("div")!;
    expect(sync).toHaveTextContent("Chưa có dữ liệu");
  });

  it("says a team is missing instead of a class, and a foreign team looks the same", async () => {
    setup("/teacher/courses/course-se330/teams/team-deli");
    expect(await screen.findByText("Không tìm thấy nhóm")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1, name: /Công nghệ Phần mềm/ })).toBeInTheDocument();
  });

  it("opens from the team list and from oversight, and goes on into the workspace", async () => {
    const view = setup("/teacher/courses/course-se330/teams");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("link", { name: /Xem chi tiết Team NEXUS/ }));
    await waitFor(() => expect(pathname(view.router)).toBe("/teacher/courses/course-se330/teams/team-nexus"));
    await user.click(await screen.findByRole("link", { name: "Bảng công việc" }));
    await waitFor(() => expect(pathname(view.router)).toBe("/projects/project-nexus/board"));
    expect(await screen.findByRole("navigation", { name: "Breadcrumb" })).toBeInTheDocument();
  });
});

describe("Workspace as an instructor (read-only)", () => {
  it("builds the breadcrumb from the workspace itself, so a deep link and a refresh are right", async () => {
    setup("/projects/project-nexus/board");
    const crumbs = await screen.findByRole("navigation", { name: "Breadcrumb" });
    const link = (name: string) => within(crumbs).getByRole("link", { name });
    expect(link("Trang chủ")).toHaveAttribute("href", "/teacher");
    expect(link("Lớp phụ trách")).toHaveAttribute("href", "/teacher/courses");
    expect(link("Đồ án Chuyên ngành Công nghệ Phần mềm")).toHaveAttribute(
      "href",
      "/teacher/courses/course-se330",
    );
    expect(link("Team NEXUS")).toHaveAttribute("href", "/teacher/courses/course-se330/teams/team-nexus");
    expect(crumbs).toHaveTextContent("NEXUS");
    expect(screen.getByText("Chế độ chỉ xem")).toBeInTheDocument();
  });

  it("uses the Teacher navigation, not the Student one", async () => {
    setup("/projects/project-nexus/backlog");
    expect(await screen.findByRole("navigation", { name: "Điều hướng giảng viên" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Dự án$/ })).not.toBeInTheDocument();
  });

  it("never asks for settings or student data, and never writes", async () => {
    const tracker = trackRequests();
    setup("/projects/project-nexus/backlog");
    await screen.findByRole("heading", { name: "Backlog & Sprint Planning" });
    tracker.stop();
    const api = tracker.calls.filter((call) => call.includes("/api/"));
    expect(api.length).toBeGreaterThan(0);
    expect(api.every((call) => call.startsWith("GET "))).toBe(true);
    expect(api.some((call) => call.includes("/settings"))).toBe(false);
    expect(api.some((call) => call.endsWith("/api/work/api/v1/courses"))).toBe(false);
  });

  it("Backlog hides every Leader action and the 'mine' filter", async () => {
    setup("/projects/project-nexus/backlog");
    const main = await page();
    await main.findByRole("heading", { name: "Product Backlog" });
    expect(main.queryByText("Trợ lý AI Scrum Copilot")).not.toBeInTheDocument();
    expect(main.queryByText("Tạo Epic")).not.toBeInTheDocument();
    expect(main.queryByText("Hoàn thành Sprint")).not.toBeInTheDocument();
    expect(main.queryByRole("button", { name: "Chỉ việc của tôi" })).not.toBeInTheDocument();
    expect(main.getByRole("button", { name: "Có Pull Request" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Cài đặt dự án" })).not.toBeInTheDocument();
  });

  it("Board hides create, 'mine' and settings, and opens an issue read-only from the URL", async () => {
    setup("/projects/project-nexus/board?issue=NEXUS-104");
    const dialog = await screen.findByRole("dialog", { name: "Chi tiết issue NEXUS-104" });
    await within(dialog).findAllByText(/Tích hợp cổng thanh toán VNPay/);

    expect(screen.queryByRole("button", { name: /Tạo issue/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Chỉ việc của tôi" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Cài đặt dự án" })).not.toBeInTheDocument();

    expect(within(dialog).getByLabelText("Trạng thái")).toBeDisabled();
    expect(within(dialog).queryByText(/AI Tự động sinh Sub-tasks/)).not.toBeInTheDocument();
    expect(within(dialog).queryByText(/Cấu hình AI key/)).not.toBeInTheDocument();
    expect(within(dialog).getByText("Bạn chỉ có quyền xem nhiệm vụ con.")).toBeInTheDocument();
  });

  it("does not let an instructor tick a subtask, even locally", async () => {
    setup("/projects/project-nexus/board?issue=NEXUS-104");
    const dialog = await screen.findByRole("dialog", { name: "Chi tiết issue NEXUS-104" });
    const boxes = await within(dialog).findAllByRole("checkbox");
    expect(boxes.length).toBeGreaterThan(0);
    for (const box of boxes) {
      const before = (box as HTMLInputElement).checked;
      await userEvent.setup().click(box);
      expect((box as HTMLInputElement).checked).toBe(before);
      expect(box).toBeDisabled();
    }
  });

  it("offers a comment draft but no way to send it, and says why", async () => {
    setup("/projects/project-nexus/board?issue=NEXUS-104");
    const dialog = await screen.findByRole("dialog", { name: "Chi tiết issue NEXUS-104" });
    await within(dialog).findByText(/Bình luận \(Comments\)/);
    expect(within(dialog).getByRole("textbox", { name: /Soạn bình luận cho task/ })).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Gửi phản hồi" })).toBeDisabled();
    expect(within(dialog).getAllByText(/chưa có hợp đồng API bình luận/).length).toBeGreaterThan(0);
    // The existing comments are still readable.
    expect(within(dialog).getByText(/wireframe trang kết quả thanh toán/)).toBeInTheDocument();
  });

  it("lands on Forbidden for project settings, not on a blank or student page", async () => {
    setup("/projects/project-nexus/settings");
    expect(await screen.findByText("Không đủ quyền truy cập")).toBeInTheDocument();
  });

  it("Code shows the five team members, no 'Bạn' badge and no judging status column", async () => {
    setup("/projects/project-nexus/code");
    const main = await page();
    const table = await main.findByRole("table");
    expect(within(table).getAllByRole("row")).toHaveLength(1 + 5);
    expect(table).toHaveTextContent("Lê Minh Khoa");
    expect(within(table).queryByText("Bạn")).not.toBeInTheDocument();
    expect(within(table).queryByRole("columnheader", { name: "Trạng thái" })).not.toBeInTheDocument();
    expect(main.queryByRole("link", { name: /Kết nối.*GitHub/ })).not.toBeInTheDocument();
  });

  it("opens a pull request's issue from Code, in the same read-only board", async () => {
    const view = setup("/projects/project-nexus/code");
    const user = userEvent.setup();
    const main = await page();
    await main.findByRole("table");
    await user.click((await main.findAllByRole("button", { name: "Mở Issue NEXUS-104 trên Bảng công việc" }))[0]);
    await waitFor(() => expect(pathname(view.router)).toBe("/projects/project-nexus/board"));
    expect(await screen.findByRole("dialog", { name: "Chi tiết issue NEXUS-104" })).toBeInTheDocument();
  });

  it("says 'no repository' for a project without one, which is not 'project not found'", async () => {
    setup("/projects/project-deli/code", teacher2TestSession);
    expect(await screen.findByText("Dự án chưa có repository")).toBeInTheDocument();
    expect(screen.queryByText("Không tìm thấy dự án")).not.toBeInTheDocument();
    expect(screen.getByText(/nên chưa có dữ liệu mã nguồn để xem/)).toBeInTheDocument();
    expect(screen.queryByText(/Trưởng nhóm có thể gắn repository/)).not.toBeInTheDocument();
  });

  it("sends a Board with no active Sprint to the Backlog with an explanation for the instructor", async () => {
    const base = projectWorkspaceFor("project-nexus", "default", TEACHER_ID, mockAnchorDate())!;
    const view = setup("/projects/project-nexus/board", teacherTestSession, "default", [
      http.get(`${API}/projects/project-nexus`, () =>
        HttpResponse.json({
          ...base,
          sprints: base.sprints.map((sprint) => ({ ...sprint, state: "upcoming" as const })),
        }),
      ),
    ]);
    expect(await screen.findByText("Nhóm chưa có Sprint đang chạy")).toBeInTheDocument();
    expect(screen.queryByText(/liên hệ Trưởng nhóm/)).not.toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("link", { name: "Xem Backlog của nhóm" }));
    await waitFor(() => expect(pathname(view.router)).toBe("/projects/project-nexus/backlog"));
  });
});

describe("Access that ends while the app is open", () => {
  it("does not show a project from the cache after the instructor's access has ended", async () => {
    const view = setup("/projects/project-nexus/board");
    // The app keeps data fresh for 30 s; the test client would refetch on every mount and hide the problem.
    view.queryClient.setDefaultOptions({ queries: { staleTime: 30_000, retry: false, gcTime: Infinity } });
    const user = userEvent.setup();
    await screen.findByRole("heading", { name: "Bảng công việc Sprint" });

    // The account loses the TEACHER role; the server now answers 404 for this project.
    view.repository.db.authUsersById[TEACHER_ID] = {
      ...view.repository.db.authUsersById[TEACHER_ID],
      roles: ["STUDENT"],
    };
    // Leave the workspace, then come straight back well inside the 30 s cache window.
    await user.click(within(await screen.findByRole("navigation", { name: "Breadcrumb" })).getByRole("link", { name: "Trang chủ" }));
    await waitFor(() => expect(pathname(view.router)).toBe("/teacher"));
    await view.router.navigate("/projects/project-nexus/board");

    expect(await screen.findByText("Không tìm thấy dự án", {}, { timeout: 4000 })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Bảng công việc Sprint" })).not.toBeInTheDocument();
  });

  it("keeps a student's workspace cached as before (only the instructor view is dropped on leaving)", async () => {
    const view = setup("/projects/project-nexus/board", leaderTestSession);
    await screen.findByRole("heading", { name: "Bảng công việc Sprint" });
    await view.router.navigate("/my-work");
    const tracker = trackRequests();
    await view.router.navigate("/projects/project-nexus/board");
    await screen.findByRole("heading", { name: "Bảng công việc Sprint" });
    tracker.stop();
    expect(tracker.calls.filter((call) => call.endsWith("/projects/project-nexus"))).toEqual([]);
  });
});

describe("Who can open a workspace", () => {
  it("keeps a teacher out of a project of a class they do not teach, without confirming it exists", async () => {
    setup("/projects/project-deli/board");
    // The workspace query retries a 404 once before giving up.
    expect(await screen.findByText("Không tìm thấy dự án", {}, { timeout: 4000 })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Về danh sách lớp phụ trách" })).toHaveAttribute(
      "href",
      "/teacher/courses",
    );
    expect(screen.queryByText("Team DELI")).not.toBeInTheDocument();
  });

  it("gives teacher2 their own class project and not the first teacher's", async () => {
    setup("/projects/project-deli/backlog", teacher2TestSession);
    expect(await screen.findByRole("heading", { name: "Backlog & Sprint Planning" })).toBeInTheDocument();
    expect(screen.getByText("Chế độ chỉ xem")).toBeInTheDocument();
  });

  it("does not turn the TEACHER role into access to the project of a class the account only studies in", async () => {
    // A student keeps the Student workspace (member), never the instructor one.
    setup("/projects/project-nexus/backlog", studentTestSession);
    expect(await screen.findByRole("heading", { name: "Backlog & Sprint Planning" })).toBeInTheDocument();
    expect(screen.queryByText("Chế độ chỉ xem")).not.toBeInTheDocument();
  });
});

describe("Student workspace is unchanged", () => {
  it("keeps the Student breadcrumb, 'mine' filter, AI toolbar and settings tab for a Leader", async () => {
    setup("/projects/project-nexus/backlog", leaderTestSession);
    const main = await page();
    await main.findByRole("heading", { name: "Product Backlog" });
    expect(main.getByText("Trợ lý AI Scrum Copilot")).toBeInTheDocument();
    expect(main.getByRole("button", { name: "Chỉ việc của tôi" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Cài đặt dự án" })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Breadcrumb dự án" })).toBeInTheDocument();
    expect(screen.queryByText("Chế độ chỉ xem")).not.toBeInTheDocument();
  });

  it("derives 'mine' from the signed-in user, so the board filter differs per account", async () => {
    const first = setup("/projects/project-nexus/board", leaderTestSession);
    const user = userEvent.setup();
    await screen.findAllByText(/NEXUS-104/);
    await user.click(screen.getByRole("button", { name: "Chỉ việc của tôi" }));
    expect(screen.getAllByText(/NEXUS-104/).length).toBeGreaterThan(0);
    expect(screen.queryByText(/NEXUS-101/)).not.toBeInTheDocument();
    first.unmount();

    setup("/projects/project-nexus/board", memberTestSession);
    await screen.findAllByText(/NEXUS-101/);
    await userEvent.setup().click(screen.getByRole("button", { name: "Chỉ việc của tôi" }));
    expect(screen.getAllByText(/NEXUS-101/).length).toBeGreaterThan(0);
    expect(screen.queryByText(/NEXUS-104/)).not.toBeInTheDocument();
  });

  it("marks only the signed-in student as 'Bạn' in the contributors table", async () => {
    setup("/projects/project-nexus/code", studentTestSession);
    const main = await page();
    const table = await main.findByRole("table");
    const rows = within(table).getAllByRole("row").slice(1);
    const marked = rows.filter((row) => within(row).queryByText("Bạn"));
    expect(marked).toHaveLength(1);
    expect(marked[0]).toHaveTextContent("Lê Minh Khoa");
    expect(within(table).getByRole("columnheader", { name: "Trạng thái" })).toBeInTheDocument();
  });

  it("does not ask a member (non-leader) for project settings", async () => {
    const tracker = trackRequests();
    setup("/projects/project-nexus/backlog", memberTestSession);
    await screen.findByRole("heading", { name: "Backlog & Sprint Planning" });
    await screen.findByRole("heading", { name: "Product Backlog" });
    tracker.stop();
    expect(tracker.calls.some((call) => call.includes("/settings"))).toBe(false);
  });
});
