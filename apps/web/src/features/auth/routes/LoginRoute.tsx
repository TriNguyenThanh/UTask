import { Navigate, useLocation } from "react-router-dom";

import { AuthLayout } from "@/app/layouts/AuthLayout";
import { useAuth } from "@/features/auth/AuthProvider";
import { LoginForm } from "@/features/auth/components/LoginForm";
import { resolveLoginTarget } from "@/features/auth/utils";

export function Component() {
  const auth = useAuth();
  const location = useLocation();
  if (auth.status === "authenticated") {
    return <Navigate to={resolveLoginTarget(location.state, auth.user)} replace />;
  }
  return <AuthLayout><LoginForm /></AuthLayout>;
}
