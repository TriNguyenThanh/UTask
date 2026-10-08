import { Menu } from "lucide-react";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { useAuth } from "@/features/auth/AuthProvider";
import { isStudentAccount } from "@/features/auth/utils";

/**
 * Top bar of the Teacher space. It carries no Student actions (create task,
 * Git sync, search of tasks) and issues no requests of its own.
 */
export function TeacherTopNavigation({ onOpenMobileNav }: { onOpenMobileNav?: () => void }) {
  const { user } = useAuth();

  return (
    <header className="sticky top-0 z-20 flex h-16 items-center justify-between gap-3 border-b bg-background/80 px-4 backdrop-blur-sm lg:px-8">
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
        <p className="truncate text-sm font-semibold">Không gian giảng viên</p>
      </div>
      {isStudentAccount(user) ? (
        <Button asChild variant="outline" size="sm">
          <Link to="/my-work">Không gian sinh viên</Link>
        </Button>
      ) : null}
    </header>
  );
}
