import { useMemo } from "react";
import { Link } from "react-router-dom";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { PageSkeleton } from "@/components/feedback/PageSkeleton";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/features/auth/AuthProvider";
import { useMyWorkGitHub, useMyWorkOverview } from "@/features/my-work/queries";
import { canOpenTeamWorkspace } from "@/features/my-work/permissions";
import type { CourseEnrollment, TeamMembership } from "@/features/my-work/types";
import { DashboardSummary } from "@/features/my-work/components/DashboardSummary";
import { PriorityBanner, derivePriorityAlert } from "@/features/my-work/components/PriorityBanner";
import { MyTasksSection } from "@/features/my-work/components/MyTasksSection";
import { CourseSprintSection } from "@/features/my-work/components/CourseSprintSection";
import { GitHubActivitySection } from "@/features/my-work/components/GitHubActivitySection";

function NoCoursesHome() {
  return (
    <div className="mx-auto max-w-6xl px-4 pt-7 sm:px-6 lg:px-8">
      <EmptyState
        title="Bạn chưa có môn học trong học kỳ hiện tại."
        description="Khi được đăng ký môn học, danh sách môn và nhiệm vụ đồ án sẽ xuất hiện tại đây. Liên hệ giảng viên hoặc phòng đào tạo nếu bạn cho rằng đây là nhầm lẫn."
        action={
          <Button disabled title="Tham gia môn học sẽ khả dụng sau khi dữ liệu học kỳ sẵn sàng">
            Xem danh sách môn học
          </Button>
        }
      />
    </div>
  );
}

function NoTeamCard({ enrollment }: { enrollment: CourseEnrollment & { membership: { status: "none" } } }) {
  const actions = [
    enrollment.teamFormation.mode === "self-select" ? "Tạo nhóm" : null,
    enrollment.teamFormation.mode === "join-code" ? "Tham gia bằng mã" : null,
    enrollment.teamFormation.mode === "instructor-assigned"
      ? "Chờ giảng viên phân nhóm"
      : "Tìm nhóm",
  ].filter((label): label is string => label !== null);

  return (
    <div className="rounded-md border border-dashed px-4 py-3 text-xs">
      <p className="font-semibold">
        {enrollment.courseName}: Bạn chưa tham gia nhóm nào.
      </p>
      <p className="mt-1 text-muted-foreground">
        Hành động khả dụng: {actions.join(" · ")}. Bạn vẫn có thể xem thông báo môn học, lịch chung
        và điểm danh.
      </p>
      <Link
        to={`/courses/${encodeURIComponent(enrollment.courseId)}/team`}
        className="mt-2 inline-flex font-semibold text-primary hover:underline"
      >
        Lập nhóm ngay →
      </Link>
    </div>
  );
}

function PendingCard({
  enrollment,
}: {
  enrollment: CourseEnrollment & { membership: Extract<TeamMembership, { status: "pending" }> };
}) {
  return (
    <div className="rounded-md border border-amber-200/90 bg-amber-50/80 px-4 py-3 text-xs text-amber-900">
      <p className="font-semibold">
        {enrollment.courseCode} · Chờ duyệt
      </p>
      <p className="mt-1">
        Yêu cầu tham gia <strong>{enrollment.membership.teamName}</strong> được gửi vào{" "}
        {new Date(enrollment.membership.requestedAt).toLocaleString("vi-VN")}. Board, backlog và
        repository của nhóm sẽ mở sau khi Leader duyệt.
      </p>
      <div className="mt-2 flex items-center gap-3">
        <Link
          to={`/courses/${encodeURIComponent(enrollment.courseId)}/team`}
          className="font-semibold text-primary hover:underline"
        >
          Theo dõi yêu cầu →
        </Link>
        <Button
          size="sm"
          variant="outline"
          disabled
          title="Hủy yêu cầu sẽ khả dụng ở slice Teams"
        >
          Hủy yêu cầu
        </Button>
      </div>
    </div>
  );
}

