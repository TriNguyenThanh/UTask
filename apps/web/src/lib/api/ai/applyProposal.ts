export interface ApplyItem<I> {
  /** `Idempotency-Key` của item: giữ nguyên khi thử lại để không tạo trùng. */
  key: string;
  input: I;
}

export interface ApplyOutcome {
  createdKeys: string[];
  failure: { key: string; error: unknown } | null;
}

/**
 * Tạo từng item theo thứ tự, dừng ở lỗi đầu tiên. AI Service không có endpoint apply và
 * `bulk-apply-ai` của Work chưa dùng được đầu-cuối (cần `verify` từ AI), nên Accept đi qua API tạo thường.
 * Không bao giờ ném lỗi: kết quả cho biết item nào đã tạo.
 */
export async function applySequentially<I>(
  items: readonly ApplyItem<I>[],
  create: (input: I, idempotencyKey: string) => Promise<unknown>,
  onProgress?: (done: number, total: number) => void,
): Promise<ApplyOutcome> {
  const createdKeys: string[] = [];
  for (const item of items) {
    try {
      await create(item.input, item.key);
    } catch (error) {
      return { createdKeys, failure: { key: item.key, error } };
    }
    createdKeys.push(item.key);
    onProgress?.(createdKeys.length, items.length);
  }
  return { createdKeys, failure: null };
}
