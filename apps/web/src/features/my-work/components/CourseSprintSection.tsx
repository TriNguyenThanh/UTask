import { Timer } from "lucide-react";

import { EmptyState } from "@/components/feedback/EmptyState";
import { Skeleton } from "@/components/ui/skeleton";
import type { CourseSprint } from "@/features/my-work/types";
import { CourseSprintCard } from "@/features/my-work/components/CourseSprintCard";

export function CourseSprintSection({
  sprints,
  now,
  isLoading,
}: {
  sprints: CourseSprint[];
  now: Date;
  isLoading: boolean;
}) {
  return (
    <section aria-labelledby="sprint-title" className="space-y-3 pt-2">
      <div className="flex items-center justify-between border-b pb-2.5">
        <h2 id="sprint-title" className="flex items-center gap-2 text-base font-bold">
          <Timer className="size-5 text-primary" aria-hidden />
          Tiến độ Đồ án trong kỳ
        </h2>
      </div>

      {isLoading ? (
        <div className="space-y-3" role="status" aria-label="Đang tải tiến độ Sprint">
          <Skeleton className="h-20 w-full" />
          <Skeleton className="h-20 w-full" />
        </div>
      ) : sprints.length === 0 ? (
        <EmptyState
          title="Chưa có Sprint nào"
          description="Sprint sẽ xuất hiện sau khi bạn được phân vào nhóm đồ án của môn học."
        />
      ) : (
        <ul className="divide-y border-y">
          {sprints.map((sprint) => (
            <CourseSprintCard key={sprint.courseId} sprint={sprint} now={now} />
          ))}
        </ul>
      )}
    </section>
  );
}