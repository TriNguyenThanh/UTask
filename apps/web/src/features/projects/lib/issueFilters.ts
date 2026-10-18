import { useCallback, useMemo } from "react";
import { useSearchParams } from "react-router-dom";

import { isOverdue } from "@/features/projects/issueMeta";
import type { Issue } from "@/features/projects/types";

export type FlagFilter = "mine" | "pr" | "bug" | "unassigned" | "blocked" | "overdue";

const FLAGS: readonly FlagFilter[] = ["mine", "pr", "bug", "unassigned", "blocked", "overdue"];
const PRIORITIES: readonly Issue["priority"][] = ["high", "medium", "low"];

export interface IssueFilters {
  search: string;
  flags: readonly FlagFilter[];
  /** User id of the assignee, or null for any. */
  assignee: string | null;
  priority: Issue["priority"] | null;
  /** Epic id, or null for any. */
  epic: string | null;
}

export const EMPTY_FILTERS: IssueFilters = {
  search: "",
  flags: [],
  assignee: null,
  priority: null,
  epic: null,
};

export function hasActiveFilters(filters: IssueFilters): boolean {
  return (
    filters.search.trim() !== "" ||
    filters.flags.length > 0 ||
    filters.assignee !== null ||
    filters.priority !== null ||
    filters.epic !== null
  );
}

export function matchesFilters(issue: Issue, filters: IssueFilters, now: Date = new Date()): boolean {
  const flags = filters.flags;
  if (flags.includes("mine") && !issue.isMine) return false;
  if (flags.includes("pr") && !issue.hasPullRequest) return false;
  if (flags.includes("bug") && issue.type !== "bug") return false;
  if (flags.includes("unassigned") && issue.assignee !== null) return false;
  if (flags.includes("blocked") && !issue.blocked) return false;
  if (flags.includes("overdue") && !isOverdue(issue, now)) return false;
  if (filters.assignee !== null && issue.assignee?.userId !== filters.assignee) return false;
  if (filters.priority !== null && issue.priority !== filters.priority) return false;
  if (filters.epic !== null && issue.epicId !== filters.epic) return false;
  const needle = filters.search.trim().toLowerCase();
  if (needle && !`${issue.key} ${issue.title}`.toLowerCase().includes(needle)) return false;
  return true;
}

/** Keys owned by the filters; everything else in the query string (e.g. `issue`) is left alone. */
const FILTER_KEYS = ["q", "assignee", "priority", "epic", ...FLAGS] as const;

/**
 * Filters kept in the URL, so a reload or a shared link shows the same board.
 * Board and Backlog read the same keys, and writing them never touches `issue`.
 */
export function useIssueFilters() {
  const [searchParams, setSearchParams] = useSearchParams();

  const filters = useMemo<IssueFilters>(() => {
    const priority = searchParams.get("priority");
    return {
      search: searchParams.get("q") ?? "",
      flags: FLAGS.filter((flag) => searchParams.get(flag) === "1"),
      assignee: searchParams.get("assignee"),
      priority: PRIORITIES.find((candidate) => candidate === priority) ?? null,
      epic: searchParams.get("epic"),
    };
  }, [searchParams]);

  const setFilters = useCallback(
    (next: IssueFilters) => {
      setSearchParams(
        (current) => {
          const params = new URLSearchParams(current);
          for (const key of FILTER_KEYS) params.delete(key);
          if (next.search.trim() !== "") params.set("q", next.search);
          for (const flag of next.flags) params.set(flag, "1");
          if (next.assignee !== null) params.set("assignee", next.assignee);
          if (next.priority !== null) params.set("priority", next.priority);
          if (next.epic !== null) params.set("epic", next.epic);
          return params;
        },
        { replace: true, preventScrollReset: true },
      );
    },
    [setSearchParams],
  );

  const toggleFlag = useCallback(
    (flag: FlagFilter) => {
      setFilters({
        ...filters,
        flags: filters.flags.includes(flag)
          ? filters.flags.filter((item) => item !== flag)
          : [...filters.flags, flag],
      });
    },
    [filters, setFilters],
  );

  const clear = useCallback(() => setFilters(EMPTY_FILTERS), [setFilters]);

  return { filters, setFilters, toggleFlag, clear };
}
