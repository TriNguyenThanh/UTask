/** Giới hạn của backend (`CommentInputSerializer.content_html`). */
export const COMMENT_MAX_LENGTH = 100_000;

/** `null` khi hợp lệ. Nội dung chỉ gồm khoảng trắng coi như rỗng. */
export function validateCommentText(text: string): string | null {
  const trimmed = text.trim();
  if (trimmed === "") return "Nhập nội dung bình luận.";
  if (trimmed.length > COMMENT_MAX_LENGTH) return `Bình luận dài quá ${COMMENT_MAX_LENGTH} ký tự.`;
  return null;
}

/** Tên người thực hiện/viết: ưu tiên tên server trả, rồi tên thành viên đã biết, cuối cùng "Chưa rõ tên". */
export function personName(
  userId: string | null,
  people: readonly { userId: string; name: string }[],
  serverName = "",
): string {
  if (serverName.trim() !== "") return serverName;
  const known = people.find((person) => person.userId === userId)?.name;
  return known && known.trim() !== "" ? known : "Chưa rõ tên";
}

export function initialsOf(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  const last = parts.at(-1) ?? "";
  return (parts.length === 1 ? last.slice(0, 2) : `${parts[0][0]}${last[0]}`).toUpperCase();
}

export function formatDateTime(value: string): string {
  return new Date(value).toLocaleString("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}
