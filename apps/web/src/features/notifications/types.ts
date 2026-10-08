/**
 * Domain types for notifications and account settings.
 */

export type NotificationCategory =
  | "course-team"
  | "task-pr"
  | "ai-risk";

export type NotificationActionTarget =
  | { kind: "team-hub"; courseId: string }
  | { kind: "team-formation"; courseId: string }
  | { kind: "join-request"; courseId: string }
  | { kind: "board-issue"; projectId: string; issueKey: string }
  | { kind: "code"; projectId: string }
  | { kind: "course-deadline"; courseId: string }
  | { kind: "backlog"; projectId: string };

export interface StudentNotification {
  id: string;
  category: NotificationCategory;
  title: string;
  body: string;
  at: string;
  read: boolean;
  actionLabel: string | null;
  target: NotificationActionTarget | null;
}

export interface GitHubIntegrationState {
  status: "disconnected" | "connected" | "connecting" | "token-expired";
  username: string | null;
  profileUrl: string | null;
  lastSyncedAt: string | null;
  linkedRepositoryCount: number;
}

export interface SecuritySession {
  id: string;
  device: string;
  location: string;
  lastActiveAt: string;
  current: boolean;
}

export interface AccountSettings {
  studentId: string;
  fullName: string;
  email: string;
  cohortClass: string;
  faculty: string;
  phone: string;
  updatedAt: string;
  github: GitHubIntegrationState;
  sessions: SecuritySession[];
}