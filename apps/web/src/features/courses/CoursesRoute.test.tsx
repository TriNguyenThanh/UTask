import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { CourseCard } from "@/features/courses/components/CourseCard";
import {
  compareSemesterDesc,
  groupBySemester,
  listSemesters,
  summarizeCourses,
} from "@/features/courses/lib/courseList";
import { Component as CoursesRoute } from "@/features/courses/routes/CoursesRoute";
import type { CourseEnrollment } from "@/features/my-work/types";
import { leaderTestSession, renderApp } from "@/test/render";

async function openCourses() {
  renderApp(<CoursesRoute />, { route: "/courses", session: leaderTestSession });
  await screen.findByRole("heading", { level: 1, name: "Môn học" });
  const cards = () =>
    within(screen.getByRole("heading", { level: 2, name: "Môn học của bạn" }).closest("section")!)
      .getAllByRole("listitem");
  return { cards };
}

function course(id: string, membership: CourseEnrollment["membership"]): CourseEnrollment {
  return {
    courseId: id,
    courseCode: id.toUpperCase(),
    courseName: id,
    semester: "HK1",
    teamFormation: { mode: "self-select", registrationDeadline: null },
    projectId: null,
    membership,
  };
}

describe("summarizeCourses", () => {
  it("counts each membership state once and keeps pending out of 'has team' and 'needs team'", () => {
    const counts = summarizeCourses([
      course("a", { status: "assigned", teamId: "t", teamName: "T", role: "leader" }),
      course("b", { status: "assigned", teamId: "t", teamName: "T", role: "member" }),
      course("c", { status: "none" }),
      course("d", { status: "pending", teamId: "t", teamName: "T", requestedAt: "2026-01-01" }),
    ]);
    expect(counts).toEqual({ all: 4, assigned: 2, none: 1, pending: 1 });
    expect(summarizeCourses([])).toEqual({ all: 0, assigned: 0, none: 0, pending: 0 });
  });
});

describe("semester ordering", () => {
  it("sorts by academic year then term, newest first, with unknown labels last", () => {
    const labels = ["HK1 2025–2026", "HK2 2026–2027", "Học kỳ hè", "HK1 2026–2027", "HK2 2025–2026"];
    expect([...labels].sort(compareSemesterDesc)).toEqual([
      "HK2 2026–2027",
      "HK1 2026–2027",
      "HK2 2025–2026",
      "HK1 2025–2026",
      "Học kỳ hè",
    ]);
    expect(listSemesters([course("a", { status: "none" }), course("b", { status: "none" })])).toEqual(["HK1"]);
  });
});

