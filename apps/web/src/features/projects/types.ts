/**
 * Domain types for the projects feature: list, backlog, board, issues, code.
 */

import type { TeamRole } from "@/features/my-work/types";

/**
 * Who is looking at a project. A viewer is either a member of the owning team
 * (with a per-team role) or an instructor of the class the team belongs to.
 * An instructor never has a team role: no "teacher" TeamRole, no fake
 * membership.
 */
export type ProjectViewer =
  | { kind: "team-member"; role: TeamRole }
  | { kind: "course-instructor"; courseId: string };

export interface ProjectSummary {
  projectId: string;
  projectKey: string;
  name: string;
  courseCode: string;
  courseName: string;
  instructorName: string;
  teamName: string;
  role: TeamRole;
  archived: boolean;
  sprint: {
    name: string;
    deadline: string | null;
    completedPoints: number;
    totalPoints: number;
  } | null;
  repository: string | null;
}

export type ProjectRoleInfo = {
  projectId: string;
  role: TeamRole;
  /** Whether AI actions are usable (BYOK key configured). */
  aiEnabled: boolean;
};

export interface Epic {
  id: string;
  name: string;
  color: string;
  issueCount: number;
}

export type IssueType = "story" | "task" | "bug";
export type IssueStatus = "todo" | "in-progress" | "review" | "done";

export type StateGroup = "BACKLOG" | "UNSTARTED" | "STARTED" | "REVIEW" | "COMPLETED" | "CANCELLED";

export interface ProjectState {
  id: string;
  name: string;
  color: string;
  sequence: number;
  group: StateGroup;
  isDefault: boolean;
}

export interface Issue {
  id: string;
  key: string;
  type: IssueType;
  title: string;
  status: IssueStatus;
  priority: "high" | "medium" | "low";
  storyPoints: number;
  epicId: string | null;
  /** Sprint id; null = product backlog. */
  sprintId: string | null;
  assignee: { userId: string; displayName: string; initials: string } | null;
  hasPullRequest: boolean;
  /** True only when the signed-in user is the assignee (derived per request). */
  isMine: boolean;
  /** Optional deadline; absent when the source has none (never treated as "not overdue"). */
  dueAt?: string | null;
  updatedAt: string;
  /**
   * Position within the project: every list (board column, backlog section)
   * orders its cards by this number.
   */
  rank: number;
  /** State id from WorkService; links to `ProjectWorkspace.states`. */
  statusId: string;
  /** State group; drives board column membership. */
  stateGroup: StateGroup;
  /** Bumped on every write; a stale value on a move gets a 409. */
  version: number;
  /** A flag on the card, not a column: a blocked card keeps its status. */
  blocked: boolean;
  blockedReason: string | null;
}

export interface Sprint {
  id: string;
  name: string;
  state: "active" | "upcoming" | "completed";
  startDate: string;
  endDate: string;
  goal: string;
  completedPoints: number;
  totalPoints: number;
}

export interface ProjectWorkspace {
  projectId: string;
  projectKey: string;
  name: string;
  courseCode: string;
  courseName: string;
  instructorName: string;
  teamName: string;
  /** Class and team that own this project, for breadcrumbs on deep link/refresh. */
  courseId: string;
  teamId: string;
  viewer: ProjectViewer;
  /** Team role of a member viewer; absent for an instructor (no default role). */
  myRole?: TeamRole;
  repository: string | null;
  epics: Epic[];
  sprints: Sprint[];
  issues: Issue[];
  /** Board columns in sequence order; built from WorkService states. */
  states: ProjectState[];
}

export interface IssueComment {
  id: string;
  authorName: string;
  authorInitials: string;
  body: string;
  createdAt: string;
}

export interface IssueHistoryEntry {
  id: string;
  actorName: string;
  /** Human-readable change summary, e.g. "chuyển trạng thái sang In Progress". */
  summary: string;
  at: string;
}

export interface IssueDetail {
  issue: Issue;
  description: string;
  acceptanceCriteria: string[];
  reporterName: string;
  comments: IssueComment[];
  history: IssueHistoryEntry[];
  subtasks: { id: string; title: string; done: boolean }[];
  gitLinks: { kind: "branch" | "commit" | "pr"; label: string }[];
}

export type ContributorStatus = "key" | "active" | "watch";

export interface CodeContributor {
  userId: string;
  displayName: string;
  studentId: string;
  githubUsername: string | null;
  roleTitle: string;
  commits: number;
  commitPercent: number;
  additions: number;
  deletions: number;
  pullRequestCount: number;
  mergedCount: number;
  linkedIssuePercent: number;
  status: ContributorStatus;
  isMe: boolean;
}

export type CodeSyncState =
  | "synced"
  | "pending-webhook"
  | "webhook-error"
  | "token-expired"
  | "no-repo-permission"
  | "disconnected"
  | "no-repository";

export interface CodePullRequest {
  id: string;
  number: number;
  title: string;
  author: string;
  branch: string;
  state: "open" | "merged";
  linkedIssueKey: string | null;
  updatedAt: string;
}

export interface CodeCommit {
  id: string;
  sha: string;
  message: string;
  author: string;
  branch: string;
  linkedIssueKey: string | null;
  committedAt: string;
}

export interface CodeBranch {
  id: string;
  name: string;
  author: string;
  linkedIssueKey: string | null;
  updatedDaysAgo: number;
}

export interface ProjectCode {
  repository: string | null;
  defaultBranch: string | null;
  latestCommitSha: string | null;
  syncState: CodeSyncState;
  stats: {
    commits: number;
    commitsWeekDelta: number;
    pullRequests: { total: number; merged: number; open: number; review: number };
    branches: number;
    linesChanged: { added: number; removed: number };
  };
  contributors: CodeContributor[];
  pullRequests: CodePullRequest[];
  commits: CodeCommit[];
  branches: CodeBranch[];
}