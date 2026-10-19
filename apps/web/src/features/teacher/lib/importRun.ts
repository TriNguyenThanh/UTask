import type { ImportResultDto, ImportRowResultDto, ImportSummaryDto, StudentRowInput } from "@/lib/api/classroom/dto";
import type { ImportRow } from "@/features/teacher/lib/csvImport";

/** Dòng có lỗi định dạng không được gửi; dòng chỉ có lưu ý hoặc ghi chú vẫn gửi để hệ thống quyết định. */
export function sendableRows(rows: readonly ImportRow[]): ImportRow[] {
  return rows.filter((row) => row.issues.every((issue) => issue.level !== "error"));
}

/** Chỉ gửi khóa có giá trị; Identity từ chối khóa lạ và coi chuỗi rỗng là không có. */
export function toStudentRow(row: Pick<ImportRow, "rowNumber" | "email" | "studentId" | "firstName" | "lastName">): StudentRowInput {
  const input: StudentRowInput = { row_number: row.rowNumber };
  if (row.email) input.email = row.email;
  if (row.studentId) input.student_id = row.studentId;
  if (row.firstName) input.first_name = row.firstName;
  if (row.lastName) input.last_name = row.lastName;
  return input;
}

export function chunk<T>(items: readonly T[], size: number): T[][] {
  const batches: T[][] = [];
  for (let start = 0; start < items.length; start += size) {
    batches.push(items.slice(start, start + size));
  }
  return batches;
}

const SUMMARY_KEYS = [
  "total_records",
  "enrolled",
  "already_enrolled",
  "failed",
  "created_accounts",
  "existing_accounts",
  "flagged",
  "duplicates",
] as const satisfies readonly (keyof ImportSummaryDto)[];

export function mergeSummaries(results: readonly ImportResultDto[]): ImportSummaryDto {
  const merged: ImportSummaryDto = {
    total_records: 0,
    enrolled: 0,
    already_enrolled: 0,
    failed: 0,
    created_accounts: 0,
    existing_accounts: 0,
    flagged: 0,
    duplicates: 0,
  };
  for (const { summary } of results) {
    for (const key of SUMMARY_KEYS) merged[key] += summary[key];
  }
  return merged;
}

/** Mã `reason` của Identity (`provisioning.py`) và Classroom (`enrollments.py`). */
const REASON_LABEL: Record<string, string> = {
  VALIDATION_ERROR: "Dòng không hợp lệ: email hoặc MSSV sai định dạng, hoặc thiếu cả hai.",
  IDENTITY_CONFLICT: "Email và MSSV thuộc hai người khác nhau, hoặc MSSV khác với hồ sơ đã có.",
  ACCOUNT_UNAVAILABLE: "Tài khoản đang bị khóa hoặc đã bị xóa.",
  FLAGGED_ROLE_CONFLICT: "Email thuộc giảng viên hoặc quản trị viên; không thêm làm sinh viên.",
  STUDENT_ID_NOT_FOUND: "Chỉ có MSSV và chưa có tài khoản khớp. Thêm email để tạo tài khoản mới.",
  DUPLICATE_IN_LIST: "Trùng email hoặc MSSV với một dòng khác trong cùng lô gửi.",
  DUPLICATE_STUDENT: "Trùng với một dòng khác cùng trỏ về một sinh viên.",
  ENROLLMENT_INACTIVE: "Sinh viên từng rời hoặc bị loại khỏi lớp; không ghi danh lại bằng danh sách.",
};

export function reasonLabel(reason: string | null): string {
  if (!reason) return "Không rõ lý do.";
  return REASON_LABEL[reason] ?? `Lý do: ${reason}`;
}

export type OutcomeTone = "success" | "neutral" | "problem";

/** Tóm một dòng kết quả thành nhãn và mức độ; `FAILED` kèm lý do. */
export function describeResult(result: ImportRowResultDto): { label: string; detail: string | null; tone: OutcomeTone } {
  if (result.enrollment_result === "ENROLLED") {
    return {
      label: result.account_result === "CREATED" ? "Tạo tài khoản mới và thêm vào lớp" : "Thêm vào lớp (tài khoản có sẵn)",
      detail:
        result.account_result === "CREATED"
          ? "Tài khoản chờ kích hoạt; sinh viên kích hoạt qua email."
          : null,
      tone: "success",
    };
  }
  if (result.enrollment_result === "ALREADY_ENROLLED") {
    return { label: "Đã thuộc lớp", detail: null, tone: "neutral" };
  }
  return { label: "Không thêm được", detail: reasonLabel(result.reason), tone: "problem" };
}
