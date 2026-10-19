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
}: Readonly<{
  query: string;
  onQueryChange: (value: string) => void;
  status: StatusFilter;
  onStatusChange: (value: StatusFilter) => void;
  counts: Record<StatusFilter, number>;
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
            className="h-10 rounded-lg pl-9"
          />
        </div>
      </div>
      <div
        className="inline-flex max-w-full flex-wrap gap-1 rounded-xl bg-muted p-1"
        role="group"
        aria-label="Lọc theo trạng thái nhóm"
      >
        {STATUS_FILTERS.map((option) => (
          <button
            key={option.id}
            type="button"
            aria-pressed={status === option.id}
            onClick={() => onStatusChange(option.id)}
            className={cn(
              "rounded-lg px-3 py-1.5 text-xs font-semibold transition-all",
              status === option.id
                ? "bg-card text-primary shadow-sm"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            {option.label} · {counts[option.id]}
          </button>
        ))}
      </div>
    </div>
  );
}
