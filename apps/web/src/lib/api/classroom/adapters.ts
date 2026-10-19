import type { CourseDetail, TeamMember } from "@/features/courses/types";
import type { CourseEnrollment, TeamMembership } from "@/features/my-work/types";
import type { ClassDto, CourseDto, GroupDto, MemberDto, TeacherDto } from "@/lib/api/classroom/dto";
import type { PublicUserDto } from "@/lib/api/identity/dto";

/** Nhóm của người dùng cùng danh sách thành viên ACTIVE, hoặc `null` khi chưa có nhóm. */
export interface MyGroup {
  group: GroupDto;
  members: MemberDto[];
}

// Sinh viên vào nhóm bằng mã mời; chưa có hạn đăng ký nhóm trong API (B6).
const TEAM_FORMATION: CourseEnrollment["teamFormation"] = { mode: "join-code", registrationDeadline: null };

export function membershipOf(userId: string, mine: MyGroup | null): TeamMembership {
  if (!mine) {
    return { status: "none" };
  }
  const self = mine.members.find((member) => member.user_id === userId && member.status === "ACTIVE");
  return {
    status: "assigned",
    teamId: mine.group.id,
    teamName: mine.group.name,
    role: self?.role === "LEADER" ? "leader" : "member",
  };
}

export function toCourseEnrollment(
  cls: ClassDto,
  course: CourseDto | undefined,
  membership: TeamMembership,
): CourseEnrollment {
  return {
    courseId: cls.id,
    courseCode: course?.code ?? cls.code,
    courseName: cls.name,
    semester: cls.term,
    teamFormation: TEAM_FORMATION,
    projectId: null,
    membership,
  };
}

/** Giảng viên ACTIVE, PRIMARY trước, nối bằng ", "; không có tên thì bỏ qua người đó. */
export function instructorNameOf(teachers: readonly TeacherDto[], users: readonly PublicUserDto[]): string {
  const names = new Map(users.map((user) => [user.id, user.display_name]));
  return [...teachers]
    .filter((teacher) => teacher.status === "ACTIVE")
    .sort((a, b) => Number(b.role === "PRIMARY") - Number(a.role === "PRIMARY"))
    .map((teacher) => names.get(teacher.user_id))
    .filter((name): name is string => Boolean(name))
    .join(", ");
}

export function toTeamMember(member: MemberDto): TeamMember {
  return {
    userId: member.user_id,
    displayName: member.profile?.display_name ?? "",
    studentId: member.profile?.student_id ?? "",
    email: member.profile?.email ?? "",
    // Skill và trách nhiệm không có trong API (B6).
    skill: "",
    responsibility: "",
    role: member.role === "LEADER" ? "leader" : "member",
  };
}

export function toCourseDetail(input: {
  userId: string;
  cls: ClassDto;
  course: CourseDto | undefined;
  instructorName: string;
  mine: MyGroup | null;
}): CourseDetail {
  const { userId, cls, course, instructorName, mine } = input;
  const membership = membershipOf(userId, mine);
  const base = toCourseEnrollment(cls, course, membership);
  const members = mine?.members.filter((member) => member.status === "ACTIVE") ?? [];
  const self = members.find((member) => member.user_id === userId);

  return {
    courseId: base.courseId,
    courseCode: base.courseCode,
    courseName: base.courseName,
    semester: base.semester,
    instructorName,
    teamSize: { min: cls.group_min_size, max: cls.group_max_size },
    // Sinh viên không đọc được danh sách ghi danh hay thành viên nhóm khác (B4e, B5).
    classSize: null,
    membership,
    teamFormation: {
      ...base.teamFormation,
      selfCreateAllowed: cls.status === "OPEN" && cls.grouping_phase === "FORMING",
    },
    team: mine
      ? {
          teamId: mine.group.id,
          teamName: mine.group.name,
          isLeader: self?.role === "LEADER",
          memberCount: members.length,
          maxMembers: cls.group_max_size,
          members: members.map(toTeamMember),
          topic: null,
          repository: null,
          projectKey: null,
          projectId: null,
        }
      : null,
    // API không cho sinh viên xem nhóm hay bạn học khác (B4e, B5): không có dữ liệu hình thành nhóm.
    formation: null,
  };
}
