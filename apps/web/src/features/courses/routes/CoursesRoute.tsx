import { sectionPanelClass } from "@/components/layout/sectionPanel";
import { ChevronDown, GraduationCap } from "lucide-react";
import { useState } from "react";

import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { PageSkeleton } from "@/components/feedback/PageSkeleton";
import { CourseCard } from "@/features/courses/components/CourseCard";
import { CourseToolbar } from "@/features/courses/components/CourseToolbar";
import {
  formatSemester,
  listSemesters,
  matchesFilters,
  summarizeCourses,
  type StatusFilter,
} from "@/features/courses/lib/courseList";
import { useMyWorkOverview } from "@/features/my-work/queries";
import { cn } from "@/lib/utils";

function NoCoursesState() {
  return (
    <EmptyState
      title="Bạn chưa có môn học nào"
      description="Danh sách môn học sẽ xuất hiện tại đây khi Giảng viên đăng ký bạn vào học phần đồ án. Nếu bạn cho rằng đây là nhầm lẫn, hãy liên hệ Giảng viên hướng dẫn hoặc phòng đào tạo để được bổ sung."
      action={
        <span className="inline-flex items-center gap-2 text-xs text-muted-foreground">
          <GraduationCap className="size-4" aria-hidden />
          Liên hệ giảng viên để được đăng ký môn học
        </span>
      }
    />
  );
}

export function Component() {
  const overviewQuery = useMyWorkOverview();
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<StatusFilter>("all");
  const [showPast, setShowPast] = useState(false);
  const enrollments = overviewQuery.data?.enrollments ?? [];

  if (overviewQuery.isPending) {
    return <PageSkeleton label="Đang tải danh sách môn học" />;
  }

  if (overviewQuery.isError) {
    return (
      <div className="page-container px-4 pt-7 short:pt-4 sm:px-6 lg:px-8">
        <ErrorState
          error={overviewQuery.error}
          onRetry={() => void overviewQuery.refetch()}
        />
      </div>
    );
  }

  const [latestSemester] = listSemesters(enrollments);
  // Mặc định chỉ học kỳ mới nhất; số liệu chip và danh sách cùng phạm vi này.
  const inScope = showPast
    ? enrollments
    : enrollments.filter((enrollment) => enrollment.semester === latestSemester);
  const counts = summarizeCourses(inScope);
  const visible = inScope.filter((enrollment) => matchesFilters(enrollment, query, status));
  const hasPast = listSemesters(enrollments).length > 1;

  return (
    <div className="page-container space-y-6 px-4 pt-7 short:pt-4 sm:px-6 lg:px-8">
      {/* Tiêu đề hiển thị nằm ở Top bar. */}
      <h1 className="sr-only">Môn học</h1>

      {enrollments.length === 0 ? (
        <NoCoursesState />
      ) : (
        <section aria-labelledby="course-list-heading" className={cn("space-y-5", sectionPanelClass)}>
          <h2 id="course-list-heading" className="text-xl font-medium tracking-tight">
            Môn học của bạn
          </h2>
          <CourseToolbar
            query={query}
            onQueryChange={setQuery}
            status={status}
            onStatusChange={setStatus}
            counts={counts}
          />
          {visible.length === 0 ? (
            <EmptyState
              title="Không có môn học phù hợp"
              description="Thử đổi từ khóa hoặc bỏ bớt bộ lọc."
            />
          ) : (
            <div className="space-y-8">
              {listSemesters(visible).map((semester) => (
                <section key={semester} aria-label={formatSemester(semester)} className="space-y-3">
                  <h3 className="text-base font-semibold text-foreground">
                    {formatSemester(semester)}
                  </h3>
                  <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4">
                    {visible
                      .filter((enrollment) => enrollment.semester === semester)
                      .map((enrollment) => (
                        <CourseCard key={enrollment.courseId} enrollment={enrollment} />
                      ))}
                  </ul>
                </section>
              ))}
            </div>
          )}
          {hasPast ? (
            <div className="flex justify-center border-t pt-4">
              <button
                type="button"
                aria-expanded={showPast}
                onClick={() => setShowPast((value) => !value)}
                className="inline-flex items-center gap-1.5 rounded-full px-4 py-2 text-sm font-medium text-primary transition-colors hover:bg-primary-subtle"
              >
                {showPast ? "Ẩn học kỳ cũ" : "Xem học kỳ cũ"}
                <ChevronDown
                  className={cn("size-4 transition-transform", showPast && "rotate-180")}
                  aria-hidden
                />
              </button>
            </div>
          ) : null}
        </section>
      )}
    </div>
  );
}

export default Component;
