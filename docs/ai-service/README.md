# AI Service

**Trạng thái: Một phần.** Pipeline API/PostgreSQL/dispatcher/Redis/Celery/ADK
đã triển khai trong `apps/ai-service/`; xác minh chữ ký JWT và kiểm tra session
qua Identity có source/test local. Work provider authorize/context và
Integration provider GitHub có source/config/test. Runtime liên service và LLM
production mới được xác minh một phần hoặc chưa xác minh;
Retention terminal đã có source, migration và lịch Celery beat; Kafka và
specialist **Chưa triển khai**. Điều kiện phát hành và phần chưa xác minh nằm
tại [mức sẵn sàng production](production-readiness.md).
CI chạy deterministic evaluation; live evaluation là lệnh thủ công tùy chọn,
không phải điều kiện deploy staging. Hướng dẫn và các biến `EVAL_AI_*` nằm tại
[phần evaluation](production-readiness.md#evaluation-và-gate-phát-hành).

Hướng dẫn chuẩn để cấu hình, chỉnh sửa contract và triển khai các service liên
quan nằm tại [cấu hình và triển khai AI Service](deployment-and-service-integration.md).

Đây là trang điều hướng cho tài liệu AI Service. Không coi các phần thiết kế
API, event, provider hoặc agent là deployment production đã hoàn chỉnh chỉ
từ thiết kế. [Code map](code-map.md) giữ bằng chứng implementation và kiểm thử.

[Checkpoint 21/10/2026](checkpoint.md) tổng hợp tiến độ M1–M4, blocker local,
bằng chứng kiểm thử và việc tiếp theo theo đội; giữ lịch sử smoke LLM thật
ngày 15/10 riêng để không nhầm với nghiệm thu domain/staging.

## Baseline và phạm vi

Thiết kế mục tiêu theo [baseline](../system/architecture-baseline.md), mục 4.6, 9–11
và 18. Các quyết định chuyển đổi nằm trong
[ADR-001](../system/adr/001-adopt-architecture-baseline.md). Baseline chọn Celery +
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
[ADR-002](../system/adr/002-ai-request-pipeline.md). Pipeline source đã được kiểm thử
với PostgreSQL, Redis và ADK fake model. Work AI provider có source/config/test;
runtime liên service đã được smoke một phần, xem
[báo cáo Work–AI](../project-service/ai-context-staging-validation-20261022.md).

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

`.env` root là nguồn giá trị runtime AI, gồm biến thường và secret; tạo theo
[mẫu root](../../.env.example). [`ai-service.env`](../../infra/env/ai-service.env)
là mapping chung cho mọi process AI của Compose, ánh xạ cả biến thường lẫn
placeholder secret `${TEN_BIEN:-}`. Mọi process AI chỉ dùng mapping này;
PostgreSQL standalone dùng thêm mapping PostgreSQL chung
[`database.env`](../../infra/env/database.env). Mapping
AI yêu cầu `AI_DATABASE_URL` và `AI_BROKER_URL` trong `.env` root hoặc
environment của process; mapping không tự dựng URL theo topology. Host
Settings đọc `.env` root và biến process; trong container Compose cấp giá trị
qua `env_file`. Biến process có ưu tiên cao nhất. `.env.example` khai báo rõ
`AI_ENVIRONMENT=development`, `MOCK_TEST=true` và proxy local; mapping mặc định
`AI_ENVIRONMENT=staging`, `MOCK_TEST=false`, model/base URL để trống. Giá trị
local trong `.env` ghi đè mapping; staging phải đặt `AI_ENVIRONMENT=staging`,
`MOCK_TEST=false` và URL của các dịch vụ tại môi trường staging. Các biến chính:

| Biến | Ý nghĩa |
| --- | --- |
| `AI_ENVIRONMENT`, `MOCK_TEST` | Chế độ development/test/staging/production và cờ context mock |
| `AI_DATABASE_URL` | Bắt buộc; URL database AI cho môi trường đang chạy. Password phải percent-encode nếu chứa ký tự đặc biệt |
| `AI_DB_NAME` | Tên database AI được khởi tạo trong PostgreSQL chung ở Compose root; phải trùng database trong `AI_DATABASE_URL` |
| `POSTGRES_USER`, `POSTGRES_PASSWORD` | Credential PostgreSQL; dùng trong URL root của `.env.example` và database standalone |
| `POSTGRES_DB` | Tên database PostgreSQL standalone; phải khớp database trong `AI_DATABASE_URL` |
| `AI_HTTP_PORT` | Nội suy cổng host của API trong Compose standalone; không được truyền vào process AI |
| `AI_WORKER_CONCURRENCY` | Nội suy tham số `--concurrency` của worker Compose; mặc định 2, không phải biến runtime |
| `AI_BROKER_URL` | Bắt buộc; Redis broker đúng môi trường, không dùng Redis làm result repository |
| `AI_COMPLETION_RECONCILE_SECONDS` | Khoảng phục hồi completion inbox và thử lại listener; mặc định 5 giây |
| `AI_REQUESTS_PER_MINUTE` | Số request mới tối đa/user trong 60 giây; mặc định 5 |
| `AI_MAX_ACTIVE_REQUESTS_PER_USER` | Số request queued/running tối đa/user; mặc định 2 |
| `AI_MAX_MODEL_CALLS` | Số lần gọi model tối đa trong một yêu cầu, gồm gọi lại và sửa kết quả; mặc định 4 |
| `AI_MAX_CONTEXT_TOOL_CALLS` | Số lần gọi công cụ lấy context tối đa trong một yêu cầu; mặc định 5 |
| `AI_MAX_OUTPUT_TOKENS` | Tổng token đầu ra của các lần gọi model trong một yêu cầu; mặc định 4000 |
| `AI_WORKFLOW_TIMEOUT_SECONDS` | Thời hạn thực thi từ khi worker nhận xử lý; mặc định và tối đa 300 giây (5 phút) |
| `AI_WORK_SERVICE_AUTH_ENABLED` | Mặc định `false`; tạm thời bỏ riêng header `X-Service-Key` khi AI gọi Work. Bearer actor và yêu cầu authorize theo target/intent vẫn được gửi |
| `AI_WORK_SERVICE_KEY` | Chỉ bắt buộc và chỉ gửi khi `AI_WORK_SERVICE_AUTH_ENABLED=true`; secret AI → Work, được mapping đưa vào environment |
| `AI_INTEGRATION_SERVICE_KEY` | Secret AI → Integration; không bị ảnh hưởng bởi cờ Work |
| `AI_GITHUB_CONTEXT_ENABLED` | Mặc định false; chỉ cấp development tool cho risk Project khi focus cho phép |
| `AI_TERMINAL_RETENTION_DAYS`, `AI_RETENTION_BATCH_SIZE`, `AI_RETENTION_INTERVAL_SECONDS` | Mặc định 30 ngày, tối đa 500 request/lần, một lần mỗi 3600 giây |
| `AI_JWT_ISSUER`, `AI_JWT_AUDIENCE` | Issuer/audience dùng để xác minh JWT; mặc định theo Identity |
| `AI_IDENTITY_BASE_URL` | Base URL nội bộ Identity; mặc định `http://identity-service:8000` |
| `AI_IDENTITY_SERVICE_KEY` | Secret caller AI gửi qua `X-Service-Key` khi gọi session-status; phải khớp mục `ai` trong `IDENTITY_SERVICE_KEYS` của Identity |
| `AI_AUTHORIZATION_URLS` | Override tùy chọn: JSON map target type → URL kiểm tra quyền; mặc định ba target Work trong `src/config.py` |
| `AI_CONTEXT_URLS` | Override tùy chọn: JSON map `target_type:domain` → URL lấy context; mặc định 10 cặp Work trong `src/config.py` |
| `AI_LLM_PROVIDER` | Chọn adapter `litellm` |
| `AI_MODEL` | Model ID mà local proxy công bố; adapter tự thêm route LiteLLM `openai/` |
| `AI_LLM_API_BASE` | URL endpoint tương thích OpenAI, ví dụ `https://provider.example/v1` |
| `AI_LLM_API_KEY` | API key trong `.env` root, bắt buộc khi gọi LLM thật |

Nếu chạy Settings bằng Python trên host, cấu hình đọc `.env` root và biến
process; URL database/broker phải dùng địa chỉ host mà Python truy cập được,
không dùng DNS nội bộ Docker. Alias `IDENTITY_JWT_ISSUER`/
`IDENTITY_JWT_AUDIENCE` được dùng khi không có `AI_JWT_ISSUER`/
`AI_JWT_AUDIENCE`. Trong Compose, mapping cấp các giá trị vào container.
`AI_DB_NAME`, `POSTGRES_*`, `AI_HTTP_PORT` và `AI_WORKER_CONCURRENCY` dùng
cho bootstrap hoặc nội suy Compose, không phải biến runtime của process AI.
Root dùng `AI_DB_NAME` với PostgreSQL chung; tên database trong URL phải khớp.
Standalone dùng `POSTGRES_USER`, `POSTGRES_PASSWORD` và `POSTGRES_DB` từ `.env`
root qua `infra/env/database.env`; URL ứng dụng phải khớp các giá trị này.

Các biến AI dùng chung đi từ `.env` qua `infra/env/ai-service.env` vào API,
worker, dispatcher và beat. Ba biến ngân sách `AI_MAX_MODEL_CALLS`,
`AI_MAX_CONTEXT_TOOL_CALLS` và `AI_MAX_OUTPUT_TOKENS` có thể tăng theo nhu cầu,
ví dụ lần lượt `12`,
`20`, `128000`, rồi recreate các process AI. Model/proxy phải hỗ trợ mức
`max_tokens` được gửi lên vì adapter hiện dùng phần ngân sách còn lại làm
giới hạn đầu ra cho mỗi lần gọi. Thời hạn thực thi mặc định là 300 giây (5 phút);
tăng ngân sách không kéo dài thời hạn này. Nếu provider không trả usage (số
token đã dùng), adapter hiện tính toàn bộ phần token còn được phép là đã dùng;
tăng token không khắc phục việc thiếu usage.

URL template chỉ dùng `{target_type}` và `{target_id}` từ request đã validate.
Các target là `project`, `task`, `sprint`; domain Work là `project`, `task`,
`team`, `progress`; domain `github_activity` đến từ Integration khi được bật.
Work boundary được khai báo trong [Work AI context v1](../../contracts/api/work-ai-context-v1.yaml),
được [Work contract](../../contracts/api/work-service.yaml) tham chiếu. Provider
Work có source/config/test; mức nghiệm thu runtime xem
[điều kiện phát hành](production-readiness.md). AI-side adapter POST body
`action: ai.analyze` và `intent`, kiểm tra envelope `success/data` cùng
target/action/allowed; GET context nhận `ContextDocument` trực tiếp, tối đa
65536 byte. Bearer actor luôn được gửi. Work hiện bắt buộc cả Bearer và caller
service key; cấu hình thật phải đặt `AI_WORK_SERVICE_AUTH_ENABLED=true` và
đồng bộ key với `WORK_SERVICE_KEYS.ai`. Cờ mặc định `false` chỉ phù hợp khi
không gọi Work provider thật. GitHub đi Integration; Integration tự hỏi Work quyền
`github.read`, AI không gọi thêm Work cho lần đọc GitHub. Xem
[boundary và cấu hình staging](production-readiness.md#boundary-domain-và-quyền).
Thiếu cấu hình hoặc quyền/context lỗi thì từ chối; không fallback fixture.

ADK dùng `LiteLlm` để gọi custom endpoint tương thích OpenAI. Model có thể là
ID gốc của proxy (ví dụ `gemini-3.8-flash-high`) hoặc route `openai/<model-id>`,
kèm `AI_LLM_API_BASE` và key.
Thiếu hoặc sai cấu hình thì worker trả `PROVIDER_UNAVAILABLE` trước lời gọi
model, với reason chỉ rõ trường cần sửa. Endpoint nhận HTTP hoặc HTTPS ở mọi
môi trường; không có điều kiện chặn HTTP riêng cho staging/production.
URL vẫn phải hợp lệ, không chứa credential, query hay fragment. Timeout lấy từ deadline
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
  --env-file ../../.env \
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

Secret `AI_IDENTITY_SERVICE_KEY` và `AI_LLM_API_KEY` nằm trong `.env` root.
AI tải JWKS trực tiếp từ
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
Điền model/base URL và API key vào `.env` root; mapping chung
`infra/env/ai-service.env` đưa các biến AI vào container qua `env_file`.
Bearer token được lưu nguyên bản trong cột credential của PostgreSQL AI để
worker xác thực lại; token bị xóa khi bàn giao kết quả hoặc request vào trạng
thái terminal. Không ghi token ra log/task.

Không commit `.env`, JWT private key, Bearer token hoặc API key.

## Mock quyền/context để chạy local

MOCK_TEST chỉ chọn fixture tại adapter cho quyền/context của Work/Integration;
không bỏ qua xác minh JWT hoặc session Identity. Xem [hướng dẫn mock data](mock-data.md)
để chạy cùng Compose. Cần access token thật từ Identity cho phiên runtime;
fixture không xác nhận contract domain production.

Compose AI độc lập và Compose root local/staging nạp
`AI_IDENTITY_SERVICE_KEY` vào process AI qua `env_file`. Cờ
`AI_WORK_SERVICE_AUTH_ENABLED` cũng được ánh xạ như vậy; khi kết nối Work thật, đặt `true` và cấp
`AI_WORK_SERVICE_KEY` cho toàn bộ process AI, khớp caller `ai` trong
`WORK_SERVICE_KEYS` của Work. Hướng dẫn chi tiết và thứ tự triển khai nằm tại
[cấu hình và triển khai AI Service](deployment-and-service-integration.md).

## Chạy từ Compose root

Compose root local/staging giữ tên `ai-service` cho API và tách `ai-worker`,
`ai-dispatcher`, `ai-beat`, dùng chung image/tag. Các process AI dùng cùng
container PostgreSQL 16 (`postgres`) với Django, nhưng lưu trong database riêng
`${AI_DB_NAME:-ai_context_db}`, dùng chung `POSTGRES_USER`/`POSTGRES_PASSWORD`.
AI dùng Redis chung DB1 làm broker. `AI_DB_NAME` là database AI được bootstrap
riêng trong PostgreSQL root.
Entrypoint API chạy `alembic upgrade head` trước Uvicorn; migration lỗi thì API
dừng. Worker/dispatcher/beat chờ API healthy và broker healthy; worker có
Celery ping, beat có probe PID. Beat chỉ lập lịch retention, không chạy model.
Không còn service `ai-migrate` riêng trong Compose root.
Root local chỉ nạp `infra/env/ai-service.env`. `.env.example` cung cấp URL DB
`postgresql+psycopg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${AI_DB_NAME}`
và broker `redis://redis:6379/1`. Giữ database trong `AI_DATABASE_URL` đồng bộ
với `AI_DB_NAME` dùng để bootstrap; khi đổi tên phải cập nhật cả hai. Nếu
password chứa ký tự đặc biệt trong URL, percent-encode trước khi đặt biến.
Xem
[cấu hình môi trường](../system/infrastructure/environment.md) cho cấu hình root.
Staging dùng cùng mapping và phải khai báo `AI_ENVIRONMENT=staging`,
`MOCK_TEST=false`, `AI_DATABASE_URL` và `AI_BROKER_URL` trong `.env` hoặc
environment được truyền cho Compose. URL phải trỏ đến database/Redis staging;
không có URL topology mặc định. Nếu `.env` trên máy đích giữ giá trị local,
chúng vẫn được ưu tiên và phải được cập nhật trước khi chạy.
Hướng dẫn và giới hạn kiểm tra nằm tại
[chạy AI local từ root](../system/infrastructure/local-development.md#chạy-riêng-pipeline-ai-từ-root)
và [CI/CD](../system/infrastructure/ci-cd.md). Compose riêng dưới đây vẫn dành cho môi
trường AI độc lập, có network/volume và cổng host riêng; không dùng chung dữ liệu tự động.

## Chạy bằng Compose riêng của AI

Chạy từ `apps/ai-service/`, sau khi điền `.env` root. Dùng cùng Compose cho cả
mock và dữ liệu thật:

```sh
docker compose --project-name ai-mock --env-file ../../.env \
  up --build -d --wait --wait-timeout 60 --remove-orphans
docker compose --project-name ai-mock --env-file ../../.env ps
curl http://localhost:8000/healthz
```

[`compose.yaml`](../../apps/ai-service/compose.yaml) chạy PostgreSQL 17 riêng,
Redis, API, dispatcher, Celery worker và beat. API chờ DB/broker healthy rồi entrypoint
chạy `alembic upgrade head` trước Uvicorn. Migration lỗi thì API không khởi động;
worker/dispatcher/beat chờ API và broker healthy. Không còn service `migrate` riêng;
DB/broker không mở cổng ra host.
Với PostgreSQL standalone, đặt `POSTGRES_USER`, `POSTGRES_PASSWORD` và
`POSTGRES_DB` trong `.env` root; giữ các giá trị này khớp với volume đã khởi
tạo nếu volume cũ đang được dùng. Cấu hình
`AI_DATABASE_URL=postgresql+psycopg://<POSTGRES_USER>:<POSTGRES_PASSWORD đã percent-encode>@database:5432/<POSTGRES_DB>`
và `AI_BROKER_URL=redis://broker:6379/0` trong `.env` root hoặc environment
của process trước khi chạy. Compose không tự dựng các URL này; host Python
phải dùng địa chỉ database/broker truy cập được từ host. Worker concurrency lấy từ
`AI_WORKER_CONCURRENCY` (mặc định 2), có thể
điều chỉnh theo tài nguyên; đây không phải quyết định topology production.

`AI_HTTP_PORT` đổi cổng host qua nội suy `ports`; nó không được truyền vào
process AI. Tương tự, `AI_WORKER_CONCURRENCY` chỉ nội suy tham số worker.
Các cờ và giới hạn runtime nằm trong `.env` root.
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

Host Settings đọc `.env` root kể cả khi cwd khác; Compose cấp cấu hình container
qua mapping chung `infra/env/ai-service.env`. URL DB/broker trong `.env` phải
truy cập được từ host khi chạy trực tiếp Python. Mock đọc fixture trong package;
xác minh JWT vẫn cần JWKS và session-status
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
- [Job nền và worker](../system/infrastructure/background-jobs.md)
- [Code map và các entry point đã xác minh](code-map.md)

Instruction mặc định khi làm việc trong source nằm tại
[`apps/ai-service/AGENTS.md`](../../apps/ai-service/AGENTS.md). Plan cho thay đổi
lớn nằm tại [`apps/ai-service/.agent/PLANS.md`](../../apps/ai-service/.agent/PLANS.md).

### Xác thực staging

Compose staging truyền Identity service key cho các process AI cần gọi Identity.
Issuer/audience mặc định theo Identity; token mock local không dùng trong
staging. Mỗi xác thực tải JWKS từ Identity, lọc khóa RSA phù hợp và không cache
JWKS. Khi gọi Work provider thật, đặt `AI_WORK_SERVICE_AUTH_ENABLED=true`
và cấp `AI_WORK_SERVICE_KEY` cho các process AI; Work luôn yêu cầu service key.
Settings từ chối khởi động staging/production nếu thiếu cấu hình xác thực. Xem
[cấu hình staging](../system/infrastructure/environment.md#cấu-hình-ai-trong-compose-root).

## Mở rộng thông báo

Notification hiện chưa consume kết quả/rủi ro AI. Khi có use case và contract
được chốt, thực hiện theo
[hướng dẫn thêm nguồn/event](../notification-service/implementation.md#thêm-service-hoặc-event-mới)
và đối chiếu [checkpoint](../notification-service/checkpoint-2026-10-22.md).
Không suy ra event/consumer đã tồn tại từ ví dụ trong baseline.
