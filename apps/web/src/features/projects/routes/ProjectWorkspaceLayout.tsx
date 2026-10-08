import { createContext, useContext, useEffect } from "react";
import { Link, Outlet, useLocation, useParams } from "react-router-dom";

import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { ForbiddenPage } from "@/components/feedback/ForbiddenPage";
import { PageSkeleton } from "@/components/feedback/PageSkeleton";
import { useRequestTeacherChrome } from "@/app/layouts/TeacherChromeContext";
import { Breadcrumbs } from "@/components/navigation/Breadcrumbs";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/features/auth/AuthProvider";
import { canUseTeacherSpace, isStudentAccount } from "@/features/auth/utils";
import { ApiError } from "@/lib/api/errors";
import { useProjectWorkspace } from "@/lib/query/studentFlowHooks";
import type { ProjectViewer, ProjectWorkspace } from "@/features/projects/types";
import { isReadOnlyViewer } from "@/lib/permissions";
import { ProjectNavigation } from "@/features/projects/components/ProjectNavigation";

/** Module heading per tab, shown under the project breadcrumb. */
export const projectModuleTitles = {
  backlog: "Backlog & Sprint Planning",
  board: "Bảng công việc Sprint",
  code: "Mã nguồn & GitHub",
  settings: "Cài đặt dự án",
} as const;

export type ProjectModule = keyof typeof projectModuleTitles;

interface ProjectWorkspaceContextValue {
  projectId: string;
  workspace: ProjectWorkspace;
  viewer: ProjectViewer;
  /** Instructors read the workspace and never change it. */
  readOnly: boolean;
  activeModule: ProjectModule;
}

const ProjectWorkspaceContext =
  createContext<ProjectWorkspaceContextValue | null>(null);

export function useProjectWorkspaceContext(): ProjectWorkspaceContextValue {
  const value = useContext(ProjectWorkspaceContext);
  if (value === null) {
    throw new Error(
      "useProjectWorkspaceContext must be used inside ProjectWorkspaceLayout",
    );
  }
  return value;
}

function moduleFromPathname(pathname: string): ProjectModule {
  if (pathname.endsWith("/board")) return "board";
  if (pathname.endsWith("/code")) return "code";
  if (pathname.endsWith("/settings")) return "settings";
  return "backlog";
}

/**
 * Shared shell for every module of one project: breadcrumb, project header,
 * module navigation and the per-project loading/permission/error states.
 * Child routes render only their module content inside the outlet.
 */
export default function ProjectWorkspaceLayout() {
  const { projectId = "" } = useParams();
  const { pathname } = useLocation();
  const { user } = useAuth();
  const workspaceQuery = useProjectWorkspace(projectId);
  const requestTeacherChrome = useRequestTeacherChrome();
  const instructorView = workspaceQuery.data?.viewer.kind === "course-instructor";

  useEffect(() => {
    if (!instructorView) return;
    requestTeacherChrome(true);
    return () => requestTeacherChrome(false);
  }, [instructorView, requestTeacherChrome]);

  // A teacher-only account has no Student project list to go back to.
  const teacherOnly = canUseTeacherSpace(user) && !isStudentAccount(user);

  if (workspaceQuery.isPending) {
    return <PageSkeleton label="Đang tải không gian dự án" />;
  }

  const error = workspaceQuery.error;
  if (error instanceof ApiError && error.status === 403) {
    return <ForbiddenPage />;
  }
  if (error instanceof ApiError && error.status === 404) {
    return (
      <div className="p-6">
        <EmptyState
          title="Không tìm thấy dự án"
          description="Dự án này không tồn tại hoặc đã bị xóa. Hãy quay lại danh sách dự án để chọn dự án khác."
          action={
            teacherOnly ? (
              <Button asChild size="sm" variant="outline">
                <Link to="/teacher/courses">Về danh sách lớp phụ trách</Link>
              </Button>
            ) : (
              <Button asChild size="sm" variant="outline">
                <Link to="/projects">Về danh sách dự án</Link>
              </Button>
            )
          }
        />
      </div>
    );
  }
  if (error !== null) {
    return (
      <div className="p-6">
        <ErrorState error={error} onRetry={() => void workspaceQuery.refetch()} />
      </div>
    );
  }

  const workspace = workspaceQuery.data;
  if (!workspace) {
    return <PageSkeleton label="Đang tải không gian dự án" />;
  }

  return (
    <ProjectWorkspaceContext.Provider
      value={{
        projectId,
        workspace,
        viewer: workspace.viewer,
        readOnly: isReadOnlyViewer(workspace.viewer),
        activeModule: moduleFromPathname(pathname),
      }}
    >
      <ProjectWorkspaceHeader workspace={workspace} />
      <Outlet />
    </ProjectWorkspaceContext.Provider>
  );
}

function ProjectWorkspaceHeader({ workspace }: { workspace: ProjectWorkspace }) {
  const { activeModule, projectId, readOnly } = useProjectWorkspaceContext();
  const teacherBase = `/teacher/courses/${workspace.courseId}`;

  return (
    <header className="border-b px-4 pt-4 md:px-6">
      {readOnly ? (
        // Built from the workspace payload, so it is right on deep link and refresh.
        <Breadcrumbs
          items={[
            { label: "Trang chủ", to: "/teacher" },
            { label: "Lớp phụ trách", to: "/teacher/courses" },
            { label: workspace.courseName, to: teacherBase },
            { label: workspace.teamName, to: `${teacherBase}/teams/${workspace.teamId}` },
            { label: workspace.projectKey },
          ]}
        />
      ) : (
        <nav
          aria-label="Breadcrumb dự án"
          className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground"
        >
          <Link to="/projects" className="hover:text-foreground">
            Dự án
          </Link>
          <span aria-hidden>/</span>
          <span className="font-semibold text-foreground">
            {workspace.courseCode} — {workspace.name}
          </span>
        </nav>
      )}
      <div className="flex flex-wrap items-start justify-between gap-3 pt-2">
        <div>
          <h1 className="text-lg font-bold tracking-tight">
            {projectModuleTitles[activeModule]}
          </h1>
          <p className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <span>Môn: {workspace.courseCode}</span>
            <span aria-hidden>•</span>
            <span>{workspace.teamName}</span>
            <span aria-hidden>•</span>
            <span>GVHD: {workspace.instructorName}</span>
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {readOnly ? (
            <span className="rounded-full border bg-muted px-2.5 py-0.5 text-xs font-medium text-muted-foreground">
              Chế độ chỉ xem
            </span>
          ) : null}
          <span className="rounded bg-primary px-2 py-0.5 font-mono text-xs font-bold tracking-wider text-primary-foreground">
            {workspace.projectKey}
          </span>
        </div>
      </div>
      <ProjectNavigation
        projectId={projectId}
        canManageSettings={workspace.myRole === "leader"}
      />
    </header>
  );
}
export function Component() {
  return <ProjectWorkspaceLayout />;
}
