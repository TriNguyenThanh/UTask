# AI Service

**Trạng thái: Một phần.** Pipeline API/PostgreSQL/dispatcher/Redis/Celery/ADK
đã triển khai trong `apps/ai-service/`; xác minh chữ ký JWT và kiểm tra session
qua Identity có source/test local. Identity/Work/Integration và LLM production
**Chưa xác minh**;
Retention terminal đã có source, migration và lịch Celery beat; Kafka và
specialist **Chưa triển khai**. Điều kiện phát hành và phần chưa xác minh nằm
tại [mức sẵn sàng production](production-readiness.md).
CI chạy deterministic evaluation; live evaluation là lệnh thủ công tùy chọn,
không phải điều kiện deploy staging. Hướng dẫn và các biến `EVAL_AI_*` nằm tại
[phần evaluation](production-readiness.md#evaluation-và-gate-phát-hành).

Đây là trang điều hướng cho tài liệu AI Service. Không coi các phần thiết kế
API, event, provider hoặc agent là deployment production đã hoàn chỉnh chỉ
từ thiết kế. [Code map](code-map.md) giữ bằng chứng implementation và kiểm thử.

[Checkpoint 21/10/2026](checkpoint.md) tổng hợp tiến độ M1–M4, blocker local,
bằng chứng kiểm thử và việc tiếp theo theo đội; giữ lịch sử smoke LLM thật
ngày 15/10 riêng để không nhầm với nghiệm thu domain/staging.

## Baseline và phạm vi

Thiết kế mục tiêu theo [baseline](../architecture/README.md), mục 4.6, 9–11
và 18. Các quyết định chuyển đổi nằm trong
[ADR-001](../adr/001-adopt-architecture-baseline.md). Baseline chọn Celery +
Redis cho job nội bộ; Kafka cho event giữa service; AI lấy context qua internal
API sau domain tool/Context Layer. API, dispatcher, worker và beat thuộc cùng service,
scale độc lập và dùng chung PostgreSQL của AI.

MVP lấy context qua REST khi thực thi và giữ nội dung trong bộ nhớ worker;
PostgreSQL vẫn lưu request/result và metadata, Redis vẫn là broker. Agent
phải đọc [chính sách context hiện tại và mở rộng](architecture.md#chính-sách-context-hiện-tại-và-mở-rộng)
trước khi thêm cache, snapshot hoặc projection.

Pipeline đã chốt theo contract là AI gửi yêu cầu authorize target qua REST,
lưu request và ý định giao job bền vững, dispatcher giao task qua Redis,
Celery worker chạy workflow và
bàn giao kết quả vào PostgreSQL của AI, phát `NOTIFY` trong cùng transaction.
Listener trong API tiếp nhận và cập nhật trạng thái/kết quả cuối, phục hồi
inbox khi bỏ lỡ tín hiệu. API đọc cùng persistence để client polling;
Kafka phục vụ sự kiện giữa service. Nguồn chi tiết là
[pipeline trong kiến trúc AI](architecture.md) và quyết định tại
[ADR-002](../adr/002-ai-request-pipeline.md). Pipeline source đã được kiểm thử
với PostgreSQL, Redis và ADK fake model. Work AI contract còn `planned`, provider
chưa có source nên quyền/role Work runtime chưa xác minh; giới hạn tích hợp nằm trong
[code map](code-map.md).

Baseline nêu roadmap AI rộng hơn contract v1. Không coi ba intent dưới đây là
thứ tự Phase 1–4 của roadmap hệ thống, hoặc tự thêm intent ngoài contract.

## Phạm vi API v1

AI Service giai đoạn 1 chỉ hỗ trợ ba intent:

- `backlog_generation`: tạo backlog nháp từ mô tả project hoặc chức năng;
- `task_decomposition`: phân rã một task phức tạp thành các subtask;
- `risk_analysis`: tổng hợp và giải thích nguy cơ ảnh hưởng Sprint hoặc deadline.

`deadline_check` độc lập, gợi ý priority, tạo mô tả task, phân bổ lại workload
và các hành động tự động nằm ngoài giai đoạn 1, dành cho giai đoạn sau.

## Cấu hình

Chỉ dùng hai nguồn: [ai-service.env](../../infra/env/ai-service.env) chứa
biến thường và cờ chế độ; `.env` ở root chứa secret, tạo theo
[mẫu root](../../.env.example). Settings đọc config rồi secret; biến process
có ưu tiên cao nhất. Compose chỉ inject các secret AI cần dùng. Các biến chính:

| Biến | Ý nghĩa |
| --- | --- |
| `AI_ENVIRONMENT`, `MOCK_TEST` | Chế độ development/test/staging/production và cờ context mock |
| `AI_DATABASE_URL` | URL database của AI; override tùy chọn trong `.env` root, password phải percent-encode nếu chứa ký tự đặc biệt |
| `AI_DB_NAME` | Tên database AI trên PostgreSQL chung của Compose root; mặc định `ai_context_db` |
| `POSTGRES_USER`, `POSTGRES_PASSWORD` | Credential PostgreSQL chung với Django trong Compose root; dùng để tạo URL khi không có `AI_DATABASE_URL` |
| `AI_DB_PASSWORD` | Chỉ dùng cho PostgreSQL của Compose riêng tại `apps/ai-service/compose.yaml` |
| `AI_BROKER_URL` | Redis broker; không dùng Redis làm result repository |
| `AI_CREDENTIAL_KEY` | Khóa Fernet giống nhau cho API/worker; ciphertext xóa khi bàn giao kết quả hoặc terminal |
| `AI_COMPLETION_RECONCILE_SECONDS` | Khoảng phục hồi completion inbox và thử lại listener; mặc định 5 giây |
| `AI_REQUESTS_PER_MINUTE` | Số request mới tối đa/user trong 60 giây; mặc định 5 |
| `AI_MAX_ACTIVE_REQUESTS_PER_USER` | Số request queued/running tối đa/user; mặc định 2 |
| `AI_WORK_SERVICE_AUTH_ENABLED` | Mặc định `false`; tạm thời bỏ riêng header `X-Service-Key` khi AI gọi Work. Bearer actor và yêu cầu authorize theo target/intent vẫn được gửi |
| `AI_WORK_SERVICE_KEY` | Chỉ bắt buộc và chỉ gửi khi `AI_WORK_SERVICE_AUTH_ENABLED=true`; secret AI → Work, inject qua environment |
| `AI_INTEGRATION_SERVICE_KEY` | Secret AI → Integration; không bị ảnh hưởng bởi cờ Work |
| `AI_GITHUB_CONTEXT_ENABLED` | Mặc định false; chỉ cấp development tool cho risk Project khi focus cho phép |
| `AI_TERMINAL_RETENTION_DAYS`, `AI_RETENTION_BATCH_SIZE`, `AI_RETENTION_INTERVAL_SECONDS` | Mặc định 30 ngày, tối đa 500 request/lần, một lần mỗi 3600 giây |
| `AI_JWT_ISSUER`, `AI_JWT_AUDIENCE` | Issuer/audience dùng để xác minh JWT; mặc định theo Identity |
| `AI_IDENTITY_BASE_URL` | Base URL nội bộ Identity; mặc định `http://identity-service:8000` |
| `AI_IDENTITY_SERVICE_KEY` | Secret caller AI gửi qua `X-Service-Key` khi gọi session-status; phải khớp mục `ai` trong `IDENTITY_SERVICE_KEYS` của Identity |
| `AI_AUTHORIZATION_URLS` | JSON map target type → URL kiểm tra quyền |
| `AI_CONTEXT_URLS` | JSON map `target_type:domain` → URL lấy context |
| `AI_LLM_PROVIDER` | Chọn adapter `litellm` |
| `AI_MODEL` | Model ID mà local proxy công bố; adapter tự thêm route LiteLLM `openai/` |
| `AI_LLM_API_BASE` | URL endpoint tương thích OpenAI, ví dụ `https://provider.example/v1` |
| `AI_LLM_API_KEY` | API key trong `.env` root, bắt buộc khi gọi LLM thật |

URL template chỉ dùng `{target_type}` và `{target_id}` từ request đã validate.
Các target là `project`, `task`, `sprint`; domain là `project`, `task`, `team`,
`progress`, `github_activity`. Work boundary đã chốt tại
[Work AI context v1](../../contracts/api/work-ai-context-v1.yaml), được
[Work contract](../../contracts/api/work-service.yaml) tham chiếu và còn ở trạng thái
`planned`; provider Work **Chưa triển khai**. AI-side adapter POST body
`action: ai.analyze` và `intent`, kiểm tra envelope `success/data` cùng
target/action/allowed; GET context nhận `ContextDocument` trực tiếp, tối đa
65536 byte. Bearer actor luôn được gửi. Header Work `X-Service-Key` chỉ được
gửi khi `AI_WORK_SERVICE_AUTH_ENABLED=true`; mặc định `false` chỉ bỏ header đó,
không bỏ yêu cầu authorize theo target/intent. Vì provider Work chưa có source,
không thể kết luận role/target authorization đã chạy runtime. GitHub đi Integration;
Integration tự hỏi Work quyền
`github.read`, AI không gọi thêm Work cho lần đọc GitHub. Xem
[boundary và cấu hình staging](production-readiness.md#boundary-domain-và-quyền).
Thiếu cấu hình hoặc quyền/context lỗi thì từ chối; không fallback fixture.

ADK dùng `LiteLlm` để gọi custom endpoint tương thích OpenAI. Model có thể là
ID gốc của proxy (ví dụ `gemini-3.8-flash-high`) hoặc route `openai/<model-id>`,
kèm `AI_LLM_API_BASE` và key.
Thiếu hoặc sai cấu hình thì worker trả `PROVIDER_UNAVAILABLE` trước lời gọi
model, với reason chỉ rõ trường cần sửa. HTTPS được yêu cầu ngoài development/
test; HTTP chỉ được phép trong development/test. Timeout lấy từ deadline
request và LiteLLM không tự retry. Cách gọi này giữ nguyên pipeline request,
context và budget; nó không xác nhận endpoint hay model cụ thể của nhà cung cấp.

Adapter yêu cầu JSON mode (`response_format: {type: json_object}`); endpoint
phải hỗ trợ JSON mode cùng tool calling. Workflow vẫn kiểm tra schema riêng
theo intent và revise trong giới hạn. Một số proxy vẫn trả khối Markdown dù
đã yêu cầu JSON mode: workflow chỉ gỡ một khối JSON bao trọn output rồi
validate schema; văn bản thừa, JSON lỗi, field thừa hoặc sai intent bị từ chối.
LiteLLM và SDK OpenAI đều tắt retry ẩn;
lỗi 429/5xx, kết nối hoặc timeout provider được workflow retry trong budget
và deadline chung. `completion_tokens` đã gồm reasoning, chỉ trừ một lần.

Để chọn model nhanh hơn cho stack local, từ `apps/ai-service/`:

```sh
AI_MODEL=gemini-3.5-flash-lite docker compose --project-name ai-mock \
  --env-file ../../.env --env-file ../../infra/env/ai-service.env \
  up --build -d --wait --wait-timeout 60
```

Compose riêng AI truyền model/base URL từ cấu hình đã resolve cho cả API,
worker và dispatcher; biến process có ưu tiên cao nhất. Giữ override model
trong lệnh khởi động tiếp theo nếu muốn dùng lại model này. Model
`gemini-3.8-flash-high` đã vượt hard deadline 30 giây trong smoke local ngày
2026-10-15; không tăng deadline ngoài hợp đồng API v1 để che lỗi đó.

LLM local qua CLIProxyAPI đã được gọi thật; quyền/context vẫn là fixture
`MOCK_TEST=true`, không chứng minh integration domain hoặc production.
Smoke ngày 2026-10-15 với `gemini-3.5-flash-lite` qua API → PostgreSQL →
dispatcher → Redis/Celery → ADK → completion → API:

| Intent | Kết quả đã xác minh | Thời gian quan sát |
| --- | --- | --- |
| task_decomposition | succeeded, 3 subtasks, context task | 13,1 giây |
| backlog_generation | succeeded, 2 items, context project | 5,3 giây |
| risk_analysis | succeeded, 1 risk, context progress/team/project/github_activity | 4,9 giây |

Đây là smoke với fixture local, không là benchmark chất lượng hay cam kết
latency. Không phải bằng chứng cho kiểm tra session Identity hoặc production.

Secret `AI_CREDENTIAL_KEY`, `AI_IDENTITY_SERVICE_KEY` và `AI_LLM_API_KEY` nằm
trong `.env` root. AI tải JWKS trực tiếp từ
`{AI_IDENTITY_BASE_URL}/.well-known/jwks.json` mỗi lần xác thực; không dùng PEM,
URL JWKS riêng hoặc cache khóa. AI chỉ chọn khóa có `kty=RSA`, `use` (mặc định
`sig`) và `alg` (mặc định `RS256`) phù hợp; JWT có `kid` thì lọc theo `kid`,
sau cùng phải còn đúng một khóa.
AI yêu cầu claim `exp`, `iss`, `aud`, `sub`, `token_type`; `sub` phải là UUID,
`token_type=access`, còn `iat` là tùy chọn. AI gọi Identity để xác minh session
trước khi cấp quyền. Phiên bị thu
hồi trả `401`; lỗi kiểm tra Identity được ghi nhận là `AUTH_UNAVAILABLE` và
trả trạng thái `503` nội bộ, rồi ánh xạ theo error envelope v1 thành
`500 INTERNAL_ERROR` với
`details.reason=AUTH_UNAVAILABLE`.
Điền model/base URL và API key vào `.env` root; `infra/env/ai-service.env` chỉ
ánh xạ các biến đó vào container.
Sinh Fernet key rồi điền vào `.env` root:

```sh
uv run python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
```

Không commit `.env`, JWT private key hoặc API key.

## Mock quyền/context để chạy local

MOCK_TEST chỉ chọn fixture tại adapter cho quyền/context của Work/Integration;
không bỏ qua xác minh JWT hoặc session Identity. Xem [hướng dẫn mock data](mock-data.md)
để chạy cùng Compose. Cần access token thật từ Identity cho phiên runtime;
fixture không xác nhận contract domain production.

Compose AI độc lập và Compose root local/staging truyền
`AI_IDENTITY_SERVICE_KEY` vào process AI. Compose cũng truyền
`AI_WORK_SERVICE_AUTH_ENABLED`; mặc định `false` nên không cần
`AI_WORK_SERVICE_KEY`. Nếu bật cờ, cấp key cho toàn bộ process AI. Việc cấu
hình không xác nhận Work provider/runtime đã hoạt động.

## Chạy từ Compose root

Compose root local/staging giữ tên `ai-service` cho API và tách `ai-worker`,
`ai-dispatcher`, `ai-beat`, dùng chung image/tag. Các process AI dùng cùng
container PostgreSQL 16 (`postgres`) với Django, nhưng lưu trong database riêng
`${AI_DB_NAME:-ai_context_db}`, dùng chung `POSTGRES_USER`/`POSTGRES_PASSWORD`.
AI dùng Redis chung DB1 làm broker. Root Compose không cần `AI_DB_PASSWORD`.
Entrypoint API chạy `alembic upgrade head` trước Uvicorn; migration lỗi thì API
dừng. Worker/dispatcher/beat chờ API healthy và broker healthy; worker có
Celery ping, beat có probe PID. Beat chỉ lập lịch retention, không chạy model.
Không còn service `ai-migrate` riêng trong Compose root.
Root Compose mặc định tạo URL `postgresql+psycopg://<POSTGRES_USER>:<POSTGRES_PASSWORD>@postgres:5432/<AI_DB_NAME>`.
Nếu credential chứa ký tự đặc biệt trong URL, đặt `AI_DATABASE_URL` với credential
đã percent-encode. Override này có ưu tiên cao hơn URL mặc định; xóa hoặc cập nhật
URL cũ trỏ tới `ai-postgres`/`localhost` trước khi chạy root Compose. Xem
[cấu hình môi trường](../infrastructure/environment.md) cho cấu hình root.
Hướng dẫn và giới hạn kiểm tra nằm tại
[chạy AI local từ root](../infrastructure/local-development.md#chạy-riêng-pipeline-ai-từ-root)
và [CI/CD](../infrastructure/ci-cd.md). Compose riêng dưới đây vẫn dành cho môi
trường AI độc lập, có network/volume và cổng host riêng; không dùng chung dữ liệu tự động.

## Chạy bằng Compose riêng của AI

Chạy từ `apps/ai-service/`, sau khi điền `.env` root. Dùng cùng Compose cho cả
mock và dữ liệu thật:

```sh
docker compose --project-name ai-mock --env-file ../../.env \
  --env-file ../../infra/env/ai-service.env up --build -d --wait --wait-timeout 60 --remove-orphans
docker compose --project-name ai-mock --env-file ../../.env \
  --env-file ../../infra/env/ai-service.env ps
curl http://localhost:8000/healthz
```

[`compose.yaml`](../../apps/ai-service/compose.yaml) chạy PostgreSQL 17 riêng,
Redis, API, dispatcher, Celery worker và beat. API chờ DB/broker healthy rồi entrypoint
chạy `alembic upgrade head` trước Uvicorn. Migration lỗi thì API không khởi động;
worker/dispatcher/beat chờ API và broker healthy. Không còn service `migrate` riêng;
DB/broker không mở cổng ra host.
Điền `AI_DB_PASSWORD` bằng password local có thể dùng trong URL; Compose tự
đặt URL DB/broker theo tên container. Worker local dùng concurrency 2, có thể
điều chỉnh theo tài nguyên; đây không phải quyết định topology production.

`AI_HTTP_PORT` đổi cổng API; các cờ và giới hạn nằm trong `.env` root.
`MOCK_TEST` chỉ hợp lệ với development/test; staging/production bật mock sẽ
lỗi startup. API/worker dùng cùng factory: mock đọc fixture tại adapter;
tắt mock gọi REST của Work/Integration. JWT và LLM vẫn thật. Đổi cờ/key rồi
chạy lại `docker compose ... up` để các process nạp cùng cấu hình. Không có
server mock, launcher riêng hoặc Compose override cho mock.

Entrypoint nhận `uvicorn` hoặc đường dẫn kết thúc bằng `/uvicorn` sẽ chạy
Alembic từ cùng thư mục executable rồi `exec` nguyên lệnh API. Mỗi lần khởi
động API đều upgrade tới `head`; Alembic không áp dụng lại revision đã có.
Lệnh worker, dispatcher, beat và lệnh quản trị như `alembic upgrade head` được thực
thi trực tiếp, giữ nguyên tham số và mã thoát. Application lifespan không tự
tạo schema. Với nhiều API replica, khởi động một API để migration xong trước
khi scale; entrypoint không có khóa điều phối migration giữa replica.

## Chạy từng process bằng uv

Chạy trong `apps/ai-service/`:

```sh
uv sync --all-groups --locked
uv run alembic upgrade head
uv run uvicorn main:app --app-dir src --reload
```

Trong ba terminal khác, từ cùng service root:

```sh
PYTHONPATH=src uv run celery -A jobs.celery_app:celery_app worker --loglevel=INFO --concurrency=2
PYTHONPATH=src uv run python -m jobs.dispatcher
PYTHONPATH=src uv run celery -A jobs.celery_app:celery_app beat --loglevel=INFO --schedule=/tmp/ai-beat-schedule --pidfile=/tmp/ai-beat.pid
```

Settings tự đọc hai file dù cwd khác. URL DB/broker host phải cấu hình phù
hợp. Mock đọc fixture trong package; xác minh JWT vẫn cần JWKS và session-status
Identity. Mock không bỏ qua kiểm tra xác thực.
Chạy migration tới `head` (gồm `0004`, terminal timestamp/index retention) trước khi
nhận request. API không chạy workflow; nếu dispatcher/worker chưa chạy thì
POST trả `202`, request chỉ được xử lý khi pipeline hoạt động. JWT phải ký
hợp lệ và phiên phải còn active tại Identity; header identity bootstrap đã bỏ. Endpoint quyền/context thiếu cấu
hình sẽ từ chối request có target. `/healthz` kiểm tra process, không thay
thế kiểm tra DB/broker/domain readiness.

Kiểm tra chất lượng:

```sh
uv run ruff format --check .
uv run ruff check .
uv run pytest
docker build --tag utask/ai-service:local .
```

Unit tests chạy không cần LLM credential. Để chạy toàn bộ integration tests,
tạo database test riêng tên `ai_test` và Redis test riêng, rồi đặt
`TEST_DATABASE_URL=postgresql+psycopg://.../ai_test` và `TEST_REDIS_URL=redis://...`
cho `uv run pytest`. Tests dùng schema riêng cho repository; migration test
upgrade/downgrade trong database test. Không dùng database nghiệp vụ. Không
có hai URL này thì test hạ tầng được skip, không coi đó là xác minh pipeline.

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

### Xác thực staging

Compose staging truyền Identity service key và Fernet key cho toàn bộ process
AI. Issuer/audience mặc định theo Identity; token mock local không dùng trong
staging. Mỗi xác thực tải JWKS từ Identity, lọc khóa RSA phù hợp và không cache
kết quả. `AI_WORK_SERVICE_AUTH_ENABLED=false` mặc định nên Work key không bắt
buộc; khi bật cờ, Compose phải cấp `AI_WORK_SERVICE_KEY` cho các process AI.
Settings từ chối khởi động staging/production nếu thiếu cấu hình xác thực
hoặc Fernet key không hợp lệ. Xem [cấu hình staging](../infrastructure/environment.md#cấu-hình-ai-trong-compose-root).
