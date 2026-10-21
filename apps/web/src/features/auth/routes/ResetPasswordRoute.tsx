import { TriangleAlert } from "lucide-react";
import { Link, Navigate, useSearchParams } from "react-router-dom";

import { AuthLayout } from "@/app/layouts/AuthLayout";
import { useAuth } from "@/features/auth/AuthProvider";
import { AuthStatusCard } from "@/features/auth/components/AuthStatusCard";
import { ResetPasswordForm } from "@/features/auth/components/ResetPasswordForm";

export function Component() {
  const auth = useAuth();
  const [searchParams] = useSearchParams();
  const uid = searchParams.get("uid");
  const token = searchParams.get("token");

  if (auth.status === "authenticated") {
    return <Navigate to="/" replace />;
  }
  if (!uid || !token) {
    return (
      <AuthLayout>
        <AuthStatusCard
          icon={TriangleAlert}
          title="Liên kết đặt lại mật khẩu không hợp lệ"
          actions={<Link className="text-primary hover:underline" to="/forgot-password">Yêu cầu liên kết mới</Link>}
        >
          Liên kết thiếu thông tin cần thiết. Hãy mở đúng liên kết trong email hoặc yêu cầu liên kết mới.
        </AuthStatusCard>
      </AuthLayout>
    );
  }
  return <AuthLayout><ResetPasswordForm uid={uid} token={token} /></AuthLayout>;
}