describe("courses repository", () => {
  it("has no header or summary tiles before the list, and shows a card per course with its link", async () => {
    const { cards } = await openCourses();
    const total = cards().length;
    expect(total).toBeGreaterThan(1);
    expect(screen.queryByText("Quản lý môn học và các nhóm dự án của bạn")).not.toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "Tổng quan môn học" })).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "Môn học của bạn" })).toBeInTheDocument();
    expect(screen.getByText(/Hiển thị/)).toHaveTextContent(`${total}/${total}`);
    expect(screen.getByRole("link", { name: "Đồ án IoT IT3090" })).toHaveAttribute(
      "href",
      "/courses/course-it3090/team",
    );
  });

  it("renders the badge and the right action for each membership state", async () => {
    const { cards } = await openCourses();
    const byName = (name: string) =>
      cards().find((card) => within(card).queryByRole("link", { name })) as HTMLElement;

    const leader = byName("Đồ án Chuyên ngành SE330");
    expect(leader).toHaveTextContent("Trưởng nhóm");
    expect(within(leader).getByRole("link", { name: "Xem nhóm & Đề tài" })).toBeInTheDocument();

    const member = byName("Phát triển Di động CS402");
    expect(member).toHaveTextContent("Thành viên");

    const none = byName("Đồ án IoT IT3090");
    expect(none).toHaveTextContent("Cần lập nhóm");
    expect(none).toHaveTextContent("Chưa có nhóm");
    expect(within(none).getByRole("link", { name: "Thành lập nhóm" })).toBeInTheDocument();
  });

  it("shows a pending request as waiting for approval, never as 'has a team'", () => {
    renderApp(
      <ul>
        <CourseCard
          enrollment={course("se331", {
            status: "pending",
            teamId: "t",
            teamName: "T",
            requestedAt: "2026-01-01",
          })}
        />
      </ul>,
    );
    const card = screen.getByRole("listitem");
    expect(card).toHaveTextContent("Chờ duyệt");
    expect(card).toHaveTextContent("Đang chờ duyệt");
    expect(card).not.toHaveTextContent("Đã có nhóm");
    expect(within(card).getByRole("link", { name: "Theo dõi yêu cầu" })).toBeInTheDocument();
  });

  it("combines search with the status filter and says so when nothing matches", async () => {
    const { cards } = await openCourses();
    const user = userEvent.setup();
    const total = cards().length;
    const search = () => screen.getByRole("searchbox", { name: /Tìm môn học/ });

    await user.click(screen.getByRole("button", { name: /^Cần lập nhóm · \d+$/ }));
    const needing = cards().length;
    expect(needing).toBeLessThan(total);
    for (const card of cards()) expect(card).toHaveTextContent("Cần lập nhóm");

    // Search narrows within the active filter, not across all courses.
    await user.type(search(), "se330");
    expect(await screen.findByText("Không có môn học phù hợp")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /^Tất cả · \d+$/ }));
    expect(cards()).toHaveLength(1);
    expect(cards()[0]).toHaveTextContent("SE330");

    await user.clear(search());
    expect(cards()).toHaveLength(total);
  });

  it("lists past terms newest first and filters by semester together with search and status", async () => {
    const { cards } = await openCourses();
    const user = userEvent.setup();
    const select = screen.getByRole("combobox", { name: "Lọc theo học kỳ" });
    const options = within(select).getAllByRole("option").map((option) => option.textContent);
    expect(options).toEqual([
      "Mọi học kỳ",
      "HK1 2026–2027",
      "HK2 2025–2026",
      "HK1 2025–2026",
      "HK2 2024–2025",
    ]);
    // One section per term, current term first; each holds only its own courses.
    const headings = screen.getAllByRole("heading", { level: 3 });
    expect(headings.map((node) => node.firstChild?.textContent)).toEqual([
      "HK1 2026–2027",
      "HK2 2025–2026",
      "HK1 2025–2026",
      "HK2 2024–2025",
    ]);
    const second = headings[1].closest("section") as HTMLElement;
    expect(within(second).getAllByRole("listitem")).toHaveLength(2);
    expect(within(second).getByRole("link", { name: "Cơ sở Dữ liệu Nâng cao DB220" })).toBeInTheDocument();

    await user.selectOptions(select, "HK2 2025–2026");
    expect(cards()).toHaveLength(2);
    expect(screen.getAllByRole("heading", { level: 3 })).toHaveLength(1);
    expect(screen.getByText(/Hiển thị/)).toHaveTextContent("2/2");

    await user.type(screen.getByRole("searchbox", { name: /Tìm môn học/ }), "DB220");
    expect(cards()).toHaveLength(1);
    await user.click(screen.getByRole("button", { name: /^Cần lập nhóm · 0$/ }));
    expect(await screen.findByText("Không có môn học phù hợp")).toBeInTheDocument();
  });

  it("links a past course to its own team page", async () => {
    renderApp(<CoursesRoute />, { route: "/courses", session: leaderTestSession });
    await screen.findByRole("heading", { level: 1, name: "Môn học" });
    expect(screen.getByRole("link", { name: "Lập trình Web WEB150" })).toHaveAttribute(
      "href",
      "/courses/course-hist-web150/team",
    );
  });
});
