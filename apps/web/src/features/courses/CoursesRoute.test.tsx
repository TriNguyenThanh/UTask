import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { CourseCard } from "@/features/courses/components/CourseCard";
import {
  compareSemesterDesc,
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
    expect(screen.queryByText(/Hiển thị/)).not.toBeInTheDocument();
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

  it("shows only the latest term, and reveals older terms newest first on demand", async () => {
    const { cards } = await openCourses();
    const user = userEvent.setup();
    expect(screen.getByRole("heading", { level: 3, name: "Học kỳ 1 · 2026–2027" })).toBeInTheDocument();
    expect(screen.getAllByRole("heading", { level: 3 })).toHaveLength(1);
    for (const card of cards()) expect(card).toHaveTextContent("HK1 2026–2027");
    expect(screen.queryByRole("link", { name: "Lập trình Web WEB150" })).not.toBeInTheDocument();

    const toggle = screen.getByRole("button", { name: /Xem học kỳ cũ/ });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    const latestCount = cards().length;
    await user.click(toggle);

    expect(screen.getByRole("button", { name: "Ẩn học kỳ cũ" })).toHaveAttribute("aria-expanded", "true");
    expect(cards()).toHaveLength(latestCount + 4);
    // One section per term, newest first.
    expect(screen.getAllByRole("heading", { level: 3 }).map((node) => node.textContent)).toEqual([
      "Học kỳ 1 · 2026–2027",
      "Học kỳ 2 · 2025–2026",
      "Học kỳ 1 · 2025–2026",
      "Học kỳ 2 · 2024–2025",
    ]);
    const semesters = cards().map((card) => /HK\d \d{4}–\d{4}/.exec(card.textContent ?? "")?.[0]);
    expect(semesters[0]).toBe("HK1 2026–2027");
    expect(semesters.at(-1)).toBe("HK2 2024–2025");
    expect(semesters).toEqual([...semesters].sort((a, b) => compareSemesterDesc(a!, b!)));
    // Past course links to its own team page.
    expect(screen.getByRole("link", { name: "Lập trình Web WEB150" })).toHaveAttribute(
      "href",
      "/courses/course-hist-web150/team",
    );

    // Search reaches past terms only while they are shown.
    await user.type(screen.getByRole("searchbox", { name: /Tìm môn học/ }), "DB220");
    expect(cards()).toHaveLength(1);
    await user.click(screen.getByRole("button", { name: "Ẩn học kỳ cũ" }));
    expect(await screen.findByText("Không có môn học phù hợp")).toBeInTheDocument();
  });
});
