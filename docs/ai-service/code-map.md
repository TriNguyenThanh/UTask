# AI Service Code Map

**Trạng thái: Chưa triển khai.** Audit ngày 2026-10-04 cho thấy chưa có file
implementation nào được theo dõi dưới `apps/ai-service/`. File này chỉ ghi
điểm vào đã xác minh và khoảng trống hiện tại; không dựng cây file tương lai.

## Service root

- Source, test và cấu hình khi được tạo: `apps/ai-service/`.
- Instruction mặc định: `apps/ai-service/AGENTS.md`.
- Plan cho thay đổi lớn: `apps/ai-service/.agent/PLANS.md`.

## API

- API entry points: **Chưa có implementation được xác minh**.
- Schemas/serializers: **Chưa có implementation được xác minh**.
- Root Nginx có route `/api/ai/` tới container `ai-service:8000`; đây là routing
  hạ tầng, không phải bằng chứng endpoint nội bộ đã tồn tại.

## AI workflows và agents

- Giai đoạn 1 gồm `backlog_generation`, `task_decomposition` và
  `risk_analysis`; implementation workflow: **Chưa có**.
- ADK Workflow điều phối macro-flow: **Chưa có**.
- `LlmAgent` điều phối micro-flow/reasoning: **Chưa có**.
- Specialist agent/agent-as-tool: **Chưa có; chỉ thêm khi use case cần**.
- Agent budget và self-review giới hạn: **Chưa có**.
- Structured output model/validation: **Chưa có**.

Các intent ngoài giai đoạn 1 như `deadline_check` độc lập, priority suggestion,
task description generation và tự động phân bổ lại workload: **Chưa có trong
phạm vi hiện tại**.

## Tools và prompts

- Context Tool Pool: **Chưa có**.
- Domain tools mục tiêu: task, project, team, progress và development context.
- Agent tools hạ tầng Kafka/database/cache: **Không được tạo**.
- Prompt management: **Chưa có**.
- Khi thêm implementation, search toàn bộ `apps/ai-service/` trước khi tạo mới.

## Context và events

- Kafka consumers: **Chưa có**.
- Event transform/idempotency: **Chưa có**.
- Context storage/repository: **Chưa có**.
- Context mục tiêu giai đoạn 1: project, task, sprint, progress metric và
  GitHub activity đã chuẩn hóa.
- Agent không biết Kafka; deterministic consumer và Context Layer che giấu
  topic, offset, replay, consumer group và database phía dưới.
- Event names ngoài phạm vi context v1 trong `docs/system/kafka-events.md` chỉ
  là danh mục thiết kế. Schema AI context đã chốt nằm tại
  `contracts/events/ai-context-v1.yaml`; producer/consumer runtime chưa có.

## LLM providers

- Google ADK 2.0 là framework workflow/agent mục tiêu: **Chưa có dependency**.
- Provider/model adapter hoặc router: **Chưa có**.
- Provider SDK/configuration: **Chưa có**.
- `infra/env/ai-service.env` hiện chỉ có `DATASETS_DIR`,
  `WORK_SERVICE_URL`, `INTEGRATION_SERVICE_URL`; không có credential hay
  provider setting nào được xác minh cho AI implementation.

## Tests và tooling

- Unit/API/integration/workflow tests: **Chưa có**.
- Test Context Tool Pool, agent budget, structured output và proposal boundary:
  **Chưa có**.
- Package manifest/lock: **Chưa có trong service root**.
- CI khai báo `uv`, Ruff, Pytest và Docker build; xem `AGENTS.md` để biết đúng
  command đã được repository cấu hình.

## Hạ tầng liên quan (read-only)

- Compose service: `docker-compose.yml` (`ai-service`).
- Service environment: `infra/env/ai-service.env`.
- Gateway route: `infra/nginx/nginx.conf` (`/api/ai/`).
- CI workflow: `.github/workflows/python-service.yml` và `.github/workflows/ci.yml`.

Các file hạ tầng trên nằm ngoài writable scope của task setup; chỉ đọc để định
vị integration context, không sửa từ công việc AI Service này.
