import type { CourseEnrollment, TeamMembership } from "@/features/my-work/types";

export type MembershipStatus = TeamMembership["status"];
export type StatusFilter = "all" | MembershipStatus;

export const STATUS_FILTERS: readonly { id: StatusFilter; label: string }[] = [
  { id: "all", label: "Tất cả" },
  { id: "none", label: "Cần lập nhóm" },
  { id: "pending", label: "Chờ duyệt" },
  { id: "assigned", label: "Đã có nhóm" },
];

export function membershipBadge(membership: TeamMembership): {
  label: string;
  className: string;
} {
  switch (membership.status) {
    case "none":
      return { label: "Cần lập nhóm", className: "border-amber-200 bg-amber-50 text-amber-900" };
    case "pending":
      return { label: "Chờ duyệt", className: "border-sky-200 bg-sky-50 text-sky-900" };
    case "assigned":
      // Vai trò thuộc về nhóm của riêng môn học này, không phải của tài khoản.
      return membership.role === "leader"
        ? { label: "Trưởng nhóm", className: "border-indigo-200 bg-indigo-50 text-indigo-900" }
        : { label: "Thành viên", className: "border-emerald-200 bg-emerald-50 text-emerald-900" };
  }
}

export function courseCtaLabel(membership: TeamMembership): string {
  if (membership.status === "none") return "Thành lập nhóm";
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
  semester: string,
): boolean {
  if (status !== "all" && enrollment.membership.status !== status) return false;
  if (semester !== "all" && enrollment.semester !== semester) return false;
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

/** Nhóm theo học kỳ, học kỳ mới nhất trước; giữ thứ tự gốc trong cùng học kỳ. */
export function groupBySemester(
  enrollments: readonly CourseEnrollment[],
): { semester: string; courses: CourseEnrollment[] }[] {
  return listSemesters(enrollments).map((semester) => ({
    semester,
    courses: enrollments.filter((enrollment) => enrollment.semester === semester),
  }));
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
  for (const enrollment of enrollments) counts[enrollment.membership.status] += 1;
  return counts;
}
