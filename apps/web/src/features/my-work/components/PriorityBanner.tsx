import { TriangleAlert } from "lucide-react";

import type { CourseEnrollment, CourseSprint, MyTask, TeamMembership } from "@/features/my-work/types";
import { isOverdue } from "@/features/my-work/taskFilters";

export interface PriorityAlert {
  id: string;
  message: string;
  /** Secondary action target; null keeps the banner informational only. */
  href: string | null;
  hrefLabel?: string;
  tone: "warning" | "danger";
}

const DAY_MS = 86_400_000;

function daysUntil(iso: string, now: Date): number {
  return Math.ceil((new Date(iso).getTime() - now.getTime()) / DAY_MS);
}

/**
 * Derives the single most urgent alert from enrollment, sprint and task
 * data. Returns null when nothing warrants attention — the Home screen
 * renders no banner in that case.
 */
export function derivePriorityAlert(
  enrollments: CourseEnrollment[],
  sprints: CourseSprint[],
  tasks: MyTask[],
  now: Date,
): PriorityAlert | null {
  const pending = enrollments.find(
    (enrollment): enrollment is CourseEnrollment & { membership: Extract<TeamMembership, { status: "pending" }> } =>
      enrollment.membership.status === "pending",
  );
  if (pending) {
    return {
      id: `pending:${pending.courseId}`,
      message: `${pending.courseCode}: Yêu cầu tham gia ${pending.membership.teamName} đang chờ Leader duyệt.`,
      href: null,
      tone: "warning",
    };
  }

  const closingSoon = enrollments.find((enrollment) => {
    if (enrollment.membership.status !== "none" || !enrollment.teamFormation.registrationDeadline) {
      return false;
    }
    return daysUntil(enrollment.teamFormation.registrationDeadline, now) <= 3;
  });
  if (closingSoon?.teamFormation.registrationDeadline) {
    const days = daysUntil(closingSoon.teamFormation.registrationDeadline, now);
    return {
      id: `closing:${closingSoon.courseId}`,
      message: `Môn ${closingSoon.courseName}: Còn ${days} ngày để hoàn thành lập nhóm trước khi hệ thống phân ngẫu nhiên.`,
      href: null,
      hrefLabel: "Xem môn học",
      tone: "warning",
    };
  }

  const riskySprint = sprints.find((sprint) => sprint.health !== "on-track");
  if (riskySprint) {
    return {
      id: `sprint:${riskySprint.courseId}`,
      message: `Sprint ${riskySprint.sprintName} của ${riskySprint.courseCode} ${riskySprint.health === "late" ? "đang trễ tiến độ" : "có rủi ro trễ"} (${riskySprint.completedPoints}/${riskySprint.totalPoints} SP).`,
      href: null,
      hrefLabel: "Vào Board",
      tone: riskySprint.health === "late" ? "danger" : "warning",
    };
  }

  const overdueCount = tasks.filter((task) => isOverdue(task, now)).length;
  if (overdueCount > 0) {
    return {
      id: "overdue-tasks",
      message: `Bạn có ${overdueCount} nhiệm vụ quá hạn cần xử lý ngay.`,
      href: null,
      hrefLabel: "Xem nhiệm vụ quá hạn",
      tone: "danger",
    };
  }

  return null;
}

export function PriorityBanner({ alert }: { alert: PriorityAlert }) {
  return (
    <div
      role="status"
      className={`flex flex-col items-start justify-between gap-2 rounded-md border px-4 py-3 text-xs sm:flex-row sm:items-center ${
        alert.tone === "danger"
          ? "border-red-200 bg-red-50 text-red-900"
          : "border-amber-200/90 bg-amber-50/80 text-amber-900"
      }`}
    >
      <div className="flex items-center gap-2.5">
        <TriangleAlert
          className={`size-4 shrink-0 ${alert.tone === "danger" ? "text-red-600" : "text-amber-600"}`}
          aria-hidden
        />
        <p className="font-medium">{alert.message}</p>
      </div>
      {alert.hrefLabel ? (
        <span className="ml-4 shrink-0 font-semibold text-primary underline-offset-2">
          {alert.hrefLabel}
        </span>
      ) : null}
    </div>
  );
}