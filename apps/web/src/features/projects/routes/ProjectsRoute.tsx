import {
  ArrowRight,
  Code,
  Flag,
  GraduationCap,
  KanbanSquare,
  ListTodo,
  Search,
  Settings,
  Users,
} from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import type { ProjectSummary } from "@/features/projects/types";
import { canManageProjectSettings } from "@/lib/permissions";
import { useProjects } from "@/lib/query/studentFlowHooks";
import { cn } from "@/lib/utils";

/* ------------------------------------------------------------------ */
/* Helpers                                                             */
/* ------------------------------------------------------------------ */

type ProjectTab = "current" | "archived";
type RoleFilter = "all" | "leader" | "member";

const roleFilterOptions: { id: RoleFilter; label: string }[] = [
  { id: "all", label: "Tất cả vai trò" },
  { id: "leader", label: "Tôi làm Trưởng nhóm" },
  { id: "member", label: "Thành viên" },
];

function matchesQuery(project: ProjectSummary, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  return (
    project.name.toLowerCase().includes(q) ||
    project.courseCode.toLowerCase().includes(q) ||
    project.projectKey.toLowerCase().includes(q)
  );
}

function formatDeadline(iso: string): string {
  return new Date(iso).toLocaleDateString("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

/* ------------------------------------------------------------------ */
/* Project card                                                        */
/* ------------------------------------------------------------------ */

function ProjectCard({ project }: { project: ProjectSummary }) {
  const sprint = project.sprint;
  const percent =
    sprint && sprint.totalPoints > 0
      ? Math.round((sprint.completedPoints / sprint.totalPoints) * 100)
      : 0;
  const backlogPath = `/projects/${project.projectId}/backlog`;
  // canManageProjectSettings chỉ đọc role; aiEnabled không liên quan quyền settings.
  const canManageSettings = canManageProjectSettings({
    role: project.role,
    aiEnabled: false,
  });

  return (
    <article className="rounded-xl border bg-card p-4 transition-colors hover:border-primary/40 md:p-6">
      {/* Header strip: course meta + role badge */}
      <header className="flex flex-wrap items-center justify-between gap-3 border-b pb-3">
        <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          <Badge className="bg-primary/10 font-bold text-primary hover:bg-primary/10">
            {project.courseCode}
          </Badge>
          <span className="font-semibold text-foreground">
            {project.courseName}
          </span>
          <span aria-hidden>•</span>
          <span className="inline-flex items-center gap-1">
            <Users className="size-3.5" aria-hidden />
            {project.teamName}
          </span>
          <span aria-hidden>•</span>
          <span className="inline-flex items-center gap-1">
            <GraduationCap className="size-3.5" aria-hidden />
            GVHD: {project.instructorName}
          </span>
        </div>
        {project.role === "leader" ? (
          <Badge className="bg-primary/10 font-semibold text-primary hover:bg-primary/10">
            Bạn là Trưởng nhóm
          </Badge>
        ) : (
          <Badge variant="secondary" className="font-semibold">
            Thành viên
          </Badge>
        )}
      </header>

      {/* Body: project key + name */}
      <div className="pt-3">
        <div className="flex flex-wrap items-center gap-3">
          <Badge className="bg-foreground font-mono font-bold tracking-wider text-background hover:bg-foreground">
            {project.projectKey}
          </Badge>
          <Link
            to={backlogPath}
            className="text-base font-bold leading-snug tracking-tight transition-colors hover:text-primary md:text-lg"
          >
            {project.name}
          </Link>
        </div>
      </div>

      {/* Sprint progress panel */}
      {sprint ? (
        <div className="my-3 rounded-lg border bg-muted/40 p-4">
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2 text-xs">
            <div className="flex flex-wrap items-center gap-2">
              <Flag className="size-4 shrink-0 text-primary" aria-hidden />
              <span className="font-bold">{sprint.name}</span>
              {sprint.deadline ? (
                <span className="text-muted-foreground">
                  (Hạn: {formatDeadline(sprint.deadline)})
                </span>
              ) : null}
            </div>
            <div className="flex items-center gap-2">
              <span className="font-bold text-primary">{percent}% hoàn thành</span>
              <span className="text-muted-foreground">
                • {sprint.completedPoints}/{sprint.totalPoints} Story Points
              </span>
            </div>
          </div>
          <div
            className="h-2 w-full overflow-hidden rounded-full border bg-card"
            role="progressbar"
            aria-valuenow={percent}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label={`Tiến độ ${sprint.name}`}
          >
            <div
              className="h-full rounded-full bg-primary transition-all"
              style={{ width: `${percent}%` }}
            />
          </div>
        </div>
      ) : (
        <p className="my-3 flex items-center gap-2 rounded-lg border border-dashed bg-muted/30 p-3 text-xs text-muted-foreground">
          <Flag className="size-4 shrink-0" aria-hidden />
          Chưa có Sprint đang hoạt động trong dự án này.
        </p>
      )}

      {/* Footer: repo info + action links */}
      <footer className="flex flex-wrap items-center justify-between gap-4 border-t pt-3">
        <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          {project.repository ? (
            <span className="inline-flex items-center gap-1.5 rounded border bg-background px-2.5 py-1 font-mono text-[11px] text-foreground">
              <Code className="size-3.5 text-muted-foreground" aria-hidden />
              {project.repository}
            </span>
          ) : null}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button asChild variant="outline" size="sm" className="h-8 text-xs">
            <Link to={backlogPath}>
              <ListTodo className="size-3.5" aria-hidden />
              Kế hoạch Backlog
            </Link>
          </Button>
          <Button asChild variant="outline" size="sm" className="h-8 text-xs">
            <Link to={`/projects/${project.projectId}/code`}>
              <Code className="size-3.5" aria-hidden />
              Mã nguồn GitHub
            </Link>
          </Button>
          {canManageSettings ? (
            <Button
              asChild
              variant="outline"
              size="icon-sm"
              aria-label="Cài đặt dự án"
              title="Cài đặt dự án"
            >
              <Link to={`/projects/${project.projectId}/settings`}>
                <Settings className="size-4" aria-hidden />
              </Link>
            </Button>
          ) : null}
          <Button asChild size="sm" className="h-8 text-xs font-bold">
            <Link to={`/projects/${project.projectId}/board`}>
              <KanbanSquare className="size-3.5" aria-hidden />
              Mở Jira Board
              <ArrowRight className="size-3.5" aria-hidden />
            </Link>
          </Button>
        </div>
      </footer>
    </article>
  );
}

/* ------------------------------------------------------------------ */
/* Loading skeleton                                                    */
/* ------------------------------------------------------------------ */

function ProjectsSkeleton() {
  return (
    <div
      className="mx-auto max-w-5xl space-y-6 p-4 md:p-6"
      role="status"
      aria-label="Đang tải danh sách dự án"
    >
      <div className="space-y-2">
        <Skeleton className="h-7 w-72" />
        <Skeleton className="h-4 w-full max-w-xl" />
      </div>
      <Skeleton className="h-9 w-64" />
      <div className="space-y-4">
        {[0, 1, 2].map((index) => (
          <div key={index} className="space-y-4 rounded-xl border bg-card p-6">
            <Skeleton className="h-4 w-1/2" />
            <Skeleton className="h-6 w-3/4" />
            <Skeleton className="h-16 w-full" />
          </div>
        ))}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Main route                                                          */
/* ------------------------------------------------------------------ */

export default function ProjectsRoute() {
  const [tab, setTab] = useState<ProjectTab>("current");
  const [roleFilter, setRoleFilter] = useState<RoleFilter>("all");
  const [query, setQuery] = useState("");
  const { data, isLoading, error, refetch } = useProjects();

  if (error) {
    return (
      <div className="p-6">
        <ErrorState error={error} onRetry={() => void refetch()} />
      </div>
    );
  }

  if (isLoading) {
    return <ProjectsSkeleton />;
  }

  const projects = data ?? [];
  const currentCount = projects.filter((project) => !project.archived).length;
  const archivedCount = projects.filter((project) => project.archived).length;

  const tabProjects = projects.filter((project) =>
    tab === "archived" ? project.archived : !project.archived,
  );
  const roleProjects =
    roleFilter === "all"
      ? tabProjects
      : tabProjects.filter((project) => project.role === roleFilter);
  const visible = query.trim()
    ? roleProjects.filter((project) => matchesQuery(project, query))
    : roleProjects;

  return (
    <div className="mx-auto max-w-5xl space-y-5 p-4 md:p-6">
      {/* Page title */}
      <div>
        <h1 className="text-xl font-bold tracking-tight md:text-2xl">
          Dự án Đồ án Môn học
        </h1>
        <p className="mt-1 max-w-3xl text-xs leading-relaxed text-muted-foreground md:text-sm">
          Không gian làm việc Jira Software của các đồ án môn học trong học kỳ.
          Theo dõi tiến độ Sprint và tích hợp mã nguồn Git theo thời gian thực.
        </p>
      </div>

      {/* Current / archived tabs */}
      <div
        className="flex items-center gap-6 border-b"
        role="tablist"
        aria-label="Phạm vi thời gian"
      >
        <button
          type="button"
          role="tab"
          aria-selected={tab === "current"}
          onClick={() => setTab("current")}
          className={cn(
            "flex items-center gap-2 border-b-2 pb-2.5 text-xs tracking-tight transition-colors",
            tab === "current"
              ? "border-primary font-bold text-primary"
              : "border-transparent font-medium text-muted-foreground hover:text-foreground",
          )}
        >
          Kỳ hiện tại
          <Badge
            variant="secondary"
            className="text-[11px] font-semibold"
            aria-label={`${currentCount} dự án`}
          >
            {currentCount}
          </Badge>
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === "archived"}
          onClick={() => setTab("archived")}
          className={cn(
            "flex items-center gap-2 border-b-2 pb-2.5 text-xs tracking-tight transition-colors",
            tab === "archived"
              ? "border-primary font-bold text-primary"
              : "border-transparent font-medium text-muted-foreground hover:text-foreground",
          )}
        >
          Đã lưu trữ
          <Badge
            variant="secondary"
            className="text-[11px] font-semibold"
            aria-label={`${archivedCount} dự án`}
          >
            {archivedCount}
          </Badge>
        </button>
      </div>

      {/* Search + role filter toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="relative w-full sm:w-72">
          <Search
            className="absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
            aria-hidden
          />
          <Input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Tìm kiếm dự án, mã key hoặc môn học..."
            aria-label="Tìm kiếm dự án theo tên, mã môn học hoặc project key"
            className="h-8 pl-8 text-xs"
          />
        </div>
        <div
          className="flex items-center rounded-lg border bg-card p-0.5 text-xs"
          role="group"
          aria-label="Lọc theo vai trò"
        >
          {roleFilterOptions.map((option) => (
            <button
              key={option.id}
              type="button"
              onClick={() => setRoleFilter(option.id)}
              aria-pressed={roleFilter === option.id}
              className={cn(
                "rounded px-2.5 py-1 font-semibold transition-colors",
                roleFilter === option.id
                  ? "bg-primary/10 text-primary"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>

      {/* Result count */}
      <p className="text-[11px] font-medium text-muted-foreground">
        Hiển thị{" "}
        <span className="font-bold text-foreground">
          {visible.length}/{tabProjects.length}
        </span>{" "}
        đồ án {tab === "current" ? "đang diễn ra" : "đã lưu trữ"}
      </p>

      {/* Card list / empty states */}
      {tabProjects.length === 0 ? (
        tab === "current" ? (
          <EmptyState
            title="Chưa có dự án đồ án"
            description="Bạn chưa thuộc nhóm nào có dự án Jira trong kỳ này. Hãy vào Môn học để tạo nhóm và nộp đề tài trước khi dùng workspace Jira."
            action={
              <Button asChild size="sm" variant="outline">
                <Link to="/courses">Xem môn học của tôi</Link>
              </Button>
            }
          />
        ) : (
          <EmptyState
            title="Chưa có dự án lưu trữ"
            description="Các đồ án đã nghiệm thu từ các học kỳ trước sẽ xuất hiện ở đây sau khi được lưu trữ."
          />
        )
      ) : roleProjects.length === 0 ? (
        <EmptyState
          title="Không có dự án với vai trò đã chọn"
          description={
            roleFilter === "leader"
              ? "Bạn không làm Trưởng nhóm ở dự án nào trong phạm vi này. Hãy chuyển sang 'Tất cả vai trò' để xem đầy đủ."
              : "Bạn không ở vai trò Thành viên ở dự án nào trong phạm vi này. Hãy chuyển sang 'Tất cả vai trò' để xem đầy đủ."
          }
          action={
            <Button
              size="sm"
              variant="outline"
              onClick={() => setRoleFilter("all")}
            >
              Xem tất cả vai trò
            </Button>
          }
        />
      ) : visible.length === 0 ? (
        <EmptyState
          title="Không tìm thấy dự án"
          description={`Không có dự án nào khớp với từ khóa "${query.trim()}". Thử từ khóa khác hoặc xóa tìm kiếm.`}
          action={
            <Button size="sm" variant="outline" onClick={() => setQuery("")}>
              Xóa tìm kiếm
            </Button>
          }
        />
      ) : (
        <div className="space-y-4">
          {visible.map((project) => (
            <ProjectCard key={project.projectId} project={project} />
          ))}
        </div>
      )}
    </div>
  );
}

export function Component() {
  return <ProjectsRoute />;
}