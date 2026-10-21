import { z } from "zod";

const payloadSchema = z.object({ exp: z.number() });

/** Thời điểm hết hạn (giây Unix) của JWT; `null` nếu không phải JWT hợp lệ. Không xác minh chữ ký. */
export function jwtExpiry(token: string): number | null {
  const segment = token.split(".")[1];
  if (!segment) {
    return null;
  }
  try {
    const base64 = segment.replace(/-/g, "+").replace(/_/g, "/");
    const json = atob(base64.padEnd(Math.ceil(base64.length / 4) * 4, "="));
    const parsed = payloadSchema.safeParse(JSON.parse(json));
    return parsed.success ? parsed.data.exp : null;
  } catch {
    return null;
  }
}
