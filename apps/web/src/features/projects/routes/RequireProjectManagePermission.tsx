import { Outlet } from "react-router-dom";

import { ForbiddenPage } from "@/components/feedback/ForbiddenPage";
import { useProjectWorkspaceContext } from "@/features/projects/routes/ProjectWorkspaceLayout";

/**
 * Route-level guard: renders the child settings route only when the current
 * member can manage project settings (leader). UI hiding is not enough —
 * direct URL access must land on Forbidden.
 */
export function RequireProjectManagePermission() {
  const { viewer } = useProjectWorkspaceContext();
  // Leader only: members and instructors both land on Forbidden.
  if (viewer.kind !== "team-member" || viewer.role !== "leader") {
    return <ForbiddenPage />;
  }
  return <Outlet />;
}