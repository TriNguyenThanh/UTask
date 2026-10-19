const CSRF_COOKIE = "csrftoken";
/** Backend chưa có endpoint CSRF riêng; trang docs đặt cookie `csrftoken` (JS đọc được). */
const WARMUP_PATH = "/api/auth/docs/";

function readCsrfCookie(): string | null {
  const entry = document.cookie.split("; ").find((item) => item.startsWith(`${CSRF_COOKIE}=`));
  return entry ? decodeURIComponent(entry.slice(CSRF_COOKIE.length + 1)) : null;
}

/** Trả token CSRF; `null` nếu backend không cấp (khi đó backend tự quyết định chấp nhận hay 403). */
export async function ensureCsrfToken(baseUrl: string): Promise<string | null> {
  const existing = readCsrfCookie();
  if (existing) {
    return existing;
  }
  try {
    await fetch(`${baseUrl.replace(/\/$/, "")}${WARMUP_PATH}`, { credentials: "include" });
  } catch {
    return null;
  }
  return readCsrfCookie();
}
