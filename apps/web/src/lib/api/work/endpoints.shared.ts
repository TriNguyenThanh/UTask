import type { ApiClient } from "@/lib/api/client";
import { MAX_PAGE_SIZE, type ListMeta } from "@/lib/api/pagination";

export const ROOT = "/api/work";

export interface WorkListMeta extends ListMeta {
  scope?: { partial: boolean; source: "WORK_MEMBERSHIP"; teacher_scope: "UNAVAILABLE" };
}

export interface PageQuery {
  cursor?: string | null;
  pageSize?: number;
  /** Tham số lọc thêm, chỉ gửi khóa có giá trị (khóa lạ làm backend trả 422). */
  params?: Record<string, string | undefined>;
}

export function listUrl(path: string, { cursor, pageSize = MAX_PAGE_SIZE, params = {} }: PageQuery) {
  const search = new URLSearchParams({ page_size: String(pageSize) });
  if (cursor) search.set("cursor", cursor);
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") search.set(key, value);
  }
  return `${ROOT}${path}?${search.toString()}`;
}

export function fetchPage<T>(client: ApiClient, path: string, query: PageQuery) {
  return client.requestEnvelope<T[], WorkListMeta>(listUrl(path, query));
}
