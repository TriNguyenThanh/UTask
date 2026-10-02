import { AlertCircle } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api/errors";

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const apiError = error instanceof ApiError ? error : null;
  const message = apiError?.message ?? "Đã xảy ra lỗi. Vui lòng thử lại.";

  return (
    <section className="rounded-lg border bg-card p-6" role="alert">
      <div className="flex items-start gap-3">
        <AlertCircle className="mt-0.5 size-5 text-destructive" aria-hidden="true" />
        <div>
          <h2 className="font-semibold">Không thể tải dữ liệu</h2>
          <p className="mt-1 text-sm text-muted-foreground">{message}</p>
          {apiError?.requestId ? (
            <p className="mt-1 text-xs text-muted-foreground">Request ID: {apiError.requestId}</p>
          ) : null}
          {onRetry ? <Button className="mt-4" variant="outline" onClick={onRetry}>Thử lại</Button> : null}
        </div>
      </div>
    </section>
  );
}
