import {
  Bell,
  CheckSquare2,
  ChevronRight,
  FolderKanban,
  GraduationCap,
  QrCode,
  Settings,
  Users,
} from "lucide-react";
import { NavLink, useParams } from "react-router-dom";

import { Badge } from "@/components/ui/badge";
import { useMyWorkOverview } from "@/features/my-work/queries";
import type { CourseEnrollment, TeamMembership } from "@/features/my-work/types";
import { useNotifications } from "@/lib/query/studentFlowHooks";
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

export function AppSidebar({ courseListLabel }: { courseListLabel?: string }) {
  const { data: overview, isLoading } = useMyWorkOverview();
  const enrollments = overview?.enrollments ?? [];
  const { data: notifications } = useNotifications();
  const unreadCount = notifications?.filter((item) => !item.read).length ?? 0;
  return (
    <div className="flex min-h-0 flex-1 flex-col gap-6 overflow-y-auto py-3">
      <nav aria-label="Điều hướng chính" className="space-y-0.5">
        <NavLink
          to="/my-work"
          className={({ isActive }) =>
            cn(
              "relative flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
              isActive
                ? "bg-accent font-semibold text-accent-foreground"
                : "text-muted-foreground hover:bg-secondary hover:text-foreground",
            )
          }
        >
          {({ isActive }) => (
            <>
              {isActive ? (
                <span
                  className="absolute inset-y-1.5 left-0 w-[2.5px] rounded-r bg-primary"
                  aria-hidden
                />
              ) : null}
              <CheckSquare2 className="size-4" aria-hidden />
              Trang chủ
            </>
          )}
        </NavLink>
        <NavLink
          to="/courses"
          className={({ isActive }) =>
            cn(
              "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
              isActive
                ? "bg-accent font-semibold text-accent-foreground"
                : "text-muted-foreground hover:bg-secondary hover:text-foreground",
            )
          }
        >
          <GraduationCap className="size-4" aria-hidden />
          Môn học
        </NavLink>
        <NavLink
          to="/projects"
          className={({ isActive }) =>
            cn(
              "relative flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
              isActive
                ? "bg-accent font-semibold text-accent-foreground"
                : "text-muted-foreground hover:bg-secondary hover:text-foreground",
            )
          }
        >
          {({ isActive }) => (
            <>
              {isActive ? (
                <span
                  className="absolute inset-y-1.5 left-0 w-[2.5px] rounded-r bg-primary"
                  aria-hidden
                />
              ) : null}
              <FolderKanban className="size-4" aria-hidden />
              Dự án
            </>
          )}
        </NavLink>
        <NavLink
          to="/settings/profile"
          className={({ isActive }) =>
            cn(
              "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
              isActive
                ? "bg-accent font-semibold text-accent-foreground"
                : "text-muted-foreground hover:bg-secondary hover:text-foreground",
            )
          }
        >
          <Settings className="size-4" aria-hidden />
          Cài đặt
        </NavLink>
        <NavLink
          to="/notifications"
          className="flex items-center justify-between rounded-md px-3 py-2 text-sm font-medium text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
        >
          <span className="flex items-center gap-3">
            <Bell className="size-4" aria-hidden />
            Thông báo
          </span>
          {unreadCount > 0 ? (
            <Badge className="size-5 justify-center rounded-full px-0 text-[11px]">
              {unreadCount}
            </Badge>
          ) : null}
        </NavLink>
      </nav>

      <div>
        <p className="flex items-center justify-between px-3 pb-1.5">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
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

      <div>
        <p className="px-3 pb-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
          Tiện ích nhanh
        </p>
        <nav aria-label="Tiện ích nhanh" className="space-y-0.5">
          <span
            className="flex cursor-not-allowed items-center gap-3 rounded-md px-3 py-1.5 text-xs font-medium text-muted-foreground/70"
            title="GitHub Sync sẽ khả dụng ở slice sau"
          >
            <Users className="size-4" aria-hidden />
            GitHub Sync
          </span>
          <span className="flex cursor-not-allowed items-center gap-3 rounded-md px-3 py-1.5 text-xs font-medium text-muted-foreground/70">
            <QrCode className="size-4" aria-hidden />
            Điểm danh QR
          </span>
        </nav>
      </div>
    </div>
  );
}