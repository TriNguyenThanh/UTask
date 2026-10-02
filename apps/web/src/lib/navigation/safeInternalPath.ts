export function isSafeInternalPath(value: unknown): value is string {
  if (typeof value !== "string" || value.length === 0 || value.length > 2048) {
    return false;
  }
  if (!value.startsWith("/") || value.startsWith("//") || value.includes("\\")) {
    return false;
  }
  return true;
}