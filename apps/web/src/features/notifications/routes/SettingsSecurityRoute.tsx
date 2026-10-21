import { IdentitySecurityPage } from "@/features/notifications/components/IdentitySecurityPage";
import { SettingsSecurityPage } from "@/features/notifications/components/SettingsSecurityPage";
import { isRealService } from "@/lib/config/services";

export function Component() {
  return isRealService("auth") ? <IdentitySecurityPage /> : <SettingsSecurityPage />;
}

export default Component;
