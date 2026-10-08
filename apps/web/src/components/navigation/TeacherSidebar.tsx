import { Bell, BookOpen, GraduationCap, Home, Settings } from "lucide-react";
import { NavLink, useMatch } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/features/auth/AuthProvider";
import { isStudentAccount } from "@/features/auth/utils";
import { courseLabel } from "@/features/teacher/components/shared";
import { useTeacherCourses } from "@/lib/query/teacherFlowHooks";
import { cn } from "@/lib/utils";

const COURSE_SECTIONS = [
  { label: "Tổng quan", to: "", end: true },
  { label: "Sinh viên", to: "/students", end: false },
  { label: "Nhóm", to: "/teams", end: false },
  { label: "Giám sát", to: "/oversight", end: false },
] as const;

const itemClass = ({ isActive }: { isActive: boolean }) =>
  cn(
    "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
    isActive
      ? "bg-accent font-semibold text-accent-foreground"
      : "text-muted-foreground hover:bg-secondary hover:text-foreground",
  );

/**
 * Navigation for the Teacher space. It reads only Teacher data (the classes
 * this account is assigned to) — never the Student overview.
 */
export function TeacherSidebar() {
  const { user } = useAuth();
  const courses = useTeacherCourses();
  const openCourseId = useMatch("/teacher/courses/:courseId/*")?.params.courseId;

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-6 overflow-y-auto py-3">
      <nav aria-label="Điều hướng giảng viên" className="space-y-0.5">
        <NavLink to="/teacher" end className={itemClass}>
          <Home className="size-4" aria-hidden />
          Trang chủ
        </NavLink>
        <NavLink to="/teacher/courses" end className={itemClass}>
          <BookOpen className="size-4" aria-hidden />
          Lớp phụ trách
        </NavLink>
        <NavLink to="/notifications" className={itemClass}>
          <Bell className="size-4" aria-hidden />
          Thông báo
        </NavLink>
        <NavLink to="/settings/profile" className={itemClass}>
          <Settings className="size-4" aria-hidden />
          Cài đặt tài khoản
        </NavLink>
        {isStudentAccount(user) ? (
          <NavLink to="/my-work" className={itemClass}>
            <GraduationCap className="size-4" aria-hidden />
            Không gian sinh viên
          </NavLink>
        ) : null}
      </nav>

      <div>
        <p className="px-3 pb-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
          Lớp phụ trách
        </p>
        {courses.isPending ? (
          <ul className="space-y-1" role="status" aria-label="Đang tải danh sách lớp">
            <li><Skeleton className="h-10" /></li>
            <li><Skeleton className="h-10" /></li>
          </ul>
        ) : courses.isError ? (
          <div className="space-y-2 px-3 text-xs text-muted-foreground" role="alert">
            <p>Không tải được danh sách lớp.</p>
            <Button type="button" size="sm" variant="outline" onClick={() => void courses.refetch()}>
              Thử lại
            </Button>
          </div>
        ) : courses.data.courses.length === 0 ? (
          <p className="px-3 text-xs text-muted-foreground">Chưa phụ trách lớp nào.</p>
        ) : (
          <ul className="space-y-1">
            {courses.data.courses.map((course) => (
              <li key={course.courseId}>
                <NavLink
                  to={`/teacher/courses/${course.courseId}`}
                  className={({ isActive }) =>
                    cn(
                      "block rounded-md border p-2 transition-all hover:border-border/60 hover:bg-secondary/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary",
                      isActive ? "border-primary/30 bg-secondary" : "border-transparent",
                    )
                  }
                >
                  <span className="line-clamp-1 text-xs font-semibold text-foreground">
                    {courseLabel(course)} — {course.name}
                  </span>
                  <span className="mt-0.5 block text-[11px] font-medium text-muted-foreground">
                    {course.studentCount} sinh viên · {course.teamCount} nhóm
                  </span>
                </NavLink>
                {course.courseId === openCourseId ? (
                  <ul
                    aria-label={`Mục của ${courseLabel(course)}`}
                    className="ml-3 mt-1 space-y-0.5 border-l pl-2"
                  >
                    {COURSE_SECTIONS.map((section) => (
                      <li key={section.label}>
                        <NavLink
                          to={`/teacher/courses/${course.courseId}${section.to}`}
                          end={section.end}
                          className={({ isActive }) =>
                            cn(
                              "block rounded-md px-2 py-1.5 text-xs font-medium transition-colors",
                              isActive
                                ? "bg-accent font-semibold text-accent-foreground"
                                : "text-muted-foreground hover:bg-secondary hover:text-foreground",
                            )
                          }
                        >
                          {section.label}
                        </NavLink>
                      </li>
                    ))}
                  </ul>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
