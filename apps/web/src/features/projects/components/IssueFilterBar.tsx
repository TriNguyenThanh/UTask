import { Search } from "lucide-react";
import { useMemo } from "react";

import { PRIORITY_LABELS } from "@/features/projects/issueMeta";
import {
  hasActiveFilters,
  type FlagFilter,
  type IssueFilters,
} from "@/features/projects/lib/issueFilters";
import type { Issue } from "@/features/projects/types";
import { cn } from "@/lib/utils";

const FLAG_LABELS: Record<FlagFilter, string> = {
  mine: "Chỉ việc của tôi",
  unassigned: "Chưa phân công",
  pr: "Có Pull Request",
  bug: "Chỉ lỗi (Bugs)",
  blocked: "Bị chặn",
  overdue: "Quá hạn",
};

const selectClass =
  "h-8 rounded-md border border-outline-subtle bg-card px-2 text-xs focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary";

/**
 * Search, flag chips, assignee and priority selects. State lives in the URL
 * (see `useIssueFilters`); this component is only the controls.
 */
export function IssueFilterBar({
  issues,
  filters,
  flags,
  onChange,
  onToggleFlag,
  onClear,
}: Readonly<{
  /** All issues of the project, to list the assignees that exist. */
  issues: readonly Issue[];
  filters: IssueFilters;
  /** Which chips to show; an instructor has no "mine". */
  flags: readonly FlagFilter[];
  onChange: (next: IssueFilters) => void;
  onToggleFlag: (flag: FlagFilter) => void;
  onClear: () => void;
}>) {
  const assignees = useMemo(() => {
    const byId = new Map<string, string>();
    for (const issue of issues) {
      if (issue.assignee) byId.set(issue.assignee.userId, issue.assignee.displayName);
    }
    return [...byId].map(([userId, displayName]) => ({ userId, displayName }));
  }, [issues]);

  return (
    <div className="flex flex-wrap items-center gap-2">
      <div className="relative">
        <Search
          className="absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
          aria-hidden
        />
        <input
          type="search"
          value={filters.search}
          onChange={(event) => onChange({ ...filters, search: event.target.value })}
          placeholder="Tìm kiếm issue..."
          aria-label="Tìm kiếm issue"
          className="h-8 w-44 rounded-md border border-outline-subtle bg-card pl-8 pr-3 text-xs placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary lg:w-52"
        />
      </div>
      {flags.map((flag) => {
        const active = filters.flags.includes(flag);
        return (
          <button
            key={flag}
            type="button"
            onClick={() => onToggleFlag(flag)}
            aria-pressed={active}
            className={cn(
              "inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50",
              active
                ? "bg-primary text-white"
                : "border border-outline-subtle bg-card text-muted-foreground hover:bg-muted hover:text-foreground",
            )}
          >
            {FLAG_LABELS[flag]}
          </button>
        );
      })}
      <select
        aria-label="Lọc theo người thực hiện"
        value={filters.assignee ?? ""}
        onChange={(event) => onChange({ ...filters, assignee: event.target.value || null })}
        className={selectClass}
      >
        <option value="">Mọi người thực hiện</option>
        {assignees.map((assignee) => (
          <option key={assignee.userId} value={assignee.userId}>
            {assignee.displayName}
          </option>
        ))}
      </select>
      <select
        aria-label="Lọc theo mức ưu tiên"
        value={filters.priority ?? ""}
        onChange={(event) =>
          onChange({
            ...filters,
            priority: (event.target.value || null) as IssueFilters["priority"],
          })
        }
        className={selectClass}
      >
        <option value="">Mọi mức ưu tiên</option>
        {(Object.keys(PRIORITY_LABELS) as Issue["priority"][]).map((priority) => (
          <option key={priority} value={priority}>
            {PRIORITY_LABELS[priority]}
          </option>
        ))}
      </select>
      {hasActiveFilters(filters) ? (
        <button
          type="button"
          onClick={onClear}
          className="text-xs font-semibold text-primary hover:underline focus-visible:underline"
        >
          Xóa bộ lọc
        </button>
      ) : null}
    </div>
  );
}
