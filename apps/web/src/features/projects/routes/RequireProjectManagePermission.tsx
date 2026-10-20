import { Outlet } from "react-router-dom";

import { ForbiddenPage } from "@/components/feedback/ForbiddenPage";
import { isRealService } from "@/lib/config/services";
import { useProjectWorkspaceContext } from "@/features/projects/routes/ProjectWorkspaceLayout";

/**
 * Route-level guard: renders the child settings route only when the current
 * member can manage project settings (leader). UI hiding is not enough —
 * direct URL access must land on Forbidden.
 *
 * In real mode the settings screen reports itself as not integrated; no demo
 * context (AI key, role) is available to check here.
 */
export function RequireProjectManagePermission() {
  return isRealService("work") ? <Outlet /> : <DemoRequireProjectManagePermission />;
}

function DemoRequireProjectManagePermission() {
  const { viewer } = useProjectWorkspaceContext();
  // Leader only: members and instructors both land on Forbidden.
  if (viewer.kind !== "team-member" || viewer.role !== "leader") {
    return <ForbiddenPage />;
  }
  return <Outlet />;
}
