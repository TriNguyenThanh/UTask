# AI Service Code Map

**Trạng thái: Một phần.** Bootstrap ngày 2026-10-05 đã tạo source, test và
cấu hình chạy được dưới `apps/ai-service/`; ngày 2026-10-07 đã tách source theo
layer application/workflow/infrastructure. File này ghi implementation đã xác
minh và khoảng trống hiện tại. Thiết kế mục tiêu đã cập nhật theo
[baseline](../architecture/README.md); thay đổi tài liệu không tạo runtime mới.

## Service root

- Source trực tiếp dưới `apps/ai-service/src/`; test và cấu hình nằm ở
  `apps/ai-service/`. Không có package bao ngoài các layer.
- Instruction mặc định: `apps/ai-service/AGENTS.md`.
- Plan cho thay đổi lớn: `apps/ai-service/.agent/PLANS.md`.

## API

- API entry points: `src/api/routes.py` — `/healthz`,
  `POST /api/ai/v1/requests` và `GET /api/ai/v1/requests/{request_id}`.
- Schemas: `src/models/` — `requests.py` cho input/target,
  `results.py` cho đề xuất và `responses.py` cho envelope/context metadata/lỗi.
  `common.py` giữ kiểu dùng chung; `__init__.py` giữ public imports ổn định.
- Root Nginx có route `/api/ai/` tới container `ai-service:8000`; đây là routing
  hạ tầng, không phải bằng chứng endpoint nội bộ đã tồn tại.

## Cách đọc source và pipeline hiện tại

Đọc theo thứ tự `main.py` → `api/routes.py` → `application/service.py` →
`workflow/bounded.py` → `infrastructure/providers.py`; đọc
`application/ports.py` và `infrastructure/repositories.py` khi cần biết cách
lưu/truy vấn request.
Các file trên đều nằm trực tiếp trong `apps/ai-service/src/`.

```text
src/
├── main.py
├── config.py
├── errors.py
├── api/
├── application/
├── workflow/
├── infrastructure/
└── models/
```

| File                        | Trách nhiệm                                                                      |
| --------------------------- | -------------------------------------------------------------------------------- |
| `main.py`                   | `create_app` lắp ghép settings, repository, provider, workflow và HTTP transport |
| `api/routes.py`             | Nhận HTTP, gọi application, trả JSON                                             |
| `api/dependencies.py`       | Lấy application từ app state và đọc identity header bootstrap                    |
| `api/middleware.py`         | `request_id_middleware` gắn trace ID cho request/response                        |
| `api/exception_handlers.py` | `handle_service_error` chuyển `ServiceError` sang HTTP error envelope            |
| `application/service.py`   | Kiểm tra idempotency, gọi workflow qua protocol, lưu response, kiểm tra ownership khi GET |
| `application/responses.py` | Dựng envelope thành công/thất bại và metadata bootstrap                         |
| `application/ports.py`     | `RequestWorkflow`, `RequestRepository` và record `StoredRequest`                |
| `workflow/bounded.py`      | `BoundedWorkflow.run` gọi provider dưới timeout                                  |
| `workflow/ports.py`        | Protocol `ModelProvider` mà workflow cần                                        |
| `infrastructure/providers.py` | Adapter `UnconfiguredProvider` trả lỗi 502 khi chưa có provider thật         |
| `infrastructure/repositories.py` | Adapter `InMemoryRequestRepository` lưu request trong memory             |
| `models/`                   | Request, result và response model bằng Pydantic                                  |

**Đã triển khai:** application phụ thuộc vào protocol workflow/repository,
workflow phụ thuộc vào protocol provider; cả hai không import HTTP hoặc
adapter infrastructure. `main.py` lắp ghép implementation cụ thể. Import từ
source root dùng `application.AiApplicationService`, `workflow.BoundedWorkflow`
và `models`; adapter nằm trong `infrastructure/`. Import giữa layer dùng đường
dẫn tuyệt đối, import bên trong mỗi package có thể dùng đường dẫn tương đối.
Uvicorn chạy `main:app --app-dir src`; Pytest và Docker cũng cấu hình source
root là `src/`. API/schema và logic nghiệp vụ giữ nguyên sau khi di chuyển.

Chưa tạo thư mục agent/tool/context/worker vì các thành phần đó chưa có
implementation. Không dùng cấu trúc thư mục để suy ra ADK/Celery đã chạy.

Pipeline POST hiện tại:

```text
request_id_middleware
  → FastAPI dependencies + Pydantic validation
  → api.routes.create_request
  → AiApplicationService.create_request
      → _fingerprint + repository.find_by_idempotency
      → BoundedWorkflow.run → provider.generate
      → _build_succeeded_response / _build_failed_response
      → repository.save
  → JSONResponse / handle_service_error
```

