import { ApiError } from "@/lib/api/errors";

/**
 * User-facing text for a failed issue write. Chosen by error code or HTTP status; only the codes whose
 * server message is already specific Vietnamese (`INVALID_OPERATION`, `VALIDATION_ERROR`) show it.
 */
export function issueWriteErrorMessage(error: unknown): string {
  if (!(error instanceof ApiError)) return "Không thể cập nhật issue. Vui lòng thử lại.";
  if (error.code === "TEACHER_MUTATION_RESTRICTED") return "Giảng viên chỉ xem, không sửa được.";
  if ((error.code === "INVALID_OPERATION" || error.code === "VALIDATION_ERROR") && error.message) {
    return error.message;
  }
  switch (error.status) {
    case 0:
      return "Mất kết nối đến máy chủ. Thay đổi chưa được lưu.";
    case 401:
      return "Phiên đăng nhập đã hết hạn.";
    case 403:
      return "Bạn không có quyền thực hiện thay đổi này.";
    case 404:
      return "Issue không còn tồn tại.";
    case 409:
      return "Issue vừa được người khác cập nhật. Bảng đã được tải lại.";
    case 422:
      return "Thay đổi không hợp lệ. Vui lòng kiểm tra lại.";
    default:
      return "Không thể cập nhật issue. Vui lòng thử lại.";
  }
}
