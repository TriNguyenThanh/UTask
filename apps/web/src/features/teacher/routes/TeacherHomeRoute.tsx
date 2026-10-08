import { useSearchParams } from "react-router-dom";

import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { PageSkeleton } from "@/components/feedback/PageSkeleton";
import { PageHeader } from "@/components/layout/PageHeader";
import { FilterSelect } from "@/features/teacher/components/FilterSelect";
import {
  CourseCard,
  DisabledAction,
  NoData,
  StatCard,
} from "@/features/teacher/components/shared";
import { useTeacherCourses } from "@/lib/query/teacherFlowHooks";

export function Component() {
  const courses = useTeacherCourses();
  const [searchParams, setSearchParams] = useSearchParams();
  const term = searchParams.get("term") ?? "all";

  if (courses.isPending) {
    return <PageSkeleton label="Đang tải bàn làm việc giảng viên" />;
  }
  if (courses.isError) {
    return (
      <div className="p-6">
        <ErrorState error={courses.error} onRetry={() => void courses.refetch()} />
      </div>
    );
  }

  const all = courses.data.courses;
  const terms = [...new Set(all.map((course) => course.term))];
  const visible = term === "all" ? all : all.filter((course) => course.term === term);

  const sum = (pick: (course: (typeof all)[number]) => number) =>
    visible.reduce((total, course) => total + pick(course), 0);

  function changeTerm(next: string) {
    const params = new URLSearchParams(searchParams);
    if (next === "all") params.delete("term");
    else params.set("term", next);
    setSearchParams(params);
  }

  return (
    <div className="space-y-6 p-4 md:p-6">
      <PageHeader
        title="Bàn làm việc giảng viên"
        description="Các lớp và nhóm bạn phụ trách."
      >
        <DisabledAction
          reason="Tạo lớp sẽ khả dụng sau khi quy trình tạo lớp được hoàn thiện."
          variant="default"
        >
          Tạo lớp
        </DisabledAction>
      </PageHeader>

      {all.length === 0 ? (
        <EmptyState
          title="Chưa phụ trách lớp nào"
          description="Khi bạn được phân công hoặc tạo lớp, lớp sẽ xuất hiện tại đây."
        />
      ) : (
        <>
          <FilterSelect
            label="Học kỳ"
            value={term}
            onChange={changeTerm}
            className="max-w-48"
            options={[
              { value: "all", label: "Tất cả học kỳ" },
              ...terms.map((value) => ({ value, label: value })),
            ]}
          />

          {visible.length === 0 ? (
            <EmptyState
              title="Không có lớp trong học kỳ này"
              description="Chọn học kỳ khác để xem các lớp còn lại."
            />
          ) : (
            <>
              <section aria-label="Chỉ số tổng quan" className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-3">
                <StatCard label="Lớp phụ trách" value={visible.length} />
                <StatCard label="Nhóm" value={sum((course) => course.teamCount)} />
                <StatCard
                  label="Chưa có nhóm"
                  value={sum((course) => course.studentsWithoutTeam)}
                  hint="Sinh viên, tính theo từng lớp"
                />
                <StatCard
                  label="Nhóm chưa có project"
                  value={sum((course) => course.teamsWithoutProject)}
                />
                <StatCard
                  label="Nhóm có tín hiệu cần chú ý"
                  value={sum((course) => course.teamsWithSignals)}
                  hint="Theo quy tắc cố định, xem ở mục Giám sát của từng lớp"
                  tone="attention"
                />
                <StatCard
                  label="Task quá hạn"
                  value={<NoData />}
                  hint="Chưa có dữ liệu hạn chót của task"
                />
              </section>

              <section aria-label="Danh sách lớp" className="space-y-3">
                <h2 className="text-lg font-semibold">Lớp phụ trách ({visible.length})</h2>
                <div className="grid gap-4 xl:grid-cols-2">
                  {visible.map((course) => (
                    <CourseCard key={course.courseId} course={course} />
                  ))}
                </div>
              </section>
            </>
          )}
        </>
      )}
    </div>
  );
}
