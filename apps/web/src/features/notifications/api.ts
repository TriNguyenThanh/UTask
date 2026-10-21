import type { StudentNotification } from "@/features/notifications/types";
import type { ApiClient } from "@/lib/api/client";

export interface NotificationPage {
  count?: number;
  next: string | null;
  previous?: string | null;
  results: StudentNotification[];
}

export type NotificationPreferences = Record<"assignment" | "deadline" | "mention" | "feedback", boolean>;

export function notificationPageRequest(client: ApiClient, next = "", signal?: AbortSignal) {
  // Follow only the query string: pagination links must never change API host/path.
  const query = next ? new URL(next, "http://localhost").search : "";
  return client.request<NotificationPage>(`/api/notifications/${query}`, { signal });
}

export function unreadNotificationCountRequest(client: ApiClient, signal?: AbortSignal) {
  return client.request<{ count: number }>("/api/notifications/unread-count", { signal });
}
