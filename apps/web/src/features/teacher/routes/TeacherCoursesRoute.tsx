import { useSearchParams } from "react-router-dom";

import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { PageSkeleton } from "@/components/feedback/PageSkeleton";
import { PageHeader } from "@/components/layout/PageHeader";
import { Input } from "@/components/ui/input";
import { FilterSelect } from "@/features/teacher/components/FilterSelect";
import { CourseCard, DisabledAction, courseLabel } from "@/features/teacher/components/shared";
import { useTeacherCourses } from "@/lib/query/teacherFlowHooks";

export function Component() {
  const courses = useTeacherCourses();
  const [searchParams, setSearchParams] = useSearchParams();
  const query = searchParams.get("q") ?? "";
  const term = searchParams.get("term") ?? "all";

  if (courses.isPending) {
    return <PageSkeleton label="Đang tải danh sách lớp" />;
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
  const needle = query.trim().toLowerCase();
  const visible = all.filter((course) => {
    if (term !== "all" && course.term !== term) return false;
    if (!needle) return true;
    return (
      course.name.toLowerCase().includes(needle) ||
      courseLabel(course).toLowerCase().includes(needle)
    );
  });

  function setParam(key: string, value: string, empty: string) {
    const params = new URLSearchParams(searchParams);
    if (value === empty) params.delete(key);
    else params.set(key, value);
    setSearchParams(params);
  }

  return (
    <div className="space-y-6 p-4 md:p-6">
      <PageHeader
        title="Lớp phụ trách"
        description="Các lớp bạn được phân công hoặc đã tạo."
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
          <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
            <div className="flex flex-1 flex-col gap-1 sm:max-w-sm">
              <label htmlFor="teacher-course-search" className="text-xs font-medium text-muted-foreground">
                Tìm lớp
              </label>
              <Input
                id="teacher-course-search"
                type="search"
                placeholder="Tên lớp hoặc mã môn"
                value={query}
                onChange={(event) => setParam("q", event.target.value, "")}
              />
            </div>
            <FilterSelect
              label="Học kỳ"
              value={term}
              onChange={(value) => setParam("term", value, "all")}
              className="sm:w-48"
              options={[
                { value: "all", label: "Tất cả học kỳ" },
                ...terms.map((value) => ({ value, label: value })),
              ]}
            />
          </div>

          {visible.length === 0 ? (
            <EmptyState
              title="Không có lớp khớp bộ lọc"
              description="Thử đổi từ khóa hoặc chọn học kỳ khác."
            />
          ) : (
            <div className="grid gap-4 xl:grid-cols-2">
              {visible.map((course) => (
                <CourseCard key={course.courseId} course={course} />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
