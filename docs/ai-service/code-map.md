# AI Service Code Map

**Trạng thái: Một phần.** Runtime request/dispatcher/worker/ADK và PostgreSQL
đã triển khai; verifier RS256, Identity session client và mock test bằng HTTP
Identity giả có source/test local. Provider Work **đã có source**; tích hợp
runtime domain/Identity, LLM production và E2E gateway staging **Chưa xác minh**.
Xem [production readiness](production-readiness.md).
Nguồn pipeline chuẩn: [architecture](architecture.md).

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
├── evaluation/        # golden cases, CLI deterministic/live và report JSON/JUnit
└── models/
```

## API

- `config.py`: nạp ai-service.env + .env root, cờ môi trường/mock; cấu hình
  `AI_IDENTITY_BASE_URL` (mặc định `http://identity-service:8000`) và
  `AI_IDENTITY_SERVICE_KEY`; `AI_WORK_SERVICE_AUTH_ENABLED=false` mặc định,
  chỉ bắt buộc Work key khi bật cờ. Cấm mock ngoài development/test; staging/
  production yêu cầu issuer/audience, Identity key và Fernet key hợp lệ.
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

- `context/tools.py`: domain tools, scope target cố định, metadata/fingerprint;
  GitHub chỉ cấp cho risk Project khi flag/focus cho phép. Sprint/flag tắt
  được runtime thêm limitation xác định, không phụ thuộc prompt model.
- Context thiết yếu được workflow kiểm tra trước khi chấp nhận proposal:
  backlog có target cần project, phân rã cần task, risk cần progress. Agent
  vẫn chọn thứ tự và context bổ sung; không có chuỗi fetch cứng mọi domain.
- `workflow/ports.py`: context gateway protocol; tools không thấy HTTP/SQL/Kafka.
- `infrastructure/context_http.py`: AI-side POST Work authorize với envelope
  target/action; Bearer luôn gửi, `X-Service-Key` chỉ gửi khi
  `AI_WORK_SERVICE_AUTH_ENABLED=true`. GET raw context; timeout, stream giới hạn
  65536 byte/freshness, không redirect. Provider Work hiện yêu cầu cả Bearer
  và caller key, nên cấu hình tích hợp phải bật flag này và cấp key khớp.
  Source adapter và test mock không tự chứng minh quyền runtime. GitHub giao
  Integration authorize Work bằng key Integration riêng, AI không gọi Work lần
  nữa trong nhánh fetch đó.
- `models/context.py`: shape project/task/team/progress/GitHub, kiểu và giới
  hạn lồng nhau; lọc trường ngoài allowlist Work, strict GitHub theo contract.
  Work boundary có hợp đồng và provider đã triển khai; xem
  [phạm vi kiểm chứng Work–AI](../project-service/ai-service-integration-guide.md).
- `workflow/instructions.py`: instruction riêng theo intent và JSON schema;
  input/context được đánh dấu untrusted. Provider adapter chỉ lắp ghép SDK.

## Worker và job nội bộ

- `application/dispatch.py`: một vòng giao delivery, retry broker, expiry.
- `jobs/celery_app.py`: Redis broker, JSON serializer, late ack, worker lost,
  prefetch 1, không result backend, không task autoretry model.
- `jobs/tasks.py`: `utask_ai.execute_request(request_id)` gọi application.
- `jobs/dispatcher.py`: process giao delivery bằng Celery publisher.
- `jobs/celery_app.py`, `jobs/tasks.py`: beat schedule và task retention terminal;
  mỗi giờ tối đa 500 request cũ hơn 30 ngày, retry lỗi DB có giới hạn.
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
  application lifespan không tạo schema. Entrypoint container API chạy
  `alembic upgrade head` trước Uvicorn; lỗi thì dừng API. Test so sánh migration
  với ORM trên PostgreSQL; `test_container_startup.py` kiểm tra shell bằng lệnh
  giả: thứ tự migrate/API, lỗi, restart ở head, args/exit/PID và lệnh bỏ qua.
- `migrations/versions/0002_completion_handoff.py`: completion inbox và index;
  migration bắt buộc trước API/worker dùng bàn giao kết quả.
- `migrations/versions/0003_request_admission.py`: hai index đếm request theo
  user/thời gian và user/trạng thái active; không thêm bảng hay broker.
- `migrations/versions/0004_terminal_retention.py`: terminal_at/backfill/check
  và partial index; index thông thường cần maintenance window khi bảng lớn.
  `repositories.cleanup_terminal` khóa batch terminal, cascade con trong AI DB.
- `infrastructure/security.py`: mỗi lần xác thực tải raw JWKS từ Identity,
  không cache hoặc dùng PEM/URL JWKS cấu hình riêng; chỉ chọn đúng một khóa RSA
  sau khi lọc `kty`, `use`/`alg` (mặc định `sig`/`RS256`) và `kid` nếu có.
  Xác minh claim bắt buộc `exp`, `iss`, `aud`, `sub`, `token_type` (`iat` tùy
  chọn), UUID `sub`, `token_type=access`; gọi session-status với Bearer và
  `X-Service-Key`, yêu cầu response 2xx cùng `success: true` và
  `data.active` boolean. Session revoked trả 401; dependency/response lỗi phát sinh
  `AUTH_UNAVAILABLE`. Fernet vault giữ token giữa API/worker và xóa ciphertext
  khi bàn giao completion hoặc terminal. `infrastructure/bootstrap.py`:
  SQLAlchemy connection pool.

