import { Link, useParams } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/feedback/EmptyState";

const MODULE_TITLES: Record<string, string> = {
  code: "Mã nguồn chưa khả dụng",
  settings: "Cài đặt dự án chưa khả dụng",
};

/**
 * Shown in real-service mode for modules not yet wired to the Work API.
 * Uses `useParams` to derive `projectId` so it works without demo context.
 */
export function WorkModuleNotIntegrated({ module }: { module: string }) {
  const { projectId = "" } = useParams();
  return (
    <div className="p-6">
      <EmptyState
        title={MODULE_TITLES[module] ?? "Chưa khả dụng"}
        description="Phần này chưa nối API Work. Hiện chỉ xem được thông tin dự án và thành viên."
        action={
          <Button asChild size="sm" variant="outline">
            <Link to={`/projects/${projectId}/info`}>Về thông tin dự án</Link>
          </Button>
        }
      />
    </div>
  );
}
