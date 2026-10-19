import { BookOpen, GraduationCap, Home } from "lucide-react";
import { NavLink, useMatch } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/features/auth/AuthProvider";
import { isStudentAccount } from "@/features/auth/utils";
import { courseLabel } from "@/features/teacher/components/shared";
import { SidebarNavItem } from "@/components/navigation/SidebarNavItem";
import { useTeacherCourses } from "@/lib/query/teacherFlowHooks";
import { cn } from "@/lib/utils";

const COURSE_SECTIONS = [
  { label: "Tổng quan", to: "", end: true },
  { label: "Sinh viên", to: "/students", end: false },
  { label: "Nhóm", to: "/teams", end: false },
  { label: "Giám sát", to: "/oversight", end: false },
] as const;



/**
 * Navigation for the Teacher space. It reads only Teacher data (the classes
 * this account is assigned to) — never the Student overview.
 */
export function TeacherSidebar({ collapsed = false }: { collapsed?: boolean }) {
  const { user } = useAuth();
  const courses = useTeacherCourses();
  const openCourseId = useMatch("/teacher/courses/:courseId/*")?.params.courseId;

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-6 short:gap-3 overflow-y-auto overflow-x-hidden px-3 py-3 short:py-2">
      <nav aria-label="Điều hướng giảng viên" className="space-y-0.5">
        <SidebarNavItem to="/teacher" end icon={Home} label="Trang chủ" collapsed={collapsed} />
        <SidebarNavItem
          to="/teacher/courses"
          end
          icon={BookOpen}
          label="Lớp phụ trách"
          collapsed={collapsed}
        />
        {isStudentAccount(user) ? (
          <SidebarNavItem
            to="/my-work"
            icon={GraduationCap}
            label="Không gian sinh viên"
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
        <p className="whitespace-nowrap px-3 pb-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
          Lớp phụ trách
        </p>
        <CourseNavList courses={courses} openCourseId={openCourseId} />
      </div>
    </div>
  );
}

function CourseNavList({
  courses,
  openCourseId,
}: Readonly<{ courses: ReturnType<typeof useTeacherCourses>; openCourseId: string | undefined }>) {
  if (courses.isPending) {
    return (
      <output className="block space-y-1" aria-label="Đang tải danh sách lớp">
        <Skeleton className="h-10" />
        <Skeleton className="h-10" />
      </output>
    );
  }
  if (courses.isError) {
    return (
      <div className="space-y-2 px-3 text-xs text-muted-foreground" role="alert">
        <p>Không tải được danh sách lớp.</p>
        <Button type="button" size="sm" variant="outline" onClick={() => void courses.refetch()}>
          Thử lại
        </Button>
      </div>
    );
  }
  if (courses.data.courses.length === 0) {
    return <p className="px-3 text-xs text-muted-foreground">Chưa phụ trách lớp nào.</p>;
  }
  return (
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
  );
}
