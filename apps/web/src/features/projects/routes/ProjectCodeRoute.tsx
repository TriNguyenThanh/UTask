import {
  GitBranch,
  GitCommitHorizontal,
  GitPullRequest,
  GitFork,
  Layers3,
  Users,
} from "lucide-react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { ForbiddenPage } from "@/components/feedback/ForbiddenPage";
import { PageSkeleton } from "@/components/feedback/PageSkeleton";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type {
  CodeBranch,
  CodeCommit,
  CodeContributor,
  CodePullRequest,
  ContributorStatus,
  ProjectCode,
} from "@/features/projects/types";
import { useProjectWorkspaceContext } from "@/features/projects/routes/ProjectWorkspaceLayout";
import { useProjectCode } from "@/lib/query/studentFlowHooks";
import { ApiError } from "@/lib/api/errors";
import { cn } from "@/lib/utils";

/* ------------------------------------------------------------------ */
/* Helpers                                                             */
/* ------------------------------------------------------------------ */


function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatNumber(value: number): string {
  return value.toLocaleString("vi-VN");
}

function initialsOf(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .map((word) => word[0]?.toUpperCase() ?? "")
    .slice(0, 2)
    .join("");
}

const contributorStatusConfig: Record<
  ContributorStatus,
  { label: string; dot: string; badge: string; bar: string }
> = {
  key: {
    label: "Rất tích cực (Key)",
    dot: "bg-emerald-600",
    badge: "border-emerald-200 bg-emerald-50 text-emerald-800",
    bar: "bg-primary",
  },
  active: {
    label: "Tích cực",
    dot: "bg-blue-600",
    badge: "border-blue-200 bg-blue-50 text-blue-800",
    bar: "bg-blue-500",
  },
  watch: {
    label: "Cần theo dõi",
    dot: "bg-amber-500",
    badge: "border-amber-200 bg-amber-50 text-amber-800",
    bar: "bg-amber-500",
  },
};

/* ------------------------------------------------------------------ */
/* Sync-state banners                                                  */
/* ------------------------------------------------------------------ */

function SyncBanner({
  tone,
  title,
  children,
}: Readonly<{
  tone: "info" | "warning" | "error";
  title: string;
  children: React.ReactNode;
}>) {
  return (
    <section
      role={tone === "error" ? "alert" : "status"}
      className={cn(
        "flex flex-col items-start justify-between gap-3 rounded-md border p-3.5 text-sm md:flex-row md:items-center",
        tone === "info" && "border-border bg-secondary/40",
        tone === "warning" && "border-amber-200 bg-amber-50",
        tone === "error" && "border-red-200 bg-red-50",
      )}
    >
      <div className="flex flex-col gap-1">
        <p
          className={cn(
            "font-semibold",
            tone === "warning" && "text-amber-800",
            tone === "error" && "text-red-700",
          )}
        >
          {title}
        </p>
        <p
          className={cn(
            "text-xs text-muted-foreground",
            tone === "error" && "text-red-700/80",
          )}
        >
          {children}
        </p>
      </div>
    </section>
  );
}

function ResyncButton() {
  return (
    <Button
      variant="outline"
      size="sm"
      disabled
      title="API đồng bộ sẽ khả dụng khi backend hỗ trợ"
    >
      Đồng bộ lại
    </Button>
  );
}

/* ------------------------------------------------------------------ */
/* Synced view sections                                                */
/* ------------------------------------------------------------------ */

function RepoStrip({ code }: Readonly<{ code: ProjectCode }>) {
  const { repository, defaultBranch, latestCommitSha } = code;
  return (
    <section className="flex flex-col justify-between gap-3 rounded-md border border-border bg-secondary/40 p-3 text-xs md:flex-row md:items-center">
      <div className="flex items-center gap-2.5">
        <GitFork className="size-5 shrink-0" aria-hidden />
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-semibold">{repository}</span>
          {defaultBranch ? (
            <>
              <span className="text-subtle" aria-hidden>
                •
              </span>
              <span className="text-muted-foreground">
                Nhánh mặc định:{" "}
                <code className="rounded border border-border bg-background px-1.5 py-0.5 font-mono text-[11px] font-semibold">
                  {defaultBranch}
                </code>
              </span>
            </>
          ) : null}
          {latestCommitSha ? (
            <>
              <span className="text-subtle" aria-hidden>
                •
              </span>
              <span className="text-muted-foreground">
                Commit hash mới nhất:{" "}
                <span className="font-mono font-medium text-primary">
                  {latestCommitSha}
                </span>
              </span>
            </>
          ) : null}
        </div>
      </div>
      <div className="flex items-center gap-1.5 rounded border border-border bg-background px-2.5 py-1 text-[11px] text-muted-foreground">
        <span className="font-bold text-amber-600">💡 Smart Commit:</span>
        <span>
          Gõ kèm mã:{" "}
          <code className="rounded bg-secondary px-1 py-0.5 font-mono text-foreground">
            git commit -m "[Mã_Issue] [Nội dung]"
          </code>{" "}
          (VD: NEXUS-104 Tích hợp VNPay)
        </span>
      </div>
    </section>
  );
}