## LLM providers

- `infrastructure/providers.py`: endpoint OpenAI-compatible qua LiteLLM,
  JSON mode, tắt retry ở cả LiteLLM và SDK, deadline/budget callback.
  Usage completion đã gồm reasoning nên không cộng thoughts lần nữa.
- `workflow/bounded.py`: retry lỗi Google và OpenAI/LiteLLM có thể phục hồi
  trong cùng model/output budget và số vòng revise; gỡ một JSON fence bao
  trọn output trước validation, không trích JSON từ văn bản tùy ý.
- `tests/test_provider_http.py`: ADK/LiteLLM/OpenAI thật với HTTP transport
  fake; kiểm tra JSON mode, tool roundtrip, HTTP 503/401 và timeout.
  Test không cần credential/provider ngoài. LLM local đã gọi thật ngày
  2026-10-15; domain context và production vẫn **Chưa xác minh**.

Lock hiện dùng Google ADK 2.11, LiteLLM, Celery 5.6, SQLAlchemy 2.1,
Psycopg 3 và Alembic; phiên bản cụ thể nằm trong `uv.lock`. Không có model mặc định
trong code; `build_litellm_model` yêu cầu `AI_MODEL` theo ID gốc hoặc route `openai/<id>`,
`AI_LLM_API_BASE` và `AI_LLM_API_KEY`. Adapter ADK `LiteLlm` gọi endpoint tương
thích OpenAI, không tự chọn endpoint/provider thay cấu hình. Chưa xác minh nhà
cung cấp cụ thể hoặc chạy evaluation production.

## Tests và tooling

- `evaluation/cases.json`: 30 golden case, phiên bản dataset/rubric; mỗi intent
  ít nhất 10 case. `evaluation/runner.py`: adapter/ADK với model/HTTP fake ở
  deterministic; live POST/GET qua gateway, model pin và target fixture staging.
  `evaluation/__main__.py`: CLI và exit code gate; JSON/JUnit chỉ lưu checks,
  timing và metadata/hash, không raw output/context/credential.
- `tests/test_evaluation.py`: dataset/rule, ngưỡng gate và hai chế độ runner;
  kiểm tra fake transport không là bằng chứng evaluation live production.

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
- `test_identity_session_auth.py`: JWKS fetch từng lần, key filter/kid, JWT
  claims và session-status; HTTP Identity fake, không bypass auth. `test_security.py`
  kiểm tra vault/config.
- `test_context.py`: quyền, thiếu/cũ context, HTTP lỗi/redirect/size, filter/tool budget.
- `test_context_contract.py`: Work POST/envelope/key theo đích, typed shape,
  PII allowlist, GitHub không double authorize, tool scope/flag và limitation.
- `test_retention_unit.py`, `test_retention_postgres.py`,
  `test_retention_migration.py`: cleanup/task wiring, cascade/concurrency,
  legacy backfill, dữ liệu thời gian sai và index/schema drift.
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
- `scripts/setup_mock.py`: tạo UUID owner/outsider, access JWT RS256 và
  `.env.mock/jwks.json` cho test HTTP Identity giả; không ghi public PEM vào
  `.env` hoặc tạo session runtime.
- `test_mock_context.py`: fixture/permission/boundary, chọn nguồn, ADK thật
  với LLM fake và kiểm tra lắp adapter giống nhau ở API/worker.
- `test_mock_pipeline.py`: API → dispatcher → Redis/Celery → ADK với fixture
  → completion/API → terminal result; JWT ký thật và Identity HTTP fake.

**Đã triển khai mock data tại adapter**; domain production vẫn **Chưa xác minh**.
Cách dùng nằm tại [mock data](mock-data.md). Không còn thư mục dev, server
mock-domain hoặc Compose override; luồng request/polling giữ nguyên.

## Hạ tầng liên quan (read-only)

Compose root local/staging có API, dispatcher, worker và beat AI dùng chung image;
entrypoint API chạy Alembic trước Uvicorn. Hướng dẫn cấu hình và vận hành nằm
trong [README](README.md#chạy-từ-compose-root). Cấu hình Compose không chứng
minh gateway/domain hoặc production đã tích hợp; xem [architecture](architecture.md)
để biết requirement còn lại.

[`compose.yaml`](../../apps/ai-service/compose.yaml) của riêng AI lắp API,
dispatcher, worker, beat, PostgreSQL và Redis; API entrypoint chạy Alembic trước
Uvicorn, worker/dispatcher/beat chờ API và broker healthy. Không còn service migrate
riêng; cấu hình mẫu ở
[cấu hình AI](../../infra/env/ai-service.env) và [mẫu secret root](../../.env.example). Đây là stack local,
không là integration test Identity/Work/Integration hoặc gateway root.
