import { http, HttpResponse, type HttpHandler } from "msw";

import type {
  AiBacklogResultDto,
  AiContextDto,
  AiIntentDto,
  AiRiskAnalysisResultDto,
  AiTaskDecompositionResultDto,
} from "@/lib/api/ai/dto";

const AI_PATH = "/api/ai/v1/requests";

const DECOMPOSITION: AiTaskDecompositionResultDto = {
  warnings: [],
  subtasks: [
    {
      title: "Thiết kế giao diện",
      description: "Phác thảo màn hình và luồng thao tác.",
      acceptance_criteria: ["Có wireframe được duyệt"],
      dependencies: [],
      estimate_points: 2,
    },
    {
      title: "Xây dựng API",
      description: "Viết endpoint và kiểm tra dữ liệu vào.",
      acceptance_criteria: ["Endpoint trả đúng mã lỗi", "Có kiểm thử đơn vị"],
      dependencies: ["Thiết kế giao diện"],
      estimate_points: 3,
    },
    {
      title: "Viết kiểm thử",
      description: "Kiểm thử tích hợp luồng chính.",
      acceptance_criteria: ["Luồng chính chạy xanh"],
      dependencies: [],
      estimate_points: 1,
    },
  ],
};

const BACKLOG: AiBacklogResultDto = {
  warnings: [],
  items: [
    {
      type: "task",
      title: "Thiết lập dự án và CI",
      description: "Khởi tạo repository, lint và pipeline.",
      priority: "high",
      estimate_points: 3,
      dependencies: [],
      acceptance_criteria: ["Pipeline chạy xanh"],
      rationale: "Nền tảng cho mọi công việc sau.",
    },
    {
      title: "Màn hình đăng nhập",
      description: "Đăng nhập bằng tài khoản của hệ thống.",
      type: "task",
      priority: "medium",
      estimate_points: 2,
      dependencies: [],
      acceptance_criteria: ["Báo lỗi khi sai mật khẩu"],
      rationale: "Cần cho mọi chức năng có phân quyền.",
    },
    {
      type: "task",
      title: "Tài liệu hướng dẫn sử dụng",
      description: "Viết hướng dẫn cho người dùng cuối.",
      priority: "low",
      estimate_points: 1,
      dependencies: [],
      acceptance_criteria: [],
      rationale: "Hoàn thiện trước khi bàn giao.",
    },
  ],
};

const RISK: AiRiskAnalysisResultDto = {
  overall_level: "medium",
  limitations: ["Chưa có dữ liệu hoạt động GitHub."],
  risks: [
    {
      code: "SPRINT_OVERLOAD",
      level: "medium",
      title: "Sprint hiện tại có thể quá tải",
      reason: "Tổng điểm đã cam kết vượt năng lực trung bình.",
      evidence: [],
      suggested_actions: ["Giảm phạm vi sprint", "Chuyển bớt việc sang sprint sau"],
    },
    {
      code: "STALE_TASKS",
      level: "low",
      title: "Một số nhiệm vụ lâu không cập nhật",
      reason: "Có nhiệm vụ không đổi trạng thái hơn 7 ngày.",
      evidence: [],
      suggested_actions: ["Hỏi người phụ trách về tiến độ"],
    },
  ],
};

const RESULTS: Record<AiIntentDto, unknown> = {
  task_decomposition: DECOMPOSITION,
  backlog_generation: BACKLOG,
  risk_analysis: RISK,
};

function context(): AiContextDto {
  return { as_of: new Date().toISOString(), sources: [{ domain: "task", status: "available" }], fingerprint: "mock" };
}

interface Stored {
  intent: AiIntentDto;
  createdAt: string;
  polls: number;
}

function head(id: string, stored: Stored) {
  return {
    request_id: id,
    intent: stored.intent,
    output_schema_version: `${stored.intent}.v1`,
    created_at: stored.createdAt,
  };
}

/** AI giả cho dev khi chưa bật `ai` trong VITE_REAL_SERVICES: POST trả 202, GET lần đầu `running`, lần sau xong. */
export function createAiHandlers(): HttpHandler[] {
  const requests = new Map<string, Stored>();

  return [
    http.post(AI_PATH, async ({ request }) => {
      if (!request.headers.get("Idempotency-Key")) {
        return HttpResponse.json(
          { error: { code: "INVALID_REQUEST", message: "Thiếu Idempotency-Key.", details: {}, retryable: false } },
          { status: 400 },
        );
      }
      const body = (await request.json()) as { intent: AiIntentDto };
      const id = crypto.randomUUID();
      const stored: Stored = { intent: body.intent, createdAt: new Date().toISOString(), polls: 0 };
      requests.set(id, stored);
      return HttpResponse.json(
        { ...head(id, stored), status: "queued", status_url: `${AI_PATH}/${id}` },
        { status: 202 },
      );
    }),
    http.get(`${AI_PATH}/:requestId`, ({ params }) => {
      const id = String(params.requestId);
      const stored = requests.get(id);
      if (!stored) {
        return HttpResponse.json(
          { error: { code: "REQUEST_NOT_FOUND", message: "Không tìm thấy yêu cầu AI.", details: {}, retryable: false } },
          { status: 404 },
        );
      }
      stored.polls += 1;
      if (stored.polls === 1) {
        return HttpResponse.json({ ...head(id, stored), status: "running" });
      }
      return HttpResponse.json({
        ...head(id, stored),
        status: "succeeded",
        result: RESULTS[stored.intent],
        context: context(),
        completed_at: new Date().toISOString(),
      });
    }),
  ];
}
