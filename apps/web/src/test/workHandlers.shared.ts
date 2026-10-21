import { HttpResponse } from "msw";

import { envelopeError } from "@/test/classroomHandlers";

export interface WorkError {
  status: number;
  code: string;
  message: string;
}

/** Yêu cầu ghi mà handler nhận được, để test kiểm header và body thật sự gửi đi. */
export interface WorkCall {
  method: string;
  path: string;
  idempotencyKey: string | null;
  body: Record<string, unknown> | null;
}

/** Phần fixture dùng chung của mọi nhóm handler. */
export interface BaseWorkFixture {
  /** Trả `meta.scope.partial` ở trang đầu của danh sách. */
  partial?: boolean;
  /** Cắt danh sách thành trang có kích thước này để thử phân trang. */
  pageSize?: number;
  calls?: WorkCall[];
}

export function failure(error: WorkError) {
  return envelopeError(error.status, error.code, error.message);
}

export function listResponse<T>(items: T[], url: URL, fixture: BaseWorkFixture, withScope: boolean) {
  const size = fixture.pageSize ?? Math.max(items.length, 1);
  const offset = Number(url.searchParams.get("cursor") ?? 0);
  const page = items.slice(offset, offset + size);
  const hasNext = offset + size < items.length;
  return HttpResponse.json({
    success: true,
    message: "OK",
    data: page,
    meta: {
      pagination: {
        total_count: items.length,
        page_size: size,
        next_cursor: hasNext ? String(offset + size) : null,
        prev_cursor: null,
        has_next: hasNext,
      },
      ...(withScope && fixture.partial && offset === 0
        ? { scope: { partial: true, source: "WORK_MEMBERSHIP", teacher_scope: "UNAVAILABLE" } }
        : {}),
    },
    error: null,
  });
}

export async function record(request: Request, fixture: BaseWorkFixture, path: string) {
  const text = await request.clone().text();
  const body = text ? (JSON.parse(text) as Record<string, unknown>) : null;
  fixture.calls?.push({
    method: request.method,
    path,
    idempotencyKey: request.headers.get("Idempotency-Key"),
    body,
  });
  return body ?? {};
}
