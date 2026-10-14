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

- `config.py`: nạp ai-service.env + .env root, cờ môi trường/mock và
  SecretStr cho LLM key; cấm mock ngoài development/test.
- `main.py`: composition root API, cleanup HTTP client/DB pool qua lifespan.
- `api/routes.py`: `/healthz`, POST/GET `/api/ai/v1/requests`; POST 200/202,
  GET ownership; chỉ gọi application, không gọi workflow.
- `api/dependencies.py`: Bearer → authenticator protocol; bỏ header identity.
- `api/middleware.py`, `exception_handlers.py`: UUID trace, error envelope
  v1, không đưa raw validation input/exception vào response/log.
  Lỗi giới hạn tiếp nhận trả `Retry-After`, không thêm header cho lỗi budget.
- `models/requests.py`: intent/target/input/version; kiểm tra analysis window.
- `models/validation.py`: output schema riêng theo intent.

## AI workflows và agents

- `application/service.py`: authorize → enqueue → chờ/đọc repository;
  `accept_completions` là use case API tiếp nhận kết quả worker.
- `application/execution.py`: claim → reauthenticate/authorize → executor →
  kiểm tra đúng request/intent/schema → stage_completion + NOTIFY;
  exception/timeout bàn giao như failed, xóa credential khi bàn giao.
  Executor/budget có protocol rõ ràng, application không
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
- Execution token + terminal state chống chạy trùng/ghi đè; worker chết trước
  bàn giao được dispatcher kết thúc failed khi deadline hết. Completion đã
  commit được giữ cho API, không timeout vì listener tạm dừng. Không tiếp tục
  phiên ADK đã mất.

## Context và events

Context lấy qua REST adapter/domain tools, không đọc DB service khác hoặc gọi
GitHub trực tiếp. Kafka consumer/projection/outbox event **Chưa triển khai**;
chỉ thêm khi có nhu cầu và contract mới phù hợp Work.

## Persistence

- `application/ports.py`: repository/auth/authorizer/vault/publisher protocols.
- `models/budget.py`: budget callback protocol, trả số còn lại sau khi trừ.
- `infrastructure/repositories.py`: transaction enqueue + delivery,
  unique user/key, claim, budget, fencing, retry/redelivery/expiry/dead-letter
  và completion inbox.
  Advisory lock theo user bảo vệ giới hạn 5 request mới/60 giây và 2 request
  queued/running; replay/conflict được kiểm tra trước giới hạn. Ngưỡng qua config.
- `infrastructure/completions.py`: listener trong API lifespan; LISTEN trước
  khi đọc inbox, nhận NOTIFY, reconnect và phục hồi định kỳ; không chạy model.
- `infrastructure/db/tables.py`: ORM metadata của bốn bảng AI.
- `migrations/versions/0001_request_pipeline.py`: Alembic migration độc lập;
  không tạo schema khi startup. Test so sánh migration với ORM trên PostgreSQL.
- `migrations/versions/0002_completion_handoff.py`: completion inbox và index;
  migration bắt buộc trước API/worker dùng bàn giao kết quả.
- `migrations/versions/0003_request_admission.py`: hai index đếm request theo
  user/thời gian và user/trạng thái active; không thêm bảng hay broker.
- `infrastructure/security.py`: JWT và Fernet credential vault; xóa ciphertext
  khi bàn giao completion hoặc terminal. `infrastructure/bootstrap.py`: SQLAlchemy connection pool.

## LLM providers

Lock hiện dùng Google ADK 2.11, LiteLLM, Celery 5.6, SQLAlchemy 2.1,
Psycopg 3 và Alembic; phiên bản cụ thể nằm trong `uv.lock`. Không có model mặc định
trong code; `build_litellm_model` yêu cầu `AI_MODEL` theo ID gốc hoặc route `openai/<id>`,
`AI_LLM_API_BASE` và `AI_LLM_API_KEY`. Adapter ADK `LiteLlm` gọi endpoint tương
thích OpenAI, không tự chọn endpoint/provider thay cấu hình. Chưa xác minh nhà
cung cấp cụ thể hoặc chạy evaluation production.

## Tests và tooling

- `test_admission.py`: quyết định giới hạn, cấu hình, replay/conflict, cửa sổ
  60 giây, queued/running/completion, giải phóng slot và POST đồng thời qua
  nhiều connection PostgreSQL.
- `test_admission_transport.py`: lỗi 429/Retry-After và wire schema v1, không
  đổi lỗi budget; API từ chối key mới nhưng vẫn cho replay/polling.
- `test_completion_unit.py`: application tiếp nhận, listener reconnect khi
  connect/LISTEN/accept/notify lỗi, thứ tự LISTEN/read, cancellation và cleanup.
- `test_completion_postgres.py`: handoff bền vững, NOTIFY thật, API lifespan
  ghi terminal result, phục hồi inbox sau restart, nhiều API consumer, token
  cũ, deadline, schema/intent/version sai và rollback transaction.
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

## Mock data cho context chưa có microservice

- `infrastructure/context_factory.py`: API và worker dùng cùng factory,
  chọn FixtureContextAdapter khi MOCK_TEST=true, InternalContextAdapter khi false.
- `infrastructure/context_fixtures.py`: đọc fixture, kiểm tra quyền domain theo
  allowed_users/target, lọc dữ liệu và trả ContextDocument giống REST adapter.
  Không gọi HTTP, không bỏ kiểm tra JWT tại API/worker.
- `infrastructure/fixtures/domain.json`: dữ liệu Project/Task/Sprint, team,
  progress và GitHub activity giả; đóng gói cùng src trong image.
- `examples/requests/`: payload để gọi API AI thật cho ba intent.
- `scripts/setup_mock.py`: tiện ích credential/JWT local khi cần; không nằm
  trong pipeline xử lý, không chạy server hoặc launcher Compose.
- `test_mock_context.py`: fixture/permission/boundary, chọn nguồn, ADK thật
  với LLM fake và kiểm tra lắp adapter giống nhau ở API/worker.
- `test_mock_pipeline.py`: API → dispatcher → Redis/Celery → ADK với fixture
  → completion/API → terminal result, PostgreSQL/Redis/JWT thật.

**Đã triển khai mock data tại adapter**; domain production vẫn **Chưa xác minh**.
Cách dùng nằm tại [mock data](mock-data.md). Không còn thư mục dev, server
mock-domain hoặc Compose override; luồng request/polling giữ nguyên.

## Hạ tầng liên quan (read-only)

Compose/env/Nginx/CI root chưa được cập nhật cùng deployment AI. Trạng thái
runtime service và deployment toàn hệ thống là hai phạm vi khác nhau; xem
[architecture](architecture.md) để biết requirement gateway/domain còn lại.

[`compose.yaml`](../../apps/ai-service/compose.yaml) của riêng AI lắp API,
dispatcher, worker, PostgreSQL, Redis và migration; cấu hình mẫu ở
[cấu hình AI](../../infra/env/ai-service.env) và [mẫu secret root](../../.env.example). Đây là stack local,
không là integration test Identity/Work/Integration hoặc gateway root.
