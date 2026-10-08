import { Link, useLocation } from "react-router-dom";

import { cn } from "@/lib/utils";

interface ProjectNavigationProps {
  projectId: string;
  /** Leader-only: shows the settings tab when true. */
  canManageSettings: boolean;
}

const tabs = [
  { id: "backlog", label: "Backlog" },
  { id: "board", label: "Bảng công việc" },
  { id: "code", label: "Mã nguồn" },
  { id: "settings", label: "Cài đặt dự án" },
] as const;

/**
 * Module-level navigation inside one project workspace. The active tab is
 * derived from the router pathname — never from local state.
 */
export function ProjectNavigation({
  projectId,
  canManageSettings,
}: ProjectNavigationProps) {
  const { pathname } = useLocation();

  return (
    <nav
      aria-label="Project navigation"
      className="flex items-center gap-5 overflow-x-auto pt-2 text-sm"
    >
      {tabs
        .filter((tab) => tab.id !== "settings" || canManageSettings)
        .map((tab) => {
          const to = `/projects/${projectId}/${tab.id}`;
          const isActive = pathname === to;
          return (
            <Link
              key={tab.id}
              to={to}
              aria-current={isActive ? "page" : undefined}
              className={cn(
                "whitespace-nowrap border-b-2 pb-2 pt-1 transition-colors",
                isActive
                  ? "border-primary font-bold text-foreground"
                  : "border-transparent font-medium text-muted-foreground hover:text-foreground focus-visible:text-foreground",
              )}
            >
              {tab.label}
            </Link>
          );
        })}
    </nav>
  );
}