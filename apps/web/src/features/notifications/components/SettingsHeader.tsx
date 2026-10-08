import { NavLink } from "react-router-dom";

import { cn } from "@/lib/utils";

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
    <header className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Cài đặt Cá nhân &amp; Tích hợp</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Quản lý hồ sơ định danh học vụ sinh viên và liên kết GitHub để ghi nhận đóng góp đồ án
          tự động.
        </p>
      </div>
      <nav
        aria-label="Các trang cài đặt"
        className="flex items-center gap-6 overflow-x-auto border-b"
      >
        {settingsTabs.map((tab) => (
          <NavLink
            key={tab.to}
            to={tab.to}
            className={({ isActive }) =>
              cn(
                "-mb-px whitespace-nowrap border-b-2 pb-2.5 text-sm font-medium transition-colors",
                isActive
                  ? "border-primary font-semibold text-primary"
                  : "border-transparent text-muted-foreground hover:text-foreground",
              )
            }
          >
            {tab.label}
          </NavLink>
        ))}
      </nav>
    </header>
  );
}