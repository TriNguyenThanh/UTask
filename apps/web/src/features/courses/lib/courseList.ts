import type { CourseEnrollment, TeamMembership } from "@/features/my-work/types";

export type MembershipStatus = TeamMembership["status"];
export type StatusFilter = "all" | MembershipStatus;

export const STATUS_FILTERS: readonly { id: StatusFilter; label: string }[] = [
  { id: "all", label: "Tất cả" },
  { id: "none", label: "Cần lập nhóm" },
  { id: "pending", label: "Chờ duyệt" },
  { id: "assigned", label: "Đã có nhóm" },
];

/**
 * Lớp đã đóng hoặc khóa lập nhóm: sinh viên chưa có nhóm không còn "cần lập nhóm"
 * và không còn nút thành lập nhóm.
 */
export function needsTeam(enrollment: Pick<CourseEnrollment, "membership" | "formationClosed">): boolean {
  return enrollment.membership.status === "none" && !enrollment.formationClosed;
}

export function membershipBadge(membership: TeamMembership, formationClosed = false): {
  label: string;
  className: string;
} {
  if (membership.status === "none" && formationClosed) {
    return { label: "Đã khóa lập nhóm", className: "border-border bg-muted text-muted-foreground" };
  }
  switch (membership.status) {
    case "none":
      return {
        label: "Cần lập nhóm",
        className: "border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300",
      };
    case "pending":
      return {
        label: "Chờ duyệt",
        className: "border-sky-500/30 bg-sky-500/10 text-sky-700 dark:text-sky-300",
      };
    case "assigned":
      // Vai trò thuộc về nhóm của riêng môn học này, không phải của tài khoản.
      return membership.role === "leader"
        ? {
            label: "Trưởng nhóm",
            className: "border-indigo-500/30 bg-indigo-500/10 text-indigo-700 dark:text-indigo-300",
          }
        : {
            label: "Thành viên",
            className: "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
          };
  }
}

export function courseCtaLabel(membership: TeamMembership, formationClosed = false): string {
  if (membership.status === "none") return formationClosed ? "Xem lớp" : "Thành lập nhóm";
  if (membership.status === "pending") return "Theo dõi yêu cầu";
  return "Xem nhóm & Đề tài";
}

export function membershipStateLabel(membership: TeamMembership): string {
  if (membership.status === "none") return "Chưa có nhóm";
  if (membership.status === "pending") return "Đang chờ duyệt";
  return "Đã có nhóm";
}

export function matchesFilters(
  enrollment: CourseEnrollment,
  query: string,
  status: StatusFilter,
): boolean {
  if (status === "none" ? !needsTeam(enrollment) : status !== "all" && enrollment.membership.status !== status) {
    return false;
  }
  const needle = query.trim().toLowerCase();
  if (!needle) return true;
  return `${enrollment.courseCode} ${enrollment.courseName}`.toLowerCase().includes(needle);
}

/** "HK2 2025–2026" → năm bắt đầu * 10 + học kỳ; nhãn lạ xếp cuối. */
function semesterRank(label: string): number {
  const match = /HK(\d)\s+(\d{4})/.exec(label);
  return match ? Number(match[2]) * 10 + Number(match[1]) : -1;
}

/** Mới nhất trước. */
export function compareSemesterDesc(a: string, b: string): number {
  return semesterRank(b) - semesterRank(a);
}

export function listSemesters(enrollments: readonly CourseEnrollment[]): string[] {
  return [...new Set(enrollments.map((enrollment) => enrollment.semester))].sort(compareSemesterDesc);
}

/** "HK1 2026–2027" → "Học kỳ 1 · 2026–2027"; nhãn lạ giữ nguyên. */
export function formatSemester(label: string): string {
  const match = /^HK(\d)\s+(.+)$/.exec(label);
  return match ? `Học kỳ ${match[1]} · ${match[2]}` : label;
}

/**
 * Số liệu tổng quan, đều tính từ danh sách môn học. Yêu cầu đang chờ duyệt
 * chỉ tính vào `total` và `pending`: chưa là "đã có nhóm" và cũng không còn
 * là "cần lập nhóm" vì sinh viên đã gửi yêu cầu.
 */
export function summarizeCourses(enrollments: readonly CourseEnrollment[]): Record<StatusFilter, number> {
  const counts: Record<StatusFilter, number> = {
    all: enrollments.length,
    none: 0,
    pending: 0,
    assigned: 0,
  };
  for (const enrollment of enrollments) {
    if (enrollment.membership.status !== "none" || needsTeam(enrollment)) counts[enrollment.membership.status] += 1;
  }
  return counts;
}
