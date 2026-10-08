import type { MyTask } from "@/features/my-work/types";

export type TaskBucketId = "today" | "week" | "overdue";

export function isDueToday(task: MyTask, now: Date): boolean {
  return new Date(task.dueAt).toDateString() === now.toDateString();
}

export function isOverdue(task: MyTask, now: Date): boolean {
  return new Date(task.dueAt) < now;
}

export function isDueWithinDays(task: MyTask, now: Date, days: number): boolean {
  const due = new Date(task.dueAt);
  const endOfWeek = new Date(now);
  endOfWeek.setUTCDate(endOfWeek.getUTCDate() + days);
  return due >= now && due <= endOfWeek;
}

export function tasksForBucket(tasks: MyTask[], bucket: TaskBucketId, now: Date): MyTask[] {
  switch (bucket) {
    case "today":
      return tasks.filter((task) => isDueToday(task, now));
    case "week":
      return tasks.filter((task) => isDueWithinDays(task, now, 7));
    case "overdue":
      return tasks.filter((task) => isOverdue(task, now));
  }
}