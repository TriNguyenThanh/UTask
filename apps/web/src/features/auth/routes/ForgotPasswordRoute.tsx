import { CircleHelp } from "lucide-react";
import { Navigate } from "react-router-dom";

import { AuthLayout } from "@/app/layouts/AuthLayout";
import { useAuth } from "@/features/auth/AuthProvider";
import { ForgotPasswordForm } from "@/features/auth/components/ForgotPasswordForm";

export function Component() {
  const auth = useAuth();
  if (auth.status === "authenticated") {
    return <Navigate to="/" replace />;
  }

  return (
    <AuthLayout
      headerActions={(
        <>
          <span className="hidden items-center gap-1.5 rounded-full border border-emerald-200/60 bg-emerald-50 px-2.5 py-1 font-medium text-emerald-700 sm:flex">
            <span className="size-2 rounded-full bg-emerald-500" aria-hidden="true" />
            Cổng ĐHQG Online
          </span>
          <a className="flex items-center gap-1 font-medium hover:text-[#1a1c1c]" href="#academic-support">
            <CircleHelp className="size-4" aria-hidden="true" />
            <span className="hidden sm:inline">Trợ giúp</span>
          </a>
        </>
      )}
    >
      <ForgotPasswordForm />
    </AuthLayout>
  );
}
