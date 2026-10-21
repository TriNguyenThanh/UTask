import { http, HttpResponse, type HttpHandler } from "msw";

import type {
  AiBacklogItemDto,
  AiBacklogResultDto,
  AiRiskAnalysisResultDto,
  AiRiskDto,
  AiSubtaskDto,
  AiTaskDecompositionResultDto,
} from "@/lib/api/ai/dto";

const AI_PATH = "/api/ai/v1/requests";

export interface AiCall {
  method: string;
  path: string;
  body: unknown;
  idempotencyKey: string | null;
}

export interface AiFixture {
  /** `sync` (mặc định): POST trả 200 xong ngay. `async`: POST trả 202, `pendingPolls` GET đầu `running`, GET sau đó xong. */
  mode?: "sync" | "async";
  /** Số GET trả `running` trước khi xong (mặc định 1). */
  pendingPolls?: number;
  decomposition?: AiTaskDecompositionResultDto;
  backlog?: AiBacklogResultDto;
  risk?: AiRiskAnalysisResultDto;
  /** POST trả lỗi HTTP này. */
  failWith?: { status: number; code: string; message: string; details?: Record<string, unknown>; retryAfter?: string };
  /** Request chạy xong nhưng `status:"failed"`. */
  failedResult?: { code: string; message: string };
  calls?: AiCall[];
}

export function buildAiSubtask(overrides: Partial<AiSubtaskDto> = {}): AiSubtaskDto {
  return {
    title: "Viết API",
    description: "Mô tả nhiệm vụ con",
    acceptance_criteria: ["Có kiểm thử"],
    dependencies: [],
    estimate_points: 2,
    ...overrides,
  };
}

export function buildAiBacklogItem(overrides: Partial<AiBacklogItemDto> = {}): AiBacklogItemDto {
  return {
    type: "task",
    title: "Thiết lập CI",
    description: "Pipeline chạy xanh",
    priority: "medium",
    estimate_points: 3,
    dependencies: [],
    acceptance_criteria: ["CI xanh"],
    rationale: "Nền tảng cho mọi việc",
    ...overrides,
  };
}

export function buildAiRisk(overrides: Partial<AiRiskDto> = {}): AiRiskDto {
  return {
    code: "SPRINT_OVERLOAD",
    level: "medium",
    title: "Sprint quá tải",
    reason: "Vượt năng lực trung bình",
    evidence: [],
    suggested_actions: ["Giảm phạm vi"],
    ...overrides,
  };
}

const CONTEXT = { as_of: "2026-10-21T00:00:00Z", sources: [{ domain: "task", status: "available" }], fingerprint: "fp" };

export function aiHandlers(fixture: AiFixture = {}): HttpHandler[] {
  const mode = fixture.mode ?? "sync";
  const intents = new Map<string, string>();
  const polls = new Map<string, number>();
  let seq = 0;

  function head(id: string, intent: string) {
    return { request_id: id, intent, output_schema_version: `${intent}.v1`, created_at: "2026-10-21T00:00:00Z" };
  }

  function resultFor(intent: string): unknown {
    if (intent === "task_decomposition") return fixture.decomposition ?? { subtasks: [], warnings: [] };
    if (intent === "backlog_generation") return fixture.backlog ?? { items: [], warnings: [] };
    return fixture.risk ?? { overall_level: "none", risks: [], limitations: [] };
  }

  function finished(id: string, intent: string) {
    if (fixture.failedResult) {
      return {
        ...head(id, intent),
        status: "failed",
        error: { ...fixture.failedResult, details: {}, retryable: false },
      };
    }
    return { ...head(id, intent), status: "succeeded", result: resultFor(intent), context: CONTEXT, completed_at: "2026-10-21T00:00:01Z" };
  }

  return [
    http.post(AI_PATH, async ({ request }) => {
      const body = (await request.json()) as { intent: string };
      fixture.calls?.push({ method: "POST", path: AI_PATH, body, idempotencyKey: request.headers.get("Idempotency-Key") });
      const failure = fixture.failWith;
      if (failure) {
        return HttpResponse.json(
          { error: { code: failure.code, message: failure.message, details: failure.details ?? {}, retryable: false } },
          { status: failure.status, headers: failure.retryAfter ? { "Retry-After": failure.retryAfter } : {} },
        );
      }
      seq += 1;
      const id = `ai-${seq}`;
      if (mode === "sync") return HttpResponse.json(finished(id, body.intent));
      intents.set(id, body.intent);
      return HttpResponse.json({ ...head(id, body.intent), status: "queued", status_url: `${AI_PATH}/${id}` }, { status: 202 });
    }),
    http.get(`${AI_PATH}/:requestId`, ({ params }) => {
      const id = String(params.requestId);
      fixture.calls?.push({ method: "GET", path: `${AI_PATH}/${id}`, body: null, idempotencyKey: null });
      const intent = intents.get(id);
      if (!intent) {
        return HttpResponse.json({ error: { code: "REQUEST_NOT_FOUND", message: "Không có.", details: {}, retryable: false } }, { status: 404 });
      }
      const count = (polls.get(id) ?? 0) + 1;
      polls.set(id, count);
      return HttpResponse.json(count <= (fixture.pendingPolls ?? 1) ? { ...head(id, intent), status: "running" } : finished(id, intent));
    }),
  ];
}
