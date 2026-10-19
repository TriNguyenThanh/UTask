export type RealService = "auth" | "classroom" | "work";

const REAL_SERVICES: readonly RealService[] = ["auth", "classroom", "work"];

/**
 * Phân tích `VITE_REAL_SERVICES` (danh sách cách nhau bởi dấu phẩy).
 * Giá trị lạ làm lỗi ngay để tránh gõ sai tên mà vẫn chạy mock.
 */
export function parseRealServices(raw: string | undefined): ReadonlySet<RealService> {
  const result = new Set<RealService>();

  for (const token of (raw ?? "").split(",")) {
    const name = token.trim();
    if (!name) {
      continue;
    }
    if (!REAL_SERVICES.includes(name as RealService)) {
      throw new Error(`VITE_REAL_SERVICES chứa giá trị không hợp lệ: ${name}`);
    }
    result.add(name as RealService);
  }

  return result;
}

/** Đọc env mỗi lần gọi để test dùng được `vi.stubEnv`. */
export function isRealService(service: RealService): boolean {
  return parseRealServices(import.meta.env.VITE_REAL_SERVICES).has(service);
}
