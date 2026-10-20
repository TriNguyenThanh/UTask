import type { ClassDto, CourseDto } from "@/lib/api/classroom/dto";
import type { ProjectDto, ProjectMemberDto, ProjectMemberRole } from "@/lib/api/work/dto";

/**
 * Kiểu hiển thị của Project thật. Không tái dùng `ProjectSummary`/`ProjectWorkspace`
 * của chế độ demo vì Work chưa cấp sprint/epic/issue.
 */

export type MyProjectRole = ProjectMemberRole | null;

export interface WorkProjectCard {
  projectId: string;
  identifier: string;
  name: string;
  archived: boolean;
  classId: string | null;
  classCode: string;
  className: string;
  courseCode: string;
  groupId: string;
  groupName: string;
  /** `null` = không phải thành viên (giảng viên xem). */
  myRole: MyProjectRole;
  repository: string | null;
  createdAt: string;
}

export interface WorkProjectShell {
  project: ProjectDto;
  classCode: string;
  className: string;
  courseCode: string;
  groupName: string;
  members: ProjectMemberDto[];
  myRole: MyProjectRole;
  /** `myRole === "LEADER"` và dự án chưa lưu trữ. */
  canEdit: boolean;
}

export interface ProjectCardContext {
  classes: ReadonlyMap<string, ClassDto>;
  courses: ReadonlyMap<string, CourseDto>;
  groupNames: ReadonlyMap<string, string>;
  roleByProject: ReadonlyMap<string, MyProjectRole>;
}

/** Chỉ xét thành viên `ACTIVE`. */
export function myRoleOf(members: readonly ProjectMemberDto[], userId: string): MyProjectRole {
  return members.find((member) => member.user_id === userId && member.status === "ACTIVE")?.role ?? null;
}

export function toProjectCards(projects: readonly ProjectDto[], context: ProjectCardContext): WorkProjectCard[] {
  return projects.map((project) => {
    const cls = project.class_id ? context.classes.get(project.class_id) : undefined;
    const course = cls ? context.courses.get(cls.course) : undefined;
    return {
      projectId: project.id,
      identifier: project.identifier,
      name: project.name,
      archived: project.archived_at !== null,
      classId: project.class_id,
      classCode: cls?.code ?? "",
      className: cls?.name ?? "",
      courseCode: course?.code ?? "",
      groupId: project.classroom_group_id,
      groupName: context.groupNames.get(project.classroom_group_id) ?? "",
      myRole: context.roleByProject.get(project.id) ?? null,
      repository: project.github_repo_name,
      createdAt: project.created_at,
    };
  });
}

function compareByCreation(a: ProjectDto, b: ProjectDto) {
  if (a.created_at !== b.created_at) return a.created_at < b.created_at ? -1 : 1;
  if (a.id === b.id) return 0;
  return a.id < b.id ? -1 : 1;
}

/** Dự án chưa lưu trữ tạo sớm nhất; hòa thì `id` tăng dần; không có thì `null`. */
export function pickPrimaryProject(projects: readonly ProjectDto[]): ProjectDto | null {
  const active = projects.filter((project) => project.archived_at === null);
  if (active.length === 0) return null;
  return [...active].sort(compareByCreation)[0];
}

export function projectsByGroup(projects: readonly ProjectDto[]): Map<string, ProjectDto[]> {
  const byGroup = new Map<string, ProjectDto[]>();
  for (const project of [...projects].sort(compareByCreation)) {
    const list = byGroup.get(project.classroom_group_id);
    if (list) list.push(project);
    else byGroup.set(project.classroom_group_id, [project]);
  }
  return byGroup;
}
