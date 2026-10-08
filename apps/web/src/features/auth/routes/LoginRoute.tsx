import { Navigate } from "react-router-dom";

import { AuthLayout } from "@/app/layouts/AuthLayout";
import { useAuth } from "@/features/auth/AuthProvider";
import { LoginForm } from "@/features/auth/components/LoginForm";

export function Component() {
  const auth = useAuth();
  if (auth.status === "authenticated") {
    return <Navigate to="/my-work" replace />;
  }
  return <AuthLayout><LoginForm /></AuthLayout>;
}
