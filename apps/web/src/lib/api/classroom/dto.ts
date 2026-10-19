/**
 * DTO của Classroom Service (`/api/classroom`), đối chiếu với serializer trong
 * `apps/classroom-service`. Enum lấy từ ràng buộc CHECK của model.
 */

export type ClassStatus = "OPEN" | "CLOSED" | "ARCHIVED";
export type GroupingPhase = "FORMING" | "LOCKED";
export type GroupStatus = "ACTIVE" | "ARCHIVED";
export type MemberRole = "LEADER" | "MEMBER";
export type MemberStatus = "ACTIVE" | "LEFT" | "REMOVED";
export type TeacherRole = "PRIMARY" | "CO_TEACHER";
export type TeacherStatus = "ACTIVE" | "LEFT";
export type EnrollmentStatus = "ACTIVE" | "LEFT" | "REMOVED";
export type EnrollmentSource = "SELF" | "TEACHER" | "BATCH";

/** Lớp học phần. Phía FE gọi là "course"; `course` là UUID của môn. */
export interface ClassDto {
  id: string;
  course: string;
  code: string;
  name: string;
  term: string;
  starts_on: string;
  ends_on: string;
  status: ClassStatus;
  grouping_phase: GroupingPhase;
  grouping_locked_at: string | null;
  group_min_size: number;
  group_max_size: number;
  join_code_expires_at: string | null;
  version: number;
  event_sequence: number;
  created_at: string;
  updated_at: string;
}

/** Môn học (code, name). Không có `GET /courses/{id}/`, chỉ có danh sách. */
export interface CourseDto {
  id: string;
  code: string;
  name: string;
  created_by_id: string | null;
  archived_at: string | null;
}

export interface TeacherDto {
  id: string;
  user_id: string;
  role: TeacherRole;
  status: TeacherStatus;
  assigned_at: string;
  left_at: string | null;
}

/** Hồ sơ rút gọn do backend điền từ Identity; rỗng khi Identity lỗi. */
export type ProfileDto = Partial<{
  display_name: string;
  email: string;
  student_id: string | null;
  avatar_url: string | null;
}> &
  Record<string, unknown>;

export interface EnrollmentDto {
  id: string;
  class_section_id: string;
  user_id: string;
  status: EnrollmentStatus;
  source: EnrollmentSource;
  enrolled_at: string;
  left_at: string | null;
  profile?: ProfileDto;
}

export interface GroupDto {
  id: string;
  class_section: string;
  name: string;
  status: GroupStatus;
  invite_expires_at: string | null;
  source_version: number;
  created_at: string;
  updated_at: string;
}

export interface MemberDto {
  id: string;
  group_id: string;
  user_id: string;
  enrollment_id: string;
  role: MemberRole;
  status: MemberStatus;
  joined_at: string;
  left_at: string | null;
  profile?: ProfileDto;
}

export interface ProjectLinkDto {
  id: string;
  class_section_id: string;
  group_id: string;
  project_id: string;
  linked_at: string;
}

/** Kết quả cấp/tắt mã. `code` (mã thô) chỉ có đúng một lần, ngay lúc cấp. */
export interface AccessCodeDto {
  id: string;
  version: number;
  code?: string;
  expires_at: string | null;
  enabled: boolean;
}

/** Một dòng gửi lên `POST /classes/{id}/students/`. Identity từ chối khóa lạ nên chỉ gửi các khóa này. */
export interface StudentRowInput {
  row_number: number;
  email?: string;
  student_id?: string;
  first_name?: string;
  last_name?: string;
}

export type AccountResult = "CREATED" | "EXISTING" | "FLAGGED" | "FAILED" | "NOT_REQUESTED";
export type EnrollmentResult = "ENROLLED" | "ALREADY_ENROLLED" | "FAILED";

/** Kết quả từng dòng; `reason` là mã lỗi của Identity hoặc Classroom (xem `importReasons`). */
export interface ImportRowResultDto {
  row_number: number | null;
  user_id: string | null;
  email: string | null;
  student_id: string | null;
  account_status: string | null;
  account_result: AccountResult;
  reason: string | null;
  enrollment_id?: string;
  enrollment_result: EnrollmentResult;
}

export interface ImportSummaryDto {
  total_records: number;
  enrolled: number;
  already_enrolled: number;
  failed: number;
  created_accounts: number;
  existing_accounts: number;
  flagged: number;
  duplicates: number;
}

export interface ImportResultDto {
  summary: ImportSummaryDto;
  results: ImportRowResultDto[];
}

export interface AdjustResultDto {
  user_id: string;
  group_id: string | null;
}

/** Lịch sử thay đổi; hình dạng `changes` chưa được backend chốt (B4f) nên không đọc nội dung. */
export interface ActivityDto {
  id: string;
  class_section_id: string;
  actor_user_id: string | null;
  verb: string;
  subject_type: string;
  subject_id: string;
  changes: Record<string, unknown>;
  created_at: string;
}
