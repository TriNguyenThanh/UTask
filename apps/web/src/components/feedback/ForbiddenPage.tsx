import { ShieldAlert } from "lucide-react";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";

export function ForbiddenPage({
  title = "Không đủ quyền truy cập",
  description = "Bạn không phải thành viên của dự án này, hoặc tính năng chỉ dành cho Trưởng nhóm. Nội dung dự án không được hiển thị.",
  backTo = "/my-work",
  backLabel = "Quay lại Bàn làm việc",
}: {
  title?: string;
  description?: string;
  backTo?: string;
  backLabel?: string;
} = {}) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-4 px-6 py-16 text-center">
      <div className="flex size-12 items-center justify-center rounded-lg bg-secondary">
        <ShieldAlert className="size-6 text-primary" aria-hidden />
      </div>
      <div className="space-y-1">
        <h1 className="text-lg font-semibold">{title}</h1>
        <p className="max-w-md text-sm text-muted-foreground">{description}</p>
      </div>
      <Button asChild variant="outline" size="sm">
        <Link to={backTo}>{backLabel}</Link>
      </Button>
    </div>
  );
}
