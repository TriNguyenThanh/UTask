import { useMemo } from "react";
import { DisabledAction } from "@/components/feedback/DisabledAction";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { PageSkeleton } from "@/components/feedback/PageSkeleton";
import { Button } from "@/components/ui/button";
import { useMyWorkOverview } from "@/features/my-work/queries";
import { currentSemesterEnrollments } from "@/features/my-work/currentSemester";
import { LatestCoursesSection } from "@/features/my-work/components/LatestCoursesSection";
import { MyTasksSection } from "@/features/my-work/components/MyTasksSection";
import { CourseSprintSection } from "@/features/my-work/components/CourseSprintSection";

function NoCoursesHome() {
  return (
    <div className="page-container px-4 pt-7 short:pt-4 sm:px-6 lg:px-8">
      <EmptyState
        title="Bạn chưa có môn học trong học kỳ hiện tại."
        description="Khi được đăng ký môn học, danh sách môn và nhiệm vụ đồ án sẽ xuất hiện tại đây. Liên hệ giảng viên hoặc phòng đào tạo nếu bạn cho rằng đây là nhầm lẫn."
        action={
          <DisabledAction
            variant="default"
            reason="Tham gia môn học sẽ khả dụng sau khi dữ liệu học kỳ sẵn sàng"
          >
            Xem danh sách môn học
          </DisabledAction>
        }
      />
    </div>
  );
}

export function MyWorkPage() {
  const overviewQuery = useMyWorkOverview();
  const now = useMemo(() => new Date(), []);

  const overview = overviewQuery.data;
  const enrollments = useMemo(() => currentSemesterEnrollments(overview), [overview]);

  if (overviewQuery.isPending) {
    return <PageSkeleton label="Đang tải bàn làm việc" />;
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

  if (!overview || enrollments.length === 0) {
    return <NoCoursesHome />;
  }

  return (
    <div className="page-container space-y-8 px-4 pt-7 short:pt-4 sm:px-6 lg:px-8">
      {/* Tiêu đề hiển thị nằm ở Top bar. */}
      <h1 className="sr-only">Bàn làm việc của tôi</h1>
      {overview.partial ? (
        <p role="status" className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900">
          Một phần dữ liệu chưa tải được.
        </p>
      ) : null}

      <MyTasksSection
        tasks={overview.tasks}
        courses={enrollments.map((enrollment) => ({
          id: enrollment.courseId,
          code: enrollment.courseCode,
        }))}
        now={now}
        isLoading={overviewQuery.isFetching && !overview}
        error={null}
        onRetry={() => void overviewQuery.refetch()}
      />

      <CourseSprintSection
        sprints={overview.sprints}
        now={now}
        isLoading={false}
      />

      <LatestCoursesSection enrollments={enrollments} />
    </div>
  );
}
