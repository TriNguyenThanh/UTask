import { ClipboardList } from "lucide-react";
import { useMemo, useState } from "react";

import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { MyTask } from "@/features/my-work/types";
import { tasksForBucket, type TaskBucketId } from "@/features/my-work/taskFilters";
import { TaskRow } from "@/features/my-work/components/TaskRow";
import { cn } from "@/lib/utils";

const buckets: { id: TaskBucketId; label: string }[] = [
  { id: "today", label: "Hôm nay" },
  { id: "week", label: "Tuần này" },
  { id: "overdue", label: "Quá hạn" },
];

interface CourseOption {
  id: string;
  code: string;
}

function MyTasksSkeleton() {
  return (
    <div className="space-y-3" role="status" aria-label="Đang tải nhiệm vụ">
      <Skeleton className="h-14 w-full" />
      <Skeleton className="h-14 w-full" />
      <Skeleton className="h-14 w-full" />
    </div>
  );
}

export function MyTasksSection({
  tasks,
  courses,
  now,
  isLoading,
  error,
  onRetry,
}: {
  tasks: MyTask[];
  courses: CourseOption[];
  now: Date;
  isLoading: boolean;
  error: unknown;
  onRetry: () => void;
}) {
  const [bucket, setBucket] = useState<TaskBucketId>("today");
  const [courseFilter, setCourseFilter] = useState<string>("all");

  const visibleTasks = useMemo(() => {
    const inBucket = tasksForBucket(tasks, bucket, now);
    if (courseFilter === "all") {
      return inBucket;
    }
    return inBucket.filter((task) => task.courseId === courseFilter);
  }, [tasks, bucket, courseFilter, now]);

  const overdueCount = tasksForBucket(tasks, "overdue", now).length;

  return (
    <section id="my-tasks" aria-labelledby="my-tasks-title" className="space-y-3 scroll-mt-24">
      <div className="flex flex-col gap-2 border-b pb-2.5 sm:flex-row sm:items-center sm:justify-between">
        <h2 id="my-tasks-title" className="flex items-center gap-2 text-base font-bold">
          <ClipboardList className="size-5 text-primary" aria-hidden />
          Nhiệm vụ của tôi (My Tasks)
        </h2>
        <div className="flex items-center gap-2">
          {courses.length > 1 ? (
            <Select value={courseFilter} onValueChange={setCourseFilter}>
              <SelectTrigger
                size="sm"
                className="text-xs"
                aria-label="Lọc nhiệm vụ theo môn học"
              >
                <SelectValue placeholder="Tất cả môn học" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all" className="text-xs">Tất cả môn học</SelectItem>
                {courses.map((course) => (
                  <SelectItem key={course.id} value={course.id} className="text-xs">
                    {course.code}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          ) : null}
          <div
            className="flex items-center gap-1 rounded-md bg-secondary p-0.5 text-xs font-medium"
            role="tablist"
            aria-label="Phạm vi thời gian nhiệm vụ"
          >
            {buckets.map((item) => {
              const active = bucket === item.id;
              return (
                <button
                  key={item.id}
                  type="button"
                  role="tab"
                  aria-selected={active}
                  onClick={() => setBucket(item.id)}
                  className={cn(
                    "flex items-center gap-1 rounded px-3 py-1 transition-colors",
                    active
                      ? "bg-card font-semibold text-foreground"
                      : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  {item.id === "overdue" && overdueCount > 0 ? (
                    <span className="flex size-4 items-center justify-center rounded-full bg-red-100 text-[10px] font-bold text-red-700">
                      {overdueCount}
                    </span>
                  ) : null}
                  {item.label}
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {error ? (
        <ErrorState error={error} onRetry={onRetry} />
      ) : isLoading ? (
        <MyTasksSkeleton />
      ) : visibleTasks.length === 0 ? (
        <EmptyState
          title="Không có nhiệm vụ"
          description={
            bucket === "overdue"
              ? "Bạn không có nhiệm vụ nào quá hạn. Tiếp tục phát huy!"
              : bucket === "today"
                ? "Không có việc gì cần làm trong hôm nay. Xem tab 'Tuần này' để chuẩn bị trước."
                : "Không có nhiệm vụ nào trong 7 ngày tới."
          }
        />
      ) : (
        <ul className="divide-y border-y">
          {visibleTasks.map((task) => (
            <TaskRow key={task.id} task={task} now={now} />
          ))}
        </ul>
      )}
    </section>
  );
}