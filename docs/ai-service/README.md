# AI Service

**Trạng thái: Một phần.** Bootstrap transport/application đã có trong
`apps/ai-service/`; provider thật, ADK workflow, Celery worker, context adapter, Kafka và
persistence production chưa triển khai.

Đây là trang điều hướng cho tài liệu AI Service. Không coi các phần thiết kế
API, event, provider hoặc agent là runtime đã hoàn chỉnh nếu code map chưa xác
nhận.

## Baseline và phạm vi

Thiết kế mục tiêu theo [baseline](../architecture/README.md), mục 4.6, 9–11
và 18. Các quyết định chuyển đổi nằm trong
[ADR-001](../adr/001-adopt-architecture-baseline.md). Baseline chọn Celery +
Redis cho job nội bộ; Kafka cho event giữa service; AI lấy context qua internal
API sau domain tool/Context Layer. Worker và context adapter chưa có trong source.

Pipeline đã chốt là API kiểm tra quyền qua REST, lưu request và ý định giao
job bền vững, dispatcher giao task qua Redis, Celery worker chạy workflow và
lưu kết quả vào PostgreSQL của AI. API đọc cùng persistence để client polling;
Kafka phục vụ sự kiện giữa service. Nguồn chi tiết là
[pipeline trong kiến trúc AI](architecture.md) và quyết định tại
[ADR-002](../adr/002-ai-request-pipeline.md). Đây là **thiết kế mục tiêu**,
không thay thế pipeline bootstrap trong [code map](code-map.md).

Baseline nêu roadmap AI rộng hơn contract v1. Không coi ba intent dưới đây là
thứ tự Phase 1–4 của roadmap hệ thống, hoặc tự thêm intent ngoài contract.

## Phạm vi API v1

AI Service giai đoạn 1 chỉ hỗ trợ ba intent:

- `backlog_generation`: tạo backlog nháp từ mô tả project hoặc chức năng;
- `task_decomposition`: phân rã một task phức tạp thành các subtask;
- `risk_analysis`: tổng hợp và giải thích nguy cơ ảnh hưởng Sprint hoặc deadline.

`deadline_check` độc lập, gợi ý priority, tạo mô tả task, phân bổ lại workload
và các hành động tự động nằm ngoài giai đoạn 1, dành cho giai đoạn sau.

## Chạy bootstrap local

Chạy trong `apps/ai-service/`:

```sh
uv sync --all-groups --locked
uv run uvicorn main:app --app-dir src --reload
```

Kiểm tra trực tiếp `GET http://localhost:8000/healthz`. Provider mặc định trả
`502 PROVIDER_UNAVAILABLE` cho yêu cầu AI hợp lệ có identity header bootstrap.
Đường đi và giới hạn triển khai nằm trong [code map](code-map.md).

Kiểm tra chất lượng:

```sh
uv run ruff format --check .
uv run ruff check .
uv run pytest
docker build --tag utask/ai-service:local .
```

## Chọn tài liệu theo task

Đây là bộ định tuyến đọc tài liệu, không yêu cầu agent nạp toàn bộ thư mục
`docs/ai-service/` cho mỗi task. Sau khi đọc trang này, chỉ đọc tài liệu bắt
buộc và phần liên quan trong cột tùy chọn.

| Loại task                                 | Bắt buộc đọc                                                                         | Chỉ đọc thêm khi cần                                                                                      |
| ----------------------------------------- | ------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------- |
| API, request/response, OpenAPI            | `api.md` và phần boundary trong `architecture.md`                                    | `workflow.md` khi thay đổi orchestration/output; `erd.md` khi thay đổi persistence                        |
| Workflow, agent, tool, prompt, budget     | Phần workflow liên quan trong `workflow.md` và phần boundary trong `architecture.md` | `api.md` khi thay đổi API output; `erd.md` khi lưu execution/context                                      |
| Context, Kafka consumer, read model       | Phần Context/Kafka trong `architecture.md`, `workflow.md` và `erd.md`                | `api.md` nếu context metadata xuất hiện trong response; `code-map.md` khi định vị implementation          |
| Database, projection, migration           | `erd.md` và phần Context flow trong `architecture.md`                                | `api.md` nếu schema ảnh hưởng request/result; `workflow.md` nếu ảnh hưởng tool/runtime                    |
| Provider, model, retry, structured output | Phần output/budget/model trong `workflow.md`                                         | `api.md` khi thay đổi schema trả cho client; `architecture.md` khi thay đổi failure boundary              |
| Tìm entry point hoặc audit implementation | `code-map.md` và tài liệu của thành phần đang kiểm tra                               | Chỉ đọc `architecture.md`, `api.md`, `workflow.md` hoặc `erd.md` khi kết quả audit cần đối chiếu thiết kế |
| Chỉ sửa tài liệu                          | File đích và các file được nó liên kết trực tiếp                                     | Không đọc file dài nếu không cần đối chiếu nội dung                                                       |

### Quy tắc đọc file dài

- Với `workflow.md`, trước tiên dùng heading để chọn section: agent/workflow,
  Context Tool Pool, Kafka, bounded autonomy, proposal, budget, structured
  output hoặc model strategy. Không đọc toàn bộ file nếu task chỉ thuộc một
  section.
- Với `architecture.md`, chọn một trong các phần: boundary/request,
  context-flow, dependency hoặc failure isolation.
- Với `erd.md`, chỉ đọc ERD và ràng buộc/index khi task liên quan persistence;
  không dùng ERD để suy ra endpoint đã triển khai.
- `tech-stack.md` chỉ dùng để kiểm tra lựa chọn công nghệ mục tiêu; không cần
  đọc cho task API, workflow hoặc context trừ khi task thay đổi stack.
- Nếu task thuộc nhiều nhóm, lấy hợp của các tài liệu bắt buộc; vẫn bỏ qua
  các tài liệu tùy chọn không ảnh hưởng.

- [Kiến trúc, boundary và discrepancy](architecture.md)
- [API mục tiêu giai đoạn 1](api.md)
- [Workflow bounded agent và Context Tool Pool](workflow.md)
- [ERD và schema mục tiêu](erd.md)
- [Stack mục tiêu và dependency hiện tại](tech-stack.md)
- [Job nền và worker](../infrastructure/background-jobs.md)
- [Code map và các entry point đã xác minh](code-map.md)

Instruction mặc định khi làm việc trong source nằm tại
[`apps/ai-service/AGENTS.md`](../../apps/ai-service/AGENTS.md). Plan cho thay đổi
lớn nằm tại [`apps/ai-service/.agent/PLANS.md`](../../apps/ai-service/.agent/PLANS.md).
