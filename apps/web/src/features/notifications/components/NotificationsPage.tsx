import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import {
  CheckCheck,
  GitPullRequest,
  GraduationCap,
  Search,
  Sparkles,
} from "lucide-react";

import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import type {
  NotificationActionTarget,
  NotificationCategory,
  StudentNotification,
} from "@/features/notifications/types";
import {
  useMarkAllNotificationsRead,
  useMarkNotificationRead,
  useNotifications,
} from "@/lib/query/studentFlowHooks";
import { cn } from "@/lib/utils";

type CategoryFilter = "all" | NotificationCategory;

const categoryTabs: { id: CategoryFilter; label: string }[] = [
  { id: "all", label: "Tất cả" },
  { id: "course-team", label: "Môn học & Nhóm" },
  { id: "task-pr", label: "Jira Tasks & PR" },
  { id: "ai-risk", label: "Cảnh báo AI & Tiến độ" },
];

const categoryLabels: Record<NotificationCategory, string> = {
  "course-team": "Môn học & Nhóm",
  "task-pr": "Jira Tasks & PR",
  "ai-risk": "Cảnh báo AI & Tiến độ",
};

function categoryIcon(category: NotificationCategory) {
  switch (category) {
    case "ai-risk":
      return <Sparkles className="size-5" aria-hidden />;
    case "course-team":
      return <GraduationCap className="size-5" aria-hidden />;
    case "task-pr":
      return <GitPullRequest className="size-5" aria-hidden />;
  }
}

