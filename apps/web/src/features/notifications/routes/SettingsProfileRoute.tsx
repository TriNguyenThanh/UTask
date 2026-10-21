import { NotificationPreferencesPanel } from "@/features/notifications/components/NotificationPreferencesPanel";
import { IdentityProfilePage } from "@/features/notifications/components/IdentityProfilePage";
import { SettingsProfilePage } from "@/features/notifications/components/SettingsProfilePage";
import { isRealService } from "@/lib/config/services";

export function Component() {
  return (
    <>
      {isRealService("auth") ? <IdentityProfilePage /> : <SettingsProfilePage />}
      <div className="page-container px-4 sm:px-6 lg:px-8">
        <NotificationPreferencesPanel />
      </div>
    </>
  );
}

export default Component;
