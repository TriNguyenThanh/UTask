import type { QueryClient } from "@tanstack/react-query";

import type { ClassDto, CourseDto, EnrollmentDto, GroupDto, MemberDto } from "@/lib/api/classroom/dto";
import {
  countActiveEnrollments,
  countActiveGroups,
  getClass,
  listClasses,
  listClassGroups,
  listClassTeachers,
  listCourses,
  listEnrollments,
  listGroupMembers,
} from "@/lib/api/classroom/endpoints";
import type { ApiClient } from "@/lib/api/client";
import { usersBatch } from "@/lib/api/identity/endpoints";
import type {
  TeacherCourseDetail,
  TeacherCourseSummary,
  TeacherStudent,
  TeacherTeam,
} from "@/lib/api/teacherFlow";

/** Số request song song khi đọc thành viên các nhóm. */
const MEMBER_BATCH = 5;
/** Thời gian dùng lại bản tải lớp giữa Layout, Sinh viên và Nhóm. */
const ROSTER_STALE_MS = 30_000;

/** Toàn bộ dữ liệu một lớp mà giảng viên đọc được; dùng chung cho tổng quan, sinh viên và nhóm. */
export interface ClassRoster {
  cls: ClassDto;
  course: CourseDto | undefined;
  enrollments: EnrollmentDto[];
  groups: GroupDto[];
  membersByGroup: Record<string, MemberDto[]>;
}

export function summaryBase(cls: ClassDto, course: CourseDto | undefined) {
  return {
    courseId: cls.id,
    courseCode: course?.code ?? cls.code,
    // Nhiều lớp cùng môn: mã lớp phân biệt chúng.
    section: cls.code,
    name: cls.name,
    term: cls.term,
    teamsWithoutProject: null,
    teamsWithSignals: null,
    overdue: null,
    lastActivity: null,
  } satisfies Partial<TeacherCourseSummary>;
}

function indexCourses(courses: readonly CourseDto[]): Map<string, CourseDto> {
  return new Map(courses.map((course) => [course.id, course]));
}

/** Danh sách lớp phụ trách; số liệu lấy từ tổng phân trang (2 request nhẹ mỗi lớp). */
export async function loadTeacherCourses(client: ApiClient): Promise<{ courses: TeacherCourseSummary[] }> {
  const [classes, courses] = await Promise.all([listClasses(client), listCourses(client)]);
  const courseById = indexCourses(courses);
  const summaries = await Promise.all(
    classes.map(async (cls): Promise<TeacherCourseSummary> => {
      const [studentCount, teamCount] = await Promise.all([
        countActiveEnrollments(client, cls.id),
        countActiveGroups(client, cls.id),
      ]);
      return {
        ...summaryBase(cls, courseById.get(cls.course)),
        studentCount,
        // Cần thành viên của mọi nhóm; chỉ tính ở trang chi tiết lớp.
        studentsWithoutTeam: null,
        teamCount,
      };
    }),
  );
  return { courses: summaries };
}

async function loadMembers(client: ApiClient, groups: readonly GroupDto[]): Promise<Record<string, MemberDto[]>> {
  const membersByGroup: Record<string, MemberDto[]> = {};
  for (let start = 0; start < groups.length; start += MEMBER_BATCH) {
    const batch = groups.slice(start, start + MEMBER_BATCH);
    const results = await Promise.all(batch.map((group) => listGroupMembers(client, group.id, "ACTIVE")));
    batch.forEach((group, index) => {
      membersByGroup[group.id] = results[index];
    });
  }
  return membersByGroup;
}

async function loadRoster(client: ApiClient, classId: string): Promise<ClassRoster> {
  const [cls, courses, enrollments, groups] = await Promise.all([
    getClass(client, classId),
    listCourses(client),
    listEnrollments(client, classId, "ACTIVE"),
    listClassGroups(client, classId, "ACTIVE"),
  ]);
  const membersByGroup = await loadMembers(client, groups);
  return { cls, course: indexCourses(courses).get(cls.course), enrollments, groups, membersByGroup };
}

/** Dùng lại bản tải gần nhất; mutation vô hiệu hóa khóa `teacher/<user>` nên lần sau tải mới. */
export function fetchRoster(queryClient: QueryClient, client: ApiClient, rosterKey: readonly unknown[], classId: string) {
  return queryClient.fetchQuery({
    queryKey: rosterKey,
    queryFn: () => loadRoster(client, classId),
    staleTime: ROSTER_STALE_MS,
  });
}