/** Relative time helper: "x phút trước" / "x giờ trước" / "x ngày trước". */
function formatRelative(at: string, now: Date): string {
  const diffMs = now.getTime() - new Date(at).getTime();
  const minutes = Math.floor(diffMs / 60_000);
  if (minutes < 1) return "Vừa xong";
  if (minutes < 60) return `${minutes} phút trước`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} giờ trước`;
  const days = Math.floor(hours / 24);
  return `${days} ngày trước`;
}

function targetUrl(target: NotificationActionTarget): string {
  switch (target.kind) {
    case "team-hub":
    case "team-formation":
    case "join-request":
    case "course-deadline":
      return `/courses/${target.courseId}/team`;
    case "board-issue":
      return `/projects/${target.projectId}/board?issue=${target.issueKey}`;
    case "code":
      return `/projects/${target.projectId}/code`;
    case "backlog":
      return `/projects/${target.projectId}/backlog`;
  }
}

function NotificationsSkeleton() {
  return (
    <div className="divide-y" role="status" aria-label="Đang tải thông báo">
      {Array.from({ length: 5 }, (_, index) => (
        <div key={index} className="flex items-start gap-4 py-4">
          <Skeleton className="size-9 rounded-lg" />
          <div className="flex-1 space-y-2">
            <Skeleton className="h-4 w-3/4" />
            <Skeleton className="h-3 w-1/2" />
          </div>
          <Skeleton className="h-8 w-28" />
        </div>
      ))}
    </div>
  );
}

export function NotificationsPage() {
  const navigate = useNavigate();
  const notificationsQuery = useNotifications();
  const markRead = useMarkNotificationRead();
  const markAllRead = useMarkAllNotificationsRead();

  const [category, setCategory] = useState<CategoryFilter>("all");
  const [search, setSearch] = useState("");
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [sortOrder, setSortOrder] = useState<"newest" | "oldest">("newest");

  const now = useMemo(() => new Date(), []);

  const notifications = notificationsQuery.data ?? [];
  const unreadCount = notifications.filter((item) => !item.read).length;

  const visible = useMemo(() => {
    const term = search.trim().toLowerCase();
    const filtered = notifications.filter((item) => {
      if (category !== "all" && item.category !== category) return false;
      if (unreadOnly && item.read) return false;
      if (
        term &&
        !item.title.toLowerCase().includes(term) &&
        !item.body.toLowerCase().includes(term)
      ) {
        return false;
      }
      return true;
    });
    const sorted = [...filtered].sort(
      (a, b) => new Date(a.at).getTime() - new Date(b.at).getTime(),
    );
    return sortOrder === "newest" ? sorted.reverse() : sorted;
  }, [notifications, category, unreadOnly, search, sortOrder]);

  function handleMarkAllRead() {
    markAllRead.mutate(undefined, {
      onSuccess: () => toast.success("Đã đánh dấu tất cả thông báo là đã đọc"),
      onError: () => toast.error("Không thể đánh dấu đã đọc. Vui lòng thử lại."),
    });
  }

  function handleOpen(item: StudentNotification) {
    if (!item.read) {
      markRead.mutate(item.id, {
        onError: () => toast.error("Không thể đánh dấu đã đọc. Vui lòng thử lại."),
      });
    }
    if (item.target) {
      navigate(targetUrl(item.target));
    }
  }

  function handleRowClick(item: StudentNotification) {
    if (item.read) return;
    markRead.mutate(item.id, {
      onSuccess: () => toast.success("Đã đánh dấu đã đọc"),
      onError: () => toast.error("Không thể đánh dấu đã đọc. Vui lòng thử lại."),
    });
  }

  return (
    <div className="mx-auto max-w-6xl space-y-4 px-4 pt-7 sm:px-6 lg:px-8">
      <header className="flex flex-col justify-between gap-4 border-b pb-4 md:flex-row md:items-center">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold tracking-tight">Trung tâm Thông báo</h1>
            {unreadCount > 0 ? <Badge variant="secondary">{unreadCount} mới</Badge> : null}
          </div>
          <p className="mt-1 text-sm text-muted-foreground">
            Cập nhật học vụ, thành lập nhóm, công việc Jira và cảnh báo tiến độ thông minh
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          className="self-start md:self-auto"
          onClick={handleMarkAllRead}
          disabled={unreadCount === 0 || markAllRead.isPending}
        >
          <CheckCheck className="size-4" aria-hidden />
          Đánh dấu tất cả đã đọc
        </Button>
      </header>

      <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
        <div
          className="flex items-center gap-1 overflow-x-auto rounded-md bg-secondary p-0.5 text-xs font-medium"
          role="tablist"
          aria-label="Lọc thông báo theo loại"
        >
          {categoryTabs.map((tab) => {
            const active = category === tab.id;
            return (
              <button
                key={tab.id}
                type="button"
                role="tab"
                aria-selected={active}
                onClick={() => setCategory(tab.id)}
                className={cn(
                  "flex items-center gap-1.5 whitespace-nowrap rounded px-3 py-1.5 transition-colors",
                  active
                    ? "bg-card font-semibold text-foreground"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                {tab.label}
                <span
                  className={cn(
                    "rounded-full px-1.5 text-[10px]",
                    active ? "bg-primary text-primary-foreground" : "text-muted-foreground",
                  )}
                >
                  {tab.id === "all"
                    ? notifications.length
                    : notifications.filter((item) => item.category === tab.id).length}
                </span>
              </button>
            );
          })}
        </div>
        <div className="flex flex-wrap items-center gap-4 text-xs text-muted-foreground">
          <label className="flex cursor-pointer select-none items-center gap-2">
            <Checkbox
              checked={unreadOnly}
              onCheckedChange={(checked) => setUnreadOnly(checked === true)}
              aria-label="Chỉ hiện chưa đọc"
            />
            Chỉ hiện chưa đọc
          </label>
          <div className="flex items-center gap-1">
            <span>Sắp xếp:</span>
            <Select value={sortOrder} onValueChange={(value) => setSortOrder(value as "newest" | "oldest")}>
              <SelectTrigger
                size="sm"
                className="h-7 border-0 bg-transparent px-1 text-xs font-semibold shadow-none"
                aria-label="Sắp xếp thông báo"
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="newest" className="text-xs">Mới nhất</SelectItem>
                <SelectItem value="oldest" className="text-xs">Cũ nhất</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
      </div>

      <div className="relative">
        <Search
          className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
          aria-hidden
        />
        <Input
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Tìm thông báo theo tiêu đề hoặc nội dung"
          className="pl-9 text-sm"
          aria-label="Tìm kiếm thông báo"
        />
      </div>

      {notificationsQuery.isError ? (
        <ErrorState
          error={notificationsQuery.error}
          onRetry={() => notificationsQuery.refetch()}
        />
      ) : notificationsQuery.isPending ? (
        <NotificationsSkeleton />
      ) : visible.length === 0 ? (
        <EmptyState
          title="Không có thông báo"
          description={
            notifications.length === 0
              ? "Bạn chưa có thông báo nào. Các cập nhật học vụ và đồ án sẽ xuất hiện tại đây."
              : "Không có thông báo khớp với bộ lọc hiện tại."
          }
        />
      ) : (
        <ul className="divide-y border-y">
          {visible.map((item) => (
            <li key={item.id}>
              <article
                className={cn(
                  "flex cursor-pointer items-start gap-4 rounded-lg px-3 py-4 transition-colors hover:bg-accent",
                  !item.read && "bg-primary/5",
                )}
                onClick={() => handleRowClick(item)}
                aria-label={item.read ? "Thông báo đã đọc" : "Thông báo chưa đọc"}
              >
                <div className="flex shrink-0 items-center gap-2.5 pt-0.5">
                  <span
                    title={item.read ? "Đã đọc" : "Chưa đọc"}
                    className={cn(
                      "size-2 rounded-full",
                      item.read ? "bg-transparent" : "bg-primary",
                    )}
                    aria-hidden
                  />
                  <div
                    className={cn(
                      "flex size-9 items-center justify-center rounded-lg",
                      item.read
                        ? "bg-secondary text-muted-foreground"
                        : item.category === "ai-risk"
                          ? "bg-primary/10 text-primary"
                          : "bg-secondary text-foreground",
                    )}
                  >
                    {categoryIcon(item.category)}
                  </div>
                </div>
                <div className="min-w-0 flex-1">
                  <p
                    className={cn(
                      "text-sm leading-relaxed",
                      item.read ? "text-muted-foreground" : "font-semibold text-foreground",
                    )}
                  >
                    {item.title}
                  </p>
                  <p className="mt-0.5 text-sm text-muted-foreground">{item.body}</p>
                  <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
                    <span className="font-medium">{categoryLabels[item.category]}</span>
                    <span aria-hidden>•</span>
                    <span>{formatRelative(item.at, now)}</span>
                  </div>
                </div>
                {item.actionLabel && item.target ? (
                  <div className="shrink-0 pt-0.5">
                    <Button
                      size="sm"
                      variant={item.read ? "outline" : "default"}
                      onClick={(event) => {
                        event.stopPropagation();
                        handleOpen(item);
                      }}
                    >
                      {item.actionLabel}
                    </Button>
                  </div>
                ) : null}
              </article>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}