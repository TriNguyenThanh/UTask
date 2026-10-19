import { toCourseDetail, toCourseEnrollment, membershipOf, instructorNameOf, type MyGroup } from "@/lib/api/classroom/adapters";
import {
  getClass,
  listClasses,
  listClassGroups,
  listClassTeachers,
  listCourses,
  listGroupMembers,
} from "@/lib/api/classroom/endpoints";
import type { ClassDto, CourseDto } from "@/lib/api/classroom/dto";
import type { ApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { usersBatch } from "@/lib/api/identity/endpoints";

/** Số request song song khi dò nhóm của sinh viên. */
const PROBE_BATCH = 5;
/** Giới hạn số nhóm dò trong một lớp để chặn N+1 (B5: chưa có `my_group` hay `member_count`). */
export const MAX_GROUPS_PROBED = 50;

/**
 * Tìm nhóm ACTIVE của người dùng trong lớp. API không cho biết "nhóm của tôi", và đọc
 * thành viên của nhóm khác trả 404, nên dò từng nhóm; 404 nghĩa là không phải nhóm của mình.
 */
export async function loadMyGroup(client: ApiClient, classId: string): Promise<MyGroup | null> {
  const groups = (await listClassGroups(client, classId, "ACTIVE")).slice(0, MAX_GROUPS_PROBED);

  for (let start = 0; start < groups.length; start += PROBE_BATCH) {
    const batch = groups.slice(start, start + PROBE_BATCH);
    const results = await Promise.all(
      batch.map(async (group) => {
        try {
          return { group, members: await listGroupMembers(client, group.id, "ACTIVE") };
        } catch (error) {
          if (error instanceof ApiError && error.status === 404) {
            return null;
          }
          throw error;
        }
      }),
    );
    const found = results.find((result) => result !== null);
    if (found) {
      return found;
    }
  }
  return null;
}

function indexCourses(courses: readonly CourseDto[]): Map<string, CourseDto> {
  return new Map(courses.map((course) => [course.id, course]));
}

export async function loadCourseEnrollments(client: ApiClient, userId: string) {
  const [classes, courses] = await Promise.all([listClasses(client), listCourses(client)]);
  const courseById = indexCourses(courses);
  // Lớp xử lý tuần tự để tổng số request song song không vượt PROBE_BATCH.
  const enrollments = [];
  for (const cls of classes) {
    const mine = await loadMyGroup(client, cls.id);
    enrollments.push(toCourseEnrollment(cls, courseById.get(cls.course), membershipOf(userId, mine)));
  }
  return enrollments;
}

async function loadInstructorName(client: ApiClient, classId: string): Promise<string> {
  try {
    const teachers = await listClassTeachers(client, classId, "ACTIVE");
    const users = await usersBatch(client, teachers.map((teacher) => teacher.user_id));
    return instructorNameOf(teachers, users);
  } catch {
    // Tên giảng viên chỉ để hiển thị; lỗi tra cứu không được làm hỏng cả trang.
    return "";
  }
}

export async function loadCourseDetail(client: ApiClient, userId: string, classId: string) {
  const cls: ClassDto = await getClass(client, classId);
  const [courses, instructorName, mine] = await Promise.all([
    listCourses(client),
    loadInstructorName(client, classId),
    loadMyGroup(client, classId),
  ]);
  return toCourseDetail({ userId, cls, course: indexCourses(courses).get(cls.course), instructorName, mine });
}
