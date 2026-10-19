import type { CourseEnrollment, MyWorkOverview } from "@/features/my-work/types";

/**
 * Overview chứa cả môn của các học kỳ đã qua (để trang Môn học lọc theo học
 * kỳ). Trang chủ và sidebar chỉ làm việc với môn của học kỳ hiện tại.
 */
export function currentSemesterEnrollments(
  overview: Pick<MyWorkOverview, "semester" | "enrollments"> | undefined,
): CourseEnrollment[] {
  if (!overview) return [];
  return overview.enrollments.filter((enrollment) => enrollment.semester === overview.semester);
}
