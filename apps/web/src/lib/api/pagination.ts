export interface ListMeta {
  pagination: {
    total_count: number;
    page_size: number;
    next_cursor: string | null;
    prev_cursor: string | null;
    has_next: boolean;
  };
}

export interface PageResult<T> {
  data: T[] | null;
  meta: ListMeta | null;
}

/** Số trang tối đa khi tải hết một danh sách; vượt quá coi là lỗi để tránh vòng lặp vô hạn. */
export const DEFAULT_MAX_PAGES = 50;

/** Kích thước trang tối đa Classroom/Work cho phép. */
export const MAX_PAGE_SIZE = 100;

export async function collectAllPages<T>(
  fetchPage: (cursor: string | null) => Promise<PageResult<T>>,
  maxPages = DEFAULT_MAX_PAGES,
): Promise<T[]> {
  const items: T[] = [];
  let cursor: string | null = null;

  for (let page = 0; page < maxPages; page += 1) {
    const result = await fetchPage(cursor);
    items.push(...(result.data ?? []));

    const pagination = result.meta?.pagination;
    if (!pagination?.has_next || pagination.next_cursor === null) {
      return items;
    }
    cursor = pagination.next_cursor;
  }

  throw new Error("Danh sách quá dài để tải hết.");
}
