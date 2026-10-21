import { newIdempotencyKey } from "@/lib/api/idempotency";

export interface DraftItem<S> {
  /** Khóa React ổn định: `key` đổi khi sửa tiêu đề nên không dùng làm khóa danh sách. */
  id: string;
  /** `Idempotency-Key` khi tạo; đổi khi nội dung gửi đi đổi. */
  key: string;
  selected: boolean;
  title: string;
  created: boolean;
  source: S;
}

const TITLE_MAX = 300;

export function toDraft<S extends { title: string }>(sources: readonly S[]): DraftItem<S>[] {
  return sources.map((source) => ({
    id: newIdempotencyKey(),
    key: newIdempotencyKey(),
    selected: true,
    title: source.title.trim().slice(0, TITLE_MAX),
    created: false,
    source,
  }));
}

function update<S>(items: readonly DraftItem<S>[], index: number, change: (item: DraftItem<S>) => DraftItem<S>) {
  return items.map((item, position) => (position === index && !item.created ? change(item) : item));
}

/** Tiêu đề đổi thì payload đổi, nên khóa idempotency đổi theo (cùng khóa + payload khác bị 409). */
export function setTitle<S>(items: readonly DraftItem<S>[], index: number, title: string): DraftItem<S>[] {
  return update(items, index, (item) => ({ ...item, title, key: newIdempotencyKey() }));
}

export function setSelected<S>(items: readonly DraftItem<S>[], index: number, selected: boolean): DraftItem<S>[] {
  return update(items, index, (item) => ({ ...item, selected }));
}

export function markCreated<S>(items: readonly DraftItem<S>[], keys: readonly string[]): DraftItem<S>[] {
  return items.map((item) => (keys.includes(item.key) ? { ...item, created: true } : item));
}

export function pendingItems<S>(items: readonly DraftItem<S>[]): DraftItem<S>[] {
  return items.filter((item) => item.selected && !item.created && item.title.trim() !== "");
}
