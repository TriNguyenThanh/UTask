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
