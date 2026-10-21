/**
 * DTO của AI Service v1 (`apps/ai-service/src/models/*`). Tên field giữ snake_case như server.
 * Phản hồi AI không bọc envelope `{success, data}`.
 */

export type AiIntentDto = "backlog_generation" | "task_decomposition" | "risk_analysis";
export type AiStatusDto = "queued" | "running" | "succeeded" | "failed";

export interface AiContextSourceDto {
  domain: "project" | "task" | "sprint" | "progress" | "github_activity" | "team";
  status: "available" | "stale" | "missing" | "partial" | "unavailable";
  as_of?: string;
  source_version?: string;
  warning?: string | null;
}

export interface AiContextDto {
  as_of: string;
  sources: AiContextSourceDto[];
  fingerprint: string;
}

export interface AiErrorPayloadDto {
  code: string;
  message: string;
  details?: Record<string, unknown>;
  request_id?: string;
  retryable: boolean;
}

export interface AiSubtaskDto {
  title: string;
  description: string;
  acceptance_criteria: string[];
  dependencies: string[];
  estimate_points: number;
}

export interface AiTaskDecompositionResultDto {
  subtasks: AiSubtaskDto[];
  warnings: string[];
}

export type AiBacklogPriorityDto = "low" | "medium" | "high" | "critical";

export interface AiBacklogItemDto {
  type: "task";
  title: string;
  description: string;
  priority: AiBacklogPriorityDto;
  estimate_points: number;
  dependencies: string[];
  acceptance_criteria: string[];
  rationale: string;
}

export interface AiBacklogResultDto {
  items: AiBacklogItemDto[];
  warnings: string[];
}

export type AiRiskLevelDto = "low" | "medium" | "high" | "critical";
export type AiOverallRiskLevelDto = AiRiskLevelDto | "none" | "unknown";

export interface AiRiskDto {
  code: string;
  level: AiRiskLevelDto;
  title: string;
  reason: string;
  evidence: { source_type: string; source_id: string; observed_at: string }[];
  suggested_actions: string[];
}

export interface AiRiskAnalysisResultDto {
  overall_level: AiOverallRiskLevelDto;
  risks: AiRiskDto[];
  limitations: string[];
}

interface AiResponseBase {
  request_id: string;
  intent: AiIntentDto;
  output_schema_version: string;
  created_at: string;
  updated_at?: string;
}

export type AiResponseDto<R> =
  | (AiResponseBase & { status: "queued"; status_url: string })
  | (AiResponseBase & { status: "running"; context?: AiContextDto })
  | (AiResponseBase & { status: "succeeded"; result: R; context: AiContextDto; completed_at: string })
  | (AiResponseBase & { status: "failed"; error: AiErrorPayloadDto });

export interface AiDecompositionRequest {
  intent: "task_decomposition";
  target: { type: "task"; id: string };
  input: { task_description?: string; acceptance_criteria?: string[]; additional_instruction?: string };
}

export interface AiBacklogRequest {
  intent: "backlog_generation";
  target: { type: "project"; id: string };
  input: {
    description: string;
    goals?: string[];
    tech_stack?: string[];
    deadline?: string;
    constraints?: string[];
    additional_instruction?: string;
  };
}

export interface AiRiskRequest {
  intent: "risk_analysis";
  target: { type: "project"; id: string };
  input: Record<string, never>;
}

export type AiRequestBody = AiDecompositionRequest | AiBacklogRequest | AiRiskRequest;
