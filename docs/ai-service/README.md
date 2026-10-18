# AI Service

**Trạng thái: Một phần.** Pipeline API/PostgreSQL/dispatcher/Redis/Celery/ADK
đã triển khai trong `apps/ai-service/`, có JWT và domain tools qua REST adapter.
Integration Identity/Work/Integration và LLM production **Chưa xác minh**;
Kafka, specialist và retention tự động **Chưa triển khai**.

Đây là trang điều hướng cho tài liệu AI Service. Không coi các phần thiết kế
API, event, provider hoặc agent là deployment production đã hoàn chỉnh chỉ
từ thiết kế. [Code map](code-map.md) giữ bằng chứng implementation và kiểm thử.

[Checkpoint 15/10/2026](checkpoint.md) tổng hợp phần đã chạy, inference LLM
thật, kiểm thử và việc còn lại để tiếp tục triển khai.

## Baseline và phạm vi

Thiết kế mục tiêu theo [baseline](../architecture/README.md), mục 4.6, 9–11
và 18. Các quyết định chuyển đổi nằm trong
[ADR-001](../adr/001-adopt-architecture-baseline.md). Baseline chọn Celery +
Redis cho job nội bộ; Kafka cho event giữa service; AI lấy context qua internal
API sau domain tool/Context Layer. API, dispatcher và worker thuộc cùng service,
scale độc lập và dùng chung PostgreSQL của AI.

