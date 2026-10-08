import { useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { NavLink, Outlet, useParams } from "react-router-dom";

import { PageSkeleton } from "@/components/feedback/PageSkeleton";
import { Breadcrumbs } from "@/components/navigation/Breadcrumbs";
import { Badge } from "@/components/ui/badge";
import { useAuth } from "@/features/auth/AuthProvider";
import { CopyJoinCodeButton } from "@/features/teacher/components/JoinCode";
import {
  TeacherQueryError,
  courseLabel,
  isCourseUnavailable,
} from "@/features/teacher/components/shared";
import { teacherKeys, useTeacherCourse } from "@/lib/query/teacherFlowHooks";
import { cn } from "@/lib/utils";

type TabCount = "studentCount" | "teamCount";

const tabs: { label: string; to: string; end: boolean; count?: TabCount }[] = [
  { label: "Tổng quan", to: ".", end: true },
  { label: "Sinh viên", to: "students", end: false, count: "studentCount" },
  { label: "Nhóm", to: "teams", end: false, count: "teamCount" },
  { label: "Giám sát", to: "oversight", end: false },
  { label: "Cài đặt", to: "settings", end: false },
];

/**
 * Shell for one class: loads the class once, authorizes the whole subtree
 * (the server answers 404 for a class the teacher does not manage) and
 * provides header, breadcrumb and tabs. Tabs are real routes so every one of
 * them can be opened, refreshed and shared as a URL.
 */
export function Component() {
  const { courseId = "" } = useParams();
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const course = useTeacherCourse(courseId);
  const unavailable = isCourseUnavailable(course.error);

  // Access lost (or never granted): drop everything cached for this class so
  // its students and teams cannot be shown again, and refresh the class list.
  useEffect(() => {
    if (!unavailable || !user) return;
    const courseKey = teacherKeys.course(user.id, courseId);
    queryClient.removeQueries({
      queryKey: courseKey,
      predicate: (query) => query.queryKey.length > courseKey.length,
    });
    void queryClient.invalidateQueries({ queryKey: teacherKeys.courses(user.id), exact: true });
  }, [unavailable, user, courseId, queryClient]);

  if (course.isPending) {
    return <PageSkeleton label="Đang tải lớp học" />;
  }
  if (course.isError) {
    return (
      <div className="p-4 md:p-6">
        <TeacherQueryError error={course.error} onRetry={() => void course.refetch()} />
      </div>
    );
  }

  const detail = course.data;

  return (
    <div className="flex flex-col">
      <div className="border-b bg-background px-4 pt-4 md:px-6">
        <Breadcrumbs
          items={[
            { label: "Trang chủ", to: "/teacher" },
            { label: "Lớp phụ trách", to: "/teacher/courses" },
            { label: detail.name },
          ]}
        />
        <div className="mt-3 flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-2xl font-bold tracking-tight">{detail.name}</h1>
              <Badge variant="secondary" className="font-mono">
                {courseLabel(detail)}
              </Badge>
            </div>
            <p className="mt-1 text-sm text-muted-foreground">
              {detail.term} • {detail.studentCount} sinh viên • {detail.teamCount} nhóm
            </p>
            <p className="text-sm text-muted-foreground">
              Giảng viên: {detail.instructors.map((entry) => entry.name).join(", ")}
            </p>
          </div>
          {detail.joinCode ? (
            <div className="flex shrink-0 items-center gap-2 rounded-md border bg-muted/50 px-3 py-1.5">
              <span className="text-xs text-muted-foreground">Mã tham gia</span>
              <span className="font-mono text-sm font-semibold">{detail.joinCode}</span>
              <CopyJoinCodeButton code={detail.joinCode} />
            </div>
          ) : null}
        </div>

        <nav aria-label="Các mục của lớp" className="mt-4 flex gap-6 overflow-x-auto">
          {tabs.map((tab) => (
            <NavLink
              key={tab.label}
              to={tab.to}
              end={tab.end}
              className={({ isActive }) =>
                cn(
                  "whitespace-nowrap border-b-2 pb-2 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:text-foreground",
                  isActive
                    ? "border-primary font-bold text-foreground"
                    : "border-transparent text-muted-foreground hover:text-foreground",
                )
              }
            >
              {tab.label}
              {tab.count ? " " : null}
              {tab.count ? (
                <span className="ml-1 rounded-full bg-primary-subtle px-1.5 py-0.5 text-[11px] font-semibold text-accent-foreground">
                  {detail[tab.count]}
                </span>
              ) : null}
            </NavLink>
          ))}
        </nav>
      </div>

      <div className="p-4 md:p-6">
        <Outlet context={detail} />
      </div>
    </div>
  );
}
