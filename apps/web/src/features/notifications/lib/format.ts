import type { NotificationActionTarget } from "@/features/notifications/types";

/** Relative time helper: "x phút trước" / "x giờ trước" / "x ngày trước". */
export function formatRelative(at: string, now: Date): string {
  const diffMs = now.getTime() - new Date(at).getTime();
  const minutes = Math.floor(diffMs / 60_000);
  if (minutes < 1) return "Vừa xong";
  if (minutes < 60) return `${minutes} phút trước`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} giờ trước`;
  const days = Math.floor(hours / 24);
  return `${days} ngày trước`;
}

/**
 * Class-level notifications open the Student team page, which a teacher-only
 * account cannot use (it answers "not found"). Such an account is sent to the
 * class it manages instead. An account that is both teacher and student keeps
 * the Student page: the notification does not say in which capacity it was
 * delivered.
 */
export function targetUrl(target: NotificationActionTarget, teacherOnly: boolean): string {
  switch (target.kind) {
    case "team-hub":
    case "team-formation":
    case "join-request":
    case "course-deadline":
      return teacherOnly
        ? `/teacher/courses/${target.courseId}`
        : `/courses/${target.courseId}/team`;
    case "board-issue":
      return `/projects/${target.projectId}/board?issue=${target.issueKey}`;
    case "code":
      return `/projects/${target.projectId}/code`;
    case "backlog":
      return `/projects/${target.projectId}/backlog`;
  }
}
