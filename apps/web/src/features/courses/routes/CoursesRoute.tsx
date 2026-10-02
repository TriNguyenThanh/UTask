import { GraduationCap, Users } from "lucide-react";
import { Link } from "react-router-dom";

import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { PageSkeleton } from "@/components/feedback/PageSkeleton";
import { Badge } from "@/components/ui/badge";
import { useMyWorkOverview } from "@/features/my-work/queries";
import type { CourseEnrollment, TeamMembership } from "@/features/my-work/types";

function membershipBadge(membership: TeamMembership): {
  label: string;
  className: string;
} {
  switch (membership.status) {
    case "none":
      return {
        label: "Cần lập nhóm",
        className: "border-amber-200 bg-amber-50 text-amber-900",
      };
    case "pending":
      return {
        label: "Chờ duyệt",
        className: "border-sky-200 bg-sky-50 text-sky-900",
      };
    case "assigned":
      return membership.role === "leader"
        ? {
            label: "Trưởng nhóm",
            className: "border-indigo-200 bg-indigo-50 text-indigo-900",
          }
        : {
            label: "Thành viên",
            className: "border-emerald-200 bg-emerald-50 text-emerald-900",
          };
  }
}

function courseCtaLabel(membership: TeamMembership): string {
  if (membership.status === "none") return "Thành lập nhóm";
  if (membership.status === "pending") return "Theo dõi yêu cầu";
  return "Xem nhóm & Đề tài";
}

function CourseRow({ enrollment }: { enrollment: CourseEnrollment }) {
  const badge = membershipBadge(enrollment.membership);
  return (
    <tr className="border-b transition-colors last:border-b-0 hover:bg-muted/40">
      <td className="px-3 py-3">
        <Badge variant="secondary" className="font-mono font-semibold">
          {enrollment.courseCode}
        </Badge>
      </td>
      <td className="px-3 py-3">
        <Link
          to={`/courses/${enrollment.courseId}/team`}
          className="font-medium hover:text-primary"
        >
          {enrollment.courseName}
        </Link>
      </td>
      <td className="hidden px-3 py-3 text-muted-foreground sm:table-cell">
        {enrollment.semester}
      </td>
      <td className="px-3 py-3">
        <Badge variant="outline" className={badge.className}>
          {badge.label}
        </Badge>
      </td>
      <td className="px-3 py-3 text-right">
        <Link
          to={`/courses/${enrollment.courseId}/team`}
          className="inline-flex items-center gap-1.5 text-xs font-semibold text-primary hover:underline"
        >
          {courseCtaLabel(enrollment.membership)}
        </Link>
      </td>
    </tr>
  );
}

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
  const enrollments = overviewQuery.data?.enrollments ?? [];

  if (overviewQuery.isPending) {
    return <PageSkeleton label="Đang tải danh sách môn học" />;
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

  return (
    <div className="mx-auto max-w-6xl space-y-6 px-4 pt-7 sm:px-6 lg:px-8">
      <div className="border-b pb-4">
        <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight">
          <GraduationCap className="size-6 text-primary" aria-hidden />
          Môn học của tôi
        </h1>
        <p className="mt-1 text-xs font-medium text-muted-foreground">
          Danh sách các học phần đồ án của bạn trong học kỳ hiện tại. Chọn một
          môn để xem nhóm và đề tài.
        </p>
      </div>

      {enrollments.length === 0 ? (
        <NoCoursesState />
      ) : (
        <div className="overflow-x-auto rounded-lg border bg-card">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b text-xs font-semibold text-muted-foreground">
                <th scope="col" className="px-3 py-2.5">Mã môn</th>
                <th scope="col" className="px-3 py-2.5">Tên môn học</th>
                <th scope="col" className="hidden px-3 py-2.5 sm:table-cell">Học kỳ</th>
                <th scope="col" className="px-3 py-2.5">Trạng thái nhóm</th>
                <th scope="col" className="px-3 py-2.5 text-right">Thao tác</th>
              </tr>
            </thead>
            <tbody>
              {enrollments.map((enrollment) => (
                <CourseRow key={enrollment.courseId} enrollment={enrollment} />
              ))}
            </tbody>
          </table>
        </div>
      )}

      <footer className="flex items-center gap-2 border-t pt-4 text-xs text-muted-foreground">
        <Users className="size-3.5" aria-hidden />
        Trạng thái nhóm được cập nhật tự động theo dữ liệu học kỳ.
      </footer>
    </div>
  );
}

export default Component;