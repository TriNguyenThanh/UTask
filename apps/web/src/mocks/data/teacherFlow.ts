import type {
  TeacherActivity,
  TeacherCourseDetail,
  TeacherCourseSummary,
  TeacherOversightRow,
  TeacherIssueStatus,
  TeacherSignal,
  TeacherStudent,
  TeacherTeam,
  TeacherTeamDetail,
  TeacherTeamProgress,
} from "@/lib/api/teacherFlow";
import { MOCK_COURSE_META, MOCK_PEOPLE, MOCK_TEAM_META } from "@/mocks/data/directory";
import {
  MOCK_COURSE_INSTRUCTORS,
  MOCK_TEAM_PROJECTS,
  assignmentFor,
  membersOfTeam,
  pendingRequestFor,
  studentsOfCourse,
  teamsOfCourse,
} from "@/mocks/data/relationships";
import { mockAnchorDate, projectDataFor } from "@/mocks/data/studentFlow";

/**
 * Teacher read models. Every number and name is derived from the shared
 * relationship graph (relationships.ts + directory.ts) — the same source the
 * Student views use — so the two roles cannot drift apart. Nothing here is a
 * literal KPI.
 */

function nameOf(userId: string): string {
  return MOCK_PEOPLE[userId]?.displayName ?? "Chưa rõ";
}

function teamNameOf(teamId: string): string {
  return MOCK_TEAM_META[teamId]?.name ?? teamId;
}

/** A team with no issue update for this many days gets the "stale" signal. */
export const STALE_AFTER_DAYS = 7;
const DAY_MS = 24 * 60 * 60 * 1000;

export interface ProjectFacts {
  key: string;
  name: string;
  progress: TeacherTeamProgress | null;
  issues: { done: number; total: number } | null;
  sprint: { name: string; endsAt: string } | null;
  lastActivity: TeacherActivity | null;
}

/**
 * Project facts come from the project fixture using a fixed clock, so
 * "last activity" is a real fixture timestamp, never the current time.
 * Progress follows the documented rule: active-sprint points when there are
 * points to measure, otherwise done/total issues, otherwise unknown.
 */
function projectFacts(projectId: string): ProjectFacts | null {
  const workspace = projectDataFor(projectId, mockAnchorDate());
  if (!workspace) {
    return null;
  }
  const activeSprint = workspace.sprints.find((sprint) => sprint.state === "active");
  let progress: TeacherTeamProgress | null = null;
  if (activeSprint && activeSprint.totalPoints > 0) {
    progress = {
      percent: Math.round((activeSprint.completedPoints / activeSprint.totalPoints) * 100),
      basis: "sprint-points",
    };
  } else if (workspace.issues.length > 0) {
    const done = workspace.issues.filter((issue) => issue.status === "done").length;
    progress = {
      percent: Math.round((done / workspace.issues.length) * 100),
      basis: "issues",
    };
  }
  const latest = workspace.issues.reduce<string | null>(
    (best, issue) => (best === null || issue.updatedAt > best ? issue.updatedAt : best),
    null,
  );
  return {
    key: workspace.projectKey,
    name: workspace.name,
    progress,
    issues:
      workspace.issues.length > 0
        ? {
            done: workspace.issues.filter((issue) => issue.status === "done").length,
            total: workspace.issues.length,
          }
        : null,
    sprint: activeSprint ? { name: activeSprint.name, endsAt: activeSprint.endDate } : null,
    lastActivity: latest ? { at: latest, kind: "issue-updated" } : null,
  };
}

export function buildTeacherTeams(courseId: string): TeacherTeam[] {
  const maxMembers = MOCK_COURSE_META[courseId]?.teamSize.max ?? 0;
  return teamsOfCourse(courseId).map((teamId) => {
    const members = membersOfTeam(teamId);
    const projectId = MOCK_TEAM_PROJECTS[teamId];
    const facts = projectId ? projectFacts(projectId) : null;
    return {
      teamId,
      name: teamNameOf(teamId),
      leaders: members
        .filter((member) => member.role === "leader")
        .map((member) => ({ userId: member.userId, name: nameOf(member.userId) })),
      members: members.map((member) => ({
        userId: member.userId,
        name: nameOf(member.userId),
        studentCode: MOCK_PEOPLE[member.userId]?.studentCode ?? "",
        role: member.role,
      })),
      memberCount: members.length,
      maxMembers,
      project: projectId && facts ? { projectId, key: facts.key, name: facts.name } : null,
      progress: facts?.progress ?? null,
      lastActivity: facts?.lastActivity ?? null,
    };
  });
}

/**
 * Rule-based signals for one team, each with its cause. Fixed rules over the
 * fixture data and the fixed anchor clock — no AI, no scoring:
 *   - no project / no data to measure / no activity recorded,
 *   - last issue update older than STALE_AFTER_DAYS,
 *   - fewer members than the class minimum.
 */
export function signalsFor(
  facts: ProjectFacts | null,
  memberCount: number,
  minMembers: number,
): TeacherSignal[] {
  const signals: TeacherSignal[] = [];
  if (!facts) {
    signals.push({ code: "no-project", label: "Chưa có project" });
  } else {
    if (!facts.progress) {
      signals.push({ code: "no-progress-data", label: "Chưa có dữ liệu để đo tiến độ" });
    }
    if (!facts.lastActivity) {
      signals.push({ code: "no-activity", label: "Chưa ghi nhận cập nhật issue nào" });
    } else {
      const idleDays = Math.floor(
        (mockAnchorDate().getTime() - Date.parse(facts.lastActivity.at)) / DAY_MS,
      );
      if (idleDays >= STALE_AFTER_DAYS) {
        signals.push({
          code: "stale-activity",
          label: `Không có cập nhật issue trong ${idleDays} ngày`,
        });
      }
    }
  }
  if (memberCount < minMembers) {
    signals.push({
      code: "below-min-size",
      label: `Chưa đủ thành viên tối thiểu (${memberCount}/${minMembers})`,
    });
  }
  return signals;
}

