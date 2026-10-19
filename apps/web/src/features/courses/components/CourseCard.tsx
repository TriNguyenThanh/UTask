import { ArrowUpRight, UserRound, Users } from "lucide-react";
import { Link } from "react-router-dom";

import { Badge } from "@/components/ui/badge";
import {
  courseCtaLabel,
  membershipBadge,
  membershipStateLabel,
} from "@/features/courses/lib/courseList";
import type { CourseEnrollment } from "@/features/my-work/types";

/** Thẻ môn học kiểu Google Classroom: dải tiêu đề, thân trống thoáng, chân thẻ chứa hành động. */
export function CourseCard({ enrollment }: Readonly<{ enrollment: CourseEnrollment }>) {
  const { membership } = enrollment;
  const badge = membershipBadge(membership);
  const href = `/courses/${enrollment.courseId}/team`;
  const StateIcon = membership.status === "none" ? UserRound : Users;
  return (
    <li className="group relative flex min-h-60 flex-col overflow-hidden rounded-xl border bg-card transition-shadow duration-200 hover:shadow-md">
      <div className="relative h-24 bg-primary-subtle px-4 pt-3.5">
        <h4 className="line-clamp-2 pr-14 text-lg font-medium leading-snug text-foreground">
          <Link
            to={href}
            className="after:absolute after:inset-0 after:z-0 after:content-[''] hover:underline"
          >
            {enrollment.courseName}
          </Link>
        </h4>
        <p className="mt-1 text-xs font-semibold tracking-wide text-muted-foreground">
          {enrollment.courseCode} · {enrollment.semester}
        </p>
        <span
          className="absolute -bottom-6 right-4 grid size-14 place-items-center rounded-full bg-primary text-xl font-medium text-primary-foreground ring-4 ring-card"
          aria-hidden
        >
          {enrollment.courseCode.charAt(0)}
        </span>
      </div>
      <div className="flex-1 space-y-2 px-4 pb-3 pt-4">
        <Badge variant="outline" className={badge.className}>
          {badge.label}
        </Badge>
        <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <StateIcon className="size-3.5" aria-hidden />
          {membershipStateLabel(membership)}
        </p>
      </div>
      <div className="flex items-center justify-end border-t px-4 py-2.5">
        <Link
          to={href}
          className="relative z-10 inline-flex items-center gap-1 text-sm font-medium text-primary hover:underline"
        >
          {courseCtaLabel(membership)}
          <ArrowUpRight className="size-4" aria-hidden />
        </Link>
      </div>
    </li>
  );
}
