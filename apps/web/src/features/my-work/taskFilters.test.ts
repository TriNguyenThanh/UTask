import { describe, expect, it } from "vitest";

import { tasksForBucket } from "@/features/my-work/taskFilters";
import type { MyTask } from "@/features/my-work/types";

const NOW = new Date("2026-10-20T08:00:00");
const task = (id: string, status: MyTask["status"], dueAt: string | null): MyTask => ({
  id,
  issueKey: id,
  title: id,
  courseId: "c",
  courseCode: "C",
  projectName: "P",
  projectId: "p",
  priority: "low",
  status,
  dueAt,
});

describe("tasksForBucket", () => {
  const tasks = [
    task("undated-open", "todo", null),
    task("undated-done", "done", null),
    task("late", "todo", "2026-10-01T23:59:00"),
    task("today", "todo", "2026-10-20T23:59:00"),
  ];

  it("undated lists open tasks without a deadline only", () => {
    expect(tasksForBucket(tasks, "undated", NOW).map((row) => row.id)).toEqual(["undated-open"]);
  });

  it("never counts a task without a deadline as due or overdue", () => {
    expect(tasksForBucket(tasks, "overdue", NOW).map((row) => row.id)).toEqual(["late"]);
    expect(tasksForBucket(tasks, "today", NOW).map((row) => row.id)).toEqual(["today"]);
    expect(tasksForBucket(tasks, "week", NOW).map((row) => row.id)).toEqual(["today"]);
  });
});
