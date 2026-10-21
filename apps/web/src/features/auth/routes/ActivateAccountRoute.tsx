import { TriangleAlert } from "lucide-react";
import { Navigate, useSearchParams } from "react-router-dom";

import { AuthLayout } from "@/app/layouts/AuthLayout";
import { useAuth } from "@/features/auth/AuthProvider";
import { ActivateAccountForm } from "@/features/auth/components/ActivateAccountForm";
import { AuthStatusCard } from "@/features/auth/components/AuthStatusCard";

export function Component() {
  const auth = useAuth();
  const [searchParams] = useSearchParams();
  const key = searchParams.get("key");

  if (auth.status === "authenticated") {
    return <Navigate to="/" replace />;
  }
  if (!key) {
    return (
      <AuthLayout>
        <AuthStatusCard icon={TriangleAlert} title="Liên kết kích hoạt không hợp lệ">
          Liên kết thiếu mã kích hoạt. Hãy mở đúng liên kết trong email kích hoạt.
        </AuthStatusCard>
      </AuthLayout>
    );
  }
  return <AuthLayout><ActivateAccountForm activationKey={key} /></AuthLayout>;
}
