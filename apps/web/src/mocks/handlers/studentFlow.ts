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
import type { MockCreatedTeam, MockDatabase } from "@/mocks/data/database";
import {
  accessibleProjectsForUser,
  enrolledCoursesFor,
  projectRoleForUser,
} from "@/mocks/data/relationships";
import type { MockRepository } from "@/mocks/data/storage";

const ROOT = "/api/work/api/v1";

const SERVER_ERROR = "Lỗi hệ thống, vui lòng thử lại sau.";
const FORBIDDEN_ERROR = "Bạn không có quyền truy cập tài nguyên này.";
const UNAUTHORIZED_ERROR = "Phiên đăng nhập đã hết hạn.";

function sleepFor(scenario: MockScenario): Promise<void> | undefined {
  return scenario === "slow-network" || scenario === "student-loading"
    ? delay(1200)
    : undefined;
}

function parseTokenUserId(request: Request): string | null {
  const header = request.headers.get("Authorization") ?? "";
  return /^Bearer mock-access:([^:]+):/.exec(header)?.[1] ?? null;
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

function unauthorized() {
  return HttpResponse.json({ detail: UNAUTHORIZED_ERROR }, { status: 401 });
}

/**
 * Project ids the logged-in account may open, derived from real team
 * memberships in the relationship graph (a user may be leader of one
 * team and member of another).
 */
function accessibleProjectsFor(userId: string): readonly string[] {
  return accessibleProjectsForUser(userId);
}

/** Courses the logged-in account is enrolled in. */
function accessibleCoursesFor(userId: string): readonly string[] {
  return enrolledCoursesFor(userId);
}

type CreateTeamPayload = { teamName?: unknown; maxMembers?: unknown };

/** Applies the demo business rules; returns an error response or the cleaned values. */
function validateCreateTeam(
  courseDetail: NonNullable<ReturnType<typeof courseDetailForScenario>>,
  payload: CreateTeamPayload,
): Response | { teamName: string; maxMembers: number } {
  // Demo business rules, mirroring the future backend contract:
  // only unteamed students may create a team, self-creation must be
  // allowed, the deadline must not have passed and the roster must
  // fit the course team size range.
  if (courseDetail.membership.status !== "none") {
    return HttpResponse.json(
      {
        detail: "Bạn đã thuộc một nhóm hoặc đã gửi yêu cầu tham gia nhóm.",
      },
      { status: 409 },
    );
  }
  if (!courseDetail.teamFormation.selfCreateAllowed) {
    return HttpResponse.json(
      { detail: "Môn học này không cho phép tự lập nhóm." },
      { status: 403 },
    );
  }
  const deadline = courseDetail.teamFormation.registrationDeadline;
  if (deadline && new Date(deadline).getTime() < Date.now()) {
    return HttpResponse.json(
      { detail: "Đã quá hạn đăng ký nhóm môn học." },
      { status: 409 },
    );
  }
  const teamName = String(payload.teamName).trim();
  if (teamName.length < 3) {
    return HttpResponse.json(
      {
        detail: "Dữ liệu không hợp lệ.",
        errors: { teamName: ["Tên nhóm cần ít nhất 3 ký tự."] },
      },
      { status: 422 },
    );
  }
  const maxMembers = Number(payload.maxMembers);
  if (
    !Number.isInteger(maxMembers) ||
    maxMembers < courseDetail.teamSize.min ||
    maxMembers > courseDetail.teamSize.max
  ) {
    return HttpResponse.json(
      {
        detail: "Dữ liệu không hợp lệ.",
        errors: {
          maxMembers: [
            `Sĩ số nhóm phải từ ${courseDetail.teamSize.min} đến ${courseDetail.teamSize.max}.`,
          ],
        },
      },
      { status: 422 },
    );
  }
  return { teamName, maxMembers };
}

export function createStudentFlowHandlers(
  scenario: MockScenario,
  repository: MockRepository,
): HttpHandler[] {
  const { db } = repository;

  return [
    // Courses & teams
    http.get(`${ROOT}/courses`, async ({ request }) => {
      await sleepFor(scenario);
      const userId = parseTokenUserId(request);
      if (!userId) return unauthorized();
      const status = errorStatus(scenario);
      if (status) return HttpResponse.json({ detail: SERVER_ERROR }, { status });
      return HttpResponse.json({
        courses: [],
      });
    }),
    http.get(`${ROOT}/courses/:courseId`, async ({ params, request }) => {
      await sleepFor(scenario);
      const userId = parseTokenUserId(request);
      if (!userId) return unauthorized();
      const status = errorStatus(scenario);
      if (status) return HttpResponse.json({ detail: SERVER_ERROR }, { status });
      const courseId = String(params.courseId);
      const detail = courseDetailForScenario(courseId, scenario, userId);
      if (!detail) {
        return HttpResponse.json({ detail: "Không tìm thấy môn học." }, { status: 404 });
      }
      // Enforced demo permission: only enrolled students open a course.
      if (!accessibleCoursesFor(userId).includes(courseId)) {
        return HttpResponse.json({ detail: FORBIDDEN_ERROR }, { status: 403 });
      }
      return HttpResponse.json(detail);
    }),
    http.post(`${ROOT}/courses/:courseId/teams`, async ({ params, request }) => {
      await sleepFor(scenario);
      const userId = parseTokenUserId(request);
      if (!userId) return unauthorized();
      const status = errorStatus(scenario);
      if (status) return HttpResponse.json({ detail: SERVER_ERROR }, { status });
      if (scenario === "student-forbidden") {
        return HttpResponse.json({ detail: FORBIDDEN_ERROR }, { status: 403 });
      }
      const courseId = String(params.courseId);
      if (!accessibleCoursesFor(userId).includes(courseId)) {
        return HttpResponse.json({ detail: FORBIDDEN_ERROR }, { status: 403 });
      }

      // Parse the JSON payload — a non-object body means the client sent
      // a pre-stringified string (double-stringify regression).
      let payload: {
        teamName?: unknown;
        description?: unknown;
        neededSkills?: unknown;
        maxMembers?: unknown;
      };
      try {
        payload = (await request.json()) as typeof payload;
      } catch {
        return HttpResponse.json(
          { detail: "Định dạng yêu cầu không hợp lệ." },
          { status: 400 },
        );
      }
      if (typeof payload !== "object" || payload === null || typeof payload.teamName !== "string") {
        return HttpResponse.json(
          {
            detail: "Dữ liệu không hợp lệ.",
            errors: { teamName: ["Tên nhóm phải là chuỗi ký tự."] },
          },
          { status: 422 },
        );
      }

      const courseDetail = courseDetailForScenario(courseId, scenario, userId);
      if (!courseDetail) {
        return HttpResponse.json({ detail: "Không tìm thấy môn học." }, { status: 404 });
      }
      const checked = validateCreateTeam(courseDetail, payload);
      if (checked instanceof Response) return checked;
      const { teamName, maxMembers } = checked;

      // A team for this user+course already exists in this session → 409.
      if (db.createdTeams[`${userId}:${courseId}`]) {
        return HttpResponse.json(
          {
            detail: "Bạn đã gửi yêu cầu thành lập nhóm cho môn học này.",
          },
          { status: 409 },
        );
      }

      // Persist the new team. The creator becomes leader; topic starts as
      // a draft and no workspace/project is provisioned automatically.
      const team: MockCreatedTeam = {
        teamId: `team-created-${userId.slice(-6)}-${courseId.slice(-4)}`,
        courseId,
        teamName,
        description:
          typeof payload.description === "string" ? payload.description.trim() : "",
        neededSkills:
          typeof payload.neededSkills === "string" && payload.neededSkills.trim() !== ""
            ? payload.neededSkills
                .split(",")
                .map((skill) => skill.trim())
                .filter(Boolean)
            : [],
        maxMembers,
        members: [{ userId, role: "leader", joinedAt: new Date().toISOString() }],
        createdAt: new Date().toISOString(),
      };
      db.createdTeams[`${userId}:${courseId}`] = team;
      repository.save();
      return HttpResponse.json(
        { teamId: team.teamId, teamName: team.teamName },
        { status: 201 },
      );
    }),

    // Projects
    http.get(`${ROOT}/projects`, async ({ request }) => {
      await sleepFor(scenario);
      const userId = parseTokenUserId(request);
      if (!userId) return unauthorized();
      const status = errorStatus(scenario);
      if (status) return HttpResponse.json({ detail: SERVER_ERROR }, { status });
      // Scenario filters pin project-list UI states; the default scenario
      // filters by the account's real memberships.
      if (scenario === "student-empty") return HttpResponse.json([]);
      if (scenario === "student-project-leader") {
        return HttpResponse.json(
          projectSummariesForScenario(scenario, userId).filter((project) => project.role === "leader"),
        );
      }
      if (scenario === "student-project-member") {
        return HttpResponse.json(
          projectSummariesForScenario(scenario, userId).filter(
            (project) => project.role === "member" && !project.archived,
          ),
        );
      }
      const accessible = new Set(accessibleProjectsFor(userId));
      return HttpResponse.json(
        projectSummariesForScenario(scenario, userId).filter((project) =>
          accessible.has(project.projectId),
        ),
      );
    }),
    http.get(`${ROOT}/projects/:projectId`, async ({ params, request }) => {
      await sleepFor(scenario);
      const userId = parseTokenUserId(request);
      if (!userId) return unauthorized();
      const status = errorStatus(scenario);
      if (status) {
        return HttpResponse.json({ detail: status === 403 ? FORBIDDEN_ERROR : SERVER_ERROR }, { status });
      }
      const projectId = String(params.projectId);
      const workspace = projectWorkspaceFor(projectId, scenario, userId);
      if (!workspace) {
        return HttpResponse.json({ detail: "Không tìm thấy dự án." }, { status: 404 });
      }
      // Enforced demo permission: only project members open a workspace.
      if (!accessibleProjectsFor(userId).includes(projectId)) {
        return HttpResponse.json({ detail: FORBIDDEN_ERROR }, { status: 403 });
      }
      return HttpResponse.json(workspace);
    }),
    http.get(`${ROOT}/projects/:projectId/issues/:issueKey`, async ({ params, request }) => {
      await sleepFor(scenario);
      const userId = parseTokenUserId(request);
      if (!userId) return unauthorized();
      const status = errorStatus(scenario);
      if (status) {
        return HttpResponse.json({ detail: status === 403 ? FORBIDDEN_ERROR : SERVER_ERROR }, { status });
      }
      const projectId = String(params.projectId);
      if (!accessibleProjectsFor(userId).includes(projectId)) {
        return HttpResponse.json({ detail: FORBIDDEN_ERROR }, { status: 403 });
      }
      const detail = issueDetailFor(projectId, String(params.issueKey), userId);
      if (!detail) {
        return HttpResponse.json({ detail: "Không tìm thấy issue." }, { status: 404 });
      }
      return HttpResponse.json(detail);
    }),
    http.get(`${ROOT}/projects/:projectId/code`, async ({ params, request }) => {
      await sleepFor(scenario);
      const userId = parseTokenUserId(request);
      if (!userId) return unauthorized();
      if (scenario === "server-error" || scenario === "student-partial-error") {
        return HttpResponse.json({ detail: SERVER_ERROR }, { status: 500 });
      }
      const projectId = String(params.projectId);
      if (!accessibleProjectsFor(userId).includes(projectId)) {
        return HttpResponse.json({ detail: FORBIDDEN_ERROR }, { status: 403 });
      }
      const code = projectCodeFor(projectId, scenario);
      if (!code) {
        return HttpResponse.json({ detail: "Không tìm thấy dự án." }, { status: 404 });
      }
      return HttpResponse.json(code);
    }),

    // Notifications — read state persists per user.
    http.get(`${ROOT}/notifications`, async ({ request }) => {
      await sleepFor(scenario);
      const userId = parseTokenUserId(request);
      if (!userId) return unauthorized();
      if (scenario === "server-error" || scenario === "student-partial-error") {
        return HttpResponse.json({ detail: SERVER_ERROR }, { status: 500 });
      }
      const readIds = db.notificationReadByUser[userId] ?? [];
      const read = new Set(readIds);
      // Default notifications reference the leader's projects; students
      // without access only see course-scope notifications.
      const visible = notificationsForScenario(scenario).filter((notification) => {
        if (
          notification.target?.kind === "team-hub" ||
          notification.target?.kind === "team-formation" ||
          notification.target?.kind === "join-request" ||
          notification.target?.kind === "course-deadline"
        ) {
          return true;
        }
        const projectId =
          notification.target && "projectId" in notification.target
            ? notification.target.projectId
            : null;
        return projectId !== null && accessibleProjectsFor(userId).includes(projectId);
      });
      return HttpResponse.json(
        visible.map((notification) => ({ ...notification, read: read.has(notification.id) })),
      );
    }),
    http.post(`${ROOT}/notifications/:id/read`, ({ params, request }) => {
      const userId = parseTokenUserId(request);
      if (!userId) return unauthorized();
      const readIds = db.notificationReadByUser[userId] ?? [];
      if (!readIds.includes(String(params.id))) {
        db.notificationReadByUser[userId] = [...readIds, String(params.id)];
      }
      repository.save();
      return new HttpResponse(null, { status: 204 });
    }),
    http.post(`${ROOT}/notifications/read-all`, ({ request }) => {
      const userId = parseTokenUserId(request);
      if (!userId) return unauthorized();
      const visible = notificationsForScenario(scenario).filter((notification) => {
        if (
          notification.target?.kind === "team-hub" ||
          notification.target?.kind === "team-formation" ||
          notification.target?.kind === "join-request" ||
          notification.target?.kind === "course-deadline"
        ) {
          return true;
        }
        const projectId =
          notification.target && "projectId" in notification.target
            ? notification.target.projectId
            : null;
        return projectId !== null && accessibleProjectsFor(userId).includes(projectId);
      });
      const readIds = db.notificationReadByUser[userId] ?? [];
      const read = new Set(readIds);
      for (const notification of visible) {
        read.add(notification.id);
      }
      db.notificationReadByUser[userId] = [...read];
      repository.save();
      return new HttpResponse(null, { status: 204 });
    }),

    // Settings — account fields stored per user.
    http.get(`${ROOT}/me/settings`, async ({ request }) => {
      await sleepFor(scenario);
      const userId = parseTokenUserId(request);
      if (!userId) return unauthorized();
      const status = errorStatus(scenario);
      if (status) return HttpResponse.json({ detail: SERVER_ERROR }, { status });
      const record = db.profilesByUser[userId];
      const githubStatus =
        scenario === "student-github-disconnected" || db.githubDisconnectedByUser[userId]
          ? "disconnected"
          : "connected";
      return HttpResponse.json({
        studentId: record?.student_id ?? "",
        fullName: record?.full_name ?? "",
        email: record?.email ?? "",
        cohortClass: record?.cohort_class ?? "",
        faculty: record?.faculty ?? "",
        phone: record?.phone ?? "",
        updatedAt: record?.updated_at ?? new Date().toISOString(),
        github: {
          status: githubStatus,
          username: githubStatus === "disconnected" ? null : "hoangnam21",
          profileUrl: githubStatus === "disconnected" ? null : "https://github.com/hoangnam21",
          lastSyncedAt: githubStatus === "disconnected" ? null : new Date().toISOString(),
          linkedRepositoryCount: githubStatus === "disconnected" ? 0 : 8,
        },
        sessions: [
          { id: "s1", device: "Chrome — Windows 11", location: "TP.HCM, VN", lastActiveAt: new Date().toISOString(), current: true },
          { id: "s2", device: "Mobile App — Android", location: "TP.HCM, VN", lastActiveAt: new Date(Date.now() - 90_000_000).toISOString(), current: false },
        ],
      });
    }),
    http.patch(`${ROOT}/me/settings`, async ({ request }) => {
      const userId = parseTokenUserId(request);
      if (!userId) return unauthorized();
      let payload: Record<string, unknown>;
      try {
        payload = (await request.json()) as Record<string, unknown>;
      } catch {
        return HttpResponse.json(
          { detail: "Định dạng yêu cầu không hợp lệ." },
          { status: 400 },
        );
      }
      if (typeof payload !== "object" || payload === null) {
        return HttpResponse.json(
          { detail: "Định dạng yêu cầu không hợp lệ." },
          { status: 400 },
        );
      }
      const record = db.profilesByUser[userId];
      if (!record) {
        return HttpResponse.json({ detail: "Không tìm thấy người dùng." }, { status: 404 });
      }
      // Only updatable fields are accepted; email/student_id stay fixed.
      const fields: [keyof MockDatabase["profilesByUser"][string], string][] = [
        ["full_name", "fullName"],
        ["cohort_class", "cohortClass"],
        ["faculty", "faculty"],
        ["phone", "phone"],
      ];
      for (const [recordKey, payloadKey] of fields) {
        const value = payload[payloadKey];
        if (typeof value === "string" && value.trim() !== "") {
          record[recordKey] = value.trim();
        }
      }
      record.updated_at = new Date().toISOString();
      repository.save();
      return new HttpResponse(null, { status: 204 });
    }),
    http.post(`${ROOT}/me/github/disconnect`, ({ request }) => {
      const userId = parseTokenUserId(request);
      if (!userId) return unauthorized();
      db.githubDisconnectedByUser[userId] = true;
      repository.save();
      return new HttpResponse(null, { status: 204 });
    }),

    // Project settings (leader-only, BYOK AI provider state)
    http.get(`${ROOT}/projects/:projectId/settings`, async ({ params, request }) => {
      await sleepFor(scenario);
      const userId = parseTokenUserId(request);
      if (!userId) return unauthorized();
      if (scenario === "student-forbidden") {
        return HttpResponse.json({ detail: FORBIDDEN_ERROR }, { status: 403 });
      }
      const projectId = String(params.projectId);
      const workspace = projectWorkspaceFor(projectId, scenario, userId);
      if (!workspace) {
        return HttpResponse.json({ detail: "Không tìm thấy dự án." }, { status: 404 });
      }
      if (!accessibleProjectsFor(userId).includes(projectId)) {
        return HttpResponse.json({ detail: FORBIDDEN_ERROR }, { status: 403 });
      }
      // Demo permission: project settings are leader-only.
      if (projectRoleForUser(userId, projectId) !== "leader") {
        return HttpResponse.json({ detail: FORBIDDEN_ERROR }, { status: 403 });
      }
      const saved = db.aiConfigByProject[projectId];
      return HttpResponse.json({
        projectId: workspace.projectId,
        myRole: workspace.myRole,
        ai: saved ?? {
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
    http.put(`${ROOT}/projects/:projectId/settings/ai-key`, async ({ params, request }) => {
      const userId = parseTokenUserId(request);
      if (!userId) return unauthorized();
      const projectId = String(params.projectId);
      const workspace = projectWorkspaceFor(projectId, scenario, userId);
      if (!workspace) {
        return HttpResponse.json({ detail: "Không tìm thấy dự án." }, { status: 404 });
      }
      if (!accessibleProjectsFor(userId).includes(projectId)) {
        return HttpResponse.json({ detail: FORBIDDEN_ERROR }, { status: 403 });
      }
      // Demo permission: only the team leader may configure the AI key.
      if (projectRoleForUser(userId, projectId) !== "leader") {
        return HttpResponse.json({ detail: FORBIDDEN_ERROR }, { status: 403 });
      }
      let payload: Record<string, unknown>;
      try {
        payload = (await request.json()) as Record<string, unknown>;
      } catch {
        return HttpResponse.json(
          { detail: "Định dạng yêu cầu không hợp lệ." },
          { status: 400 },
        );
      }
      const provider = typeof payload.provider === "string" ? payload.provider : null;
      const apiKey = typeof payload.apiKey === "string" ? payload.apiKey : "";
      if (!provider || apiKey.trim() === "") {
        return HttpResponse.json(
          {
            detail: "Dữ liệu không hợp lệ.",
            errors: { apiKey: ["Vui lòng nhập API key."] },
          },
          { status: 422 },
        );
      }
      // Demo persistence keeps only provider + masked metadata. The raw
      // key is never written to the repository or storage.
      db.aiConfigByProject[projectId] = {
        provider,
        keyConfigured: true,
        keyHint: `${apiKey.slice(0, 3)}••••${apiKey.slice(-2)}`,
        configuredAt: new Date().toISOString(),
      };
      repository.save();
      return new HttpResponse(null, { status: 204 });
    }),
  ];
}