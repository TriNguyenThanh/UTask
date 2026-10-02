import { Plus, RefreshCw, Search } from "lucide-react";
import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/features/auth/AuthProvider";
import { hasTeamPermission } from "@/features/my-work/permissions";
import { useMyWorkOverview } from "@/features/my-work/queries";
import { cn } from "@/lib/utils";

/**
 * Placeholder handlers are explicit: unimplemented actions render disabled
 * with a title explaining why, instead of pretending to work.
 */
function DisabledActionButton({ children, reason }: { children: ReactNode; reason: string }) {
  return (
    <Button type="button" variant="outline" size="sm" disabled title={reason}>
      {children}
    </Button>
  );
}

export function TopNavigation({ onOpenMobileNav }: { onOpenMobileNav?: () => void }) {
  const { user } = useAuth();
  const { data: overview } = useMyWorkOverview();
  void user;

  const leaderEnrollment = overview?.enrollments.find(
    (enrollment) =>
      enrollment.membership.status === "assigned" &&
      hasTeamPermission(enrollment.membership.role, "task:create"),
  );

  return (
    <header className="sticky top-0 z-20 flex h-16 items-center justify-between gap-3 border-b bg-background/80 px-4 backdrop-blur-sm lg:px-8">
      <div className="flex min-w-0 flex-1 items-center gap-3">
        {onOpenMobileNav ? (
          <Button
            type="button"
            variant="outline"
            size="icon"
            className="lg:hidden"
            aria-label="Mở điều hướng"
            onClick={onOpenMobileNav}
          >
            <span className="sr-only">Mở điều hướng</span>
            <RefreshCw className="size-4 rotate-90" aria-hidden />
          </Button>
        ) : null}
        <div className="relative w-full min-w-0 max-w-lg">
          <Search
            className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
            aria-hidden
          />
          <Input
            type="search"
            aria-label="Tìm kiếm toàn cục"
            placeholder="Tìm kiếm nhiệm vụ, mã issue, PR hoặc môn học..."
            disabled
            title="Tìm kiếm toàn cục sẽ khả dụng ở slice sau"
            className={cn("bg-card pl-9 text-xs")}
          />
          <kbd className="pointer-events-none absolute right-2.5 top-1/2 hidden -translate-y-1/2 rounded border bg-secondary px-1 font-mono text-[10px] text-muted-foreground sm:block">
            /
          </kbd>
        </div>
      </div>

      <div className="flex shrink-0 flex-wrap items-center justify-end gap-2">
        <DisabledActionButton reason="Đồng bộ Git sẽ khả dụng sau khi kết nối GitHub">
          <RefreshCw className="size-3.5" aria-hidden />
          Đồng bộ Git
        </DisabledActionButton>
        {leaderEnrollment ? (
          <Button type="button" size="sm" disabled title="Tạo task mới sẽ khả dụng ở slice Board">
            <Plus className="size-3.5" aria-hidden />
            Tạo task mới
          </Button>
        ) : (
          <DisabledActionButton reason="Chỉ Leader nhóm mới có thể tạo task">
            <Plus className="size-3.5" aria-hidden />
            Tạo task mới
          </DisabledActionButton>
        )}
      </div>
    </header>
  );
}