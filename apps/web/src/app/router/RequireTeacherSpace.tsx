import { Navigate, Outlet } from "react-router-dom";

import { ForbiddenPage } from "@/components/feedback/ForbiddenPage";
import { useAuth } from "@/features/auth/AuthProvider";
import { canUseTeacherSpace, defaultLandingPath } from "@/features/auth/utils";

/**
 * Route guard for `/teacher/*`. Blocks accounts without the TEACHER role
 * before any Teacher query is issued. It never grants class access: each
 * class is still authorized by its own assignment on every request.
 */
export function RequireTeacherSpace() {
  const { user } = useAuth();
  if (!canUseTeacherSpace(user)) {
    return (
      <ForbiddenPage
        title="Không đủ quyền truy cập"
        description="Khu vực này chỉ dành cho tài khoản giảng viên."
        backTo={defaultLandingPath(user)}
        backLabel="Quay lại trang chủ"
      />
    );
  }
  return <Outlet />;
}

/** `/` sends each account to its own home. */
export function HomeRedirect() {
  const { user } = useAuth();
  return <Navigate to={defaultLandingPath(user)} replace />;
}
