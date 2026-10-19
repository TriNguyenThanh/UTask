import { Search } from "lucide-react";

import { Input } from "@/components/ui/input";
import { STATUS_FILTERS, type StatusFilter } from "@/features/courses/lib/courseList";
import { cn } from "@/lib/utils";

export function CourseToolbar({
  query,
  onQueryChange,
  status,
  onStatusChange,
  counts,
  semesters,
  semester,
  onSemesterChange,
  shown,
  total,
}: Readonly<{
  query: string;
  onQueryChange: (value: string) => void;
  status: StatusFilter;
  onStatusChange: (value: StatusFilter) => void;
  counts: Record<StatusFilter, number>;
  semesters: readonly string[];
  semester: string;
  onSemesterChange: (value: string) => void;
  shown: number;
  total: number;
}>) {
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative min-w-0 flex-1 basis-64">
          <Search
            className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
            aria-hidden
          />
          <Input
            type="search"
            value={query}
            onChange={(event) => onQueryChange(event.target.value)}
            placeholder="Tìm theo mã hoặc tên môn học"
            aria-label="Tìm môn học theo mã hoặc tên"
            className="h-10 pl-9"
          />
        </div>
        {semesters.length > 1 ? (
          <select
            value={semester}
            onChange={(event) => onSemesterChange(event.target.value)}
            aria-label="Lọc theo học kỳ"
            className="h-10 rounded-md border bg-card px-3 text-sm"
          >
            <option value="all">Mọi học kỳ</option>
            {semesters.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        ) : null}
      </div>
      <div className="flex flex-wrap gap-2" role="group" aria-label="Lọc theo trạng thái nhóm">
        {STATUS_FILTERS.map((option) => (
          <button
            key={option.id}
            type="button"
            aria-pressed={status === option.id}
            onClick={() => onStatusChange(option.id)}
            className={cn(
              "rounded-full border px-3 py-1 text-xs font-semibold transition-colors",
              status === option.id
                ? "border-primary/30 bg-primary/10 text-primary"
                : "bg-card text-muted-foreground hover:text-foreground",
            )}
          >
            {option.label} · {counts[option.id]}
          </button>
        ))}
      </div>
      <p className="text-xs text-muted-foreground" aria-live="polite">
        Hiển thị{" "}
        <span className="font-semibold text-foreground">
          {shown}/{total}
        </span>{" "}
        môn học
      </p>
    </div>
  );
}
