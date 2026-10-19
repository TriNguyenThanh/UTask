import { BookOpen, CheckSquare2, ChevronRight, FolderKanban, GraduationCap } from "lucide-react";
import { NavLink, useParams } from "react-router-dom";

import { SidebarNavItem } from "@/components/navigation/SidebarNavItem";
import { useAuth } from "@/features/auth/AuthProvider";
import { canUseTeacherSpace } from "@/features/auth/utils";
import { currentSemesterEnrollments } from "@/features/my-work/currentSemester";
import { useMyWorkOverview } from "@/features/my-work/queries";
import type { CourseEnrollment, TeamMembership } from "@/features/my-work/types";
import { cn } from "@/lib/utils";

const membershipLabels: Record<TeamMembership["status"], string> = {
  none: "Chưa có nhóm",
  pending: "Chờ duyệt",
  assigned: "—",
};

/**
 * Sidebar destination per enrollment state:
 * - assigned + project provisioned → project backlog workspace
 * - none / pending / assigned-without-approved-project → course team page
 * - fallthrough → courses list
 */
function getSidebarCourseDestination(
  enrollment: CourseEnrollment,
): string {
  if (
    enrollment.membership.status === "assigned" &&
    enrollment.projectId !== null
  ) {
    return `/projects/${enrollment.projectId}/backlog`;
  }
  return `/courses/${enrollment.courseId}/team`;
}

function CourseNavItem({ enrollment }: { enrollment: CourseEnrollment }) {
  const { membership, courseCode, courseName, projectId } = enrollment;
  const { projectId: routeProjectId } = useParams();
  const to = getSidebarCourseDestination(enrollment);
  // A project course stays active across every module of that project.
  const isProjectActive =
    membership.status === "assigned" &&
    projectId !== null &&
    projectId === routeProjectId;

  return (
    <li>
      <NavLink
        to={to}
        className={({ isActive }) =>
          cn(
            "block rounded-md border p-2 transition-all hover:border-border/60 hover:bg-secondary/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary",
            isActive || isProjectActive
              ? "border-primary/30 bg-secondary"
              : "border-transparent",
          )
        }
      >
        <div className="flex items-center gap-2">
          <span
            className={cn(
              "size-2 shrink-0 rounded-full",
              membership.status === "assigned" && "bg-primary",
              membership.status === "pending" && "bg-amber-500",
              membership.status === "none" && "bg-neutral-300",
            )}
            aria-hidden
          />
          <span className="line-clamp-1 text-xs font-semibold text-foreground">
            {courseCode} — {courseName}
          </span>
        </div>
        <div className="mt-1 flex items-center gap-1.5 pl-4">
          <ChevronRight className="size-3.5 text-muted-foreground" aria-hidden />
          {membership.status === "assigned" ? (
            <span className="text-[11px] font-medium text-muted-foreground">
              {membership.role === "leader" ? "Leader" : "Member"} ·{" "}
              {membership.teamName}
            </span>
          ) : (
            <span className="text-[11px] font-medium text-muted-foreground">
              {membershipLabels[membership.status]}
            </span>
          )}
        </div>
      </NavLink>
    </li>
  );
}

export function AppSidebar({
  collapsed = false,
  courseListLabel,
}: {
  collapsed?: boolean;
  courseListLabel?: string;
}) {
  const { user } = useAuth();
  const { data: overview, isLoading } = useMyWorkOverview();
  const enrollments = currentSemesterEnrollments(overview);
  return (
    <div className="flex min-h-0 flex-1 flex-col gap-6 short:gap-3 overflow-y-auto overflow-x-hidden px-3 py-3 short:py-2">
      <nav aria-label="Điều hướng chính" className="space-y-0.5">
        <SidebarNavItem to="/my-work" icon={CheckSquare2} label="Trang chủ" collapsed={collapsed} />
        <SidebarNavItem to="/courses" icon={GraduationCap} label="Môn học" collapsed={collapsed} />
        <SidebarNavItem to="/projects" icon={FolderKanban} label="Dự án" collapsed={collapsed} />
        {canUseTeacherSpace(user) ? (
          <SidebarNavItem
            to="/teacher"
            icon={BookOpen}
            label="Không gian giảng viên"
            collapsed={collapsed}
          />
        ) : null}
      </nav>

      <div
        className={cn(
          "transition-[opacity,visibility] duration-200",
          collapsed && "invisible opacity-0",
        )}
        aria-hidden={collapsed}
      >
        <p className="flex items-center justify-between px-3 pb-1.5">
          <span className="whitespace-nowrap text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
            {courseListLabel ?? "Học kỳ hiện tại"}
          </span>
          <span className="text-[11px] font-medium text-muted-foreground">
            {overview?.semester ?? ""}
          </span>
        </p>
        {isLoading ? (
          <ul className="space-y-1" aria-label="Đang tải danh sách môn học">
            <li className="h-12 animate-pulse rounded-md bg-secondary" />
            <li className="h-12 animate-pulse rounded-md bg-secondary" />
          </ul>
        ) : (
          <ul className="space-y-1">
            {enrollments.map((enrollment) => (
              <CourseNavItem key={enrollment.courseId} enrollment={enrollment} />
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}