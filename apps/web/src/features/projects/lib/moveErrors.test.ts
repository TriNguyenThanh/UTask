import { describe, expect, it } from "vitest";

import { issueWriteErrorMessage } from "@/features/projects/lib/moveErrors";
import { ApiError } from "@/lib/api/errors";

const error = (status: number, code: string | null, message = "Lỗi máy chủ") =>
  new ApiError({ status, code, message, fieldErrors: {}, details: [] });

describe("issueWriteErrorMessage", () => {
  it("explains a teacher's refused write", () => {
    expect(issueWriteErrorMessage(error(403, "TEACHER_MUTATION_RESTRICTED"))).toBe("Giảng viên chỉ xem, không sửa được.");
  });

  it("shows the server's own Vietnamese text for INVALID_OPERATION and VALIDATION_ERROR", () => {
    expect(issueWriteErrorMessage(error(400, "INVALID_OPERATION", "Dự án đang ở chế độ chỉ đọc."))).toBe("Dự án đang ở chế độ chỉ đọc.");
    expect(issueWriteErrorMessage(error(422, "VALIDATION_ERROR", "Tiêu đề quá dài."))).toBe("Tiêu đề quá dài.");
  });

  it("names a blocking cycle and shows the server text for an inactive member", () => {
    expect(issueWriteErrorMessage(error(409, "DAG_CYCLE_DETECTED", "Liên kết phụ thuộc tạo thành vòng lặp không hợp lệ."))).toBe("Liên kết này tạo vòng chặn.");
    expect(issueWriteErrorMessage(error(422, "MEMBER_NOT_ACTIVE", "Người phụ trách phải là thành viên đang hoạt động."))).toBe("Người phụ trách phải là thành viên đang hoạt động.");
  });

  it("falls back to the status for everything else", () => {
    expect(issueWriteErrorMessage(error(403, "FORBIDDEN"))).toBe("Bạn không có quyền thực hiện thay đổi này.");
    expect(issueWriteErrorMessage(error(409, "VERSION_CONFLICT"))).toBe("Issue vừa được người khác cập nhật. Bảng đã được tải lại.");
    expect(issueWriteErrorMessage(error(404, null))).toBe("Issue không còn tồn tại.");
    expect(issueWriteErrorMessage(error(0, null))).toBe("Mất kết nối đến máy chủ. Thay đổi chưa được lưu.");
    expect(issueWriteErrorMessage(new Error("x"))).toBe("Không thể cập nhật issue. Vui lòng thử lại.");
  });
});