**Một phần:** bootstrap đọc `X-Authenticated-User-ID`; chưa xác minh token hay
nguồn gửi header, chưa kiểm tra quyền trên project/task/sprint. GET mới kiểm
tra user sở hữu AI request. Nginx hiện rewrite `/api/ai/` thành `/`; route
bootstrap giữ đủ prefix nên tích hợp qua gateway còn cần task cấu hình riêng.
Các test API hiện gọi trực tiếp ASGI app. Request validation vẫn dùng envelope
`detail` mặc định của FastAPI, chưa dùng error envelope contract.

## AI workflows và agents

- Giai đoạn 1 gồm `backlog_generation`, `task_decomposition` và
  `risk_analysis`; request boundary đã có, xử lý AI thật: **Chưa có**.
- `BoundedWorkflow` trong `src/workflow/bounded.py` mới là seam timeout
  và provider injection; ADK Workflow điều phối macro-flow: **Chưa có**.
- `LlmAgent` điều phối micro-flow/reasoning: **Chưa có**.
- Specialist agent/agent-as-tool: **Chưa có; chỉ thêm khi use case cần**.
- Agent budget và self-review giới hạn: **Chưa có**.
- Structured output models: **Đã triển khai** trong `models/results.py` và
  response construction. Validation/revise/retry theo intent trong workflow:
  **Chưa triển khai**.

Các intent ngoài giai đoạn 1 như `deadline_check` độc lập, priority suggestion,
task description generation và tự động phân bổ lại workload: **Chưa có trong
phạm vi hiện tại**.

## Tools và prompts

- Context Tool Pool: **Chưa có**.
- Domain tools mục tiêu: task, project, team, progress và development context.
- Agent tools hạ tầng Kafka/database/cache: **Không được tạo**.
- Prompt management: **Chưa có**.
- Khi thêm implementation, search toàn bộ `apps/ai-service/` trước khi tạo mới.

## Worker và job nội bộ

- Celery/Redis dependency, cấu hình app, task và worker entry point: **Chưa có**.
- Compose mới có Redis; chưa khai báo worker/scheduler/outbox publisher.
- Baseline chọn Celery + Redis cho job nội bộ. Khi triển khai, source worker
  nằm trong package AI, gọi application/workflow; API/worker có thể dùng chung
  image và tách process/container. Không ghi file hoặc lệnh chưa tồn tại như
  entry point đã xác minh; xem [job nền](../infrastructure/background-jobs.md).

## Context và events

- Kafka consumers: **Chưa có**.
- Event transform/idempotency: **Chưa có**.
- Internal API adapter/Context Layer: **Chưa có**.
- Context storage/repository: **Chưa có**.
- Context mục tiêu giai đoạn 1: project, task, sprint, progress metric và
  GitHub activity đã chuẩn hóa.
- Agent không biết Kafka; deterministic consumer và Context Layer che giấu
  topic, offset, replay, consumer group và database phía dưới.
- Baseline lấy Project/Task context qua internal API của Work; projection qua
  Kafka chỉ bổ sung khi có nhu cầu. Chưa có endpoint/adapter được xác minh.
- `contracts/events/ai-context-v1.yaml` là schema thiết kế cũ, có producer
  Project/Progress và envelope khác baseline; cần version/mapping trước khi
  dùng với Work. Producer/consumer runtime chưa có. Event kết quả AI chưa có
  schema; xem [danh mục sự kiện](../system/kafka-events.md).

## LLM providers

- Google ADK 2.0 là framework workflow/agent mục tiêu: **Chưa có dependency**.
- `ModelProvider` protocol trong `workflow/ports.py` và `UnconfiguredProvider`
  trong `infrastructure/providers.py` đã có;
  provider/model adapter thật hoặc router: **Chưa có**.
- Provider SDK/configuration: **Chưa có**.
- `infra/env/ai-service.env` hiện chỉ có `DATASETS_DIR`,
  `WORK_SERVICE_URL`, `INTEGRATION_SERVICE_URL`; không có credential hay
  provider setting nào được xác minh cho AI implementation.

## Tests và tooling

- Unit/API/workflow bootstrap tests: `tests/` — **Đã triển khai một phần**.
- Unit test repository, response builders, fingerprint/replay helper và kiểm
  tra hướng import giữa layer: **Đã triển khai**. Wiring HTTP được kiểm tra qua
  API test và container smoke; protocol/re-export không có logic riêng.
- Test Context Tool Pool, agent budget, structured output và proposal boundary:
  **Chưa có**.
- Package manifest/lock: `pyproject.toml`, `uv.lock` — **Đã có**.
- Dockerfile: **Đã có**; image local và healthcheck đã kiểm tra.
- CI khai báo `uv`, Ruff, Pytest và Docker build; xem `AGENTS.md` để biết đúng
  command đã được repository cấu hình.

## Hạ tầng liên quan (read-only)

- Compose service: `docker-compose.yml` (`ai-service`).
- Service environment: `infra/env/ai-service.env`.
- Gateway route: `infra/nginx/nginx.conf` (`/api/ai/`).
- CI workflow: `.github/workflows/python-service.yml` và `.github/workflows/ci.yml`.

Các file hạ tầng trên nằm ngoài writable scope của task setup; chỉ đọc để định
vị integration context, không sửa từ công việc AI Service này.
