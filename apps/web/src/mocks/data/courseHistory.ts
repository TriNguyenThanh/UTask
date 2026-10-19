import type { CourseDetail, TeamMember } from "@/features/courses/types";
import type { CourseEnrollment, TeamRole } from "@/features/my-work/types";
import { LEADER_ID, MEMBER_ID, STUDENT_ID } from "@/mocks/data/database";
import { CHAU_ID, CUONG_ID, HUONG_ID, LONG_ID, MOCK_PEOPLE } from "@/mocks/data/directory";

/**
 * Môn học của các học kỳ/năm học đã kết thúc, chỉ để demo bộ lọc học kỳ ở
 * trang Môn học. Đây là lịch sử học tập (read-only): nhóm đã chốt, không còn
 * project đang chạy (`projectId: null`) nên không có sprint, task hay đồng bộ
 * GitHub. Không nằm trong relationship graph: Teacher và các endpoint khác
 * không thấy các lớp này.
 */

interface PastTeam {
  teamName: string;
  topicTitle: string;
  /** Vai trò của từng tài khoản demo trong nhóm này, theo riêng môn học. */
  roles: Record<string, TeamRole>;
  /** Bạn cùng nhóm hiển thị trong danh sách thành viên. */
  mates: readonly string[];
}

interface PastCourse {
  courseId: string;
  courseCode: string;
  courseName: string;
  semester: string;
  instructorName: string;
  team: PastTeam;
}

const PAST_COURSES: readonly PastCourse[] = [
  {
    courseId: "course-hist-se210",
    courseCode: "SE210",
    courseName: "Công nghệ Phần mềm SE210",
    semester: "HK2 2025–2026",
    instructorName: "TS. Trần Minh Đức",
    team: {
      teamName: "Team ORION",
      topicTitle: "Nền tảng đặt lịch khám bệnh trực tuyến",
      roles: { [LEADER_ID]: "member", [MEMBER_ID]: "leader", [STUDENT_ID]: "member" },
      mates: [CHAU_ID, CUONG_ID],
    },
  },
  {
    courseId: "course-hist-db220",
    courseCode: "DB220",
    courseName: "Cơ sở Dữ liệu Nâng cao DB220",
    semester: "HK2 2025–2026",
    instructorName: "ThS. Lê Thu Hà",
    team: {
      teamName: "Team DELTA",
      topicTitle: "Tối ưu truy vấn cho kho dữ liệu bán lẻ",
      roles: { [LEADER_ID]: "leader", [MEMBER_ID]: "member", [STUDENT_ID]: "leader" },
      mates: [HUONG_ID, LONG_ID],
    },
  },
  {
    courseId: "course-hist-web150",
    courseCode: "WEB150",
    courseName: "Lập trình Web WEB150",
    semester: "HK1 2025–2026",
    instructorName: "TS. Trần Minh Đức",
    team: {
      teamName: "Team PIXEL",
      topicTitle: "Cổng thông tin câu lạc bộ sinh viên",
      roles: { [LEADER_ID]: "member", [MEMBER_ID]: "member", [STUDENT_ID]: "leader" },
      mates: [CUONG_ID, LONG_ID],
    },
  },
  {
    courseId: "course-hist-prg101",
    courseCode: "PRG101",
    courseName: "Nhập môn Lập trình PRG101",
    semester: "HK2 2024–2025",
    instructorName: "ThS. Lê Thu Hà",
    team: {
      teamName: "Team SPARK",
      topicTitle: "Trò chơi ôn tập kiến thức C++ cơ bản",
      roles: { [LEADER_ID]: "leader", [MEMBER_ID]: "leader", [STUDENT_ID]: "member" },
      mates: [CHAU_ID, HUONG_ID],
    },
  },
];

function pastCoursesFor(userId: string): readonly PastCourse[] {
  return PAST_COURSES.filter((course) => userId in course.team.roles);
}

export function historyCourseIdsFor(userId: string): readonly string[] {
  return pastCoursesFor(userId).map((course) => course.courseId);
}

export function historyEnrollmentsFor(userId: string): CourseEnrollment[] {
  return pastCoursesFor(userId).map((course) => ({
    courseId: course.courseId,
    courseCode: course.courseCode,
    courseName: course.courseName,
    semester: course.semester,
    teamFormation: { mode: "instructor-assigned", registrationDeadline: null },
    projectId: null,
    membership: {
      status: "assigned",
      teamId: `${course.courseId}-team`,
      teamName: course.team.teamName,
      role: course.team.roles[userId],
    },
  }));
}

function memberOf(userId: string, role: TeamRole): TeamMember {
  const person = MOCK_PEOPLE[userId];
  return {
    userId,
    displayName: person?.displayName ?? "Chưa rõ",
    studentId: person?.studentCode ?? "",
    email: person?.email ?? "",
    skill: person?.skill ?? "",
    responsibility: "",
    role,
  };
}

export function historyCourseDetailFor(courseId: string, userId: string): CourseDetail | null {
  const course = pastCoursesFor(userId).find((candidate) => candidate.courseId === courseId);
  if (!course) return null;
  const role = course.team.roles[userId];
  const members = [
    memberOf(userId, role),
    ...course.team.mates.map((mateId) => memberOf(mateId, "member")),
  ];
  return {
    courseId: course.courseId,
    courseCode: course.courseCode,
    courseName: course.courseName,
    semester: course.semester,
    instructorName: course.instructorName,
    teamSize: { min: 3, max: 5 },
    classSize: { total: 40, teamed: 40 },
    membership: {
      status: "assigned",
      teamId: `${course.courseId}-team`,
      teamName: course.team.teamName,
      role,
    },
    teamFormation: { mode: "instructor-assigned", registrationDeadline: null, selfCreateAllowed: false },
    team: {
      teamId: `${course.courseId}-team`,
      teamName: course.team.teamName,
      isLeader: role === "leader",
      memberCount: members.length,
      maxMembers: 5,
      members,
      topic: {
        status: "approved",
        title: course.team.topicTitle,
        description: null,
        objectives: [],
        reviewedBy: course.instructorName,
        reviewedAt: null,
        feedback: null,
      },
      repository: null,
      projectKey: null,
      projectId: null,
    },
    formation: null,
  };
}
