/** Quy tắc của backend (`PresignInputSerializer`); kiểm trước để không tốn một lượt presign. */
export const ATTACHMENT_TYPES = [
  "image/jpeg",
  "image/png",
  "image/webp",
  "application/pdf",
  "application/zip",
  "text/plain",
  "application/json",
] as const;

export const ATTACHMENT_MAX_BYTES = 26_214_400;
export const ATTACHMENT_NAME_MAX = 255;

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** Trả thông báo lỗi tiếng Việt, hoặc `null` khi tệp hợp lệ. */
export function validateAttachmentFile(file: { name: string; size: number; type: string }): string | null {
  if (file.size < 1) return "Tệp rỗng, hãy chọn tệp khác.";
  if (file.size > ATTACHMENT_MAX_BYTES) {
    return `Tệp ${formatBytes(file.size)} vượt giới hạn ${formatBytes(ATTACHMENT_MAX_BYTES)}.`;
  }
  if (!(ATTACHMENT_TYPES as readonly string[]).includes(file.type)) {
    return "Chỉ nhận ảnh JPEG/PNG/WebP, PDF, ZIP, văn bản thuần và JSON.";
  }
  if (file.name.length > ATTACHMENT_NAME_MAX) return `Tên tệp dài quá ${ATTACHMENT_NAME_MAX} ký tự.`;
  return null;
}
