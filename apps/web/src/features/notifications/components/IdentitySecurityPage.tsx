import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { KeyRound, LogOut, MonitorSmartphone, ShieldCheck } from "lucide-react";

import { ErrorState } from "@/components/feedback/ErrorState";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/features/auth/AuthProvider";
import { oldPasswordMessages } from "@/features/auth/errorMessages";
import { REVOKE_FAILED_MESSAGE, useSignOut } from "@/features/auth/useSignOut";
import { FieldError } from "@/features/notifications/components/FieldError";
import { SettingsHeader } from "@/features/notifications/components/SettingsHeader";
import { ApiError } from "@/lib/api/errors";
import { useChangePassword, useRevokeSession, useSessions } from "@/lib/query/identityHooks";

export const PASSWORD_CHANGED_NOTICE = "Đổi mật khẩu thành công. Hãy đăng nhập lại.";

function SecuritySkeleton() {
  return (
    <div className="space-y-6" role="status" aria-label="Đang tải cài đặt bảo mật">
      <Skeleton className="h-8 w-80" />
      <Skeleton className="h-40 w-full" />
    </div>
  );
}

function PasswordSection() {
  const auth = useAuth();
  const navigate = useNavigate();
  const changePassword = useChangePassword();
  const [oldPassword, setOldPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");

  const mismatch = confirmPassword.length > 0 && confirmPassword !== newPassword;
  const error = changePassword.error instanceof ApiError ? changePassword.error : null;
  const fieldErrors = error?.fieldErrors ?? {};
  const hasFieldErrors = Object.keys(fieldErrors).length > 0;

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (mismatch || changePassword.isPending) {
      return;
    }
    changePassword.mutate(
      { old_password: oldPassword, new_password1: newPassword, new_password2: confirmPassword },
      {
        onSuccess: () => {
          // Backend thu hồi mọi phiên khi đổi mật khẩu, kể cả phiên này.
          auth.handleUnauthorized();
          navigate("/login", { replace: true, state: { notice: PASSWORD_CHANGED_NOTICE } });
        },
      },
    );
  }

  return (
    <section aria-labelledby="password-section-title" className="space-y-4">
      <header className="space-y-1">
        <h2 id="password-section-title" className="flex items-center gap-2 text-lg font-semibold">
          <KeyRound className="size-5 text-primary" aria-hidden />
          Đổi mật khẩu
        </h2>
        <p className="text-sm text-muted-foreground">
          Đổi mật khẩu sẽ đăng xuất mọi thiết bị, kể cả thiết bị này.
        </p>
      </header>
      <form className="max-w-md space-y-4 short:space-y-3" onSubmit={handleSubmit}>
        <div className="space-y-1.5">
          <Label htmlFor="security-current-password">Mật khẩu hiện tại</Label>
          <Input
            id="security-current-password"
            type="password"
            autoComplete="current-password"
            value={oldPassword}
            onChange={(event) => setOldPassword(event.target.value)}
            aria-invalid={fieldErrors.old_password ? true : undefined}
          />
          <FieldError messages={oldPasswordMessages(fieldErrors.old_password)} />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="security-new-password">Mật khẩu mới</Label>
          <Input
            id="security-new-password"
            type="password"
            autoComplete="new-password"
            value={newPassword}
            onChange={(event) => setNewPassword(event.target.value)}
            aria-invalid={fieldErrors.new_password1 ? true : undefined}
          />
          <FieldError messages={fieldErrors.new_password1} />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="security-confirm-password">Xác nhận mật khẩu mới</Label>
          <Input
            id="security-confirm-password"
            type="password"
            autoComplete="new-password"
            value={confirmPassword}
            onChange={(event) => setConfirmPassword(event.target.value)}
            aria-invalid={mismatch || fieldErrors.new_password2 ? true : undefined}
          />
          {mismatch ? (
            <p className="text-xs text-destructive" role="alert">
              Xác nhận mật khẩu không khớp.
            </p>
          ) : null}
          <FieldError messages={fieldErrors.new_password2} />
        </div>
        {error && !hasFieldErrors ? (
          <p className="text-sm text-destructive" role="alert">
            {error.message}
          </p>
        ) : null}
        <Button type="submit" disabled={mismatch || !oldPassword || !newPassword || changePassword.isPending}>
          Cập nhật mật khẩu
        </Button>
      </form>
    </section>
  );
}

function LogoutAllDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const auth = useAuth();
  const navigate = useNavigate();
  const [pending, setPending] = useState(false);

  async function confirm() {
    setPending(true);
    let notice: string;
    try {
      const count = await auth.logoutAll();
      notice = `Đã đăng xuất khỏi ${count} thiết bị.`;
    } catch {
      // Phiên cục bộ đã bị xóa; báo rõ rằng máy chủ chưa thu hồi.
      notice = REVOKE_FAILED_MESSAGE;
    }
    navigate("/login", { replace: true, state: { notice } });
  }

  return (
    <Dialog open={open} onOpenChange={(next) => !pending && onOpenChange(next)}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Đăng xuất khỏi mọi thiết bị?</DialogTitle>
          <DialogDescription>
            Mọi phiên đăng nhập của tài khoản, kể cả thiết bị này, sẽ bị thu hồi. Bạn cần đăng nhập lại.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={pending}>
            Hủy
          </Button>
          <Button variant="destructive" onClick={confirm} disabled={pending}>
            Đăng xuất mọi thiết bị
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function IdentitySecurityPage() {
  const sessionsQuery = useSessions();
  const revokeSession = useRevokeSession();
  const signOut = useSignOut();
  const [confirmingLogoutAll, setConfirmingLogoutAll] = useState(false);
  const sessions = sessionsQuery.data;

  function handleRevoke(sessionId: string) {
    revokeSession.mutate(sessionId, {
      onError: (error) => toast.error(error.message || "Không thể đăng xuất thiết bị này."),
    });
  }

  return (
    <div className="page-container space-y-8 short:space-y-4 px-4 pt-7 short:pt-4 sm:px-6 lg:px-8">
      <SettingsHeader />

      <div className="grid gap-8 short:gap-4 lg:grid-cols-2 lg:items-start">
        <PasswordSection />

        <section aria-labelledby="sessions-section-title" className="space-y-4">
          <header className="space-y-1">
            <h2 id="sessions-section-title" className="flex items-center gap-2 text-lg font-semibold">
              <MonitorSmartphone className="size-5 text-primary" aria-hidden />
              Phiên đăng nhập
            </h2>
            <p className="text-sm text-muted-foreground">
              Các thiết bị đang giữ phiên đăng nhập của tài khoản của bạn.
            </p>
          </header>

          {sessionsQuery.isError ? (
            <ErrorState error={sessionsQuery.error} onRetry={() => sessionsQuery.refetch()} />
          ) : sessionsQuery.isPending || !sessions ? (
            <SecuritySkeleton />
          ) : sessions.length === 0 ? (
            <p className="text-sm text-muted-foreground">Không có phiên đăng nhập nào.</p>
          ) : (
            <ul className="divide-y rounded-lg border">
              {sessions.map((session) => (
                <li
                  key={session.id}
                  className="flex flex-col gap-2 px-4 py-3 sm:flex-row sm:items-center sm:justify-between"
                >
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-sm font-medium">{session.device_name || "Thiết bị không tên"}</span>
                      {session.is_current ? (
                        <Badge variant="secondary" className="gap-1">
                          <ShieldCheck className="size-3" aria-hidden />
                          Thiết bị hiện tại
                        </Badge>
                      ) : null}
                    </div>
                    <p className="text-xs text-muted-foreground">
                      {session.ip_address ?? "Không rõ IP"} • Đăng nhập{" "}
                      {new Date(session.created_at).toLocaleString("vi-VN")}
                    </p>
                  </div>
                  {!session.is_current ? (
                    <Button
                      size="sm"
                      variant="outline"
                      className="shrink-0"
                      onClick={() => handleRevoke(session.id)}
                      disabled={revokeSession.isPending}
                    >
                      Đăng xuất thiết bị
                    </Button>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      <section aria-labelledby="account-section-title" className="space-y-4">
        <h2 id="account-section-title" className="text-lg font-semibold">
          Đăng xuất
        </h2>
        <p className="text-sm text-muted-foreground">
          Kết thúc phiên trên thiết bị này, hoặc thu hồi mọi phiên trên tất cả thiết bị.
        </p>
        <div className="flex flex-wrap gap-3">
          <Button variant="outline" onClick={() => void signOut()}>
            <LogOut className="size-4" aria-hidden />
            Đăng xuất
          </Button>
          <Button variant="outline" onClick={() => setConfirmingLogoutAll(true)}>
            <LogOut className="size-4" aria-hidden />
            Đăng xuất mọi thiết bị
          </Button>
        </div>
      </section>

      <LogoutAllDialog open={confirmingLogoutAll} onOpenChange={setConfirmingLogoutAll} />
    </div>
  );
}
