import type { LucideIcon } from "lucide-react";
import { NavLink } from "react-router-dom";

import { cn } from "@/lib/utils";

/**
 * Mục điều hướng sidebar. Icon luôn đứng yên ở cùng vị trí; khi sidebar thu
 * lại (rail) nhãn mờ dần và bị cắt bởi `overflow-hidden` của sidebar.
 */
export function SidebarNavItem({
  to,
  icon: Icon,
  label,
  collapsed,
  end = false,
}: Readonly<{
  to: string;
  icon: LucideIcon;
  label: string;
  collapsed: boolean;
  end?: boolean;
}>) {
  return (
    <NavLink
      to={to}
      end={end}
      title={collapsed ? label : undefined}
      className={({ isActive }) =>
        cn(
          "relative flex items-center gap-3 rounded-md px-3 py-2 short:py-1.5 text-sm font-medium transition-colors",
          isActive
            ? "bg-accent font-semibold text-accent-foreground"
            : "text-muted-foreground hover:bg-secondary hover:text-foreground",
        )
      }
    >
      {({ isActive }) => (
        <>
          {isActive ? (
            <span
              className="absolute inset-y-1.5 left-0 w-[2.5px] rounded-r bg-primary"
              aria-hidden
            />
          ) : null}
          <Icon className="size-4 shrink-0" aria-hidden />
          <span
            className={cn(
              "whitespace-nowrap transition-opacity duration-200",
              collapsed && "opacity-0",
            )}
          >
            {label}
          </span>
        </>
      )}
    </NavLink>
  );
}
