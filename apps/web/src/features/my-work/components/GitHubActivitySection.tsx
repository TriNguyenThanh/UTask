import { GitBranch, GitPullRequest } from "lucide-react";
import type { GitHubActivity } from "@/features/my-work/types";

import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import type { GitHubPullRequest } from "@/features/my-work/types";

function relativeTime(iso: string, now: Date): string {
  const diffMs = now.getTime() - new Date(iso).getTime();
  const minutes = Math.round(diffMs / 60_000);
  if (minutes < 60) {
    return `${minutes} phút trước`;
  }
  const hours = Math.round(minutes / 60);
  if (hours < 24) {
    return `${hours} giờ trước`;
  }
  return `${Math.round(hours / 24)} ngày trước`;
}

function PullRequestRow({ pr, now }: { pr: GitHubPullRequest; now: Date }) {
  const awaiting = pr.kind === "awaiting-review";
  return (
    <li className="flex flex-col justify-between gap-3 px-2 py-3.5 transition-colors hover:bg-secondary/50 md:flex-row md:items-center md:gap-4">
      <div className="flex min-w-0 flex-1 items-center gap-3">
        <GitPullRequest className="size-5 shrink-0 text-emerald-600" aria-hidden />
        <div className="min-w-0 flex-1">
          <div className="flex min-w-0 items-center gap-2">
            <a
              href={`#pr-${pr.number}`}
              className="block min-w-0 truncate text-sm font-semibold transition-colors hover:text-primary"
              aria-label={`Pull request ${pr.title} (chi tiết sẽ khả dụng ở slice GitHub)`}
            >
              PR #{pr.number}: {pr.title}
            </a>
          </div>
          <div className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <span className="font-mono">{pr.repository}</span>
            <span aria-hidden>•</span>
            <span>Tác giả: {pr.author}</span>
            <span aria-hidden>•</span>
            <span>{relativeTime(pr.updatedAt, now)}</span>
          </div>
        </div>
      </div>
      <div className="flex shrink-0 flex-wrap items-center gap-3">
        <span
          className={`inline-flex items-center gap-1 rounded px-2.5 py-1 text-xs font-semibold ${
            awaiting ? "bg-secondary text-muted-foreground" : "bg-primary-subtle text-primary"
          }`}
        >
          {awaiting ? "Chờ người khác review" : "Chờ bạn review"}
        </span>
        <Button
          asChild
          size="sm"
          disabled
          title="Review PR sẽ khả dụng ở slice GitHub"
        >
          <a href={`#review-pr-${pr.number}`} aria-disabled="true" tabIndex={-1}>
            Xem Diff &amp; Review
          </a>
        </Button>
      </div>
    </li>
  );
}

function GitHubSkeleton() {
  return (
    <div className="space-y-3" role="status" aria-label="Đang tải hoạt động GitHub">
      <Skeleton className="h-14 w-full" />
      <Skeleton className="h-14 w-full" />
    </div>
  );
}

export function GitHubActivitySection({
  activity,
  now,
  isLoading,
  error,
  onRetry,
}: {
  activity: GitHubActivity | undefined;
  now: Date;
  isLoading: boolean;
  error: unknown;
  onRetry: () => void;
}) {
  return (
    <section aria-labelledby="github-title" className="space-y-3 pt-2">
      <div className="flex items-center justify-between border-b pb-2.5">
        <h2 id="github-title" className="flex items-center gap-2 text-base font-bold">
          <GitBranch className="size-5" aria-hidden />
          Hoạt động GitHub liên quan
        </h2>
        {activity && activity.sync.state === "connected" ? (
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <span className="size-2 rounded-full bg-emerald-500" aria-hidden />
            <span>Đồng bộ Webhook tự động</span>
          </div>
        ) : null}
      </div>

      {error ? (
        <ErrorState
          error={error}
          onRetry={onRetry}
        />
      ) : isLoading ? (
        <GitHubSkeleton />
      ) : !activity ? null : activity.sync.state === "disconnected" ? (
        <EmptyState
          title="Chưa kết nối GitHub"
          description="Kết nối tài khoản GitHub để nhận thông tin Pull Request, commit và trạng thái đồng bộ repository của đồ án."
          action={
            <Button disabled title="Kết nối GitHub sẽ khả dụng ở slice Settings">
              Kết nối GitHub
            </Button>
          }
        />
      ) : activity.sync.linkedProjectCount === 0 ? (
        <EmptyState
          title="Chưa thuộc project nào"
          description="Tài khoản GitHub đã được kết nối. Hoạt động repository sẽ xuất hiện sau khi bạn tham gia project của nhóm đồ án."
        />
      ) : activity.pullRequests.length === 0 && activity.commits.length === 0 ? (
        <EmptyState
          title="Chưa có hoạt động"
          description="Chưa có Pull Request hoặc commit nào liên quan đến nhiệm vụ của bạn trong 7 ngày qua."
        />
      ) : (
        <div className="space-y-3">
          {activity.pullRequests.length > 0 ? (
            <ul className="divide-y border-y">
              {activity.pullRequests.map((pr) => (
                <PullRequestRow key={pr.id} pr={pr} now={now} />
              ))}
            </ul>
          ) : null}
          {activity.commits.length > 0 ? (
            <ul className="space-y-1.5" aria-label="Commit liên kết nhiệm vụ">
              {activity.commits.map((commit) => (
                <li
                  key={commit.id}
                  className="flex flex-wrap items-center gap-2 px-2 text-xs text-muted-foreground"
                >
                  <GitBranch className="size-3.5 shrink-0" aria-hidden />
                  <span className="font-mono text-foreground">{commit.message}</span>
                  <span aria-hidden>•</span>
                  <span className="font-mono">{commit.branchName}</span>
                  {commit.issueKey ? (
                    <span className="rounded bg-primary-subtle px-1.5 py-0.5 font-mono font-semibold text-primary">
                      {commit.issueKey}
                    </span>
                  ) : null}
                  <span aria-hidden>•</span>
                  <span>{relativeTime(commit.committedAt, now)}</span>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      )}
    </section>
  );
}