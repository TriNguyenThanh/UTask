import { useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { useRealProjectContext } from "@/features/projects/components/RealProjectLayout";
import { ApiError } from "@/lib/api/errors";
import type { ProjectRepositoryDto, ProjectRepositoryStatusDto } from "@/lib/api/work/dto";
import { RepositoryPendingTimeoutError } from "@/lib/api/work/endpoints.github";
import { isRealService } from "@/lib/config/services";
import { useGitHubAccount, useGitHubInstallations, useGitHubRepositories } from "@/lib/query/integrationHooks";
import { useProjectRepository, useSelectProjectRepository } from "@/lib/query/workGithubHooks";

/** Lỗi chọn repo → tiếng Việt; lỗi không nhận diện giữ nguyên thông điệp của máy chủ. */
export function repositoryErrorMessage(error: unknown): string {
  if (error instanceof RepositoryPendingTimeoutError) return error.message;
  if (!(error instanceof ApiError)) return error instanceof Error ? error.message : String(error);
  if (error.status === 503 && error.code === "INTEGRATION_UNAVAILABLE") {
    return "Work chưa kết nối được Integration (chờ backend, B34).";
  }
  if (error.status === 409) return "Kết nối repo đã thay đổi, đã tải lại.";
  return error.message;
}

const STATUS_LABEL: Record<ProjectRepositoryStatusDto, string> = {
  CONNECTED: "Đã kết nối",
  PENDING: "Đang kết nối",
  DISCONNECTED: "Chưa kết nối",
};

export function repositoryStatusLabel(status: ProjectRepositoryDto["status"]): string {
  return status ? (STATUS_LABEL[status] ?? "Chưa kết nối") : "Chưa kết nối";
}

function RepositoryPicker({
  projectId,
  repository,
  onDone,
}: {
  projectId: string;
  repository: ProjectRepositoryDto;
  onDone: () => void;
}) {
  const account = useGitHubAccount();
  const installations = useGitHubInstallations();
  const [installationId, setInstallationId] = useState<string | null>(null);
  const repositories = useGitHubRepositories(installationId);
  const select = useSelectProjectRepository(projectId);

  if (!isRealService("integration")) {
    return <p className="text-sm text-muted-foreground">Cần bật Integration để chọn repo.</p>;
  }
  if (account.isPending) return <Skeleton className="h-10 w-full" role="status" aria-label="Đang tải tài khoản GitHub" />;
  const active = account.data?.status === "LINKED" && account.data.authorization_status === "ACTIVE";
  if (!active) {
    return (
      <p className="text-sm text-muted-foreground">
        Cần liên kết GitHub trước.{" "}
        <Link className="underline" to="/settings/integrations">
          Mở cài đặt tích hợp
        </Link>
      </p>
    );
  }

  const installationItems = installations.data?.pages.flatMap((page) => page.items) ?? [];
  const repositoryItems = repositories.data?.pages.flatMap((page) => page.items) ?? [];

  function connect(repoId: string) {
    select.mutate(
      { githubRepoId: repoId, expectedGeneration: repository.connection_generation ?? 0 },
      {
        onSuccess: () => {
          toast.success("Đã kết nối repository.");
          onDone();
        },
      },
    );
  }

  return (
    <div className="space-y-3">
      {installations.isPending ? (
        <Skeleton className="h-10 w-full" role="status" aria-label="Đang tải danh sách cài đặt" />
      ) : installationItems.length === 0 ? (
        <p className="text-sm text-muted-foreground">Chưa cài GitHub App cho tài khoản/tổ chức nào.</p>
      ) : (
        <ul className="flex flex-wrap gap-2" aria-label="Cài đặt GitHub App">
          {installationItems.map((installation) => (
            <li key={installation.installation_id}>
              <Button
                type="button"
                size="sm"
                variant={installationId === installation.installation_id ? "default" : "outline"}
                onClick={() => setInstallationId(installation.installation_id)}
              >
                {installation.account.login}
              </Button>
            </li>
          ))}
        </ul>
      )}
      {installationId !== null ? (
        repositories.isPending ? (
          <Skeleton className="h-10 w-full" role="status" aria-label="Đang tải repository" />
        ) : repositoryItems.length === 0 ? (
          <p className="text-sm text-muted-foreground">Chưa có repository nào.</p>
        ) : (
          <ul className="divide-y rounded-md border" aria-label="Repository">
            {repositoryItems.map((item) => (
              <li key={item.repository_id} className="flex items-center justify-between gap-2 px-3 py-2 text-sm">
                <span className="font-medium">{item.full_name}</span>
                <Button
                  type="button"
                  size="sm"
                  disabled={select.isPending}
                  aria-label={`Kết nối ${item.full_name}`}
                  onClick={() => connect(item.repository_id)}
                >
                  {select.isPending && select.variables?.githubRepoId === item.repository_id ? "Đang kết nối…" : "Kết nối"}
                </Button>
              </li>
            ))}
          </ul>
        )
      ) : null}
      {repositories.hasNextPage ? (
        <Button variant="outline" size="sm" onClick={() => repositories.fetchNextPage()} disabled={repositories.isFetchingNextPage}>
          Tải thêm
        </Button>
      ) : null}
      {select.error ? (
        <p role="alert" className="text-sm text-destructive">
          {repositoryErrorMessage(select.error)}
        </p>
      ) : null}
    </div>
  );
}

export function RealProjectCode() {
  const { projectId, shell } = useRealProjectContext();
  const query = useProjectRepository(projectId);
  const [pickerOpen, setPickerOpen] = useState(false);
  const canSelect = shell.myRole === "LEADER" && shell.project.archived_at === null;

  if (query.isPending) return <Skeleton className="m-6 h-32" role="status" aria-label="Đang tải kho mã nguồn" />;
  if (query.isError) {
    return (
      <p role="alert" className="p-6 text-sm text-destructive">
        {repositoryErrorMessage(query.error)}
      </p>
    );
  }

  const repository = query.data;
  const connected = repository.github_repo_owner && repository.github_repo_name;
  return (
    <div className="space-y-4 p-4 md:p-6">
      <section className="rounded-md border bg-card">
        <div className="flex items-center justify-between gap-3 border-b px-4 py-3">
          <h2 className="font-semibold">Kho mã nguồn</h2>
          <Badge variant={repository.status === "CONNECTED" ? "default" : "secondary"}>
            {repositoryStatusLabel(repository.status)}
          </Badge>
        </div>
        <div className="space-y-2 p-4 text-sm">
          {connected ? (
            <>
              <a
                className="font-medium underline"
                href={`https://github.com/${repository.github_repo_owner}/${repository.github_repo_name}`}
                target="_blank"
                rel="noreferrer"
              >
                {repository.github_repo_owner}/{repository.github_repo_name}
              </a>
              {repository.github_default_branch ? (
                <p className="text-muted-foreground">Nhánh mặc định: {repository.github_default_branch}</p>
              ) : null}
              {repository.synced_at ? (
                <p className="text-muted-foreground">
                  Đồng bộ lúc {new Date(repository.synced_at).toLocaleString("vi-VN")}
                </p>
              ) : null}
            </>
          ) : (
            <p className="text-muted-foreground">Dự án chưa kết nối repository GitHub.</p>
          )}
          {canSelect ? (
            <Button size="sm" onClick={() => setPickerOpen(true)}>
              Chọn repository
            </Button>
          ) : null}
        </div>
      </section>
      <p className="text-sm text-muted-foreground">Hoạt động commit/PR chưa có API (B36).</p>

      <Dialog open={pickerOpen} onOpenChange={setPickerOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Chọn repository</DialogTitle>
            <DialogDescription>Chọn repository GitHub để kết nối với dự án.</DialogDescription>
          </DialogHeader>
          <RepositoryPicker projectId={projectId} repository={repository} onDone={() => setPickerOpen(false)} />
        </DialogContent>
      </Dialog>
    </div>
  );
}
