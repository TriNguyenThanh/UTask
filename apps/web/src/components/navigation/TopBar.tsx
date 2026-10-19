import { Menu } from "lucide-react";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { useAuth } from "@/features/auth/AuthProvider";
import { isStudentAccount } from "@/features/auth/utils";
import { NotificationBell } from "@/features/notifications/components/NotificationBell";

/** Top bar: tiêu đề mục đang xem + chuông thông báo; không có hành động nghiệp vụ. */
export function TopBar({
  title,
  inTeacherSpace,
  onOpenMobileNav,
}: Readonly<{
  title: string;
  inTeacherSpace: boolean;
  onOpenMobileNav?: () => void;
}>) {
  const { user } = useAuth();

  return (
    <header className="sticky top-0 z-20 flex h-16 shrink-0 short:h-12 items-center justify-between gap-3 border-b bg-card px-4 lg:px-8">
      <div className="flex min-w-0 items-center gap-3">
        {onOpenMobileNav ? (
          <Button
            type="button"
            variant="outline"
            size="icon"
            className="lg:hidden"
            aria-label="Mở điều hướng"
            onClick={onOpenMobileNav}
          >
            <Menu className="size-4" aria-hidden />
          </Button>
        ) : null}
        <p className="truncate text-base font-semibold tracking-tight">{title}</p>
      </div>
      <div className="flex items-center gap-2">
        {inTeacherSpace ? null : <NotificationBell />}
        {inTeacherSpace && isStudentAccount(user) ? (
          <Button asChild variant="outline" size="sm">
            <Link to="/my-work">Không gian sinh viên</Link>
          </Button>
        ) : null}
      </div>
    </header>
  );
}
