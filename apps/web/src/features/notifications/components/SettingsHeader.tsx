import { NavLink } from "react-router-dom";

import { segmentedTabClass, segmentedTabsListClass } from "@/components/navigation/segmentedTabs";

const settingsTabs = [
  { to: "/settings/profile", label: "Hồ sơ" },
  { to: "/settings/integrations", label: "Tích hợp" },
  { to: "/settings/security", label: "Bảo mật" },
];

/**
 * Shared page header + tab navigation for the three /settings routes.
 */
export function SettingsHeader() {
  return (
    <header className="space-y-4 short:space-y-2">
      <nav aria-label="Các trang cài đặt" className={segmentedTabsListClass}>
        {settingsTabs.map((tab) => (
          <NavLink
            key={tab.to}
            to={tab.to}
            className={({ isActive }) => segmentedTabClass(isActive)}
          >
            {tab.label}
          </NavLink>
        ))}
      </nav>
    </header>
  );
}