export function buildTeacherOversight(courseId: string): TeacherOversightRow[] {
  const minMembers = MOCK_COURSE_META[courseId]?.teamSize.min ?? 0;
  return teamsOfCourse(courseId).map((teamId) => {
    const memberCount = membersOfTeam(teamId).length;
    const projectId = MOCK_TEAM_PROJECTS[teamId];
    const facts = projectId ? projectFacts(projectId) : null;
    return {
      teamId,
      name: teamNameOf(teamId),
      project: projectId && facts ? { projectId, key: facts.key, name: facts.name } : null,
      memberCount,
      progress: facts?.progress ?? null,
      issues: facts?.issues ?? null,
      sprint: facts?.sprint ?? null,
      lastActivity: facts?.lastActivity ?? null,
      signals: signalsFor(facts, memberCount, minMembers),
    };
  });
}

/**
 * Team dashboard. Reads the same viewer-independent project facts as the
 * class views, at the fixed demo clock, so numbers agree across screens.
 * Returns null when the team is not part of `courseId`.
 */
export function buildTeacherTeamDetail(courseId: string, teamId: string): TeacherTeamDetail | null {
  if (!teamsOfCourse(courseId).includes(teamId)) {
    return null;
  }
  const meta = MOCK_COURSE_META[courseId];
  const now = mockAnchorDate();
  const team = buildTeacherTeams(courseId).find((candidate) => candidate.teamId === teamId);
  const oversight = buildTeacherOversight(courseId).find((row) => row.teamId === teamId);
  if (!meta || !team || !oversight) {
    return null;
  }
  const projectId = MOCK_TEAM_PROJECTS[teamId];
  const data = projectId ? projectDataFor(projectId, now) : null;

  const byStatus: Record<TeacherIssueStatus, number> = {
    todo: 0,
    "in-progress": 0,
    review: 0,
    done: 0,
  };
  for (const issue of data?.issues ?? []) {
    byStatus[issue.status] += 1;
  }
  const withDueDate = (data?.issues ?? []).filter((issue) => issue.dueAt);
  const activeSprint = data?.sprints.find((sprint) => sprint.state === "active");

  return {
    team: { teamId, name: team.name, courseId },
    members: team.members,
    maxMembers: meta.teamSize.max,
    project: team.project,
    progress: team.progress,
    issues: data && data.issues.length > 0 ? { total: data.issues.length, byStatus } : null,
    sprint: activeSprint
      ? {
          name: activeSprint.name,
          endsAt: activeSprint.endDate,
          completedPoints: activeSprint.completedPoints,
          totalPoints: activeSprint.totalPoints,
        }
      : null,
    overdue:
      withDueDate.length > 0
        ? {
            overdue: withDueDate.filter(
              (issue) => issue.status !== "done" && Date.parse(issue.dueAt as string) < now.getTime(),
            ).length,
            withDueDate: withDueDate.length,
          }
        : null,
    asOf: now.toISOString(),
    lastActivity: team.lastActivity,
    signals: oversight.signals,
  };
}

export function buildTeacherStudents(courseId: string): TeacherStudent[] {
  return studentsOfCourse(courseId).map((userId) => {
    const person = MOCK_PEOPLE[userId];
    const assignment = assignmentFor(userId, courseId);
    const pending = pendingRequestFor(userId, courseId);
    return {
      userId,
      studentCode: person?.studentCode ?? "",
      name: nameOf(userId),
      email: person?.email ?? "",
      team: assignment
        ? { teamId: assignment.teamId, name: teamNameOf(assignment.teamId), role: assignment.role }
        : null,
      pendingTeam: pending ? { teamId: pending.teamId, name: teamNameOf(pending.teamId) } : null,
    };
  });
}

function latestActivity(teams: TeacherTeam[]): TeacherActivity | null {
  return teams.reduce<TeacherActivity | null>((best, team) => {
    if (!team.lastActivity) return best;
    return best === null || team.lastActivity.at > best.at ? team.lastActivity : best;
  }, null);
}

export function buildTeacherCourseSummary(courseId: string): TeacherCourseSummary | null {
  const meta = MOCK_COURSE_META[courseId];
  if (!meta) {
    return null;
  }
  const students = buildTeacherStudents(courseId);
  const teams = buildTeacherTeams(courseId);
  return {
    courseId,
    courseCode: meta.courseCode,
    section: meta.section,
    name: meta.courseName,
    term: meta.term,
    studentCount: students.length,
    studentsWithoutTeam: students.filter((student) => student.team === null).length,
    teamCount: teams.length,
    teamsWithoutProject: teams.filter((team) => team.project === null).length,
    teamsWithSignals: buildTeacherOversight(courseId).filter((row) => row.signals.length > 0).length,
    lastActivity: latestActivity(teams),
  };
}

export function buildTeacherCourseDetail(courseId: string): TeacherCourseDetail | null {
  const summary = buildTeacherCourseSummary(courseId);
  const meta = MOCK_COURSE_META[courseId];
  if (!summary || !meta) {
    return null;
  }
  return {
    ...summary,
    instructors: (MOCK_COURSE_INSTRUCTORS[courseId] ?? []).map((entry) => ({
      userId: entry.userId,
      name: nameOf(entry.userId),
      isOwner: entry.isOwner,
    })),
    joinCode: meta.joinCode,
    teamSize: meta.teamSize,
  };
}
