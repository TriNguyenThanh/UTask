import type { ApiClient } from "@/lib/api/client";

/**
 * Teacher read models. The /teacher/* paths below are demo-only (MSW) and are
 * NOT an agreed backend contract: the Classroom and Project services have not
 * published one yet. Keep this file as the single place that knows them so a
 * real contract only changes the wrappers.
 */
const TEACHER_ROOT = "/api/work/api/v1/teacher";

/** What happened and when; never a bare timestamp. */
export interface TeacherActivity {
  at: string;
  kind: "issue-updated";
}

export interface TeacherCourseSummary {
  courseId: string;
  /** Subject code. Several classes can share it; use `courseId` as the key. */
  courseCode: string;
  /** Distinguishes classes of the same subject; null when the code is unique. */
  section: string | null;
  name: string;
  term: string;
  studentCount: number;
  studentsWithoutTeam: number;
  teamCount: number;
  teamsWithoutProject: number;
  /** Teams with at least one rule-based signal (see TeacherSignal). */
  teamsWithSignals: number;
  /** Null when no team has recorded activity. */
  lastActivity: TeacherActivity | null;
}

export interface TeacherCourseDetail extends TeacherCourseSummary {
  instructors: { userId: string; name: string; isOwner: boolean }[];
  /** Null when the class has no join code. */
  joinCode: string | null;
  teamSize: { min: number; max: number };
}

export interface TeacherStudent {
  userId: string;
  studentCode: string;
  name: string;
  email: string;
  /** Team inside THIS class only. */
  team: { teamId: string; name: string; role: "leader" | "member" } | null;
  /** Set when the student asked to join a team and is awaiting approval. */
  pendingTeam: { teamId: string; name: string } | null;
}

export interface TeacherTeamProgress {
  percent: number;
  /** What the percentage counts, so the UI can say so. */
  basis: "sprint-points" | "issues";
}

export interface TeacherTeamMember {
  userId: string;
  name: string;
  studentCode: string;
  role: "leader" | "member";
}

export interface TeacherTeam {
  teamId: string;
  name: string;
  leaders: { userId: string; name: string }[];
  members: TeacherTeamMember[];
  memberCount: number;
  maxMembers: number;
  project: { projectId: string; key: string; name: string } | null;
  /** Null when there is nothing to measure yet (not zero percent). */
  progress: TeacherTeamProgress | null;
  lastActivity: TeacherActivity | null;
}

/**
 * A fact worth the teacher's attention, stated with its cause. Signals come
 * from fixed rules over project data (not from AI) and never become a grade.
 */
export interface TeacherSignal {
  code: "no-project" | "no-progress-data" | "no-activity" | "stale-activity" | "below-min-size";
  label: string;
}

export interface TeacherOversightRow {
  teamId: string;
  name: string;
  project: { projectId: string; key: string; name: string } | null;
  memberCount: number;
  progress: TeacherTeamProgress | null;
  /** Null when the project has no issues. */
  issues: { done: number; total: number } | null;
  /** Active sprint of the project, if any. */
  sprint: { name: string; endsAt: string } | null;
  lastActivity: TeacherActivity | null;
  signals: TeacherSignal[];
}

export type TeacherIssueStatus = "todo" | "in-progress" | "review" | "done";

/**
 * Team dashboard (T08). Every field says where it comes from; a field with no
 * source is null, never zero.
 */
export interface TeacherTeamDetail {
  team: { teamId: string; name: string; courseId: string };
  members: TeacherTeamMember[];
  maxMembers: number;
  project: { projectId: string; key: string; name: string } | null;
  progress: TeacherTeamProgress | null;
  /** Issues of the project by status; null when the project has no issues. */
  issues: { total: number; byStatus: Record<TeacherIssueStatus, number> } | null;
  /** Active Sprint with the points its progress is computed from. */
  sprint: {
    name: string;
    endsAt: string;
    completedPoints: number;
    totalPoints: number;
  } | null;
  /**
   * Overdue = has a deadline, is not done and the deadline is before the
   * reference time. `withDueDate` is the denominator. Null when no issue has
   * a deadline: "no data", not "none overdue".
   */
  overdue: { overdue: number; withDueDate: number } | null;
  /** Reference time the overdue count was computed at (fixed demo clock). */
  asOf: string;
  lastActivity: TeacherActivity | null;
  signals: TeacherSignal[];
}

export function teacherCoursesRequest(client: ApiClient) {
  return client.request<{ courses: TeacherCourseSummary[] }>(`${TEACHER_ROOT}/courses`);
}

export function teacherCourseRequest(client: ApiClient, courseId: string) {
  return client.request<TeacherCourseDetail>(
    `${TEACHER_ROOT}/courses/${encodeURIComponent(courseId)}`,
  );
}

export function teacherStudentsRequest(client: ApiClient, courseId: string) {
  return client.request<{ students: TeacherStudent[] }>(
    `${TEACHER_ROOT}/courses/${encodeURIComponent(courseId)}/students`,
  );
}

export function teacherTeamsRequest(client: ApiClient, courseId: string) {
  return client.request<{ teams: TeacherTeam[] }>(
    `${TEACHER_ROOT}/courses/${encodeURIComponent(courseId)}/teams`,
  );
}

export function teacherOversightRequest(client: ApiClient, courseId: string) {
  return client.request<{ teams: TeacherOversightRow[]; staleAfterDays: number }>(
    `${TEACHER_ROOT}/courses/${encodeURIComponent(courseId)}/oversight`,
  );
}

export function teacherTeamRequest(client: ApiClient, courseId: string, teamId: string) {
  return client.request<TeacherTeamDetail>(
    `${TEACHER_ROOT}/courses/${encodeURIComponent(courseId)}/teams/${encodeURIComponent(teamId)}`,
  );
}
