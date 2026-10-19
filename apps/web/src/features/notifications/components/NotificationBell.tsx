import { Bell } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/features/auth/AuthProvider";
import { canUseTeacherSpace, isStudentAccount } from "@/features/auth/utils";
import { formatRelative, targetUrl } from "@/features/notifications/lib/format";
import {
  useMarkAllNotificationsRead,
  useMarkNotificationRead,
  useNotifications,
} from "@/lib/query/studentFlowHooks";

const PREVIEW_COUNT = 5;

/** Chuông thông báo trên top bar: 5 thông báo mới nhất, mở nhanh đích liên quan. */
export function NotificationBell() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const query = useNotifications();
  const markRead = useMarkNotificationRead();
  const markAllRead = useMarkAllNotificationsRead();
  const now = useMemo(() => new Date(), []);
  const teacherOnly = canUseTeacherSpace(user) && !isStudentAccount(user);

  const items = query.data ?? [];
  const unreadCount = items.filter((item) => !item.read).length;
  const latest = [...items]
    .sort((a, b) => new Date(b.at).getTime() - new Date(a.at).getTime())
    .slice(0, PREVIEW_COUNT);

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="relative"
          aria-label={unreadCount > 0 ? `Thông báo (${unreadCount} chưa đọc)` : "Thông báo"}
        >
          <Bell className="size-4" aria-hidden />
          {unreadCount > 0 ? (
            <Badge className="absolute -right-1 -top-1 size-4 justify-center rounded-full px-0 text-[10px]">
              {unreadCount}
            </Badge>
          ) : null}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-80 p-0">
        <div className="flex items-center justify-between border-b px-4 py-2.5">
          <p className="text-sm font-semibold">Thông báo</p>
          {unreadCount > 0 ? (
            <Button
              type="button"
              variant="link"
              size="sm"
              className="h-auto p-0 text-xs"
              onClick={() => markAllRead.mutate()}
            >
              Đánh dấu tất cả đã đọc
            </Button>
          ) : null}
        </div>
        <div className="max-h-96 overflow-y-auto">
          {query.isPending ? (
            <div className="space-y-2 p-3" role="status" aria-label="Đang tải thông báo">
              {Array.from({ length: 3 }, (_, index) => (
                <Skeleton key={index} className="h-10 w-full" />
              ))}
            </div>
          ) : query.isError ? (
            <div className="space-y-2 p-4 text-sm">
              <p>Không thể tải thông báo.</p>
              <Button type="button" variant="outline" size="sm" onClick={() => void query.refetch()}>
                Thử lại
              </Button>
            </div>
          ) : latest.length === 0 ? (
            <p className="p-4 text-sm text-muted-foreground">Không có thông báo nào.</p>
          ) : (
            <ul className="divide-y">
              {latest.map((item) => (
                <li key={item.id}>
                  <button
                    type="button"
                    className="flex w-full items-start gap-2 px-4 py-2.5 text-left hover:bg-muted"
                    onClick={() => {
                      if (!item.read) markRead.mutate(item.id);
                      if (item.target) {
                        setOpen(false);
                        navigate(targetUrl(item.target, teacherOnly));
                      }
                    }}
                  >
                    <span
                      className={
                        item.read
                          ? "mt-1.5 size-2 shrink-0"
                          : "mt-1.5 size-2 shrink-0 rounded-full bg-primary"
                      }
                      aria-hidden
                    />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-medium">{item.title}</span>
                      <span className="block text-xs text-muted-foreground">
                        {formatRelative(item.at, now)}
                      </span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div className="border-t px-4 py-2.5 text-center">
          <Link
            to="/notifications"
            className="text-sm font-medium text-primary hover:underline"
            onClick={() => setOpen(false)}
          >
            Xem tất cả thông báo
          </Link>
        </div>
      </PopoverContent>
    </Popover>
  );
}
