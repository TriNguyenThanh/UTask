# AI Service Code Map

**Trạng thái: Một phần.** Runtime request/dispatcher/worker/ADK và PostgreSQL
đã triển khai; kiểm tra ngày 2026-10-08. Integration domain/LLM production và
gateway chưa xác minh. Nguồn pipeline chuẩn: [architecture](architecture.md).

## Service root

Source trực tiếp dưới `apps/ai-service/src/`. Model/schema nghiệp vụ v1 được
reuse; bootstrap synchronous và repository in-memory đã được thay thế.

```text
src/
├── main.py, config.py, errors.py
├── api/
├── application/       # nhận, dispatch, execute request
├── workflow/          # ADK custom workflow + gateway protocol
├── context/           # domain tools gắn với request target
├── infrastructure/    # PostgreSQL, JWT, HTTP, ADK runtime/provider
├── jobs/              # Celery task và dispatcher process
└── models/
```

## API

- `main.py`: composition root API, cleanup HTTP client/DB pool qua lifespan.
- `api/routes.py`: `/healthz`, POST/GET `/api/ai/v1/requests`; POST 200/202,
  GET ownership; chỉ gọi application, không gọi workflow.
- `api/dependencies.py`: Bearer → authenticator protocol; bỏ header identity.
- `api/middleware.py`, `exception_handlers.py`: UUID trace, error envelope
  v1, không đưa raw validation input/exception vào response/log.
- `models/requests.py`: intent/target/input/version; kiểm tra analysis window.
- `models/validation.py`: output schema riêng theo intent.

## AI workflows và agents

- `application/service.py`: authorize → enqueue → chờ/đọc repository.
- `application/execution.py`: claim → reauthenticate/authorize → executor →
  kiểm tra đúng request/intent/schema → finish; exception/timeout thành failed
  và xóa credential. Executor/budget có protocol rõ ràng, application không
  import SDK hoặc adapter concrete.
- `workflow/bounded.py`: ADK `ProposalWorkflow(BaseAgent)` chạy LlmAgent,
  validation, bounded revise/retry; result qua state-delta event.
- `infrastructure/providers.py`: `AdkRuntime`, `AdkRequestExecutor`; chọn model
  qua config/adapter, Runner/session cục bộ, budget callback và hard deadline.
- Ba intent v1 đã có request/result/schema/runtime chung; chất lượng LLM thật
  **Chưa xác minh**. Không có specialist hoặc endpoint apply.

## Tools và prompts

- `context/tools.py`: năm domain tools, scope target cố định, metadata/fingerprint.
- Context thiết yếu được workflow kiểm tra trước khi chấp nhận proposal:
  backlog có target cần project, phân rã cần task, risk cần progress. Agent
  vẫn chọn thứ tự và context bổ sung; không có chuỗi fetch cứng mọi domain.
- `workflow/ports.py`: context gateway protocol; tools không thấy HTTP/SQL/Kafka.
- `infrastructure/context_http.py`: URL cấu hình, quyền, timeout, size/freshness,
  allowlist fields, không redirect. Contract domain thật **Chưa xác minh**.
- `workflow/instructions.py`: instruction riêng theo intent và JSON schema;
  input/context được đánh dấu untrusted. Provider adapter chỉ lắp ghép SDK.

## Worker và job nội bộ

- `application/dispatch.py`: một vòng giao delivery, retry broker, expiry.
- `jobs/celery_app.py`: Redis broker, JSON serializer, late ack, worker lost,
  prefetch 1, không result backend, không task autoretry model.
- `jobs/tasks.py`: `utask_ai.execute_request(request_id)` gọi application.
- `jobs/dispatcher.py`: process giao delivery bằng Celery publisher.
- Execution token + terminal state chống chạy trùng/ghi đè; worker chết được
  dispatcher kết thúc failed khi deadline hết. Không tiếp tục phiên ADK đã mất.

## Context và events

Context lấy qua REST adapter/domain tools, không đọc DB service khác hoặc gọi
GitHub trực tiếp. Kafka consumer/projection/outbox event **Chưa triển khai**;
chỉ thêm khi có nhu cầu và contract mới phù hợp Work.

## Persistence

- `application/ports.py`: repository/auth/authorizer/vault/publisher protocols.
- `models/budget.py`: budget callback protocol, trả số còn lại sau khi trừ.
- `infrastructure/repositories.py`: transaction enqueue + delivery,
  unique user/key, claim, budget, fencing, retry/redelivery/expiry/dead-letter.
- `infrastructure/db/tables.py`: ORM metadata của ba bảng AI.
- `migrations/versions/0001_request_pipeline.py`: Alembic migration độc lập;
  không tạo schema khi startup. Test so sánh migration với ORM trên PostgreSQL.
- `infrastructure/security.py`: JWT và Fernet credential vault; xóa ciphertext
  khi terminal. `infrastructure/bootstrap.py`: SQLAlchemy connection pool.

## LLM providers

Lock hiện dùng Google ADK 2.11, Google GenAI, Celery 5.6, SQLAlchemy 2.1,
Psycopg 3 và Alembic; phiên bản cụ thể nằm trong `uv.lock`. Model mặc định
`gemini-flash-latest`, cấu hình `AI_MODEL`. Cần `GOOGLE_API_KEY` hoặc cơ chế
credential Google tương ứng trước khi gọi model thật; chưa chạy evaluation.

## Tests và tooling

- `test_models.py`, `test_contract.py`: request/version/range và wire schema v1.
- `test_security.py`: JWT ký thật, issuer/audience/expiry, vault và config.
- `test_context.py`: quyền, thiếu/cũ context, HTTP lỗi/redirect/size, filter/tool budget.
- `test_workflow.py`: Runner/ADK thật với BaseLlm fake; success, tools, schema
  sai, retry provider, budget và timeout.
- `test_repository.py`: PostgreSQL thật, enqueue đồng thời, rollback, claim,
  budget, fencing, redelivery, expiry và dead-letter.
- `test_application.py`, `test_api_transport.py`: 200/202, ownership/replay,
  conflict, worker failed, permission và error envelope.
- `test_jobs.py`: task/dispatcher wiring, migration và Redis/Celery thật khi
  có `TEST_REDIS_URL`. Protocol và composition không có business rule riêng;
  kiểm tra qua API/integration thay mock từng dòng wiring.
- `test_architecture.py`: import boundaries.
- `test_layer_frameworks.py`: SDK/I/O chỉ nằm trong layer cho phép.
- `test_application_unit.py`, `test_execution_unit.py`, `test_instructions.py`,
  `test_lifecycle.py`: polling/replay, worker boundary, prompt/schema và cleanup
  lỗi bằng doubles, không cần DB. `test_workflow_intents.py` kiểm tra context
  thiết yếu và wire schema thành công/lỗi cho cả ba intent qua ADK thật.

Chạy lệnh tại [README](README.md). Không đặt `TEST_DATABASE_URL`/`TEST_REDIS_URL`
thì test hạ tầng được skip; báo rõ khi chỉ chạy unit tests.

## Hạ tầng liên quan (read-only)

Compose/env/Nginx/CI root chưa được cập nhật cùng deployment AI. Trạng thái
runtime service và deployment toàn hệ thống là hai phạm vi khác nhau; xem
[architecture](architecture.md) để biết requirement gateway/domain còn lại.

[`compose.yaml`](../../apps/ai-service/compose.yaml) của riêng AI lắp API,
dispatcher, worker, PostgreSQL, Redis và migration; cấu hình mẫu ở
[`.env.example`](../../apps/ai-service/.env.example). Đây là stack local,
không là integration test Identity/Work/Integration hoặc gateway root.
