import { VERSION_CONFLICT } from "@/features/courses/lib/groupErrors";
import { ApiError } from "@/lib/api/errors";

export const STALE_CLASS_MESSAGE = "Lớp học đã thay đổi, hãy xem lại dữ liệu mới rồi thử lại.";

/** Lỗi lệnh lớp: xung đột phiên bản dùng câu chung, lỗi khác giữ lời của server. */
export function classErrorMessage(error: unknown): string {
  if (!(error instanceof ApiError)) {
    return "Không thể thực hiện thao tác. Vui lòng thử lại.";
  }
  return error.code === VERSION_CONFLICT ? STALE_CLASS_MESSAGE : error.message;
}
