import { delay, http, HttpResponse, type HttpHandler } from "msw";

import type { MockScenario } from "@/mocks/scenarios";
import {
  accountSettingsForScenario,
  courseDetailForScenario,
  issueDetailFor,
  notificationsForScenario,
  projectCodeFor,
  mockAnchorDate,
  projectSummariesForScenario,
  projectWorkspaceFor,
} from "@/mocks/data/studentFlow";
import type { MockCreatedTeam, MockDatabase } from "@/mocks/data/database";
import {
  accessibleProjectsForUser,
  classesVisibleForNotifications,
  enrolledCoursesFor,
  projectViewerFor,
  type MockProjectViewer,
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

/**
 * How the caller may see a project: as a team member, or as an instructor of
 * the owning class. An instructor needs BOTH the TEACHER role on the account
 * and the per-class assignment; the role alone opens nothing. Null = no
 * access, answered like a project that does not exist.
 */
function projectViewerOf(
  db: MockDatabase,
  userId: string,
  projectId: string,
): MockProjectViewer | null {
  const viewer = projectViewerFor(userId, projectId);
  if (viewer?.kind === "course-instructor" && !db.authUsersById[userId]?.roles?.includes("TEACHER")) {
    return null;
  }
  return viewer;
}

/**
 * Instructors read through the fixed demo clock so what they see does not
 * drift with the real time; students keep the live clock they always had.
 */
function clockFor(viewer: MockProjectViewer): Date {
  return viewer.kind === "course-instructor" ? mockAnchorDate() : new Date();
}

/**
 * Courses the logged-in account is enrolled in as a student. Instructors are
 * deliberately excluded: these are Student endpoints, and a Teacher role must
 * not unlock them (Teachers read classes through the /teacher/* endpoints).
 */
function accessibleCoursesFor(userId: string): readonly string[] {
  return enrolledCoursesFor(userId);
}

/**
 * Access-failure policy shared by every resource endpoint: a resource that
 * does not exist and one the caller may not open answer identically (404), so
 * the response never reveals which ids exist. 403 is reserved for a caller who
 * can open the resource but lacks the permission for the action (for example
 * a Member opening project settings).
 */
function notFound(detail: string) {
  return HttpResponse.json({ detail }, { status: 404 });
}

/**
 * The single definition of which notifications a user may see. List, mark-read
 * and read-all all go through it so their scopes cannot diverge. Class-level
 * notifications need enrollment or an instructor assignment for that class;
 * project-level ones need project membership.
 */
function visibleNotifications(scenario: MockScenario, userId: string) {
  const classes = classesVisibleForNotifications(userId);
  const projects = accessibleProjectsFor(userId);
  return notificationsForScenario(scenario).filter((notification) => {
    const target = notification.target;
    if (!target) return false;
    if ("courseId" in target) return classes.includes(target.courseId);
    return projects.includes(target.projectId);
  });
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
      // Enforced demo permission: only enrolled students open a course.
      // Check access BEFORE existence to avoid leaking existence (R2).
      if (!accessibleCoursesFor(userId).includes(courseId)) {
        return notFound("Không tìm thấy môn học.");
      }
      const detail = courseDetailForScenario(courseId, scenario, userId);
      if (!detail) {
        return notFound("Không tìm thấy môn học.");
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
        return notFound("Không tìm thấy môn học.");
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
      const teamName = payload.teamName.trim();
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
      // Enforced demo permission: team members and instructors of the owning
      // class open a workspace. Access is checked BEFORE existence (R2).
      const viewer = projectViewerOf(db, userId, projectId);
      if (!viewer) {
        return HttpResponse.json({ detail: "Không tìm thấy dự án." }, { status: 404 });
      }
      const workspace = projectWorkspaceFor(projectId, scenario, userId, clockFor(viewer));
      if (!workspace) {
        return HttpResponse.json({ detail: "Không tìm thấy dự án." }, { status: 404 });
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
      const viewer = projectViewerOf(db, userId, projectId);
      if (!viewer) {
        return notFound("Không tìm thấy dự án.");
      }
      const detail = issueDetailFor(projectId, String(params.issueKey), userId, clockFor(viewer));
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
      const viewer = projectViewerOf(db, userId, projectId);
      if (!viewer) {
        return notFound("Không tìm thấy dự án.");
      }
      const code = projectCodeFor(projectId, scenario, userId, clockFor(viewer));
      if (!code) {
        return HttpResponse.json({ detail: "Không tìm thấy dự án." }, { status: 404 });
      }
      return HttpResponse.json(code);
    }),

    // Notifications — read state persists per user. List, mark-read and
    // read-all share `visibleNotifications`, so none can reach an id the
    // others hide.
    http.get(`${ROOT}/notifications`, async ({ request }) => {
      await sleepFor(scenario);
      const userId = parseTokenUserId(request);
      if (!userId) return unauthorized();
      if (scenario === "server-error" || scenario === "student-partial-error") {
        return HttpResponse.json({ detail: SERVER_ERROR }, { status: 500 });
      }
      const read = new Set(db.notificationReadByUser[userId] ?? []);
      return HttpResponse.json(
        visibleNotifications(scenario, userId).map((notification) => ({
          ...notification,
          read: read.has(notification.id),
        })),
      );
    }),
    http.post(`${ROOT}/notifications/:id/read`, async ({ params, request }) => {
      const userId = parseTokenUserId(request);
      if (!userId) return unauthorized();
      const id = String(params.id);
      if (!visibleNotifications(scenario, userId).some((notification) => notification.id === id)) {
        return notFound("Không tìm thấy thông báo.");
      }
      const readIds = db.notificationReadByUser[userId] ?? [];
      if (!readIds.includes(id)) {
        db.notificationReadByUser[userId] = [...readIds, id];
      }
      repository.save();
      return new HttpResponse(null, { status: 204 });
    }),
    http.post(`${ROOT}/notifications/read-all`, async ({ request }) => {
      const userId = parseTokenUserId(request);
      if (!userId) return unauthorized();
      const read = new Set(db.notificationReadByUser[userId] ?? []);
      for (const notification of visibleNotifications(scenario, userId)) {
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
          { id: "s2", device: "Mobile App — Android", location: "TP.HCM, VN", lastActiveAt: new Date(new Date().getTime() - 90_000_000).toISOString(), current: false },
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
      const fields: [keyof MockDatabase["profilesByUser"][string] & string, string][] = [
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
    http.post(`${ROOT}/me/github/disconnect`, async ({ request }) => {
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
      // Whoever can open the project but is not its leader (a member, or an
      // instructor) gets 403: the resource exists for them, the action does not.
      const viewer = projectViewerOf(db, userId, projectId);
      if (!viewer) {
        return notFound("Không tìm thấy dự án.");
      }
      if (viewer.kind !== "team-member" || viewer.role !== "leader") {
        return HttpResponse.json({ detail: FORBIDDEN_ERROR }, { status: 403 });
      }
      const workspace = projectWorkspaceFor(projectId, scenario, userId);
      if (!workspace) {
        return notFound("Không tìm thấy dự án.");
      }
      const saved = db.aiConfigByProject[projectId];
      return HttpResponse.json({
        projectId: workspace.projectId,
        myRole: viewer.role,
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
      const viewer = projectViewerOf(db, userId, projectId);
      if (!viewer) {
        return notFound("Không tìm thấy dự án.");
      }
      // Only the team leader may configure the AI key; an instructor never can.
      if (viewer.kind !== "team-member" || viewer.role !== "leader") {
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