import { IdentityProfilePage } from "@/features/notifications/components/IdentityProfilePage";
import { SettingsProfilePage } from "@/features/notifications/components/SettingsProfilePage";
import { isRealService } from "@/lib/config/services";

export function Component() {
  return isRealService("auth") ? <IdentityProfilePage /> : <SettingsProfilePage />;
}

export default Component;
