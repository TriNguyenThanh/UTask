import { useState } from "react";
import { toast } from "sonner";
import { ExternalLink, GitFork, Link2Off, TriangleAlert } from "lucide-react";

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
import { IntegrationFeatureColumns } from "@/features/notifications/components/SettingsIntegrationsPage";
import { SettingsHeader } from "@/features/notifications/components/SettingsHeader";
import { ApiError } from "@/lib/api/errors";
import type { GitHubAccountDto } from "@/lib/api/integration/dto";
import {
  useGitHubAccount,
  useGitHubInstallations,
  useGitHubRepositories,
  useStartGitHubAuthorization,
  useStartGitHubInstallation,
  useUnlinkGitHubAccount,
} from "@/lib/query/integrationHooks";

/** Dịch lỗi Integration sang tiếng Việt; lỗi không nhận diện được giữ nguyên thông điệp của máy chủ. */
export function githubErrorMessage(error: unknown): string {
  if (!(error instanceof ApiError)) {
    return error instanceof Error ? error.message : "Đã xảy ra lỗi. Vui lòng thử lại.";
  }
  switch (error.code) {
    case "GITHUB_UNAVAILABLE":
      return "Máy chủ chưa bật kết nối GitHub.";
    case "GITHUB_CONSENT_CONFLICT":
      return "Phiên cấp quyền đã thay đổi, vui lòng thử lại.";
    case "GITHUB_REAUTH_REQUIRED":
      return "Cần cấp quyền GitHub lại.";
    case "GITHUB_RATE_LIMITED":
      return "GitHub đang giới hạn yêu cầu, thử lại sau.";
    case "GITHUB_ACCESS_DENIED":
      return "GitHub từ chối truy cập.";
    default:
      return error.status === 400 ? "Phiên cấp quyền đã hết hạn hoặc không hợp lệ." : error.message;
  }
}

export type GitHubAccountView = "linked" | "reauth" | "revoked" | "unlinked";

/** Chỉ `LINKED` được xem là đã liên kết; giá trị lạ rơi về `unlinked` thay vì làm vỡ giao diện. */
export function githubAccountView(account: GitHubAccountDto): GitHubAccountView {
  if (account.status !== "LINKED") return "unlinked";
  switch (account.authorization_status) {
    case "ACTIVE":
      return "linked";
    case "REAUTH_REQUIRED":
      return "reauth";
    case "REVOKED":
    case "NOT_AUTHORIZED":
      return "revoked";
    default:
      return "unlinked";
  }
}

function formatDate(value: string | null): string {
  return value ? new Date(value).toLocaleDateString("vi-VN") : "—";
}

