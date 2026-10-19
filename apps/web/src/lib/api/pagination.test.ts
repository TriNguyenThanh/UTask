import { describe, expect, it, vi } from "vitest";

import { collectAllPages, type ListMeta, type PageResult } from "@/lib/api/pagination";

function meta(hasNext: boolean, nextCursor: string | null): ListMeta {
  return {
    pagination: { total_count: 0, page_size: 100, next_cursor: nextCursor, prev_cursor: null, has_next: hasNext },
  };
}

describe("collectAllPages", () => {
  it("follows cursors until has_next is false", async () => {
    const pages: Record<string, PageResult<number>> = {
      start: { data: [1, 2], meta: meta(true, "c2") },
      c2: { data: [3], meta: meta(true, "c3") },
      c3: { data: [4], meta: meta(false, null) },
    };
    const fetchPage = vi.fn((cursor: string | null) => Promise.resolve(pages[cursor ?? "start"]));

    await expect(collectAllPages(fetchPage)).resolves.toEqual([1, 2, 3, 4]);
    expect(fetchPage.mock.calls.map(([cursor]) => cursor)).toEqual([null, "c2", "c3"]);
  });

  it("treats null data and missing meta as a single empty page", async () => {
    const fetchPage = vi.fn(() => Promise.resolve({ data: null, meta: null }));

    await expect(collectAllPages<number>(fetchPage)).resolves.toEqual([]);
    expect(fetchPage).toHaveBeenCalledTimes(1);
  });

  it("stops when has_next is true but next_cursor is null", async () => {
    const fetchPage = vi.fn(() => Promise.resolve({ data: [1], meta: meta(true, null) }));

    await expect(collectAllPages(fetchPage)).resolves.toEqual([1]);
    expect(fetchPage).toHaveBeenCalledTimes(1);
  });

  it("throws when the list exceeds maxPages", async () => {
    const fetchPage = vi.fn(() => Promise.resolve({ data: [1], meta: meta(true, "again") }));

    await expect(collectAllPages(fetchPage, 3)).rejects.toThrow("Danh sách quá dài để tải hết.");
    expect(fetchPage).toHaveBeenCalledTimes(3);
  });

  it("propagates fetch errors", async () => {
    await expect(collectAllPages(() => Promise.reject(new Error("boom")))).rejects.toThrow("boom");
  });
});
