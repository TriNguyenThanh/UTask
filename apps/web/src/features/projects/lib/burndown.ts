import type { BurndownDayDto } from "@/lib/api/work/dto";

export interface BurndownPoint {
  x: number;
  y: number;
}

export interface BurndownLines {
  /** Điểm còn lại theo ngày. */
  remaining: BurndownPoint[];
  /** Đường lý tưởng từ phạm vi đầu kỳ về 0 ở ngày cuối. */
  ideal: BurndownPoint[];
  max: number;
}

/**
 * Dựng tọa độ SVG cho biểu đồ burndown theo điểm ước lượng còn lại. Trục Y đảo (0 ở đáy); một ngày duy nhất
 * vẽ ở giữa. Đường lý tưởng dựa trên điểm còn lại của ngày đầu, nên `null` khi chưa có ngày nào.
 */
export function burndownLines(
  days: readonly Pick<BurndownDayDto, "remaining_estimate_points">[],
  width: number,
  height: number,
): BurndownLines | null {
  if (days.length === 0) return null;
  const max = Math.max(1, ...days.map((day) => day.remaining_estimate_points));
  const xAt = (index: number) => (days.length === 1 ? width / 2 : (index / (days.length - 1)) * width);
  const yAt = (value: number) => height - (value / max) * height;
  const first = days[0].remaining_estimate_points;
  return {
    max,
    remaining: days.map((day, index) => ({ x: xAt(index), y: yAt(day.remaining_estimate_points) })),
    ideal: days.map((_, index) => ({
      x: xAt(index),
      y: yAt(days.length === 1 ? first : first * (1 - index / (days.length - 1))),
    })),
  };
}

export function toPolyline(points: readonly BurndownPoint[]): string {
  return points.map((point) => `${Math.round(point.x * 10) / 10},${Math.round(point.y * 10) / 10}`).join(" ");
}
