import { statusForGroup } from "@/features/projects/issueMeta";
import type {
  Epic,
  Issue,
  IssueDetail,
  IssueType,
  ProjectState,
  ProjectWorkspace,
  Sprint,
} from "@/features/projects/types";
import type { WorkProjectShell } from "@/lib/api/work/adapters";
import type { EpicDto, SprintDto, StateDto, TaskDto } from "@/lib/api/work/dto";

/** Work không lưu màu epic (D6): màu suy ra từ `id` nên ổn định giữa các lần tải. */
const EPIC_COLORS = ["#7c3aed", "#2563eb", "#0891b2", "#059669", "#d97706", "#dc2626", "#db2777", "#475569"];

export function epicColor(id: string): string {
  let hash = 0;
  for (let index = 0; index < id.length; index += 1) {
    hash = (hash * 31 + id.charCodeAt(index)) >>> 0;
  }
  return EPIC_COLORS[hash % EPIC_COLORS.length];
}

export function toProjectState(dto: StateDto): ProjectState {
  return {
    id: dto.id,
    name: dto.name,
    color: dto.color,
    sequence: dto.sequence,
    group: dto.group,
    isDefault: dto.is_default,
  };
}

/** Cột Board theo `sequence` tăng dần (D1). */
export function sortStates(states: readonly ProjectState[]): ProjectState[] {
  return [...states].sort((a, b) => a.sequence - b.sequence);
}

export function initialsOf(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return "?";
  const first = words[0][0];
  const last = words.length > 1 ? words[words.length - 1][0] : "";
  return (first + last).toUpperCase();
}

const TYPES: Record<string, IssueType> = { STORY: "story", BUG: "bug", TASK: "task" };

export interface IssueContext {
  userId: string;
  statesById: ReadonlyMap<string, ProjectState>;
  /** Task chưa có `sprint_id` (D4): ghép từ `tasks?sprint_id=…`. */
  sprintByTask: ReadonlyMap<string, string>;
}

/** `null` cho SUBTASK: Board và Backlog chỉ hiện task gốc; subtask nằm trong chi tiết. */
export function toIssue(dto: TaskDto, context: IssueContext): Issue | null {
  if (dto.type === "SUBTASK") return null;
  const state = context.statesById.get(dto.state_id);
  const group = state?.group ?? "UNSTARTED";
  const assignee = dto.assignees?.[0];
  const assigneeId = assignee?.user_id ?? dto.assignee_ids[0];
  return {
    id: dto.id,
    key: dto.code,
    type: TYPES[dto.type] ?? "task",
    title: dto.title,
    status: statusForGroup(group),
    statusId: dto.state_id,
    stateGroup: group,
    // Web chỉ có ba mức; URGENT gộp vào "high".
    priority: dto.priority === "LOW" ? "low" : dto.priority === "MEDIUM" ? "medium" : "high",
    storyPoints: dto.story_points ?? 0,
    epicId: dto.epic_id,
    sprintId: context.sprintByTask.get(dto.id) ?? null,
    // Web chỉ hiện một người phụ trách: lấy người đầu tiên.
    assignee: assigneeId
      ? {
          userId: assigneeId,
          displayName: assignee?.display_name ?? "",
          initials: initialsOf(assignee?.display_name ?? ""),
        }
      : null,
    hasPullRequest: false,
    isMine: dto.assignee_ids.includes(context.userId),
    dueAt: dto.due_date,
    updatedAt: dto.updated_at,
    rank: dto.sort_order,
    version: dto.version,
    blocked: dto.is_blocked,
    blockedReason: dto.blocked_reason,
  };
}

export function toEpic(dto: EpicDto, issueCount: number): Epic {
  return { id: dto.id, name: dto.name, color: epicColor(dto.id), issueCount };
}

export function toSprint(dto: SprintDto, issues: readonly Issue[]): Sprint {
  const own = issues.filter((issue) => issue.sprintId === dto.id);
  return {
    id: dto.id,
    name: dto.name,
    state: dto.status === "ACTIVE" ? "active" : dto.status === "COMPLETED" ? "completed" : "upcoming",
    startDate: dto.start_date ?? "",
    endDate: dto.end_date ?? "",
    goal: dto.goal,
    totalPoints: own.reduce((sum, issue) => sum + issue.storyPoints, 0),
    completedPoints: own
      .filter((issue) => issue.stateGroup === "COMPLETED")
      .reduce((sum, issue) => sum + issue.storyPoints, 0),
  };
}

export interface WorkspaceInput {
  shell: WorkProjectShell;
  userId: string;
  states: readonly StateDto[];
  epics: readonly EpicDto[];
  tasks: readonly TaskDto[];
  sprints: readonly SprintDto[];
  /** `taskId → sprintId`, ghép từ các lời gọi `sprint_id=<id>` (D4). */
  sprintByTask: ReadonlyMap<string, string>;
}

/** Ghép dữ liệu Work thành `ProjectWorkspace` mà Board/Backlog hiện có đang đọc. */
export function buildWorkspace(input: WorkspaceInput): ProjectWorkspace {
  const { shell, userId } = input;
  const states = sortStates(input.states.map(toProjectState));
  const statesById = new Map(states.map((state) => [state.id, state]));
  const issues = input.tasks
    .map((task) => toIssue(task, { userId, statesById, sprintByTask: input.sprintByTask }))
    .filter((issue): issue is Issue => issue !== null)
    .sort((a, b) => a.rank - b.rank || a.key.localeCompare(b.key));

  const epics = input.epics
    .filter((epic) => epic.deleted_at === null)
    .map((epic) => toEpic(epic, issues.filter((issue) => issue.epicId === epic.id).length));

  const sprints = input.sprints
    .filter((sprint) => sprint.archived_at === null)
    .sort((a, b) => a.sort_order - b.sort_order)
    .map((sprint) => toSprint(sprint, issues));

  const { project } = shell;
  return {
    projectId: project.id,
    projectKey: project.identifier,
    name: project.name,
    courseCode: shell.courseCode,
    courseName: shell.className,
    instructorName: "",
    teamName: shell.groupName,
    courseId: project.class_id ?? "",
    teamId: project.classroom_group_id,
    viewer:
      shell.myRole === null
        ? { kind: "course-instructor", courseId: project.class_id ?? "" }
        : { kind: "team-member", role: shell.myRole === "LEADER" ? "leader" : "member" },
    ...(shell.myRole === null ? {} : { myRole: shell.myRole === "LEADER" ? ("leader" as const) : ("member" as const) }),
    repository: project.github_repo_name,
    states,
    epics,
    sprints,
    issues,
  };
}

/**
 * Chi tiết task cho `IssuePanel`. Bình luận, lịch sử và liên kết Git chưa có ở Phase 10
 * (Phase 14 nối), nên để rỗng thay vì bịa dữ liệu.
 */
export function toIssueDetail(
  dto: TaskDto,
  issue: Issue,
  members: readonly { user_id: string; display_name: string }[],
): IssueDetail {
  return {
    issue,
    // Không render `description_html` (rule 12): repo chưa có thư viện làm sạch HTML.
    description: dto.description_stripped,
    acceptanceCriteria: dto.acceptance_criteria
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean),
    reporterName: members.find((member) => member.user_id === dto.created_by_user_id)?.display_name ?? "",
    comments: [],
    history: [],
    subtasks: (dto.subtasks ?? []).map((subtask) => ({
      id: subtask.id,
      title: subtask.title,
      done: subtask.completed_at !== null,
    })),
    gitLinks: [],
  };
}
