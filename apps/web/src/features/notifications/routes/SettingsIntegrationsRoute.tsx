import { RealGitHubIntegration } from "@/features/notifications/components/RealGitHubIntegration";
import { SettingsIntegrationsPage } from "@/features/notifications/components/SettingsIntegrationsPage";
import { isRealService } from "@/lib/config/services";

export function Component() {
  return isRealService("integration") ? <RealGitHubIntegration /> : <SettingsIntegrationsPage />;
}

export default SettingsIntegrationsPage;
