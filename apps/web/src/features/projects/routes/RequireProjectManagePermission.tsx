import { Outlet } from "react-router-dom";

import { ForbiddenPage } from "@/components/feedback/ForbiddenPage";
import { useProjectWorkspaceContext } from "@/features/projects/routes/ProjectWorkspaceLayout";

/**
 * Route-level guard: renders the child settings route only when the current
 * member can manage project settings (leader). UI hiding is not enough —
 * direct URL access must land on Forbidden.
 */
export function RequireProjectManagePermission() {
  const { workspace } = useProjectWorkspaceContext();
  if (workspace.myRole !== "leader") {
    return <ForbiddenPage />;
  }
  return <Outlet />;
}