import { Hourglass } from "lucide-react";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";
import type { CourseSprint, SprintHealth } from "@/features/my-work/types";
import { cn } from "@/lib/utils";

const healthMeta: Record<SprintHealth, { label: string; dot: string; bar: string }> = {
  "on-track": { label: "Đúng tiến độ", dot: "bg-emerald-500", bar: "bg-primary" },
  "at-risk": { label: "Có rủi ro", dot: "bg-amber-500", bar: "bg-amber-500" },
  late: { label: "Trễ tiến độ", dot: "bg-red-500", bar: "bg-destructive" },
};

const DAY_MS = 86_400_000;

function daysUntil(iso: string, now: Date): number {
  return Math.ceil((new Date(iso).getTime() - now.getTime()) / DAY_MS);
}

export function CourseSprintCard({ sprint, now }: { sprint: CourseSprint; now: Date }) {
  const health = healthMeta[sprint.health];
  const daysLeft = daysUntil(sprint.deadline, now);
  // totalPoints 0 → 0%; clamp so fixture drift can never show >100%.
  const percent =
    sprint.totalPoints > 0
      ? Math.min(100, Math.max(0, Math.round((sprint.completedPoints / sprint.totalPoints) * 100)))
      : 0;

  return (
    <li className="px-2 py-4 transition-colors hover:bg-secondary/50">
      <div className="flex flex-col justify-between gap-4 md:flex-row md:items-center">
        <div className="min-w-0 md:w-1/3">
          <div className="flex items-center gap-2">
            <span className="text-xs font-bold">{sprint.courseName}</span>
            <span className="rounded border bg-secondary px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
              {sprint.semester}
            </span>
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <span className="font-medium text-foreground">{sprint.projectName}</span>
            <span aria-hidden>•</span>
            <span className="font-semibold text-primary">{sprint.sprintName}</span>
            <span aria-hidden>•</span>
            <span className="text-[11px]">
              {sprint.teamName} · {sprint.role === "leader" ? "Leader" : "Member"}
            </span>
          </div>
          <p className="mt-0.5 text-[11px] text-muted-foreground">GVHD: {sprint.instructorName}</p>
        </div>

        <div className="flex-1 md:max-w-md">
          <div className="mb-1.5 flex items-center justify-between text-xs">
            <span className="font-medium text-muted-foreground">Tiến độ Sprint</span>
            <span
              className={cn(
                "font-bold",
                sprint.health === "on-track" ? "text-primary" : health.bar.replace("bg-", "text-"),
              )}
            >
              {percent}% hoàn thành ({sprint.completedPoints}/{sprint.totalPoints} SP)
            </span>
          </div>
          <div
            className="h-2 w-full overflow-hidden rounded-full bg-secondary"
            role="progressbar"
            aria-valuenow={percent}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label={`Tiến độ ${sprint.sprintName} ${sprint.courseCode}`}
          >
            <div
              className={cn("h-full rounded-full transition-all", health.bar)}
              style={{ width: `${percent}%` }}
            />
          </div>
        </div>

        <div className="flex shrink-0 items-center justify-between gap-5 md:w-56 md:justify-end">
          <div className="text-right">
            <span className="flex items-center justify-end gap-1 text-xs font-semibold">
              <Hourglass
                className={cn(
                  "size-3.5",
                  daysLeft <= 2 ? "text-red-500" : daysLeft <= 5 ? "text-amber-500" : "text-muted-foreground",
                )}
                aria-hidden
              />
              {daysLeft < 0
                ? `Quá hạn ${Math.abs(daysLeft)} ngày`
                : `${daysLeft} ngày còn lại`}
            </span>
            <p className="mt-0.5 text-[11px] text-muted-foreground">
              Hạn chót: {new Date(sprint.deadline).toLocaleDateString("vi-VN")}
            </p>
            <p className="mt-0.5 flex items-center justify-end gap-1 text-[11px] font-medium">
              <span className={cn("size-1.5 rounded-full", health.dot)} aria-hidden />
              <span
                className={cn(
                  sprint.health === "on-track" && "text-emerald-700",
                  sprint.health === "at-risk" && "text-amber-700",
                  sprint.health === "late" && "text-red-700",
                )}
              >
                {health.label}
              </span>
            </p>
          </div>
          {sprint.projectId ? (
            <Button
              asChild
              size="sm"
              variant="outline"
              className="border-primary/30 bg-primary-subtle text-primary hover:bg-primary hover:text-primary-foreground"
            >
              <Link to={`/projects/${sprint.projectId}/board`}>
                Vào Board
              </Link>
            </Button>
          ) : (
            <Button
              size="sm"
              variant="outline"
              disabled
              className="border-primary/30"
              title="Workspace của nhóm chưa được khởi tạo"
            >
              Vào Board
            </Button>
          )}
        </div>
      </div>
    </li>
  );
}