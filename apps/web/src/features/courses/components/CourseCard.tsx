import { UserRound, Users } from "lucide-react";
import { Link } from "react-router-dom";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  courseCtaLabel,
  membershipBadge,
  membershipStateLabel,
} from "@/features/courses/lib/courseList";
import type { CourseEnrollment } from "@/features/my-work/types";

export function CourseCard({ enrollment }: Readonly<{ enrollment: CourseEnrollment }>) {
  const { membership } = enrollment;
  const badge = membershipBadge(membership);
  const href = `/courses/${enrollment.courseId}/team`;
  const StateIcon = membership.status === "none" ? UserRound : Users;
  return (
    <li className="flex flex-col gap-4 rounded-xl border bg-card p-4 transition-colors hover:border-primary/40">
      <div className="flex items-center justify-between gap-2">
        <Badge variant="secondary" className="font-mono font-semibold">
          {enrollment.courseCode}
        </Badge>
        <Badge variant="outline" className={badge.className}>
          {badge.label}
        </Badge>
      </div>
      <div className="min-w-0 flex-1">
        <h4 className="text-base font-semibold leading-snug">
          <Link to={href} className="hover:text-primary">
            {enrollment.courseName}
          </Link>
        </h4>
      </div>
      <p className="flex items-center gap-1.5 border-t pt-3 text-xs text-muted-foreground">
        <StateIcon className="size-3.5" aria-hidden />
        {membershipStateLabel(membership)}
      </p>
      <Button asChild variant={membership.status === "assigned" ? "default" : "outline"} className="w-full">
        <Link to={href}>{courseCtaLabel(membership)}</Link>
      </Button>
    </li>
  );
}
