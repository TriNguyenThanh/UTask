import type { ApiClient } from "@/lib/api/client";
import type {
  ClassDto,
  CourseDto,
  EnrollmentDto,
  EnrollmentStatus,
  GroupDto,
  GroupStatus,
  MemberDto,
  MemberStatus,
  ProjectLinkDto,
  TeacherDto,
  TeacherStatus,
} from "@/lib/api/classroom/dto";
import { collectAllPages, MAX_PAGE_SIZE, type ListMeta } from "@/lib/api/pagination";

const ROOT = "/api/classroom";

interface PageQuery<S extends string> {
  cursor?: string | null;
  pageSize?: number;
  status?: S;
}

function listUrl<S extends string>(path: string, { cursor, pageSize = MAX_PAGE_SIZE, status }: PageQuery<S>) {
  const params = new URLSearchParams({ page_size: String(pageSize) });
  if (cursor) params.set("cursor", cursor);
  if (status) params.set("status", status);
  return `${ROOT}${path}?${params.toString()}`;
}

async function fetchPage<T, S extends string>(client: ApiClient, path: string, query: PageQuery<S>) {
  const { data, meta } = await client.requestEnvelope<T[], ListMeta>(listUrl(path, query));
  return { data, meta };
}

/** Lớp nhìn thấy được theo vai trò: sinh viên = lớp đã ghi danh ACTIVE; giảng viên thêm lớp được phân công; admin tất cả. */
export function listClasses(client: ApiClient, status?: ClassDto["status"]) {
  return collectAllPages((cursor) => fetchPage<ClassDto, ClassDto["status"]>(client, "/classes/", { cursor, status }));
}

export async function getClass(client: ApiClient, classId: string) {
  const { data } = await client.requestEnvelope<ClassDto>(`${ROOT}/classes/${encodeURIComponent(classId)}/`);
  return data;
}

/** Danh sách môn không phân trang. */
export async function listCourses(client: ApiClient) {
  const { data } = await client.requestEnvelope<CourseDto[]>(`${ROOT}/courses/`);
  return data;
}

export function listClassTeachers(client: ApiClient, classId: string, status?: TeacherStatus) {
  return collectAllPages((cursor) =>
    fetchPage<TeacherDto, TeacherStatus>(client, `/classes/${encodeURIComponent(classId)}/teachers/`, { cursor, status }));
}

/** Chỉ giảng viên của lớp hoặc admin đọc được; sinh viên nhận 403. */
export function listEnrollments(client: ApiClient, classId: string, status?: EnrollmentStatus) {
  return collectAllPages((cursor) =>
    fetchPage<EnrollmentDto, EnrollmentStatus>(client, `/classes/${encodeURIComponent(classId)}/enrollments/`, { cursor, status }));
}

export function listClassGroups(client: ApiClient, classId: string, status?: GroupStatus) {
  return collectAllPages((cursor) =>
    fetchPage<GroupDto, GroupStatus>(client, `/classes/${encodeURIComponent(classId)}/groups/`, { cursor, status }));
}

/** Chỉ thành viên ACTIVE của nhóm hoặc giảng viên của lớp đọc được; người khác nhận 404. */
export function listGroupMembers(client: ApiClient, groupId: string, status?: MemberStatus) {
  return collectAllPages((cursor) =>
    fetchPage<MemberDto, MemberStatus>(client, `/groups/${encodeURIComponent(groupId)}/members/`, { cursor, status }));
}

export function listGroupProjects(client: ApiClient, groupId: string) {
  return collectAllPages((cursor) =>
    fetchPage<ProjectLinkDto, never>(client, `/groups/${encodeURIComponent(groupId)}/projects/`, { cursor }));
}

/** `Idempotency-Key` bắt buộc; sinh một lần cho mỗi ý định của người dùng. */
export async function joinClass(client: ApiClient, code: string, idempotencyKey: string) {
  const { data } = await client.requestEnvelope<EnrollmentDto>(`${ROOT}/classes/join/`, {
    method: "POST",
    body: { code },
    idempotencyKey,
  });
  return data;
}
