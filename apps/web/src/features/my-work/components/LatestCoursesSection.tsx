import { sectionPanelClass } from "@/components/layout/sectionPanel";
import { Link } from "react-router-dom";

import { Badge } from "@/components/ui/badge";
import { membershipBadge } from "@/features/courses/lib/courseList";
import type { CourseEnrollment } from "@/features/my-work/types";

/** Số môn tối đa hiển thị ở Trang chủ; còn lại xem ở trang Môn học. */
const LATEST_COURSE_LIMIT = 4;

/** Các môn của học kỳ mới nhất, dạng danh sách gọn. */
export function LatestCoursesSection({
  enrollments,
}: Readonly<{ enrollments: readonly CourseEnrollment[] }>) {
  const shown = enrollments.slice(0, LATEST_COURSE_LIMIT);
  return (
    <section aria-labelledby="latest-courses-heading" className={`space-y-3 ${sectionPanelClass}`}>
      <div className="flex items-center justify-between gap-3">
        <h2 id="latest-courses-heading" className="text-lg font-bold tracking-tight">
          Môn học
        </h2>
        <Link to="/courses" className="text-xs font-semibold text-primary hover:underline">
          Xem tất cả
        </Link>
      </div>
      <ul className="divide-y rounded-lg border bg-card">
        {shown.map((enrollment) => {
          const badge = membershipBadge(enrollment.membership);
          return (
            <li key={enrollment.courseId} className="flex items-center gap-3 px-4 py-3">
              <Badge variant="secondary" className="shrink-0 font-mono font-semibold">
                {enrollment.courseCode}
              </Badge>
              <Link
                to={`/courses/${encodeURIComponent(enrollment.courseId)}/team`}
                className="min-w-0 flex-1 truncate text-sm font-medium hover:text-primary"
              >
                {enrollment.courseName}
              </Link>
              <Badge variant="outline" className={badge.className}>
                {badge.label}
              </Badge>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