MVP lấy context qua REST khi thực thi và giữ nội dung trong bộ nhớ worker;
PostgreSQL vẫn lưu request/result và metadata, Redis vẫn là broker. Agent
phải đọc [chính sách context hiện tại và mở rộng](architecture.md#chính-sách-context-hiện-tại-và-mở-rộng)
trước khi thêm cache, snapshot hoặc projection.

Pipeline đã chốt là API kiểm tra quyền qua REST, lưu request và ý định giao
job bền vững, dispatcher giao task qua Redis, Celery worker chạy workflow và
bàn giao kết quả vào PostgreSQL của AI, phát `NOTIFY` trong cùng transaction.
Listener trong API tiếp nhận và cập nhật trạng thái/kết quả cuối, phục hồi
inbox khi bỏ lỡ tín hiệu. API đọc cùng persistence để client polling;
Kafka phục vụ sự kiện giữa service. Nguồn chi tiết là
[pipeline trong kiến trúc AI](architecture.md) và quyết định tại
[ADR-002](../adr/002-ai-request-pipeline.md). Pipeline source đã được kiểm thử
với PostgreSQL, Redis và ADK fake model; giới hạn tích hợp nằm trong
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
| `AI_JWT_PUBLIC_KEY` hoặc `AI_JWT_JWKS_URL` | Public key PEM hoặc JWKS của Identity; chỉ chọn một |
| `AI_JWT_ISSUER`, `AI_JWT_AUDIENCE` | Issuer/audience bắt buộc khi xác minh JWT |
| `AI_AUTHORIZATION_URLS` | JSON map target type → URL kiểm tra quyền |
| `AI_CONTEXT_URLS` | JSON map `target_type:domain` → URL lấy context |
| `AI_LLM_PROVIDER` | Chọn adapter `litellm` |
| `AI_MODEL` | Model ID mà local proxy công bố; adapter tự thêm route LiteLLM `openai/` |
| `AI_LLM_API_BASE` | URL endpoint tương thích OpenAI, ví dụ `https://provider.example/v1` |
| `AI_LLM_API_KEY` | API key trong `.env` root, bắt buộc khi gọi LLM thật |

URL template chỉ dùng `{target_type}` và `{target_id}` từ request đã validate.
Các target là `project`, `task`, `sprint`; domain là `project`, `task`, `team`,
`progress`, `github_activity`. Không điền endpoint suy đoán: cần URL và mapping
do Work/Integration công bố. Adapter hiện nhận quyết định quyền `{allowed:
true}` và [ContextDocument](../../apps/ai-service/src/models/context.py);
đây là hợp đồng nội bộ adapter, không khẳng định domain đã cung cấp schema đó.
Thiếu cấu hình hoặc quyền/context lỗi thì từ chối.

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
latency. JWT local đã được refresh; token owner/outsider giữ tại `.env.mock/`.

Secret `AI_CREDENTIAL_KEY`, `AI_JWT_PUBLIC_KEY` và `AI_LLM_API_KEY` nằm trong
`.env` root. Chỉ `AI_CREDENTIAL_KEY` là khóa Fernet bí mật; public key là
credential xác minh JWT, lưu cùng bộ credential để không commit key local.
Điền model/base URL vào `infra/env/ai-service.env` và API key vào `.env` root.
Sinh Fernet key rồi điền vào `.env` root:

```sh
uv run python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
```

Không commit `.env`, JWT private key hoặc API key.

## Mock quyền/context để chạy local

MOCK_TEST chọn fixture tại adapter cho quyền/context của Work/Integration;
luồng API, job và LLM giữ nguyên. Xem [hướng dẫn mock data](mock-data.md) để
chạy cùng Compose và gửi request mẫu. Không cần server mock hoặc launcher;
fixture không xác nhận contract domain production.

## Chạy từ Compose root

Compose root local/staging giữ tên `ai-service` cho API và tách `ai-worker`,
`ai-dispatcher`, dùng chung image/tag. Các process AI dùng cùng
container PostgreSQL 16 (`postgres`) với Django, nhưng lưu trong database riêng
`${AI_DB_NAME:-ai_context_db}`, dùng chung `POSTGRES_USER`/`POSTGRES_PASSWORD`.
AI dùng Redis chung DB1 làm broker. Root Compose không cần `AI_DB_PASSWORD`.
Entrypoint API chạy `alembic upgrade head` trước Uvicorn; migration lỗi thì API
dừng. Worker/dispatcher chờ API healthy và broker healthy; worker còn có Celery ping.
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

Chạy từ `apps/ai-service/`, sau khi điền `.env` root và chọn chế độ trong
`infra/env/ai-service.env`. Dùng cùng Compose cho cả mock và dữ liệu thật:

```sh
docker compose --project-name ai-mock --env-file ../../.env \
  --env-file ../../infra/env/ai-service.env up --build -d --wait --wait-timeout 60 --remove-orphans
docker compose --project-name ai-mock --env-file ../../.env \
  --env-file ../../infra/env/ai-service.env ps
curl http://localhost:8000/healthz
```

[`compose.yaml`](../../apps/ai-service/compose.yaml) chạy PostgreSQL 17 riêng,
Redis, API, dispatcher và Celery worker. API chờ DB/broker healthy rồi entrypoint
chạy `alembic upgrade head` trước Uvicorn. Migration lỗi thì API không khởi động;
worker/dispatcher chờ API và broker healthy. Không còn service `migrate` riêng;
DB/broker không mở cổng ra host.
Điền `AI_DB_PASSWORD` bằng password local có thể dùng trong URL; Compose tự
đặt URL DB/broker theo tên container. Worker local dùng concurrency 2, có thể
điều chỉnh theo tài nguyên; đây không phải quyết định topology production.

`AI_HTTP_PORT` đổi cổng API; các cờ và giới hạn nằm trong `ai-service.env`.
`MOCK_TEST` chỉ hợp lệ với development/test; staging/production bật mock sẽ
lỗi startup. API/worker dùng cùng factory: mock đọc fixture tại adapter;
tắt mock gọi REST của Work/Integration. JWT và LLM vẫn thật. Đổi cờ/key rồi
chạy lại `docker compose ... up` để các process nạp cùng cấu hình. Không có
server mock, launcher riêng hoặc Compose override cho mock.

Entrypoint nhận `uvicorn` hoặc đường dẫn kết thúc bằng `/uvicorn` sẽ chạy
Alembic từ cùng thư mục executable rồi `exec` nguyên lệnh API. Mỗi lần khởi
động API đều upgrade tới `head`; Alembic không áp dụng lại revision đã có.
Lệnh worker, dispatcher và lệnh quản trị như `alembic upgrade head` được thực
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

Trong hai terminal khác, từ cùng service root:

```sh
PYTHONPATH=src uv run celery -A jobs.celery_app:celery_app worker --loglevel=INFO --concurrency=2
PYTHONPATH=src uv run python -m jobs.dispatcher
```

Settings tự đọc hai file dù cwd khác. URL DB/broker host phải cấu hình phù
hợp. Mock đọc fixture trong package và không cần microservice/server khác.
Chạy migration tới `head` (hiện gồm `0003`, hai index chống spam) trước khi
nhận request. API không chạy workflow; nếu dispatcher/worker chưa chạy thì
POST trả `202`, request chỉ được xử lý khi pipeline hoạt động. JWT phải ký
hợp lệ; header identity bootstrap đã bỏ. Endpoint quyền/context thiếu cấu
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
