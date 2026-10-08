/**
 * Domain types for the My Work home screen.
 *
 * Role model: `Student` is a system-level identity; `member`/`leader` are
 * per-team roles carried on each course enrollment.
 */

export type TeamRole = "member" | "leader";

export type TeamMembership =
  | {
      status: "none";
    }
  | {
      status: "pending";
      teamId: string;
      teamName: string;
      requestedAt: string;
    }
  | {
      status: "assigned";
      teamId: string;
      teamName: string;
      role: TeamRole;
    };

export interface CourseEnrollment {
  courseId: string;
  courseCode: string;
  courseName: string;
  semester: string;
  /** Course-level team configuration, drives no-team call-to-action copy. */
  teamFormation: {
    mode: "self-select" | "join-code" | "instructor-assigned";
    /** Team registration deadline (ISO 8601); null when the course has no deadline. */
    registrationDeadline: string | null;
  };
  /**
   * Project workspace id once the topic is approved and the project is
   * provisioned; null while the course has no ready project.
   */
  projectId: string | null;
  membership: TeamMembership;
}

export type TaskPriority = "high" | "medium" | "low";
export type TaskStatus = "todo" | "in-progress" | "review" | "done";

export interface TaskSubtaskProgress {
  completed: number;
  total: number;
}

export interface MyTask {
  id: string;
  issueKey: string;
  title: string;
  courseId: string;
  courseCode: string;
  projectName: string;
  priority: TaskPriority;
  status: TaskStatus;
  /** Deadline (ISO 8601). */
  dueAt: string;
  subtasks?: TaskSubtaskProgress;
  /** Linked git branch name, when the task has one. */
  branchName?: string;
}

export type SprintHealth = "on-track" | "at-risk" | "late";

export interface CourseSprint {
  courseId: string;
  courseCode: string;
  courseName: string;
  semester: string;
  projectName: string;
  teamId: string;
  teamName: string;
  role: TeamRole;
  sprintName: string;
  completedPoints: number;
  totalPoints: number;
  /** Sprint deadline (ISO 8601). */
  deadline: string;
  health: SprintHealth;
  instructorName: string;
}

export type GitHubSyncStatus =
  | { state: "disconnected" }
  | { state: "connected"; linkedProjectCount: number };

export type PullRequestKind = "to-review" | "awaiting-review";

export interface GitHubPullRequest {
  id: string;
  number: number;
  title: string;
  repository: string;
  author: string;
  /** When the PR was last updated (ISO 8601). */
  updatedAt: string;
  kind: PullRequestKind;
}

export interface GitHubCommit {
  id: string;
  message: string;
  repository: string;
  branchName: string;
  issueKey: string | null;
  /** When the commit was created (ISO 8601). */
  committedAt: string;
}

export interface GitHubActivity {
  sync: GitHubSyncStatus;
  pullRequests: GitHubPullRequest[];
  commits: GitHubCommit[];
}

export interface MyWorkSummary {
  dueToday: number;
  overdue: number;
  openPullRequests: number;
  /** Average sprint completion across assigned teams, 0–100. */
  sprintProgressPercent: number;
}

export interface MyWorkOverview {
  semester: string;
  /** When the overview was last refreshed (ISO 8601). */
  refreshedAt: string;
  enrollments: CourseEnrollment[];
  tasks: MyTask[];
  sprints: CourseSprint[];
  summary: MyWorkSummary;
}