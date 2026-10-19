/**
 * Handler Classroom chỉ dùng trong test: không đăng ký ở runtime. Mô phỏng hợp
 * đồng thật (envelope, phân trang theo cursor, 404 khi không phải thành viên nhóm).
 */
import { http, HttpResponse, type HttpHandler } from "msw";

import type { ClassDto, CourseDto, EnrollmentDto, GroupDto, MemberDto, TeacherDto } from "@/lib/api/classroom/dto";
import type { PublicUserDto } from "@/lib/api/identity/dto";

export function buildClass(overrides: Partial<ClassDto> = {}): ClassDto {
  return {
    id: "class-1",
    course: "course-1",
    code: "SE100.N11",
    name: "Đồ án phần mềm",
    term: "HK1 2026–2027",
    starts_on: "2026-09-01",
    ends_on: "2027-01-15",
    status: "OPEN",
    grouping_phase: "FORMING",
    grouping_locked_at: null,
    group_min_size: 3,
    group_max_size: 5,
    join_code_expires_at: null,
    version: 1,
    event_sequence: 0,
    created_at: "2026-08-01T00:00:00Z",
    updated_at: "2026-08-01T00:00:00Z",
    ...overrides,
  };
}

export function buildCourse(overrides: Partial<CourseDto> = {}): CourseDto {
  return { id: "course-1", code: "SE100", name: "Đồ án phần mềm", created_by_id: null, archived_at: null, ...overrides };
}

export function buildGroup(overrides: Partial<GroupDto> = {}): GroupDto {
  return {
    id: "group-1",
    class_section: "class-1",
    name: "Nhóm 1",
    status: "ACTIVE",
    invite_expires_at: null,
    source_version: 1,
    created_at: "2026-09-02T00:00:00Z",
    updated_at: "2026-09-02T00:00:00Z",
    ...overrides,
  };
}

export function buildMember(overrides: Partial<MemberDto> = {}): MemberDto {
  return {
    id: "member-1",
    group_id: "group-1",
    user_id: "user-1",
    enrollment_id: "enr-1",
    role: "MEMBER",
    status: "ACTIVE",
    joined_at: "2026-09-02T00:00:00Z",
    left_at: null,
    profile: { display_name: "Nguyễn Văn An", email: "an@st.edu.vn", student_id: "6451071001" },
    ...overrides,
  };
}

export function buildEnrollment(overrides: Partial<EnrollmentDto> = {}): EnrollmentDto {
  return {
    id: "enr-1",
    class_section_id: "class-1",
    user_id: "user-1",
    status: "ACTIVE",
    source: "SELF",
    enrolled_at: "2026-09-01T00:00:00Z",
    left_at: null,
    profile: { display_name: "Nguyễn Văn An", email: "an@st.edu.vn", student_id: "6451071001" },
    ...overrides,
  };
}

export function buildTeacher(overrides: Partial<TeacherDto> = {}): TeacherDto {
  return {
    id: "teacher-1",
    user_id: "teacher-user-1",
    role: "PRIMARY",
    status: "ACTIVE",
    assigned_at: "2026-08-01T00:00:00Z",
    left_at: null,
    ...overrides,
  };
}

export interface ClassroomFixture {
  classes: ClassDto[];
  courses: CourseDto[];
  teachers?: Record<string, TeacherDto[]>;
  enrollments?: Record<string, EnrollmentDto[]>;
  groups?: Record<string, GroupDto[]>;
  /** Chỉ nhóm có trong bảng này trả được thành viên; nhóm khác trả 404 như thật. */
  members?: Record<string, MemberDto[]>;
  users?: PublicUserDto[];
}

export function envelope<T>(data: T, extra: { status?: number; hasNext?: boolean; nextCursor?: string | null } = {}) {
  const total = Array.isArray(data) ? data.length : 0;
  return HttpResponse.json(
    {
      success: true,
      message: "OK",
      data,
      meta: Array.isArray(data)
        ? {
            pagination: {
              total_count: total,
              page_size: 100,
              next_cursor: extra.nextCursor ?? null,
              prev_cursor: null,
              has_next: extra.hasNext ?? false,
            },
          }
        : null,
      error: null,
    },
    { status: extra.status ?? 200 },
  );
}

export function envelopeError(status: number, code: string, message: string) {
  return HttpResponse.json(
    { success: false, message, data: null, meta: null, error: { code, details: [] } },
    { status },
  );
}

export function classroomHandlers(fixture: ClassroomFixture): HttpHandler[] {
  return [
    http.get("/api/classroom/classes/", () => envelope(fixture.classes)),
    http.get("/api/classroom/courses/", () => envelope(fixture.courses)),
    http.get("/api/classroom/classes/:classId/", ({ params }) => {
      const found = fixture.classes.find((cls) => cls.id === params.classId);
      return found ? envelope(found) : envelopeError(404, "RESOURCE_NOT_FOUND", "Không tìm thấy lớp học.");
    }),
    http.get("/api/classroom/classes/:classId/teachers/", ({ params }) =>
      envelope(fixture.teachers?.[String(params.classId)] ?? [])),
    http.get("/api/classroom/classes/:classId/enrollments/", ({ params }) =>
      envelope(fixture.enrollments?.[String(params.classId)] ?? [])),
    http.get("/api/classroom/classes/:classId/groups/", ({ params }) =>
      envelope(fixture.groups?.[String(params.classId)] ?? [])),
    http.get("/api/classroom/groups/:groupId/members/", ({ params }) => {
      const members = fixture.members?.[String(params.groupId)];
      return members ? envelope(members) : envelopeError(404, "RESOURCE_NOT_FOUND", "Không tìm thấy nhóm học tập.");
    }),
    http.post("/api/auth/users/batch", async ({ request }) => {
      const { user_ids: ids } = (await request.json()) as { user_ids: string[] };
      return envelope({ users: (fixture.users ?? []).filter((user) => ids.includes(user.id)) });
    }),
  ];
}
