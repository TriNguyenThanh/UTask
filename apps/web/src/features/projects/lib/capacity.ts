export const CAPACITY_MAX = 2147483647;

/** Số giờ/tuần phải là số nguyên từ 0 đến giới hạn của backend; `null` khi nhập sai. */
export function parseCapacity(text: string): number | null {
  const trimmed = text.trim();
  if (!/^\d+$/.test(trimmed)) return null;
  const value = Number(trimmed);
  return value <= CAPACITY_MAX ? value : null;
}