function AccountCard({ account }: { account: GitHubAccountDto }) {
  const start = useStartGitHubAuthorization();
  const unlink = useUnlinkGitHubAccount();
  const [confirmOpen, setConfirmOpen] = useState(false);
  const view = githubAccountView(account);

  function handleStart() {
    start.mutate(undefined, { onError: (error) => toast.error(githubErrorMessage(error)) });
  }

  function handleUnlink() {
    unlink.mutate(undefined, {
      onSuccess: () => {
        toast.success("Đã ngắt liên kết GitHub");
        setConfirmOpen(false);
      },
      onError: (error) => toast.error(githubErrorMessage(error)),
    });
  }

  const authorizeButton = (label: string) => (
    <Button size="sm" onClick={handleStart} disabled={start.isPending}>
      <GitFork className="size-4" aria-hidden />
      {label}
    </Button>
  );

  return (
    <div className="flex flex-col gap-5 border-y py-5 lg:flex-row lg:items-center lg:justify-between">
      <div className="flex items-start gap-4 sm:items-center">
        <div className="flex size-12 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground">
          <GitFork className="size-7" aria-hidden />
        </div>
        <div className="space-y-1">
          {view === "linked" ? (
            <>
              <div className="flex flex-wrap items-center gap-2.5">
                <span className="text-base font-bold">Đã liên kết @{account.github_username}</span>
                <a
                  href={`https://github.com/${account.github_username}`}
                  target="_blank"
                  rel="noreferrer"
                  className="flex items-center gap-0.5 text-sm text-primary hover:underline"
                >
                  github.com/{account.github_username}
                  <ExternalLink className="size-3.5" aria-hidden />
                </a>
                <Badge variant="outline" className="border-emerald-200 bg-emerald-100 font-semibold text-emerald-800">
                  Đang hoạt động
                </Badge>
              </div>
              <p className="text-sm text-muted-foreground">Liên kết từ {formatDate(account.linked_at)}</p>
            </>
          ) : view === "reauth" ? (
            <>
              <p className="flex items-center gap-2 text-base font-bold text-amber-800">
                <TriangleAlert className="size-4" aria-hidden />
                Cần cấp quyền lại
              </p>
              <p className="text-sm text-muted-foreground">
                Quyền của tài khoản @{account.github_username} đã hết hiệu lực, cần cấp quyền lại để tiếp tục.
              </p>
            </>
          ) : view === "revoked" ? (
            <>
              <p className="flex items-center gap-2 text-base font-bold text-amber-800">
                <TriangleAlert className="size-4" aria-hidden />
                Quyền GitHub đã bị thu hồi
              </p>
              <p className="text-sm text-muted-foreground">Cấp quyền lại để dùng tiếp các tính năng GitHub.</p>
            </>
          ) : (
            <>
              <p className="text-base font-bold">Chưa liên kết GitHub</p>
              <p className="text-sm text-muted-foreground">
                Liên kết tài khoản GitHub để ghi nhận commit, Pull Request và điểm đóng góp đồ án.
              </p>
            </>
          )}
        </div>
      </div>
      <div className="flex shrink-0 items-center gap-2.5">
        {view === "linked" ? (
          <Button
            variant="outline"
            size="sm"
            className="text-destructive hover:bg-destructive/10"
            onClick={() => setConfirmOpen(true)}
            disabled={unlink.isPending}
          >
            <Link2Off className="size-4" aria-hidden />
            Ngắt liên kết
          </Button>
        ) : view === "unlinked" ? (
          authorizeButton("Liên kết GitHub")
        ) : (
          authorizeButton("Cấp quyền lại")
        )}
      </div>

      <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Ngắt liên kết GitHub?</DialogTitle>
            <DialogDescription>
              Hệ thống sẽ dừng dùng tài khoản @{account.github_username}. Bạn có thể liên kết lại sau.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmOpen(false)}>
              Hủy
            </Button>
            <Button variant="destructive" onClick={handleUnlink} disabled={unlink.isPending}>
              Xác nhận ngắt liên kết
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function selectionLabel(selection: string): string {
  if (selection === "all") return "Tất cả repo";
  if (selection === "selected") return "Repo được chọn";
  return selection;
}

function RepositoryList({ installationId }: { installationId: string }) {
  const repositories = useGitHubRepositories(installationId);
  const items = repositories.data?.pages.flatMap((page) => page.items) ?? [];

  if (repositories.isError) {
    return (
      <p role="alert" className="text-sm text-destructive">
        {githubErrorMessage(repositories.error)}
      </p>
    );
  }
  if (repositories.isPending) {
    return <Skeleton className="h-10 w-full" role="status" aria-label="Đang tải repository" />;
  }
  if (items.length === 0) {
    return <p className="text-sm text-muted-foreground">Chưa có repository nào.</p>;
  }
  return (
    <div className="space-y-2">
      <ul className="divide-y rounded-md border" aria-label="Repository">
        {items.map((repository) => (
          <li key={repository.repository_id} className="flex items-center justify-between gap-2 px-3 py-2 text-sm">
            <span className="font-medium">{repository.full_name}</span>
            {repository.private ? <Badge variant="outline">Private</Badge> : null}
          </li>
        ))}
      </ul>
      {repositories.hasNextPage ? (
        <Button variant="outline" size="sm" onClick={() => repositories.fetchNextPage()} disabled={repositories.isFetchingNextPage}>
          Tải thêm
        </Button>
      ) : null}
    </div>
  );
}

function InstallationsCard({ account }: { account: GitHubAccountDto }) {
  const start = useStartGitHubInstallation();
  const installations = useGitHubInstallations();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const linked = githubAccountView(account) === "linked";
  const items = installations.data?.pages.flatMap((page) => page.items) ?? [];

  function handleStart() {
    start.mutate(undefined, { onError: (error) => toast.error(githubErrorMessage(error)) });
  }

  return (
    <section aria-labelledby="github-app-title" className="space-y-4 border-b pb-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="space-y-1">
          <h3 id="github-app-title" className="text-base font-semibold">
            GitHub App
          </h3>
          <p className="text-sm text-muted-foreground">
            {linked ? "Cài GitHub App vào tài khoản hoặc tổ chức chứa repository của đồ án." : "Cần liên kết GitHub trước."}
          </p>
        </div>
        <Button size="sm" onClick={handleStart} disabled={!linked || start.isPending}>
          {linked ? "Cài/cập nhật GitHub App" : "Cài GitHub App"}
        </Button>
      </div>

      {!linked ? null : installations.isError ? (
        <p role="alert" className="text-sm text-destructive">
          {githubErrorMessage(installations.error)}
        </p>
      ) : installations.isPending ? (
        <Skeleton className="h-12 w-full" role="status" aria-label="Đang tải danh sách cài đặt" />
      ) : items.length === 0 ? (
        <p className="text-sm text-muted-foreground">Chưa cài GitHub App cho tài khoản/tổ chức nào.</p>
      ) : (
        <div className="space-y-3">
          <ul className="space-y-2" aria-label="Cài đặt GitHub App">
            {items.map((installation) => (
              <li key={installation.installation_id}>
                <button
                  type="button"
                  onClick={() => setSelectedId(selectedId === installation.installation_id ? null : installation.installation_id)}
                  aria-expanded={selectedId === installation.installation_id}
                  className="flex w-full items-center justify-between gap-2 rounded-md border px-3 py-2 text-left text-sm hover:bg-muted"
                >
                  <span className="font-medium">
                    {installation.account.login} ({installation.account.type})
                  </span>
                  <span className="text-muted-foreground">{selectionLabel(installation.repository_selection)}</span>
                </button>
                {selectedId === installation.installation_id ? (
                  <div className="pt-2 pl-3">
                    <RepositoryList installationId={installation.installation_id} />
                  </div>
                ) : null}
              </li>
            ))}
          </ul>
          {installations.hasNextPage ? (
            <Button variant="outline" size="sm" onClick={() => installations.fetchNextPage()} disabled={installations.isFetchingNextPage}>
              Tải thêm cài đặt
            </Button>
          ) : null}
        </div>
      )}
    </section>
  );
}

export function RealGitHubIntegration() {
  const accountQuery = useGitHubAccount();

  return (
    <div className="page-container space-y-8 short:space-y-4 px-4 pt-7 short:pt-4 sm:px-6 lg:px-8">
      <SettingsHeader />
      <section aria-labelledby="integrations-section-title" className="space-y-6">
        <header className="space-y-1">
          <h2 id="integrations-section-title" className="flex items-center gap-2 text-lg font-semibold">
            <GitFork className="size-5 text-primary" aria-hidden />
            Tích hợp Tài khoản GitHub
          </h2>
          <p className="text-sm text-muted-foreground">
            Liên kết GitHub Account để hệ thống ghi nhận hoạt động mã nguồn của bạn trong đồ án.
          </p>
        </header>

        {accountQuery.isError ? (
          <div role="alert" className="flex items-start justify-between gap-4 rounded-lg border bg-card p-5">
            <div className="flex items-start gap-3">
              <TriangleAlert className="mt-0.5 size-5 text-destructive" aria-hidden />
              <p className="text-sm">{githubErrorMessage(accountQuery.error)}</p>
            </div>
            <Button variant="outline" size="sm" onClick={() => accountQuery.refetch()}>
              Thử lại
            </Button>
          </div>
        ) : accountQuery.data ? (
          <>
            <AccountCard account={accountQuery.data} />
            <InstallationsCard account={accountQuery.data} />
          </>
        ) : (
          <Skeleton className="h-24 w-full" role="status" aria-label="Đang tải trạng thái GitHub" />
        )}

        <IntegrationFeatureColumns />
      </section>
    </div>
  );
}
