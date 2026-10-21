import type { ProjectWorkspace } from "@/features/projects/types";
import type { ClassDto, CourseDto, GroupDto } from "@/lib/api/classroom/dto";
import { getClass, listClassGroups, listCourses } from "@/lib/api/classroom/endpoints";
import type { ApiClient } from "@/lib/api/client";
import {
  myRoleOf,
  projectsByGroup,
  toProjectCards,
  type MyProjectRole,
  type WorkProjectCard,
  type WorkProjectShell,
} from "@/lib/api/work/adapters";
import type { ProjectDto } from "@/lib/api/work/dto";
import {
  getProject,
  listEpics,
  listProjectMembers,
  listProjects,
  listSprints,
  listStates,
  listTaskIdsInSprint,
  listTasks,
} from "@/lib/api/work/endpoints";
import { buildWorkspace } from "@/lib/api/work/workspaceAdapters";

/** Số request song song mỗi đợt, giống `loadMembers` của giảng viên. */
const BATCH = 5;

/** Lời gọi phụ lỗi thì dùng giá trị thay thế, không làm hỏng cả danh sách. */
async function orElse<T>(call: Promise<T>, fallback: T): Promise<T> {
  try {
    return await call;
  } catch {
    return fallback;
  }
}

async function inBatches<T, R>(items: readonly T[], run: (item: T) => Promise<R>): Promise<R[]> {
  const results: R[] = [];
  for (let start = 0; start < items.length; start += BATCH) {
    results.push(...(await Promise.all(items.slice(start, start + BATCH).map(run))));
  }
  return results;
}

interface ClassLookup {
  classes: Map<string, ClassDto>;
  groupNames: Map<string, string>;
}

async function loadClassLookup(client: ApiClient, classIds: readonly string[]): Promise<ClassLookup> {
  const classes = new Map<string, ClassDto>();
  const groupNames = new Map<string, string>();
  await inBatches(classIds, async (classId) => {
    const [cls, groups] = await Promise.all([
      orElse<ClassDto | null>(getClass(client, classId), null),
      orElse<GroupDto[]>(listClassGroups(client, classId, "ACTIVE"), []),
    ]);
    if (cls) classes.set(classId, cls);
    for (const group of groups) groupNames.set(group.id, group.name);
  });
  return { classes, groupNames };
}

function indexCourses(courses: readonly CourseDto[]) {
  return new Map(courses.map((course) => [course.id, course]));
}

function distinctClassIds(projects: readonly ProjectDto[]): string[] {
  return [...new Set(projects.map((project) => project.class_id).filter((id): id is string => id !== null))];
}

/** Danh sách dự án kèm tên lớp/môn/nhóm và vai trò của tôi; lời gọi phụ lỗi chỉ làm trống trường tương ứng. */
export async function loadProjectCards(
  client: ApiClient,
  userId: string,
): Promise<{ cards: WorkProjectCard[]; partial: boolean }> {
  const { projects, partial } = await listProjects(client, "all");
  if (projects.length === 0) return { cards: [], partial };

  const [courses, lookup, roles] = await Promise.all([
    orElse<CourseDto[]>(listCourses(client), []),
    loadClassLookup(client, distinctClassIds(projects)),
    inBatches(projects, async (project): Promise<[string, MyProjectRole]> => {
      const members = await orElse(listProjectMembers(client, project.id, "ACTIVE"), []);
      return [project.id, myRoleOf(members, userId)];
    }),
  ]);

  const cards = toProjectCards(projects, {
    classes: lookup.classes,
    courses: indexCourses(courses),
    groupNames: lookup.groupNames,
    roleByProject: new Map(roles),
  });
  return { cards, partial };
}

/** `getProject` lỗi thì ném tiếp để route phân biệt 403/404; phần còn lại lỗi thì để trống. */
export async function loadProjectShell(
  client: ApiClient,
  userId: string,
  projectId: string,
): Promise<WorkProjectShell> {
  const [project, members] = await Promise.all([
    getProject(client, projectId),
    listProjectMembers(client, projectId, "ACTIVE"),
  ]);

  const classId = project.class_id;
  const [cls, courses, groups] = classId
    ? await Promise.all([
        orElse<ClassDto | null>(getClass(client, classId), null),
        orElse<CourseDto[]>(listCourses(client), []),
        orElse<GroupDto[]>(listClassGroups(client, classId, "ACTIVE"), []),
      ])
    : [null, [], []];

  const myRole = myRoleOf(members, userId);
  return {
    project,
    classCode: cls?.code ?? "",
    className: cls?.name ?? "",
    courseCode: (cls ? indexCourses(courses).get(cls.course)?.code : undefined) ?? "",
    groupName: groups.find((group) => group.id === project.classroom_group_id)?.name ?? "",
    members,
    myRole,
    canEdit: myRole === "LEADER" && project.archived_at === null,
  };
}

export async function loadGroupProjects(
  client: ApiClient,
): Promise<{ byGroup: Map<string, ProjectDto[]>; partial: boolean }> {
  const { projects, partial } = await listProjects(client, "all");
  return { byGroup: projectsByGroup(projects), partial };
}

/**
 * Tải dữ liệu Board/Backlog. Task không có `sprint_id` nên hỏi theo từng chu kỳ
 * DRAFT/ACTIVE (D4); task đã xong trong chu kỳ đã đóng không còn thành viên chu kỳ
 * nên hiện như ngoài chu kỳ.
 */
export async function loadWorkspace(
  client: ApiClient,
  userId: string,
  shell: WorkProjectShell,
): Promise<ProjectWorkspace> {
  const projectId = shell.project.id;
  const [states, epics, tasks, sprints] = await Promise.all([
    listStates(client, projectId),
    listEpics(client, projectId).catch(() => null),
    listTasks(client, projectId),
    listSprints(client, projectId),
  ]);

  const planned = sprints.filter((sprint) => sprint.status !== "COMPLETED" && sprint.archived_at === null);
  const memberships = await inBatches(planned, async (sprint): Promise<[string, string[]]> => [
    sprint.id,
    await listTaskIdsInSprint(client, projectId, sprint.id),
  ]);
  const sprintByTask = new Map<string, string>();
  for (const [sprintId, taskIds] of memberships) {
    for (const taskId of taskIds) sprintByTask.set(taskId, sprintId);
  }

  const workspace = buildWorkspace({ shell, userId, states, epics: epics ?? [], tasks, sprints, sprintByTask });
  return epics === null ? { ...workspace, partial: true } : workspace;
}
