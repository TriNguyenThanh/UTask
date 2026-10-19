import { useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { useAuth } from "@/features/auth/AuthProvider";

export const REVOKE_FAILED_MESSAGE =
  "Chưa thu hồi được phiên trên máy chủ. Hãy đổi mật khẩu nếu dùng máy công cộng.";

/** Đăng xuất, cảnh báo khi máy chủ chưa thu hồi phiên, rồi về trang đăng nhập. */
export function useSignOut(): () => Promise<void> {
  const auth = useAuth();
  const navigate = useNavigate();

  return useCallback(async () => {
    const { revoked } = await auth.logout();
    if (!revoked) {
      toast.warning(REVOKE_FAILED_MESSAGE);
    }
    navigate("/login", { replace: true });
  }, [auth, navigate]);
}
