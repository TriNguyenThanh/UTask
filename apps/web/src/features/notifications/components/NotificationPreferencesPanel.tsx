import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { ErrorState } from "@/components/feedback/ErrorState";
import { Checkbox } from "@/components/ui/checkbox";
import { useAuth } from "@/features/auth/AuthProvider";
import type { NotificationPreferences } from "@/features/notifications/api";
import { useApiClient } from "@/lib/api/ApiClientProvider";
import { isRealService } from "@/lib/config/services";

const labels: Record<keyof NotificationPreferences, string> = {
  assignment: "Phân công công việc",
  deadline: "Nhắc hạn công việc",
  mention: "Lượt nhắc tên",
  feedback: "Phản hồi của giảng viên",
};

export function NotificationPreferencesPanel() {
  const client = useApiClient();
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const live = isRealService("notifications");
  const queryKey = ["notification-preferences", user?.id];
  const query = useQuery({
    queryKey,
    queryFn: ({ signal }) => client.request<NotificationPreferences>("/api/notifications/preferences", { signal }),
    enabled: !!user && live,
  });
  const update = useMutation({
    mutationFn: (body: Partial<NotificationPreferences>) => client.request<NotificationPreferences>("/api/notifications/preferences", { method: "PATCH", body }),
    onSuccess: () => { void queryClient.invalidateQueries({ queryKey }); },
    onError: () => toast.error("Không thể lưu cài đặt thông báo. Vui lòng thử lại."),
  });
  if (!live) return null;
  return (
    <section aria-labelledby="notification-preferences-title" className="space-y-3 border-t py-5">
      <h2 id="notification-preferences-title" className="text-lg font-semibold">Thông báo qua email</h2>
      <p className="text-sm text-muted-foreground">Chọn các cập nhật bạn muốn nhận qua email.</p>
      {query.isError ? <ErrorState error={query.error} onRetry={() => void query.refetch()} /> : query.isPending ? (
        <p role="status">Đang tải cài đặt thông báo…</p>
      ) : (
        <fieldset disabled={update.isPending} className="space-y-3">
          <legend className="sr-only">Loại thông báo qua email</legend>
          {(Object.keys(labels) as (keyof NotificationPreferences)[]).map((key) => (
            <label key={key} className="flex items-center gap-2 text-sm">
              <Checkbox checked={query.data[key]} onCheckedChange={(checked) => update.mutate({ [key]: checked === true })} />
              {labels[key]}
            </label>
          ))}
        </fieldset>
      )}
    </section>
  );
}
