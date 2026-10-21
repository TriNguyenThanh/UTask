import { Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { aiErrorMessage } from "@/features/projects/lib/aiErrors";

/** Đang chạy (kèm nút Hủy) hoặc lỗi; không hiện gì khi lỗi do người dùng hủy. */
export function AiRunStatus({
  pending,
  error,
  onCancel,
}: Readonly<{ pending: boolean; error: unknown; onCancel: () => void }>) {
  if (pending) {
    return (
      <div className="flex items-center justify-between gap-2 text-sm text-muted-foreground" role="status">
        <span className="flex items-center gap-2">
          <Loader2 className="size-4 animate-spin" aria-hidden />
          AI đang phân tích… (có thể mất tới 30 giây)
        </span>
        <Button type="button" variant="outline" size="xs" onClick={onCancel}>
          Hủy
        </Button>
      </div>
    );
  }
  const message = error ? aiErrorMessage(error) : "";
  if (!message) return null;
  return (
    <p className="text-sm text-destructive" role="alert">
      {message}
    </p>
  );
}
