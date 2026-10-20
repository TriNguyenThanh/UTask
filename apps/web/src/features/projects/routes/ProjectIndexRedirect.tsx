import { Navigate } from "react-router-dom";

import { isRealService } from "@/lib/config/services";

/**
 * Index redirect for /projects/:projectId.
 * Flag evaluated at render (not at module level) so vi.stubEnv works in tests.
 */
export function ProjectIndexRedirect() {
  return <Navigate to={isRealService("work") ? "info" : "backlog"} replace />;
}
