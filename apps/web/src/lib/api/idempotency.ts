/**
 * Khóa chống tạo trùng cho POST/PATCH của Classroom và Work.
 * Sinh một lần cho mỗi ý định của người dùng (xem biến mutation), không sinh lại khi retry.
 */
export function newIdempotencyKey(): string {
  return crypto.randomUUID();
}
