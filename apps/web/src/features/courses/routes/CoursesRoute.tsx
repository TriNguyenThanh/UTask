import { GraduationCap } from "lucide-react";
import { useState } from "react";

import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { PageSkeleton } from "@/components/feedback/PageSkeleton";
import { CourseCard } from "@/features/courses/components/CourseCard";
import { CourseToolbar } from "@/features/courses/components/CourseToolbar";
import {
  groupBySemester,
  listSemesters,
  matchesFilters,
  summarizeCourses,
  type StatusFilter,
} from "@/features/courses/lib/courseList";
import { useMyWorkOverview } from "@/features/my-work/queries";

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
  const [semester, setSemester] = useState("all");
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

  const semesters = listSemesters(enrollments);
  // Số liệu và chip đếm theo học kỳ đang chọn, khớp với danh sách bên dưới.
  const inSemester = enrollments.filter(
    (enrollment) => semester === "all" || enrollment.semester === semester,
  );
  const counts = summarizeCourses(inSemester);
  const visible = inSemester.filter((enrollment) =>
    matchesFilters(enrollment, query, status, semester),
  );

  return (
    <div className="page-container space-y-6 px-4 pt-7 short:pt-4 sm:px-6 lg:px-8">
      {/* Tiêu đề hiển thị nằm ở Top bar. */}
      <h1 className="sr-only">Môn học</h1>

      {enrollments.length === 0 ? (
        <NoCoursesState />
      ) : (
        <section aria-labelledby="course-list-heading" className="space-y-4">
          <h2 id="course-list-heading" className="text-sm font-bold">
            Môn học của bạn
          </h2>
          <CourseToolbar
            query={query}
            onQueryChange={setQuery}
            status={status}
            onStatusChange={setStatus}
            counts={counts}
            semesters={semesters}
            semester={semester}
            onSemesterChange={setSemester}
            shown={visible.length}
            total={inSemester.length}
          />
          {visible.length === 0 ? (
            <EmptyState
              title="Không có môn học phù hợp"
              description="Thử đổi từ khóa hoặc bỏ bớt bộ lọc."
            />
          ) : (
            <div className="space-y-6">
              {groupBySemester(visible).map((group, index) => (
                <section
                  key={group.semester}
                  aria-labelledby={`semester-heading-${index}`}
                  className="space-y-3"
                >
                  <h3
                    id={`semester-heading-${index}`}
                    className="border-b pb-2 text-sm font-semibold"
                  >
                    {group.semester}
                  </h3>
                  <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
                    {group.courses.map((enrollment) => (
                      <CourseCard key={enrollment.courseId} enrollment={enrollment} />
                    ))}
                  </ul>
                </section>
              ))}
            </div>
          )}
        </section>
      )}
    </div>
  );
}

export default Component;
