import { delay, http, HttpResponse, type HttpHandler } from "msw";

import {
  buildTeacherCourseDetail,
  STALE_AFTER_DAYS,
  buildTeacherCourseSummary,
  buildTeacherOversight,
  buildTeacherStudents,
  buildTeacherTeamDetail,
  buildTeacherTeams,
} from "@/mocks/data/teacherFlow";
import { mockAnchorDate } from "@/mocks/data/studentFlow";
import { coursesTaughtBy } from "@/mocks/data/relationships";
import type { MockRepository } from "@/mocks/data/storage";
import type { MockScenario } from "@/mocks/scenarios";

/**
 * Demo-only Teacher read endpoints (not a backend contract).
 *
 * Authorization order, identical on every endpoint:
 *   1. no/invalid token            → 401
 *   2. account without TEACHER role → 403 (role gate for the whole area)
 *   3. class not assigned to caller → 404, whether or not the class exists
 *
 * Step 3 deliberately returns one response for "unknown class" and "class
 * taught by someone else", so ids cannot be probed. The role alone grants
 * nothing on a class; the per-class assignment does.
 */
const ROOT = "/api/work/api/v1/teacher";

const SERVER_ERROR = "Lỗi hệ thống, vui lòng thử lại sau.";

function parseTokenUserId(request: Request): string | null {
  const header = request.headers.get("Authorization") ?? "";
  return /^Bearer mock-access:([^:]+):/.exec(header)?.[1] ?? null;
}

function sleepFor(scenario: MockScenario): Promise<void> | undefined {
  return scenario === "slow-network" ? delay(1200) : undefined;
}

export function createTeacherFlowHandlers(
  scenario: MockScenario,
  repository: MockRepository,
): HttpHandler[] {
  const { db } = repository;

  /** Classes the caller may read; the `teacher-empty` scenario revokes them all. */
  function taughtBy(userId: string): readonly string[] {
    return scenario === "teacher-empty" ? [] : coursesTaughtBy(userId);
  }

  /** Runs the shared authorization steps, then `respond` with the caller id. */
  async function guarded(
    request: Request,
    courseId: string | null,
    respond: (userId: string) => Response,
    { failsInPartialError = false }: { failsInPartialError?: boolean } = {},
  ): Promise<Response> {
    await sleepFor(scenario);
    const userId = parseTokenUserId(request);
    const account = userId ? db.authUsersById[userId] : undefined;
    if (!userId || !account) {
      return HttpResponse.json({ detail: "Phiên đăng nhập đã hết hạn." }, { status: 401 });
    }
    if (scenario === "server-error" || (failsInPartialError && scenario === "teacher-partial-error")) {
      return HttpResponse.json({ detail: SERVER_ERROR }, { status: 500 });
    }
    if (!account.roles?.includes("TEACHER")) {
      return HttpResponse.json(
        { detail: "Tài khoản không có quyền dùng không gian giảng viên." },
        { status: 403 },
      );
    }
    if (courseId !== null && !taughtBy(userId).includes(courseId)) {
      return HttpResponse.json({ detail: "Không tìm thấy lớp học." }, { status: 404 });
    }
    return respond(userId);
  }

  return [
    http.get(`${ROOT}/courses`, ({ request }) =>
      guarded(request, null, (userId) => {
        const courses = taughtBy(userId).flatMap((courseId) => {
          const summary = buildTeacherCourseSummary(courseId, scenario);
          return summary ? [summary] : [];
        });
        return HttpResponse.json({ courses });
      }),
    ),

    http.get(`${ROOT}/courses/:courseId`, ({ params, request }) =>
      guarded(request, String(params.courseId), () => {
        const detail = buildTeacherCourseDetail(String(params.courseId), scenario);
        return detail
          ? HttpResponse.json(detail)
          : HttpResponse.json({ detail: "Không tìm thấy lớp học." }, { status: 404 });
      }),
    ),

    http.get(`${ROOT}/courses/:courseId/students`, ({ params, request }) =>
      guarded(
        request,
        String(params.courseId),
        () => HttpResponse.json({ students: buildTeacherStudents(String(params.courseId)) }),
        { failsInPartialError: true },
      ),
    ),

    http.get(`${ROOT}/courses/:courseId/teams`, ({ params, request }) =>
      guarded(
        request,
        String(params.courseId),
        () => HttpResponse.json({ teams: buildTeacherTeams(String(params.courseId)) }),
        { failsInPartialError: true },
      ),
    ),

    http.get(`${ROOT}/courses/:courseId/teams/:teamId`, ({ params, request }) =>
      guarded(
        request,
        String(params.courseId),
        () => {
          const detail = buildTeacherTeamDetail(String(params.courseId), String(params.teamId), scenario);
          // A team that is not in this (assigned) class answers like one that does not exist.
          return detail
            ? HttpResponse.json(detail)
            : HttpResponse.json({ detail: "Không tìm thấy nhóm." }, { status: 404 });
        },
        { failsInPartialError: true },
      ),
    ),

    http.get(`${ROOT}/courses/:courseId/oversight`, ({ params, request }) =>
      guarded(
        request,
        String(params.courseId),
        () =>
          HttpResponse.json({
            teams: buildTeacherOversight(String(params.courseId), scenario),
            staleAfterDays: STALE_AFTER_DAYS,
            asOf: mockAnchorDate().toISOString(),
          }),
        { failsInPartialError: true },
      ),
    ),
  ];
}
