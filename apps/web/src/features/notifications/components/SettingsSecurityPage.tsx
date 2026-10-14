import { useMemo, useState } from "react";
import { toast } from "sonner";
import { KeyRound, LogOut, MonitorSmartphone, ShieldCheck } from "lucide-react";

import { ErrorState } from "@/components/feedback/ErrorState";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/features/auth/AuthProvider";
import { SettingsHeader } from "@/features/notifications/components/SettingsHeader";
import { useAccountSettings } from "@/lib/query/studentFlowHooks";

function formatRelative(at: string, now: Date): string {
  const diffMs = now.getTime() - new Date(at).getTime();
  const minutes = Math.floor(diffMs / 60_000);
  if (minutes < 1) return "Vừa xong";
  if (minutes < 60) return `${minutes} phút trước`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} giờ trước`;
  return `${Math.floor(hours / 24)} ngày trước`;
}

function SecuritySkeleton() {
  return (
    <div className="space-y-6" role="status" aria-label="Đang tải cài đặt bảo mật">
      <Skeleton className="h-8 w-80" />
      <Skeleton className="h-64 w-full max-w-md" />
      <Skeleton className="h-32 w-full" />
    </div>
  );
}

export function SettingsSecurityPage() {
  const settingsQuery = useAccountSettings();
  const auth = useAuth();
  const now = useMemo(() => new Date(), []);

  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");

  const settings = settingsQuery.data;
  const sessions = settings?.sessions ?? [];

  const newPasswordError =
    newPassword.length > 0 && newPassword.length < 8
      ? "Mật khẩu mới phải có ít nhất 8 ký tự."
      : null;
  const confirmPasswordError =
    confirmPassword.length > 0 && confirmPassword !== newPassword
      ? "Xác nhận mật khẩu không khớp."
      : null;

  function handleLogout() {
    auth.logout().catch(() => {
      // Local session already cleared by provider; nothing else to do.
    });
  }

  if (settingsQuery.isError) {
    return (
      <div className="mx-auto max-w-6xl space-y-6 px-4 pt-7 sm:px-6 lg:px-8">
        <SettingsHeader />
        <ErrorState error={settingsQuery.error} onRetry={() => settingsQuery.refetch()} />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-6xl space-y-8 px-4 pt-7 sm:px-6 lg:px-8">
      <SettingsHeader />

      {settingsQuery.isPending || !settings ? (
        <SecuritySkeleton />
      ) : (
        <>
          <section aria-labelledby="password-section-title" className="space-y-4">
            <header className="space-y-1">
              <h2
                id="password-section-title"
                className="flex items-center gap-2 text-lg font-semibold"
              >
                <KeyRound className="size-5 text-primary" aria-hidden />
                Đổi mật khẩu
              </h2>
              <p className="text-sm text-muted-foreground">
                Sử dụng mật khẩu mạnh và không trùng với mật khẩu email trường.
              </p>
            </header>
            <form
              className="max-w-md space-y-4"
              onSubmit={(event) => {
                event.preventDefault();
                toast.info("API đổi mật khẩu sẽ khả dụng khi backend hỗ trợ");
              }}
            >
              <div className="space-y-1.5">
                <Label htmlFor="security-current-password">Mật khẩu hiện tại</Label>
                <Input
                  id="security-current-password"
                  type="password"
                  value={currentPassword}
                  onChange={(event) => setCurrentPassword(event.target.value)}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="security-new-password">Mật khẩu mới</Label>
                <Input
                  id="security-new-password"
                  type="password"
                  value={newPassword}
                  onChange={(event) => setNewPassword(event.target.value)}
                  aria-invalid={newPasswordError !== null || undefined}
                />
                {newPasswordError ? (
                  <p className="text-xs text-destructive" role="alert">
                    {newPasswordError}
                  </p>
                ) : null}
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="security-confirm-password">Xác nhận mật khẩu mới</Label>
                <Input
                  id="security-confirm-password"
                  type="password"
                  value={confirmPassword}
                  onChange={(event) => setConfirmPassword(event.target.value)}
                  aria-invalid={confirmPasswordError !== null || undefined}
                />
                {confirmPasswordError ? (
                  <p className="text-xs text-destructive" role="alert">
                    {confirmPasswordError}
                  </p>
                ) : null}
              </div>
              <Button
                type="submit"
                disabled
                title="API đổi mật khẩu sẽ khả dụng khi backend hỗ trợ"
              >
                Cập nhật mật khẩu
              </Button>
            </form>
          </section>

          <section aria-labelledby="sessions-section-title" className="space-y-4">
            <header className="space-y-1">
              <h2
                id="sessions-section-title"
                className="flex items-center gap-2 text-lg font-semibold"
              >
                <MonitorSmartphone className="size-5 text-primary" aria-hidden />
                Phiên đăng nhập
              </h2>
              <p className="text-sm text-muted-foreground">
                Các thiết bị đang giữ phiên đăng nhập của tài khoản của bạn.
              </p>
            </header>
            <ul className="divide-y rounded-lg border">
              {sessions.map((session) => (
                <li
                  key={session.id}
                  className="flex flex-col gap-2 px-4 py-3 sm:flex-row sm:items-center sm:justify-between"
                >
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-sm font-medium">{session.device}</span>
                      {session.current ? (
                        <Badge variant="secondary" className="gap-1">
                          <ShieldCheck className="size-3" aria-hidden />
                          Thiết bị hiện tại
                        </Badge>
                      ) : null}
                    </div>
                    <p className="text-xs text-muted-foreground">
                      {session.location} • Hoạt động {formatRelative(session.lastActiveAt, now)}
                    </p>
                  </div>
                  {!session.current ? (
                    <Button
                      size="sm"
                      variant="outline"
                      disabled
                      title="Đăng xuất thiết bị khác sẽ khả dụng khi backend hỗ trợ"
                      className="shrink-0"
                    >
                      Đăng xuất thiết bị
                    </Button>
                  ) : null}
                </li>
              ))}
            </ul>
          </section>

          <section aria-labelledby="account-section-title" className="space-y-4">
            <h2 id="account-section-title" className="text-lg font-semibold">
              Đăng xuất
            </h2>
            <p className="text-sm text-muted-foreground">
              Kết thúc phiên đăng nhập hiện tại trên thiết bị này.
            </p>
            <Button variant="outline" onClick={handleLogout}>
              <LogOut className="size-4" aria-hidden />
              Đăng xuất
            </Button>
          </section>
        </>
      )}
    </div>
  );
}