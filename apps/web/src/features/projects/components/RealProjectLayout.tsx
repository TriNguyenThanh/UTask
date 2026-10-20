import { createContext, useContext, useMemo } from "react";
import { Link, Outlet, useParams } from "react-router-dom";

import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { ForbiddenPage } from "@/components/feedback/ForbiddenPage";
import { PageSkeleton } from "@/components/feedback/PageSkeleton";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Breadcrumbs } from "@/components/navigation/Breadcrumbs";
import { segmentedTabClass, segmentedTabsListClass } from "@/components/navigation/segmentedTabs";
import { ApiError } from "@/lib/api/errors";
import type { WorkProjectShell } from "@/lib/api/work/adapters";
import { useWorkProject } from "@/lib/query/workHooks";

export interface RealProjectContextValue {
  projectId: string;
  shell: WorkProjectShell;
}

const RealProjectContext = createContext<RealProjectContextValue | null>(null);

export function useRealProjectContext(): RealProjectContextValue {
  const ctx = useContext(RealProjectContext);
  if (!ctx) throw new Error("useRealProjectContext must be used inside RealProjectLayout");
  return ctx;
}

export function RealProjectLayout() {
  const { projectId = "" } = useParams();
  const query = useWorkProject(projectId);

  if (query.isPending) {
    return <PageSkeleton label="Đang tải dự án" />;
  }

  const error = query.error;
  if (error instanceof ApiError && error.status === 404) {
    return (
      <div className="p-6">
        <EmptyState
          title="Không tìm thấy dự án"
          description="Dự án không tồn tại hoặc bạn không có quyền truy cập."
          action={
            <Button asChild size="sm" variant="outline">
              <Link to="/projects">Về danh sách dự án</Link>
            </Button>
          }
        />
      </div>
    );
  }
  if (error instanceof ApiError && error.status === 403) {
    return <ForbiddenPage />;
  }
  if (error !== null) {
    return (
      <div className="p-6">
        <ErrorState error={error} onRetry={() => void query.refetch()} />
      </div>
    );
  }

  if (!query.data) {
    return <PageSkeleton label="Đang tải dự án" />;
  }

  return <RealProjectLayoutInner projectId={projectId} shell={query.data} />;
}

function RealProjectLayoutInner({
  projectId,
  shell,
}: {
  projectId: string;
  shell: WorkProjectShell;
}) {
  const contextValue = useMemo<RealProjectContextValue>(
    () => ({ projectId, shell }),
    [projectId, shell],
  );

  const { project } = shell;
  const isArchived = project.archived_at !== null;
  const isReadOnly = shell.myRole === null;

  // Build subtitle line (drop empty parts)
  const parts = [shell.classCode, shell.className, shell.groupName].filter(Boolean);
  const subtitle = parts.join(" • ");

  return (
    <RealProjectContext.Provider value={contextValue}>
      <div className="flex min-h-full flex-col">
        <header className="shrink-0 border-b px-4 pt-4 md:px-6">
          <Breadcrumbs
            items={[
              { label: "Dự án", to: "/projects" },
              { label: project.name },
            ]}
          />
          <div className="flex flex-wrap items-start justify-between gap-3 pt-2">
            <div>
              <h1 className="text-xl font-bold tracking-tight">{project.name}</h1>
              {subtitle ? (
                <p className="mt-0.5 text-xs text-muted-foreground">{subtitle}</p>
              ) : null}
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="outline" className="font-mono text-xs font-bold tracking-wider">
                {project.identifier}
              </Badge>
              {isArchived ? (
                <Badge variant="secondary">Đã lưu trữ</Badge>
              ) : null}
              {isReadOnly ? (
                <Badge variant="secondary">Chế độ chỉ xem</Badge>
              ) : null}
            </div>
          </div>
          <nav
            aria-label="Project navigation"
            className={`${segmentedTabsListClass} my-3`}
          >
            <Link
              to={`/projects/${projectId}/info`}
              aria-current="page"
              className={segmentedTabClass(true)}
            >
              Thông tin
            </Link>
          </nav>
        </header>
        <Outlet />
      </div>
    </RealProjectContext.Provider>
  );
}

export function Component() {
  return <RealProjectLayout />;
}
