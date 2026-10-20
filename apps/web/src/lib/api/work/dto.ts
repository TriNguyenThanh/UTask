/**
 * DTO của Work Service (`/api/work`), nguồn Work OpenAPI 1.4, đối chiếu serializer
 * ngày 19/10/2026. Gồm Project, State, Epic, Label, Sprint và Task (đọc).
 */

export type ProjectMemberRole = "LEADER" | "MEMBER";
export type ProjectMemberStatus = "ACTIVE" | "LEFT" | "REMOVED";
export type ProjectStatusFilter = "active" | "archived" | "all";

export interface ProjectDto {
  id: string;
  identifier: string;
  name: string;
  /** Luôn là chuỗi, có thể rỗng. */
  description: string;
  /** Luôn là chuỗi, có thể rỗng. */
  target_goals: string;
  /** Object tự do, chưa có cấu trúc (B17). */
  tech_stack: Record<string, unknown>;
  start_date: string | null;
  end_date: string | null;
  classroom_group_id: string;
  class_id: string | null;
  group_source_version: number;
  version: number;
  board_revision: number;
  github_repo_name: string | null;
  github_repo_id: string | null;
  github_connection_status: string | null;
  github_synced_at: string | null;
  created_at: string;
  updated_at: string;
  archived_at: string | null;
}

export interface ProjectMemberDto {
  id: string;
  user_id: string;
  /** Luôn là chuỗi; có thể rỗng khi `UserProjection` chưa đồng bộ. */
  display_name: string;
  avatar_url: string | null;
  role: ProjectMemberRole;
  status: ProjectMemberStatus;
  weekly_capacity: number;
  github_username: string | null;
  github_user_id: string | null;
  is_github_verified: boolean;
  joined_at: string;
  left_at: string | null;
  updated_at: string;
}

export type StateGroupDto = "BACKLOG" | "UNSTARTED" | "STARTED" | "REVIEW" | "COMPLETED" | "CANCELLED";
export type TaskTypeDto = "TASK" | "BUG" | "STORY" | "SUBTASK";
export type TaskPriorityDto = "LOW" | "MEDIUM" | "HIGH" | "URGENT";
export type SprintStatusDto = "DRAFT" | "ACTIVE" | "COMPLETED";
export type EpicStatusDto = "PLANNED" | "IN_PROGRESS" | "COMPLETED" | "CANCELLED";

export type RelationTypeDto = "BLOCKS" | "BLOCKED_BY" | "DUPLICATE" | "RELATES_TO";

/** Liên kết task theo góc nhìn của task đang xem (`expand=relations`). */
export interface RelationDto {
  id: string;
  related_task_id: string;
  related_task_code: string;
  relation_type: RelationTypeDto;
}

export type TaskScopeDto = "active" | "archived" | "deleted";

export interface StateDto {
  id: string;
  project_id: string;
  name: string;
  slug: string;
  color: string;
  sequence: number;
  group: StateGroupDto;
  is_default: boolean;
  created_at: string;
}

export interface EpicDto {
  id: string;
  project_id: string;
  name: string;
  description: string;
  lead_user_id: string | null;
  status: EpicStatusDto;
  start_date: string | null;
  target_date: string | null;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
}

export interface LabelDto {
  id: string;
  project_id: string;
  name: string;
  color: string;
  description: string | null;
  created_at: string;
  deleted_at: string | null;
}

export interface SprintDto {
  id: string;
  project_id: string;
  name: string;
  goal: string;
  status: SprintStatusDto;
  start_date: string | null;
  end_date: string | null;
  sort_order: number;
  version: number;
  started_at: string | null;
  closed_at: string | null;
  created_at: string;
  updated_at: string;
  archived_at: string | null;
}

export interface TaskAssigneeDto {
  user_id: string;
  /** Có thể rỗng khi `UserProjection` chưa đồng bộ. */
  display_name: string;
  avatar_url: string | null;
}

/** Task theo `TaskSerializer`; các khóa `state/epic/labels/assignees` chỉ có khi truyền `expand`. */
export interface TaskDto {
  id: string;
  project_id: string;
  sequence_id: number;
  /** Ví dụ `NEXUS-12`. */
  code: string;
  epic_id: string | null;
  state_id: string;
  parent_id: string | null;
  type: TaskTypeDto;
  source: string;
  acceptance_criteria: string;
  version: number;
  title: string;
  /** Không render (repo chưa có thư viện làm sạch HTML); dùng `description_stripped`. */
  description_html: string;
  description_stripped: string;
  priority: TaskPriorityDto;
  story_points: number | null;
  due_date: string | null;
  is_blocked: boolean;
  blocked_reason: string | null;
  sort_order: number;
  created_by_user_id: string;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
  archived_at: string | null;
  deleted_at: string | null;
  assignee_ids: string[];
  label_ids: string[];
  subtasks_count: number;
  comments_count: number;
  attachments_count: number;
  state?: StateDto;
  epic?: EpicDto | null;
  labels?: LabelDto[];
  assignees?: TaskAssigneeDto[];
  /** Chỉ có ở trang chi tiết (`expand=subtasks`). */
  subtasks?: TaskDto[];
  /** Chỉ có ở trang chi tiết (`expand=relations`). */
  relations?: RelationDto[];
}
