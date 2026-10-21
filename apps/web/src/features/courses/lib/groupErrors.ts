import { ApiError } from "@/lib/api/errors";

/** Mã lỗi khi phiên bản gửi lên không còn khớp nhóm trên server. */
export const VERSION_CONFLICT = "VERSION_CONFLICT";

export const STALE_GROUP_MESSAGE = "Dữ liệu nhóm đã thay đổi, hãy thử lại.";

/** Thông báo cho lệnh nhóm thất bại: xung đột phiên bản dùng câu chung, lỗi khác giữ lời của server. */
export function groupErrorMessage(error: unknown): string {
  if (!(error instanceof ApiError)) {
    return "Không thể thực hiện thao tác. Vui lòng thử lại.";
  }
  return error.code === VERSION_CONFLICT ? STALE_GROUP_MESSAGE : error.message;
}

/** 409 nghĩa là dữ liệu đang hiển thị có thể đã cũ: cần tải lại. */
export function isConflict(error: unknown): boolean {
  return error instanceof ApiError && error.status === 409;
}
