import { Navigate } from "react-router-dom";

import { AuthLayout } from "@/app/layouts/AuthLayout";
import { useAuth } from "@/features/auth/AuthProvider";
import { ResetPasswordForm } from "@/features/auth/components/ResetPasswordForm";

export function Component() {
  const auth = useAuth();
  if (auth.status === "authenticated") {
    return <Navigate to="/" replace />;
  }
  return <AuthLayout><ResetPasswordForm /></AuthLayout>;
}
