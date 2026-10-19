import type { ApiClient } from "@/lib/api/client";
import type {
  AccessCodeDto,
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

interface CommandOptions {
  idempotencyKey: string;
}

/** Tạo nhóm; người gọi thành Trưởng nhóm. */
export async function createGroup(client: ApiClient, input: { classId: string; name: string } & CommandOptions) {
  const { data } = await client.requestEnvelope<GroupDto>(`${ROOT}/groups/`, {
    method: "POST",
    body: { class_id: input.classId, name: input.name },
    idempotencyKey: input.idempotencyKey,
  });
  return data;
}

export async function joinGroup(client: ApiClient, input: { code: string } & CommandOptions) {
  const { data } = await client.requestEnvelope<GroupDto>(`${ROOT}/groups/join/`, {
    method: "POST",
    body: { code: input.code },
    idempotencyKey: input.idempotencyKey,
  });
  return data;
}

export async function patchGroup(
  client: ApiClient,
  groupId: string,
  input: { version: number; name?: string; status?: GroupStatus } & CommandOptions,
) {
  const { idempotencyKey, ...body } = input;
  const { data } = await client.requestEnvelope<GroupDto>(`${ROOT}/groups/${encodeURIComponent(groupId)}/`, {
    method: "PATCH",
    body,
    idempotencyKey,
  });
  return data;
}

/** Cấp mã mới (`enabled: true`, hạn mặc định 7 ngày) hoặc tắt mã. Mã thô chỉ có trong kết quả cấp. */
export async function issueGroupInviteCode(
  client: ApiClient,
  groupId: string,
  input: { version: number; enabled: boolean; expiresAt?: string } & CommandOptions,
) {
  const { data } = await client.requestEnvelope<AccessCodeDto>(
    `${ROOT}/groups/${encodeURIComponent(groupId)}/invite-code/`,
    {
      method: "POST",
      body: { version: input.version, enabled: input.enabled, expires_at: input.expiresAt },
      idempotencyKey: input.idempotencyKey,
    },
  );
  return data;
}

type MemberCommand = "leave" | "remove-member" | "transfer-leader";

async function memberCommand(
  client: ApiClient,
  groupId: string,
  command: MemberCommand,
  body: { version: number; reason: string; user_id?: string },
  idempotencyKey: string,
) {
  const { data } = await client.requestEnvelope<GroupDto>(`${ROOT}/groups/${encodeURIComponent(groupId)}/${command}/`, {
    method: "POST",
    body,
    idempotencyKey,
  });
  return data;
}

export function leaveGroup(client: ApiClient, groupId: string, input: { version: number; reason: string } & CommandOptions) {
  return memberCommand(client, groupId, "leave", { version: input.version, reason: input.reason }, input.idempotencyKey);
}

export function transferLeader(
  client: ApiClient,
  groupId: string,
  input: { version: number; reason: string; userId: string } & CommandOptions,
) {
  return memberCommand(
    client,
    groupId,
    "transfer-leader",
    { version: input.version, reason: input.reason, user_id: input.userId },
    input.idempotencyKey,
  );
}

export function removeMember(
  client: ApiClient,
  groupId: string,
  input: { version: number; reason: string; userId: string } & CommandOptions,
) {
  return memberCommand(
    client,
    groupId,
    "remove-member",
    { version: input.version, reason: input.reason, user_id: input.userId },
    input.idempotencyKey,
  );
}