function groupedUserIds(roster: ClassRoster): Set<string> {
  return new Set(Object.values(roster.membersByGroup).flatMap((members) => members.map((member) => member.user_id)));
}

export function toTeacherStudents(roster: ClassRoster): TeacherStudent[] {
  const teamOf = new Map<string, TeacherStudent["team"]>();
  for (const group of roster.groups) {
    for (const member of roster.membersByGroup[group.id] ?? []) {
      teamOf.set(member.user_id, {
        teamId: group.id,
        name: group.name,
        role: member.role === "LEADER" ? "leader" : "member",
      });
    }
  }
  return roster.enrollments.map((enrollment) => ({
    userId: enrollment.user_id,
    studentCode: enrollment.profile?.student_id ?? "",
    name: enrollment.profile?.display_name ?? "",
    email: enrollment.profile?.email ?? "",
    team: teamOf.get(enrollment.user_id) ?? null,
    // Chưa có luồng xin gia nhập chờ duyệt trong API (B6).
    pendingTeam: null,
  }));
}

export function toTeacherTeams(roster: ClassRoster): TeacherTeam[] {
  return roster.groups.map((group) => {
    const members = (roster.membersByGroup[group.id] ?? []).map((member) => ({
      userId: member.user_id,
      name: member.profile?.display_name ?? "",
      studentCode: member.profile?.student_id ?? "",
      role: member.role === "LEADER" ? ("leader" as const) : ("member" as const),
    }));
    return {
      teamId: group.id,
      name: group.name,
      leaders: members.filter((member) => member.role === "leader").map(({ userId, name }) => ({ userId, name })),
      members,
      memberCount: members.length,
      maxMembers: roster.cls.group_max_size,
      // Project, tiến độ và hoạt động thuộc Work (B7).
      project: null,
      progress: null,
      lastActivity: null,
    };
  });
}

/** Giảng viên ACTIVE của lớp, PRIMARY trước. Tra tên lỗi thì dùng nhãn thay thế, không làm hỏng trang. */
export async function loadInstructors(client: ApiClient, classId: string): Promise<TeacherCourseDetail["instructors"]> {
  const teachers = await listClassTeachers(client, classId, "ACTIVE");
  const names = new Map<string, string>();
  try {
    for (const user of await usersBatch(client, teachers.map((teacher) => teacher.user_id))) {
      names.set(user.id, user.display_name);
    }
  } catch {
    // Tên chỉ để hiển thị.
  }
  return [...teachers]
    .sort((a, b) => Number(b.role === "PRIMARY") - Number(a.role === "PRIMARY"))
    .map((teacher) => ({
      userId: teacher.user_id,
      name: names.get(teacher.user_id) ?? UNKNOWN_NAME,
      isOwner: teacher.role === "PRIMARY",
    }));
}

export const UNKNOWN_NAME = "Chưa rõ tên";

export function toTeacherCourseDetail(roster: ClassRoster, instructors: TeacherCourseDetail["instructors"]): TeacherCourseDetail {
  const { cls } = roster;
  const grouped = groupedUserIds(roster);
  return {
    ...summaryBase(cls, roster.course),
    studentCount: roster.enrollments.length,
    studentsWithoutTeam: roster.enrollments.filter((enrollment) => !grouped.has(enrollment.user_id)).length,
    teamCount: roster.groups.length,
    instructors,
    // Mã thô chỉ trả một lần lúc cấp, không đọc lại được.
    joinCode: null,
    teamSize: { min: cls.group_min_size, max: cls.group_max_size },
    classroom: {
      version: cls.version,
      code: cls.code,
      status: cls.status,
      groupingPhase: cls.grouping_phase,
      groupingLockedAt: cls.grouping_locked_at,
      joinCodeExpiresAt: cls.join_code_expires_at,
      startsOn: cls.starts_on,
      endsOn: cls.ends_on,
    },
  };
}

export async function loadTeacherCourse(
  queryClient: QueryClient,
  client: ApiClient,
  rosterKey: readonly unknown[],
  classId: string,
): Promise<TeacherCourseDetail> {
  const [roster, instructors] = await Promise.all([
    fetchRoster(queryClient, client, rosterKey, classId),
    loadInstructors(client, classId),
  ]);
  return toTeacherCourseDetail(roster, instructors);
}
