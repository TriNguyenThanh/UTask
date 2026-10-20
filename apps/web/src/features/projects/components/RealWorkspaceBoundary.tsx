import { useMemo, type ReactNode } from "react";
import { useLocation } from "react-router-dom";

import { ErrorState } from "@/components/feedback/ErrorState";
import { PageSkeleton } from "@/components/feedback/PageSkeleton";
import { useRealProjectContext } from "@/features/projects/components/RealProjectLayout";
import {
  moduleOfPathname,
  ProjectWorkspaceProvider,
  type ProjectWorkspaceContextValue,
} from "@/features/projects/routes/ProjectWorkspaceLayout";
import { isReadOnlyViewer } from "@/lib/permissions";
import { useWorkspaceReal } from "@/lib/query/workHooks";

/**
 * Tải workspace (states, epics, tasks, sprints) của Work thật rồi cấp cùng context
 * mà Board/Backlog của demo đang đọc, nên hai màn hình dùng chung một giao diện.
 */
export function RealWorkspaceBoundary({ children }: Readonly<{ children: ReactNode }>) {
  const { projectId, shell } = useRealProjectContext();
  const { pathname } = useLocation();
  const query = useWorkspaceReal(shell);
  const workspace = query.data;

  const value = useMemo<ProjectWorkspaceContextValue | null>(
    () =>
      workspace
        ? {
            projectId,
            workspace,
            viewer: workspace.viewer,
            readOnly: isReadOnlyViewer(workspace.viewer),
            activeModule: moduleOfPathname(pathname),
          }
        : null,
    [projectId, workspace, pathname],
  );

  if (query.isPending) return <PageSkeleton label="Đang tải công việc" />;
  if (query.error !== null) {
    return (
      <div className="p-6">
        <ErrorState error={query.error} onRetry={() => void query.refetch()} />
      </div>
    );
  }
  if (!value) return <PageSkeleton label="Đang tải công việc" />;

  return <ProjectWorkspaceProvider value={value}>{children}</ProjectWorkspaceProvider>;
}
