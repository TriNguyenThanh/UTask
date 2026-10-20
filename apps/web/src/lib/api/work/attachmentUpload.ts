import type { ApiClient } from "@/lib/api/client";
import { confirmAttachment, presignAttachment, uploadToStorage } from "@/lib/api/work/endpoints.collab";
import { newIdempotencyKey } from "@/lib/api/idempotency";

/**
 * Tải một tệp lên task: xin presign → `PUT` lên kho lưu trữ → xác nhận. Dừng ở bước lỗi đầu tiên và
 * ném lỗi của bước đó; không tự thử lại (presign hết hạn sau 900 giây, thử lại phải bắt đầu từ đầu).
 */
export async function uploadTaskAttachment(
  client: ApiClient,
  taskId: string,
  file: File,
  options: { fetchImpl?: typeof fetch; idempotencyKey?: string } = {},
) {
  const presign = await presignAttachment(client, taskId, {
    fileName: file.name,
    fileSize: file.size,
    contentType: file.type,
  });
  await uploadToStorage(presign, file, options.fetchImpl);
  return confirmAttachment(client, taskId, {
    attachmentId: presign.attachment_id,
    idempotencyKey: options.idempotencyKey ?? newIdempotencyKey(),
  });
}
