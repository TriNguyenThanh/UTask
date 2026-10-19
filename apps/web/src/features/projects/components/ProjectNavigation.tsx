import { Link, useLocation } from "react-router-dom";

import { segmentedTabClass, segmentedTabsListClass } from "@/components/navigation/segmentedTabs";

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
    <nav aria-label="Project navigation" className={`${segmentedTabsListClass} my-3`}>
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
              className={segmentedTabClass(isActive)}
            >
              {tab.label}
            </Link>
          );
        })}
    </nav>
  );
}