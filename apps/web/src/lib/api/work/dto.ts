/**
 * DTO của Work Service (`/api/work`), nguồn Work OpenAPI 1.4, đối chiếu serializer
 * ngày 19/10/2026. Chỉ gồm phần Project; Board/Backlog/Sprint chưa tích hợp.
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