function MetricCard({
  label,
  icon,
  value,
  valueHint,
  footer,
}: Readonly<{
  label: string;
  icon: React.ReactNode;
  value: string;
  valueHint?: React.ReactNode;
  footer: React.ReactNode;
}>) {
  return (
    <div className="flex flex-col justify-between rounded-md border border-border bg-card p-3.5">
      <div className="mb-1 flex items-center justify-between text-muted-foreground">
        <span className="text-xs font-medium">{label}</span>
        <span className="text-primary" aria-hidden>
          {icon}
        </span>
      </div>
      <div className="flex items-baseline gap-2">
        <span className="text-2xl font-bold">{value}</span>
        {valueHint}
      </div>
      <div className="mt-2 border-t border-border pt-2 text-[11px] text-muted-foreground">
        {footer}
      </div>
    </div>
  );
}

function MetricsRow({ code }: Readonly<{ code: ProjectCode }>) {
  const { stats } = code;
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
      <MetricCard
        label="Tổng số Commits"
        icon={<GitCommitHorizontal className="size-4" aria-hidden />}
        value={String(stats.commits)}
        valueHint={
          stats.commitsWeekDelta > 0 ? (
            <span className="rounded bg-emerald-50 px-1.5 py-0.5 text-[11px] font-medium text-emerald-700">
              +{stats.commitsWeekDelta} tuần này
            </span>
          ) : null
        }
        footer="Đều đặn các thành viên đóng góp"
      />
      <MetricCard
        label="Pull Requests"
        icon={<GitPullRequest className="size-4 text-purple-600" aria-hidden />}
        value={String(stats.pullRequests.total)}
        valueHint={
          <span className="text-[11px] text-muted-foreground">PRs tích hợp</span>
        }
        footer={
          <span className="flex flex-wrap items-center gap-1.5">
            <span className="font-semibold text-emerald-700">
              {stats.pullRequests.merged} merged
            </span>
            <span aria-hidden>•</span>
            <span className="font-semibold text-primary">
              {stats.pullRequests.open} open
            </span>
            <span aria-hidden>•</span>
            <span className="font-semibold text-amber-600">
              {stats.pullRequests.review} review
            </span>
          </span>
        }
      />
      <MetricCard
        label="Branches Đang Mở"
        icon={<GitBranch className="size-4 text-blue-600" aria-hidden />}
        value={String(stats.branches)}
        valueHint={
          <span className="text-[11px] text-muted-foreground">
            feature branches
          </span>
        }
        footer={
          <>
            Theo chuẩn GitFlow:{" "}
            <code className="font-mono text-[10px]">feature/*</code>,{" "}
            <code className="font-mono text-[10px]">fix/*</code>
          </>
        }
      />
      <MetricCard
        label="Thay đổi Code"
        icon={<Layers3 className="size-4 text-teal-600" aria-hidden />}
        value={formatNumber(
          stats.linesChanged.added + stats.linesChanged.removed,
        )}
        valueHint={
          <span className="text-[11px] text-muted-foreground">dòng mã</span>
        }
        footer={
          <span className="flex items-center gap-1.5 font-mono">
            <span className="font-medium text-emerald-700">
              +{formatNumber(stats.linesChanged.added)}
            </span>
            <span aria-hidden>/</span>
            <span className="font-medium text-red-600">
              -{formatNumber(stats.linesChanged.removed)}
            </span>
          </span>
        }
      />
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Contributors table                                                  */
/* ------------------------------------------------------------------ */

function ContributorRow({
  contributor,
  showStatus,
}: Readonly<{
  contributor: CodeContributor;
  showStatus: boolean;
}>) {
  const status = contributorStatusConfig[contributor.status];
  const githubUrl =
    contributor.githubUsername !== null
      ? `https://github.com/${contributor.githubUsername}`
      : null;
  return (
    <tr className="transition-colors hover:bg-secondary/40">
      <td className="px-4 py-3">
        <div className="flex items-center gap-2.5">
          <div className="flex size-7 shrink-0 items-center justify-center rounded-full bg-primary/15 text-xs font-bold text-primary">
            {initialsOf(contributor.displayName)}
          </div>
          <div>
            <div className="flex items-center gap-1.5 font-semibold">
              {contributor.displayName}
              {contributor.isMe ? (
                <Badge
                  variant="outline"
                  className="border-purple-200 bg-purple-50 text-[10px] text-primary"
                >
                  Bạn
                </Badge>
              ) : null}
            </div>
            <div className="font-mono text-[11px] text-muted-foreground">
              MSSV: {contributor.studentId}
              {githubUrl ? (
                <>
                  {" • "}
                  <a
                    href={githubUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="text-primary hover:underline"
                  >
                    @{contributor.githubUsername}
                  </a>
                </>
              ) : null}
            </div>
          </div>
        </div>
      </td>
      <td className="px-3 py-3">
        <span className="font-medium">{contributor.roleTitle}</span>
      </td>
      <td className="px-3 py-3">
        <div className="flex items-center gap-2">
          <span className="font-bold">{contributor.commits}</span>
          <span className="text-[11px] text-muted-foreground">
            ({contributor.commitPercent}%)
          </span>
        </div>
        <div className="mt-1 h-1.5 w-24 overflow-hidden rounded-full bg-secondary">
          <div
            className={cn("h-full rounded-full", status.bar)}
            style={{ width: `${Math.min(100, contributor.commitPercent)}%` }}
            role="progressbar"
            aria-valuenow={contributor.commitPercent}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label={`Tỷ lệ commit của ${contributor.displayName}`}
          />
        </div>
      </td>
      <td className="px-3 py-3 font-mono text-[11px]">
        <span className="font-semibold text-emerald-700">
          +{formatNumber(contributor.additions)}
        </span>{" "}
        /{" "}
        <span className="text-red-600">-{formatNumber(contributor.deletions)}</span>
      </td>
      <td className="px-3 py-3">
        <span className="font-semibold">{contributor.pullRequestCount} PRs</span>
        <div className="text-[11px] text-muted-foreground">
          {contributor.mergedCount} merged •{" "}
          {contributor.pullRequestCount - contributor.mergedCount} open
        </div>
      </td>
      <td className="px-3 py-3">
        <span className="font-bold text-emerald-700">
          {contributor.linkedIssuePercent}%
        </span>
        <div className="text-[11px] text-muted-foreground">commits gắn Issue</div>
      </td>
      {showStatus ? (
        <td className="px-4 py-3 text-right">
          <span
            className={cn(
              "inline-flex items-center gap-1 rounded px-2 py-0.5 text-[11px] font-semibold",
              status.badge,
            )}
          >
            <span className={cn("size-1.5 rounded-full", status.dot)} aria-hidden />
            {status.label}
          </span>
        </td>
      ) : null}
    </tr>
  );
}

/**
 * `showStatus` is off for instructors: the status label judges a student's
 * contribution from commit counts, which an instructor view must not do
 * (US-5.3, scope §8.5). The raw numbers stay.
 */
function ContributorsTable({
  contributors,
  showStatus,
}: Readonly<{
  contributors: CodeContributor[];
  showStatus: boolean;
}>) {
  return (
    <section className="rounded-md border border-border bg-card">
      <div className="border-b border-border p-4">
        <h2 className="flex items-center gap-2 text-sm font-bold">
          <Users className="size-4 text-primary" aria-hidden />
          Thống kê Đóng góp của Thành viên (Contributors Breakdown)
        </h2>

      </div>
      {contributors.length === 0 ? (
        <EmptyState description="Chưa có dữ liệu đóng góp nào được ghi nhận." />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-left text-xs">
            <thead>
              <tr className="border-b border-border bg-secondary/40 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                <th className="px-4 py-2.5">Thành viên &amp; GitHub</th>
                <th className="px-3 py-2.5">Vai trò</th>
                <th className="px-3 py-2.5">Commits (%)</th>
                <th className="px-3 py-2.5 font-mono">Dòng Code (+ / -)</th>
                <th className="px-3 py-2.5">Pull Requests</th>
                <th className="px-3 py-2.5">Gắn Issue Key</th>
                {showStatus ? <th className="px-4 py-2.5 text-right">Trạng thái</th> : null}
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {contributors.map((contributor) => (
                <ContributorRow
                  key={contributor.userId}
                  contributor={contributor}
                  showStatus={showStatus}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

/* ------------------------------------------------------------------ */
/* PRs / Branches / Commits lists                                     */
/* ------------------------------------------------------------------ */

function IssueKeyLink({
  projectId,
  issueKey,
  onOpenIssue,
  muted = false,
}: Readonly<{
  projectId: string;
  issueKey: string;
  onOpenIssue: (projectId: string, issueKey: string) => void;
  muted?: boolean;
}>) {
  return (
    <button
      type="button"
      onClick={() => onOpenIssue(projectId, issueKey)}
      className={cn(
        "rounded px-1.5 py-0.5 font-mono text-[11px] font-medium text-primary hover:underline",
        muted ? "bg-secondary text-muted-foreground" : "bg-purple-50",
      )}
      aria-label={`Mở Issue ${issueKey} trên Bảng công việc`}
    >
      {issueKey}
    </button>
  );
}

function PullRequestsSection({
  projectId,
  pullRequests,
  onOpenIssue,
}: Readonly<{
  projectId: string;
  pullRequests: CodePullRequest[];
  onOpenIssue: (projectId: string, issueKey: string) => void;
}>) {
  return (
    <section className="rounded-md border border-border bg-card">
      <div className="flex items-center justify-between border-b border-border px-4 pb-2.5 pt-3">
        <h2 className="flex items-center gap-1.5 text-xs font-semibold text-primary">
          <GitPullRequest className="size-4" aria-hidden />
          Pull Requests gần đây
          <span className="rounded-full bg-purple-100 px-1.5 text-[11px] text-primary">
            {pullRequests.length}
          </span>
        </h2>
      </div>
      {pullRequests.length === 0 ? (
        <EmptyState description="Chưa có Pull Request nào được ghi nhận." />
      ) : (
        <ul className="divide-y divide-border">
          {pullRequests.map((pr) => (
            <li
              key={pr.id}
              className="flex flex-col gap-1.5 p-3.5 transition-colors hover:bg-secondary/40 md:flex-row md:items-center md:justify-between md:gap-3"
            >
              <div className="flex min-w-0 items-start gap-3">
                <GitPullRequest
                  className={cn(
                    "mt-0.5 size-4 shrink-0",
                    pr.state === "merged" ? "text-purple-600" : "text-emerald-600",
                  )}
                  aria-hidden
                />
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-[13px] font-semibold">
                      #{pr.number} {pr.title}
                    </span>
                    <Badge
                      variant="outline"
                      className={
                        pr.state === "merged"
                          ? "border-purple-200 bg-purple-50 text-[10px] font-semibold text-purple-700"
                          : "border-emerald-200 bg-emerald-50 text-[10px] font-semibold text-emerald-700"
                      }
                    >
                      {pr.state === "merged" ? "Merged" : "Open"}
                    </Badge>
                    {pr.linkedIssueKey ? (
                      <IssueKeyLink
                        projectId={projectId}
                        issueKey={pr.linkedIssueKey}
                        onOpenIssue={onOpenIssue}
                      />
                    ) : null}
                  </div>
                  <div className="mt-1 flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
                    <span>
                      Nhánh:{" "}
                      <code className="rounded bg-secondary px-1 py-0.5 font-mono text-foreground">
                        {pr.branch}
                      </code>
                    </span>
                    <span aria-hidden>•</span>
                    <span>
                      Tác giả: <strong className="text-foreground">{pr.author}</strong>
                    </span>
                    <span aria-hidden>•</span>
                    <span>{formatDateTime(pr.updatedAt)}</span>
                  </div>
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function BranchesSection({
  projectId,
  branches,
  onOpenIssue,
}: Readonly<{
  projectId: string;
  branches: CodeBranch[];
  onOpenIssue: (projectId: string, issueKey: string) => void;
}>) {
  return (
    <section className="rounded-md border border-border bg-card">
      <div className="flex items-center justify-between border-b border-border px-4 pb-2.5 pt-3">
        <h2 className="flex items-center gap-1.5 text-xs font-semibold text-primary">
          <GitBranch className="size-4" aria-hidden />
          Nhánh tính năng (Feature Branches)
          <span className="rounded-full bg-secondary px-1.5 text-[11px] text-muted-foreground">
            {branches.length}
          </span>
        </h2>
      </div>
      {branches.length === 0 ? (
        <EmptyState description="Chưa có nhánh tính năng nào đang mở." />
      ) : (
        <ul className="divide-y divide-border">
          {branches.map((branch) => (
            <li
              key={branch.id}
              className="flex flex-col gap-1.5 p-3.5 transition-colors hover:bg-secondary/40 md:flex-row md:items-center md:justify-between md:gap-3"
            >
              <div className="flex min-w-0 items-center gap-3">
                <GitBranch className="size-4 shrink-0 text-blue-600" aria-hidden />
                <code className="min-w-0 truncate font-mono text-xs font-semibold">
                  {branch.name}
                </code>
                {branch.linkedIssueKey ? (
                  <IssueKeyLink
                    projectId={projectId}
                    issueKey={branch.linkedIssueKey}
                    onOpenIssue={onOpenIssue}
                  />
                ) : null}
              </div>
              <div className="flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
                <span>
                  Tác giả:{" "}
                  <strong className="text-foreground">{branch.author}</strong>
                </span>
                <span aria-hidden>•</span>
                <span>
                  {branch.updatedDaysAgo === 0
                    ? "Cập nhật hôm nay"
                    : `Cập nhật ${branch.updatedDaysAgo} ngày trước`}
                </span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function CommitsSection({
  projectId,
  commits,
  onOpenIssue,
}: Readonly<{
  projectId: string;
  commits: CodeCommit[];
  onOpenIssue: (projectId: string, issueKey: string) => void;
}>) {
  return (
    <section className="rounded-md border border-border bg-card">
      <div className="flex items-center justify-between border-b border-border px-4 pb-2.5 pt-3">
        <h2 className="flex items-center gap-1.5 text-xs font-semibold text-primary">
          <GitCommitHorizontal className="size-4" aria-hidden />
          Lịch sử Commit gần đây
          <span className="rounded-full bg-secondary px-1.5 text-[11px] text-muted-foreground">
            {commits.length}
          </span>
        </h2>
      </div>
      {commits.length === 0 ? (
        <EmptyState description="Chưa có commit nào được đồng bộ." />
      ) : (
        <ul className="divide-y divide-border">
          {commits.map((commit) => (
            <li
              key={commit.id}
              className="flex flex-col gap-1.5 p-3.5 transition-colors hover:bg-secondary/40 md:flex-row md:items-center md:justify-between md:gap-3"
            >
              <div className="flex min-w-0 items-start gap-3">
                <GitCommitHorizontal
                  className="mt-0.5 size-4 shrink-0 text-primary"
                  aria-hidden
                />
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <code className="font-mono text-xs font-semibold text-primary">
                      {commit.sha}
                    </code>
                    <span className="text-xs font-medium">{commit.message}</span>
                    {commit.linkedIssueKey ? (
                      <IssueKeyLink
                        projectId={projectId}
                        issueKey={commit.linkedIssueKey}
                        onOpenIssue={onOpenIssue}
                        muted
                      />
                    ) : null}
                  </div>
                  <div className="mt-1 flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
                    <span>
                      Tác giả:{" "}
                      <strong className="text-foreground">{commit.author}</strong>
                    </span>
                    <span aria-hidden>•</span>
                    <span className="font-mono">{commit.branch}</span>
                    <span aria-hidden>•</span>
                    <span>{formatDateTime(commit.committedAt)}</span>
                  </div>
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/* ------------------------------------------------------------------ */
/* Main route                                                          */
/* ------------------------------------------------------------------ */

function SyncStatusBanner({
  syncState,
  readOnly,
}: Readonly<{ syncState: ProjectCode["syncState"]; readOnly: boolean }>) {
  if (syncState === "pending-webhook") {
    return (
      <SyncBanner tone="info" title="Đang chờ webhook đồng bộ">
        Dữ liệu GitHub sẽ được cập nhật tự động trong ít phút.
      </SyncBanner>
    );
  }
  if (syncState === "webhook-error") {
    return (
      <div className="flex flex-col items-start justify-between gap-3 rounded-md border border-red-200 bg-red-50 p-3.5 md:flex-row md:items-center">
        <div>
          <p className="text-sm font-semibold text-red-700">
            Webhook đồng bộ gặp lỗi
          </p>
          <p className="mt-0.5 text-xs text-red-700/80">
            Dữ liệu hiển thị có thể không mới nhất. Hãy thử đồng bộ lại.
          </p>
        </div>
        <ResyncButton />
      </div>
    );
  }
  if (syncState === "token-expired") {
    return (
      <div className="flex flex-col items-start justify-between gap-3 rounded-md border border-red-200 bg-red-50 p-3.5 md:flex-row md:items-center">
        <div>
          <p className="text-sm font-semibold text-red-700">
            Token GitHub đã hết hạn
          </p>
          <p className="mt-0.5 text-xs text-red-700/80">
            Hãy kết nối lại GitHub trong Cài đặt tích hợp để tiếp tục đồng bộ.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {readOnly ? null : (
            <Button asChild variant="outline" size="sm">
              <Link to="/settings/integrations">Kết nối lại GitHub</Link>
            </Button>
          )}
          <ResyncButton />
        </div>
      </div>
    );
  }
  if (syncState === "no-repo-permission") {
    return (
      <SyncBanner tone="warning" title="UTask chưa có quyền đọc repository">
        Hãy kiểm tra đã cấp quyền cho ứng dụng UTask trên repository của nhóm,
        sau đó đồng bộ lại.
      </SyncBanner>
    );
  }
  return null;
}

function codeUnavailableState(
  syncState: ProjectCode["syncState"],
  readOnly: boolean,
): React.ReactElement | null {
  if (syncState === "disconnected") {
    return (
      <div className="p-6">
        <EmptyState
          title="Chưa kết nối GitHub"
          description={
            readOnly
              ? "Nhóm chưa kết nối GitHub nên chưa có commit hay pull request để xem."
              : "Kết nối tài khoản GitHub để theo dõi commits, pull requests và đóng góp của từng thành viên trong dự án."
          }
          action={
            readOnly ? undefined : (
              <Button asChild size="sm">
                <Link to="/settings/integrations">Kết nối GitHub</Link>
              </Button>
            )
          }
        />
      </div>
    );
  }

  if (syncState === "no-repository") {
    return (
      <div className="p-6">
        <EmptyState
          title="Dự án chưa có repository"
          description={
            readOnly
              ? "Nhóm chưa gắn repository GitHub cho dự án này, nên chưa có dữ liệu mã nguồn để xem."
              : "Nhóm chưa gắn repository GitHub cho dự án này. Trưởng nhóm có thể gắn repository trong cài đặt tích hợp GitHub."
          }
        />
      </div>
    );
  }
  return null;
}

export default function ProjectCodeRoute() {
  const { projectId = "" } = useParams();
  const navigate = useNavigate();
  const { data, isLoading, error, refetch } = useProjectCode(projectId);
  const { readOnly } = useProjectWorkspaceContext();

  const openIssueKey = (pid: string, key: string) => {
    navigate(`/projects/${pid}/board?issue=${key}`);
  };

  if (error) {
    if (error instanceof ApiError && error.status === 403) {
      return <ForbiddenPage />;
    }
    return (
      <div className="p-6">
        <ErrorState error={error} onRetry={() => void refetch()} />
      </div>
    );
  }

  if (isLoading || !data) {
    return <PageSkeleton label="Đang tải thống kê mã nguồn" />;
  }

  const { syncState } = data;
  const unavailable = codeUnavailableState(syncState, readOnly);
  if (unavailable) return unavailable;

  const hasRepository = data.repository !== null;

  return (
    <div className="space-y-4 p-4 md:p-6">
      {hasRepository ? (
        <div className="flex justify-end">
          <Button asChild variant="outline" size="sm">
            <a
              href={`https://github.com/${data.repository}`}
              target="_blank"
              rel="noreferrer"
            >
              Mở GitHub
            </a>
          </Button>
        </div>
      ) : null}

      <SyncStatusBanner syncState={syncState} readOnly={readOnly} />

      {!hasRepository ? null : (
        <>
          <RepoStrip code={data} />
          <MetricsRow code={data} />
          <ContributorsTable contributors={data.contributors} showStatus={!readOnly} />
          <PullRequestsSection
            projectId={projectId}
            pullRequests={data.pullRequests}
            onOpenIssue={openIssueKey}
          />
          <BranchesSection
            projectId={projectId}
            branches={data.branches}
            onOpenIssue={openIssueKey}
          />
          <CommitsSection
            projectId={projectId}
            commits={data.commits}
            onOpenIssue={openIssueKey}
          />
        </>
      )}
    </div>
  );
}
export function Component() {
  return <ProjectCodeRoute />;
}
