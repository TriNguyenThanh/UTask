import { useMemo, useState } from "react";
import { toast } from "sonner";
import {
  ExternalLink,
  GitCommitHorizontal,
  GitFork,
  Link2Off,
  RefreshCw,
  TriangleAlert,
  Webhook,
} from "lucide-react";

import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { SettingsHeader } from "@/features/notifications/components/SettingsHeader";
import type { GitHubIntegrationState } from "@/features/notifications/types";
import { useAccountSettings, useDisconnectGitHub } from "@/lib/query/studentFlowHooks";

function formatRelative(at: string, now: Date): string {
  const diffMs = now.getTime() - new Date(at).getTime();
  const minutes = Math.floor(diffMs / 60_000);
  if (minutes < 1) return "Vừa xong";
  if (minutes < 60) return `${minutes} phút trước`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} giờ trước`;
  return `${Math.floor(hours / 24)} ngày trước`;
}

const featureColumns = [
  {
    title: "Ghi nhận Commit & Issue Key",
    description:
      "Tự động ánh xạ commit hash chứa mã định danh công việc (ví dụ NEXUS-12) vào bảng theo dõi đồ án học kỳ.",
  },
  {
    title: "Pull Request & Peer Review",
    description:
      "Ghi nhận hoạt động duyệt mã nguồn (code review), thảo luận kỹ thuật và số lượng PR được merge chuẩn GitHub Flow.",
  },
  {
    title: "Tính Điểm Đóng Góp",
    description:
      "Thuật toán UTask tổng hợp tần suất đẩy code, số dòng thay đổi và tính đều đặn qua các tuần Sprint để giảng viên chấm điểm công bằng.",
  },
];

function ConnectedBanner({
  github,
  now,
  onDisconnect,
  disconnectPending,
}: {
  github: GitHubIntegrationState;
  now: Date;
  onDisconnect: () => void;
  disconnectPending: boolean;
}) {
  return (
    <div className="flex flex-col gap-5 border-y py-5 lg:flex-row lg:items-center lg:justify-between">
      <div className="flex items-start gap-4 sm:items-center">
        <div className="flex size-12 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground">
          <GitFork className="size-7" aria-hidden />
        </div>
        <div className="space-y-1">
          <div className="flex flex-wrap items-center gap-2.5">
            <span className="text-base font-bold">@{github.username}</span>
            {github.profileUrl ? (
              <a
                href={github.profileUrl}
                target="_blank"
                rel="noreferrer"
                className="flex items-center gap-0.5 text-sm text-primary hover:underline"
              >
                github.com/{github.username}
                <ExternalLink className="size-3.5" aria-hidden />
              </a>
            ) : null}
            <Badge
              variant="outline"
              className="gap-1 border-emerald-200 bg-emerald-100 font-semibold text-emerald-800"
            >
              <span className="size-1.5 rounded-full bg-emerald-600" aria-hidden />
              {github.status === "connected"
                ? "Đã kết nối & Đồng bộ Webhook"
                : "Đồng bộ Webhook"}
            </Badge>
          </div>
          <p className="flex items-center gap-1.5 text-sm text-muted-foreground">
            Đồng bộ tự động {github.lastSyncedAt ? formatRelative(github.lastSyncedAt, now) : "—"} •
            Repositories: {github.linkedRepositoryCount} môn học liên kết
          </p>
        </div>
      </div>
      <div className="flex shrink-0 items-center gap-2.5">
        <Button
          variant="outline"
          size="sm"
          disabled
          title="Kiểm tra kết nối lại sẽ khả dụng khi backend hỗ trợ"
        >
          <RefreshCw className="size-4" aria-hidden />
          Kiểm tra kết nối lại
        </Button>
        <Button
          variant="outline"
          size="sm"
          className="text-destructive hover:bg-destructive/10"
          onClick={onDisconnect}
          disabled={disconnectPending}
        >
          <Link2Off className="size-4" aria-hidden />
          Ngắt kết nối
        </Button>
      </div>
    </div>
  );
}

function IntegrationsSkeleton() {
  return (
    <div className="space-y-6" role="status" aria-label="Đang tải trạng thái tích hợp">
      <Skeleton className="h-8 w-80" />
      <Skeleton className="h-24 w-full" />
      <div className="grid gap-6 md:grid-cols-3">
        <Skeleton className="h-40" />
        <Skeleton className="h-40" />
        <Skeleton className="h-40" />
      </div>
    </div>
  );
}

export function SettingsIntegrationsPage() {
  const settingsQuery = useAccountSettings();
  const disconnectGitHub = useDisconnectGitHub();
  const [confirmOpen, setConfirmOpen] = useState(false);
  const now = useMemo(() => new Date(), []);

  const settings = settingsQuery.data;
  const github = settings?.github;

  function handleDisconnect() {
    disconnectGitHub.mutate(undefined, {
      onSuccess: () => {
        toast.success("Đã ngắt kết nối GitHub");
        setConfirmOpen(false);
      },
      onError: () => toast.error("Không thể ngắt kết nối. Vui lòng thử lại."),
    });
  }

  if (settingsQuery.isError) {
    return (
      <div className="mx-auto max-w-6xl space-y-6 px-4 pt-7 sm:px-6 lg:px-8">
        <SettingsHeader />
        <ErrorState error={settingsQuery.error} onRetry={() => settingsQuery.refetch()} />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-6xl space-y-8 px-4 pt-7 sm:px-6 lg:px-8">
      <SettingsHeader />

      {settingsQuery.isPending || !settings || !github ? (
        <IntegrationsSkeleton />
      ) : (
        <section aria-labelledby="integrations-section-title" className="space-y-6">
          <header className="space-y-1">
            <h2 id="integrations-section-title" className="flex items-center gap-2 text-lg font-semibold">
              <GitFork className="size-5 text-primary" aria-hidden />
              Tích hợp Tài khoản GitHub
            </h2>
            <p className="text-sm text-muted-foreground">
              Liên kết GitHub Account để hệ thống tự động đồng bộ commit, tính điểm đóng góp cá
              nhân và kiểm tra tiến độ Sprint qua Webhook.
            </p>
          </header>

          {github.status === "connected" || github.status === "connecting" ? (
            <ConnectedBanner
              github={github}
              now={now}
              onDisconnect={() => setConfirmOpen(true)}
              disconnectPending={disconnectGitHub.isPending}
            />
          ) : github.status === "token-expired" ? (
            <div className="flex flex-col items-start justify-between gap-4 border-y border-amber-200 bg-amber-50 py-5 text-amber-900 lg:flex-row lg:items-center">
              <div className="flex items-start gap-3">
                <TriangleAlert className="mt-0.5 size-5 shrink-0" aria-hidden />
                <div>
                  <p className="font-semibold">Token hết hạn</p>
                  <p className="text-sm">
                    Tài khoản @{github.username} đã kết nối nhưng token OAuth đã hết hạn. Cần kết
                    nối lại để tiếp tục đồng bộ commit và Pull Request.
                  </p>
                </div>
              </div>
              <Button
                size="sm"
                disabled
                title="Kết nối lại sẽ khả dụng khi backend hỗ trợ OAuth"
                className="shrink-0"
              >
                Kết nối lại
              </Button>
            </div>
          ) : (
            <EmptyState
              title="Chưa kết nối GitHub"
              description="Liên kết tài khoản GitHub để tự động ghi nhận commit, Pull Request và điểm đóng góp đồ án."
              action={
                <Button disabled title="OAuth sẽ khả dụng khi backend hỗ trợ">
                  <GitFork className="size-4" aria-hidden />
                  Kết nối GitHub
                </Button>
              }
            />
          )}

          <div className="grid grid-cols-1 gap-6 pb-2 md:grid-cols-3">
            {featureColumns.map((column) => (
              <div
                key={column.title}
                className="flex flex-col justify-between space-y-3 border-l-2 pl-4"
              >
                <div className="space-y-1.5">
                  <div className="flex size-8 items-center justify-center rounded bg-secondary text-primary">
                    <GitCommitHorizontal className="size-4" aria-hidden />
                  </div>
                  <h3 className="text-sm font-bold">{column.title}</h3>
                  <p className="text-sm leading-relaxed text-muted-foreground">
                    {column.description}
                  </p>
                </div>
              </div>
            ))}
          </div>

          <div className="flex items-start gap-2.5 border-t py-3 text-sm text-muted-foreground">
            <Webhook className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden />
            <p>
              Payload Secret Token đang được lưu trữ an toàn. Khi đẩy code vào repository nhóm môn
              học, Webhook sẽ tự gửi tín hiệu về UTask.
            </p>
          </div>

          <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
            <DialogContent className="sm:max-w-md">
              <DialogHeader>
                <DialogTitle>Bạn chắc chắn?</DialogTitle>
                <DialogDescription>
                  Ngắt kết nối GitHub sẽ dừng đồng bộ commit, Pull Request và điểm đóng góp từ tài
                  khoản @{github.username}. Hành động này có thể kết nối lại sau.
                </DialogDescription>
              </DialogHeader>
              <DialogFooter>
                <Button variant="outline" onClick={() => setConfirmOpen(false)}>
                  Hủy
                </Button>
                <Button
                  variant="destructive"
                  onClick={handleDisconnect}
                  disabled={disconnectGitHub.isPending}
                >
                  Ngắt kết nối
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </section>
      )}
    </div>
  );
}