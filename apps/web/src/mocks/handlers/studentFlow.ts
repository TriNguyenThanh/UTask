import { delay, http, HttpResponse, type HttpHandler } from "msw";

import type { MockScenario } from "@/mocks/scenarios";
import {
  accountSettingsForScenario,
  courseDetailForScenario,
  issueDetailFor,
  notificationsForScenario,
  projectCodeFor,
  projectSummariesForScenario,
  projectWorkspaceFor,
} from "@/mocks/data/studentFlow";

const ROOT = "/api/work/api/v1";

const SERVER_ERROR = "Lỗi hệ thống, vui lòng thử lại sau.";
const FORBIDDEN_ERROR = "Bạn không có quyền truy cập tài nguyên này.";

function sleepFor(scenario: MockScenario): Promise<void> | undefined {
  return scenario === "slow-network" || scenario === "student-loading"
    ? delay(1200)
    : undefined;
}

/**
 * Error routing: `student-partial-error` fails only the notifications and
 * code endpoints so sections degrade independently; `server-error` fails
 * everything; `student-forbidden` returns 403 for project detail endpoints.
 */
function errorStatus(scenario: MockScenario): 500 | 403 | null {
  if (scenario === "server-error") return 500;
  if (scenario === "student-forbidden") return 403;
  return null;
}

export function createStudentFlowHandlers(scenario: MockScenario): HttpHandler[] {
  return [
    // Courses & teams
    http.get(`${ROOT}/courses`, async () => {
      await sleepFor(scenario);
      const status = errorStatus(scenario);
      if (status) return HttpResponse.json({ detail: SERVER_ERROR }, { status });
      return HttpResponse.json({
        courses: [],
      });
    }),
    http.get(`${ROOT}/courses/:courseId`, async ({ params }) => {
      await sleepFor(scenario);
      const status = errorStatus(scenario);
      if (status) return HttpResponse.json({ detail: SERVER_ERROR }, { status });
      const detail = courseDetailForScenario(
        String(params.courseId),
        scenario,
      );
      if (!detail) {
        return HttpResponse.json({ detail: "Không tìm thấy môn học." }, { status: 404 });
      }
      return HttpResponse.json(detail);
    }),
    http.post(`${ROOT}/courses/:courseId/teams`, async () => {
      await sleepFor(scenario);
      const status = errorStatus(scenario);
      if (status) return HttpResponse.json({ detail: SERVER_ERROR }, { status });
      if (scenario === "student-forbidden") {
        return HttpResponse.json({ detail: FORBIDDEN_ERROR }, { status: 403 });
      }
      return new HttpResponse(null, { status: 201 });
    }),

    // Projects
    http.get(`${ROOT}/projects`, async () => {
      await sleepFor(scenario);
      const status = errorStatus(scenario);
      if (status) return HttpResponse.json({ detail: SERVER_ERROR }, { status });
      return HttpResponse.json(projectSummariesForScenario(scenario));
    }),
    http.get(`${ROOT}/projects/:projectId`, async ({ params }) => {
      await sleepFor(scenario);
      const status = errorStatus(scenario);
      if (status) {
        return HttpResponse.json({ detail: status === 403 ? FORBIDDEN_ERROR : SERVER_ERROR }, { status });
      }
      const workspace = projectWorkspaceFor(String(params.projectId), scenario);
      if (!workspace) {
        return HttpResponse.json({ detail: "Không tìm thấy dự án." }, { status: 404 });
      }
      return HttpResponse.json(workspace);
    }),
    http.get(`${ROOT}/projects/:projectId/issues/:issueKey`, async ({ params }) => {
      await sleepFor(scenario);
      const status = errorStatus(scenario);
      if (status) {
        return HttpResponse.json({ detail: status === 403 ? FORBIDDEN_ERROR : SERVER_ERROR }, { status });
      }
      const detail = issueDetailFor(String(params.projectId), String(params.issueKey));
      if (!detail) {
        return HttpResponse.json({ detail: "Không tìm thấy issue." }, { status: 404 });
      }
      return HttpResponse.json(detail);
    }),
    http.get(`${ROOT}/projects/:projectId/code`, async ({ params }) => {
      await sleepFor(scenario);
      if (scenario === "server-error" || scenario === "student-partial-error") {
        return HttpResponse.json({ detail: SERVER_ERROR }, { status: 500 });
      }
      const code = projectCodeFor(String(params.projectId), scenario);
      if (!code) {
        return HttpResponse.json({ detail: "Không tìm thấy dự án." }, { status: 404 });
      }
      return HttpResponse.json(code);
    }),

    // Notifications
    http.get(`${ROOT}/notifications`, async () => {
      await sleepFor(scenario);
      if (scenario === "server-error" || scenario === "student-partial-error") {
        return HttpResponse.json({ detail: SERVER_ERROR }, { status: 500 });
      }
      return HttpResponse.json(notificationsForScenario(scenario));
    }),
    http.post(`${ROOT}/notifications/:id/read`, async () => new HttpResponse(null, { status: 204 })),
    http.post(`${ROOT}/notifications/read-all`, async () => new HttpResponse(null, { status: 204 })),

    // Settings
    http.get(`${ROOT}/me/settings`, async () => {
      await sleepFor(scenario);
      const status = errorStatus(scenario);
      if (status) return HttpResponse.json({ detail: SERVER_ERROR }, { status });
      return HttpResponse.json(accountSettingsForScenario(scenario));
    }),
    http.patch(`${ROOT}/me/settings`, async () => new HttpResponse(null, { status: 204 })),
    http.post(`${ROOT}/me/github/disconnect`, async () => new HttpResponse(null, { status: 204 })),

    // Project settings (leader-only, BYOK AI provider state)
    http.get(`${ROOT}/projects/:projectId/settings`, async ({ params }) => {
      await sleepFor(scenario);
      if (scenario === "student-forbidden") {
        return HttpResponse.json({ detail: FORBIDDEN_ERROR }, { status: 403 });
      }
      const workspace = projectWorkspaceFor(String(params.projectId), scenario);
      if (!workspace) {
        return HttpResponse.json({ detail: "Không tìm thấy dự án." }, { status: 404 });
      }
      return HttpResponse.json({
        projectId: workspace.projectId,
        myRole: workspace.myRole,
        ai: {
          provider: "openai",
          keyConfigured: scenario !== "student-ai-key-missing",
          keyHint: null,
          lastCheckedAt: null,
          status:
            scenario === "student-ai-key-missing"
              ? "not-configured"
              : "connected",
        },
      });
    }),
    http.put(`${ROOT}/projects/:projectId/settings/ai-key`, async () => new HttpResponse(null, { status: 204 })),
  ];
}