function githubSyncMessageFor(isError: boolean, state: string | undefined): string {
  if (isError) return "Không thể tải trạng thái đồng bộ GitHub";
  if (state === "connected") return "Đồng bộ GitHub đang hoạt động";
  if (state === "disconnected") return "Kết nối GitHub để đồng bộ hoạt động đồ án";
  return "Đang tải trạng thái đồng bộ GitHub";
}

export function MyWorkPage() {
  const { user } = useAuth();
  const overviewQuery = useMyWorkOverview();
  const githubQuery = useMyWorkGitHub();
  const now = useMemo(() => new Date(), []);

  const overview = overviewQuery.data;
  const enrollments = overview?.enrollments ?? [];

  const alert = useMemo(() => {
    if (!overview) {
      return null;
    }
    return derivePriorityAlert(overview.enrollments, overview.sprints, overview.tasks, now);
  }, [overview, now]);

  if (overviewQuery.isPending) {
    return <PageSkeleton label="Đang tải bàn làm việc" />;
  }

  if (overviewQuery.isError) {
    return (
      <div className="mx-auto max-w-6xl px-4 pt-7 sm:px-6 lg:px-8">
        <ErrorState
          error={overviewQuery.error}
          onRetry={() => void overviewQuery.refetch()}
        />
      </div>
    );
  }

  if (!overview) {
    return <NoCoursesHome />;
  }

  if (overview.enrollments.length === 0) {
    return <NoCoursesHome />;
  }

  const noTeamEnrollments = enrollments.filter(
    (enrollment): enrollment is CourseEnrollment & { membership: { status: "none" } } =>
      enrollment.membership.status === "none",
  );
  const pendingEnrollments = enrollments.filter(
    (enrollment): enrollment is CourseEnrollment & { membership: Extract<TeamMembership, { status: "pending" }> } =>
      enrollment.membership.status === "pending",
  );

  const firstName = user?.display_name.split(" ").at(-1) ?? "";
  const githubSyncMessage = githubSyncMessageFor(githubQuery.isError, githubQuery.data?.sync.state);

  return (
    <div className="mx-auto max-w-6xl space-y-8 px-4 pt-7 sm:px-6 lg:px-8">
      <div className="space-y-4">
        <div className="flex flex-col justify-between gap-2 border-b pb-4 md:flex-row md:items-baseline">
          <div>
            <h1 className="text-2xl font-bold tracking-tight">Bàn làm việc của tôi (My Work)</h1>
            <p className="mt-1 text-xs font-medium text-muted-foreground">
              {overview.semester} • Cập nhật lúc{" "}
              {new Date(overview.refreshedAt).toLocaleTimeString("vi-VN", {
                hour: "2-digit",
                minute: "2-digit",
              })}
              {firstName ? ` • Chào ${firstName}` : ""}
            </p>
          </div>
          <DashboardSummary summary={overview.summary} />
        </div>

        {alert ? <PriorityBanner alert={alert} /> : null}

        {noTeamEnrollments.map((enrollment) => (
          <NoTeamCard key={enrollment.courseId} enrollment={enrollment} />
        ))}
        {pendingEnrollments.map((enrollment) => (
          <PendingCard key={enrollment.courseId} enrollment={enrollment} />
        ))}
      </div>

      <MyTasksSection
        tasks={overview.tasks}
        courses={overview.enrollments.map((enrollment) => ({
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

      <GitHubActivitySection
        activity={githubQuery.data}
        now={now}
        isLoading={githubQuery.isPending}
        error={githubQuery.isError ? githubQuery.error : null}
        onRetry={() => void githubQuery.refetch()}
      />

      <footer className="flex flex-col items-center justify-between gap-4 border-t pt-6 text-xs text-muted-foreground sm:flex-row">
        <span>
          {githubSyncMessage}
        </span>
      </footer>
    </div>
  );
}