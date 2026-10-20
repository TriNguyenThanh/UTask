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
import { useUserNames } from "@/lib/query/teacherClassHooks";
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
  const active = useMemo(() => shell.members.filter((member) => member.status === "ACTIVE"), [shell.members]);
  const namesQuery = useUserNames(active.filter((m) => !m.display_name).map((m) => m.user_id));
  const assignees = useMemo(
    () =>
      active.map((member) => ({
        userId: member.user_id,
        name: member.display_name || namesQuery.data?.get(member.user_id) || "Thành viên",
      })),
    [active, namesQuery.data],
  );

  const value = useMemo<ProjectWorkspaceContextValue | null>(
    () =>
      workspace
        ? {
            projectId,
            workspace,
            viewer: workspace.viewer,
            readOnly: isReadOnlyViewer(workspace.viewer),
            activeModule: moduleOfPathname(pathname),
            archived: shell.project.archived_at !== null,
            assignees,
          }
        : null,
    [projectId, workspace, pathname, shell.project.archived_at, assignees],
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
