import { LEADER_ID, MEMBER_ID, STUDENT_ID, TEACHER2_ID, TEACHER3_ID, TEACHER_ID } from "@/mocks/data/database";
import { LARGE_COURSE_ID, LARGE_STUDENTS, LARGE_TEAMS } from "@/mocks/data/largeClass";

/**
 * Display directory for the demo mock: who the people, classes and teams in
 * the relationship graph are. Pure reference data — membership, enrollment
 * and instructor assignment live in `relationships.ts`.
 *
 * Most people here have NO login account. They exist only so rosters can show
 * a name, student code and email; only the accounts in `MOCK_USERS`
 * (database.ts) can sign in.
 *
 * Limitation: this is static. Editing a profile through the demo settings
 * page updates `db.profilesByUser`, not this directory.
 */

export interface MockPerson {
  userId: string;
  displayName: string;
  /** Roster email. For demo logins this is the school address, not the login email. */
  email: string;
  /** Student code; null for instructors. */
  studentCode: string | null;
  skill: string | null;
}

const id = (suffix: string) => `00000000-0000-4000-8000-${suffix.padStart(12, "0")}`;

export const KHANG_ID = id("6");
export const DANG_KHOA_ID = id("8");
export const DIEP_ID = id("a");
export const KHANH_ID = id("b");
export const HUY_ID = id("c");
export const DIEU_ANH_ID = id("d");
export const CHAU_ID = id("e");
export const THANG_ID = id("4");
export const LONG_ID = id("5");
export const MAI_STUDENT_ID = id("f");
/** Instructors without a demo login. */
export const HUONG_ID = id("f3");
export const CUONG_ID = id("f4");

function student(
  userId: string,
  displayName: string,
  studentCode: string,
  email: string,
  skill: string,
): MockPerson {
  return { userId, displayName, studentCode, email, skill };
}

function instructor(userId: string, displayName: string, email: string): MockPerson {
  return { userId, displayName, studentCode: null, email, skill: null };
}

export const MOCK_PEOPLE: Record<string, MockPerson> = Object.fromEntries(
  [
    student(LEADER_ID, "Nguyễn Hoàng Nam", "21120015", "nam.nh21120015@sis.edu.vn", "Backend Go & DevOps"),
    student(MEMBER_ID, "Đặng Thảo Linh", "21020872", "linh.dt21020872@sis.edu.vn", "Frontend React & Tailwind"),
    student(STUDENT_ID, "Lê Minh Khoa", "21020999", "student@utask.test", "Frontend React & TypeScript"),
    student(THANG_ID, "Bùi Quang Thắng", "21020215", "thang.bq21020215@sis.edu.vn", "AI & Analytics"),
    student(LONG_ID, "Trần Bảo Long", "21020301", "long.tb21020301@sis.edu.vn", "Database & QA"),
    student(KHANG_ID, "Hoàng Trọng Khang", "21021004", "khang.ht21021004@sis.edu.vn", "Backend FastAPI"),
    student(DANG_KHOA_ID, "Trần Đăng Khoa", "21021061", "khoa.td21021061@sis.edu.vn", "Embedded & IoT"),
    student(DIEP_ID, "Vũ Ngọc Diệp", "21021103", "diep.vn21021103@sis.edu.vn", "Data Engineering"),
    student(KHANH_ID, "Đinh Tuấn Khanh", "21021120", "khanh.dt21021120@sis.edu.vn", "Backend Golang"),
    student(HUY_ID, "Phạm Quốc Huy", "21120020", "huy.pq21120020@sis.edu.vn", "Backend FastAPI"),
    student(DIEU_ANH_ID, "Ngô Diệu Anh", "21021058", "anh.nd21021058@sis.edu.vn", "UI/UX & Figma"),
    student(CHAU_ID, "Lý Bảo Châu", "21021090", "chau.lb21021090@sis.edu.vn", "QA Automation"),
    student(MAI_STUDENT_ID, "Võ Thanh Mai", "21021033", "mai.vt21021033@sis.edu.vn", "MQTT & Backend Node.js"),
    instructor(TEACHER_ID, "TS. Trần Minh Đức", "teacher@utask.test"),
    instructor(TEACHER2_ID, "ThS. Lê Thị Mai", "teacher2@utask.test"),
    instructor(TEACHER3_ID, "TS. Phạm Quốc Bảo", "teacher3@utask.test"),
    instructor(HUONG_ID, "TS. Vũ Thu Hương", "huong.vt@faculty.edu.vn"),
    instructor(CUONG_ID, "TS. Đặng Văn Cường", "cuong.dv@faculty.edu.vn"),
    ...LARGE_STUDENTS.map((s) => student(s.userId, s.displayName, s.studentCode, s.email, s.skill)),
  ].map((person) => [person.userId, person]),
);

