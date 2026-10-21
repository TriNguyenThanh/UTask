import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";

import { Component as CoursesRoute } from "@/features/courses/routes/CoursesRoute";
import { Component as CourseTeamRoute } from "@/features/courses/routes/CourseTeamRoute";
import { LEADER_ID } from "@/mocks/data/database";
import { createMemoryRepository } from "@/mocks/data/storage";
import { createAuthHandlers } from "@/mocks/handlers/auth";
import { server } from "@/mocks/server";
import {
  buildClass,
  buildCourse,
  buildGroup,
  buildMember,
  classroomHandlers,
  envelope,
  envelopeError,
  type ClassroomFixture,
} from "@/test/classroomHandlers";
import { leaderTestSession, renderApp } from "@/test/render";

function useRealClassroom(fixture: ClassroomFixture, ...overrides: Parameters<typeof server.use>) {
  vi.stubEnv("VITE_REAL_SERVICES", "auth,classroom");
  server.use(...overrides, ...classroomHandlers(fixture), ...createAuthHandlers("default", createMemoryRepository("default")));
}

describe("CoursesRoute (real classroom)", () => {
  it("shows the empty state and the join button when the student has no class", async () => {
    useRealClassroom({ classes: [], courses: [] });
    renderApp(<CoursesRoute />, { route: "/courses", session: leaderTestSession });

    expect(await screen.findByText("Bạn chưa có môn học nào")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Tham gia lớp bằng mã/ })).toBeInTheDocument();
  });

  it("groups classes by term, newest first, and hides older terms until expanded", async () => {
    useRealClassroom({
      classes: [
        buildClass({ id: "a", course: "c-old", name: "Lớp cũ", term: "HK1 2025–2026" }),
        buildClass({ id: "b", course: "c-new", name: "Lớp mới", term: "HK2 2025–2026" }),
      ],
      courses: [
        buildCourse({ id: "c-old", code: "OLD1", name: "Môn cũ" }),
        buildCourse({ id: "c-new", code: "NEW1", name: "Môn mới" }),
      ],
    });
    const user = userEvent.setup();
    renderApp(<CoursesRoute />, { route: "/courses", session: leaderTestSession });

    expect(await screen.findByText("Môn mới")).toBeInTheDocument();
    expect(screen.queryByText("Lớp mới")).not.toBeInTheDocument();
    expect(screen.queryByText("Môn cũ")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Xem học kỳ cũ/ }));
    expect(await screen.findByText("Môn cũ")).toBeInTheDocument();
  });

  it("shows an error state when the class list fails, without falling back to mock data", async () => {
    useRealClassroom({ classes: [], courses: [] }, http.get("/api/classroom/classes/", () => envelopeError(500, "INTERNAL_ERROR", "Lỗi máy chủ.")));
    renderApp(<CoursesRoute />, { route: "/courses", session: leaderTestSession });

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.queryByText("Môn học của bạn")).not.toBeInTheDocument();
  });
});

describe("JoinClassDialog", () => {
  async function openDialog() {
    const user = userEvent.setup();
    renderApp(<CoursesRoute />, { route: "/courses", session: leaderTestSession });
    await user.click(await screen.findByRole("button", { name: /Tham gia lớp bằng mã/ }));
    await user.type(await screen.findByLabelText("Mã lớp"), " ABC123 ");
    return user;
  }

  it("sends the trimmed code with an Idempotency-Key, then refetches the list", async () => {
    let body: unknown;
    let key: string | null = null;
    let lists = 0;
    useRealClassroom(
      { classes: [], courses: [] },
      http.get("/api/classroom/classes/", () => {
        lists += 1;
        return envelope([]);
      }),
      http.post("/api/classroom/classes/join/", async ({ request }) => {
        body = await request.json();
        key = request.headers.get("Idempotency-Key");
        return envelope({ id: "enr-1" }, { status: 201 });
      }),
    );
    const user = await openDialog();
    await user.click(screen.getByRole("button", { name: "Tham gia" }));

    await waitFor(() => expect(body).toEqual({ code: "ABC123" }));
    expect(key).toMatch(/^[0-9a-f-]{36}$/);
    await waitFor(() => expect(lists).toBeGreaterThan(1));
    await waitFor(() => expect(screen.queryByLabelText("Mã lớp")).not.toBeInTheDocument());
  });

  it("keeps the dialog open and shows the server message for a wrong code", async () => {
    useRealClassroom(
      { classes: [], courses: [] },
      http.post("/api/classroom/classes/join/", () => envelopeError(404, "RESOURCE_NOT_FOUND", "Mã tham gia lớp không đúng.")),
    );
    const user = await openDialog();
    await user.click(screen.getByRole("button", { name: "Tham gia" }));

    expect(await screen.findByText("Mã tham gia lớp không đúng.")).toBeInTheDocument();
    expect(screen.getByLabelText("Mã lớp")).toBeInTheDocument();
  });

  it("shows the conflict message for an expired code", async () => {
    useRealClassroom(
      { classes: [], courses: [] },
      http.post("/api/classroom/classes/join/", () => envelopeError(409, "ACCESS_CODE_EXPIRED", "Mã tham gia lớp đã hết hạn. Hãy xin mã mới.")),
    );
    const user = await openDialog();
    await user.click(screen.getByRole("button", { name: "Tham gia" }));

    expect(await screen.findByText(/Mã tham gia lớp đã hết hạn/)).toBeInTheDocument();
  });

  it("disables submit while the code is blank", async () => {
    useRealClassroom({ classes: [], courses: [] });
    const user = userEvent.setup();
    renderApp(<CoursesRoute />, { route: "/courses", session: leaderTestSession });
    await user.click(await screen.findByRole("button", { name: /Tham gia lớp bằng mã/ }));

    expect(await screen.findByRole("button", { name: "Tham gia" })).toBeDisabled();
  });
});

describe("CourseTeamRoute (real classroom)", () => {
  const routes = (element: React.ReactElement) => [{ path: "/courses/:courseId", element }];

  it("shows a student without group an explanatory state and no fabricated class numbers", async () => {
    useRealClassroom({ classes: [buildClass()], courses: [buildCourse()] });
    renderApp(<CourseTeamRoute />, { route: "/courses/class-1", session: leaderTestSession, routes: routes(<CourseTeamRoute />) });

    expect(await screen.findByText("Bạn chưa có nhóm")).toBeInTheDocument();
    expect(screen.queryByText(/Sĩ số lớp/)).not.toBeInTheDocument();
    expect(screen.queryByText("Các nhóm đang còn chỗ trống")).not.toBeInTheDocument();
  });

  it("shows the team hub without topic or skill columns", async () => {
    useRealClassroom({
      classes: [buildClass()],
      courses: [buildCourse()],
      groups: { "class-1": [buildGroup()] },
      members: { "group-1": [buildMember({ user_id: LEADER_ID, role: "LEADER" })] },
    });
    renderApp(<CourseTeamRoute />, { route: "/courses/class-1", session: leaderTestSession, routes: routes(<CourseTeamRoute />) });

    expect(await screen.findByText("Nguyễn Văn An")).toBeInTheDocument();
    expect(screen.queryByText("Vai trò chuyên môn")).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /Đề tài/ })).not.toBeInTheDocument();
  });

  it("shows not-found for a class the student cannot read", async () => {
    useRealClassroom({ classes: [], courses: [] });
    renderApp(<CourseTeamRoute />, { route: "/courses/nope", session: leaderTestSession, routes: routes(<CourseTeamRoute />) });

    expect(await screen.findByText("Không tìm thấy môn học")).toBeInTheDocument();
  });
});
