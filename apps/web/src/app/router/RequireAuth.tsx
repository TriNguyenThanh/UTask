import type { ReactNode } from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";

import { PageSkeleton } from "@/components/feedback/PageSkeleton";
import { useAuth } from "@/features/auth/AuthProvider";

export function RequireAuth({ children }: { children?: ReactNode }) {
  const auth = useAuth();
  const location = useLocation();

  if (auth.status === "restoring") {
    return <PageSkeleton label="Đang khôi phục phiên đăng nhập" />;
  }
  if (auth.status === "anonymous") {
    const returnTo = `${location.pathname}${location.search}${location.hash}`;
    return <Navigate to="/login" replace state={{ returnTo }} />;
  }
  return children ?? <Outlet />;
}