export interface MockCourseMeta {
  courseId: string;
  /** Subject code. Several classes may share one code; never use it as a key. */
  courseCode: string;
  /** Distinguishes classes of the same subject; null when the code is unique. */
  section: string | null;
  courseName: string;
  term: string;
  teamSize: { min: number; max: number };
  /** Join code shown to the instructor; null when the class has none. */
  joinCode: string | null;
}

const TERM = "HK1 2026–2027";

/** `courseId` identifies a class opened in a term, not a subject. */
export const MOCK_COURSE_META: Record<string, MockCourseMeta> = {
  "course-se330": {
    courseId: "course-se330",
    courseCode: "SE330",
    section: "Lớp 1",
    courseName: "Đồ án Chuyên ngành Công nghệ Phần mềm",
    term: TERM,
    teamSize: { min: 3, max: 5 },
    joinCode: "SE330-A1",
  },
  "course-se330-n2": {
    courseId: "course-se330-n2",
    courseCode: "SE330",
    section: "Lớp 2",
    courseName: "Đồ án Chuyên ngành Công nghệ Phần mềm",
    term: TERM,
    teamSize: { min: 3, max: 5 },
    joinCode: "SE330-B2",
  },
  "course-cs402": {
    courseId: "course-cs402",
    courseCode: "CS402",
    section: null,
    courseName: "Phát triển Ứng dụng Di động Nâng cao",
    term: TERM,
    teamSize: { min: 3, max: 5 },
    joinCode: "CS402-MOB",
  },
  "course-se331": {
    courseId: "course-se331",
    courseCode: "SE331",
    section: null,
    courseName: "Kiểm thử Phần mềm",
    term: TERM,
    teamSize: { min: 3, max: 5 },
    joinCode: null,
  },
  [LARGE_COURSE_ID]: {
    courseId: LARGE_COURSE_ID,
    courseCode: "SE360",
    section: null,
    courseName: "Lập trình Web Nâng cao",
    term: TERM,
    teamSize: { min: 3, max: 5 },
    joinCode: "SE360-WEB",
  },
  "course-it3090": {
    courseId: "course-it3090",
    courseCode: "IT3090",
    section: null,
    courseName: "Đồ án IoT",
    term: TERM,
    teamSize: { min: 3, max: 5 },
    joinCode: "IOT3090-X",
  },
};

export interface MockTeamMeta {
  name: string;
  neededSkills: string[];
}

export const MOCK_TEAM_META: Record<string, MockTeamMeta> = {
  "team-nexus": { name: "Team NEXUS", neededSkills: [] },
  "team-deli": { name: "Team DELI", neededSkills: [] },
  "team-phoenix": { name: "Team PHOENIX", neededSkills: [] },
  "team-iot-vision": { name: "Team VISION", neededSkills: ["Embedded C", "Computer Vision"] },
  "team-iot-sense": { name: "Team SENSE", neededSkills: ["MQTT", "Backend Node.js"] },
  ...Object.fromEntries(LARGE_TEAMS.map((team) => [team.teamId, { name: team.name, neededSkills: [] }])),
};
