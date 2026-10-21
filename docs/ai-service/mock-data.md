# Dùng mock data trong luồng AI Service

**Trạng thái: Đã triển khai.** Client vẫn gọi API AI thật; request đi qua
PostgreSQL, dispatcher, Redis/Celery, ADK và pipeline completion/polling hiện
có. Chỉ quyền/context từ các microservice chưa có được thay bằng fixture tại
adapter. LLM vẫn dùng provider thật; không có server mock, launcher riêng hay
Compose override cho mock.

## Cấu hình

`.env` ở repository root giữ cấu hình AI; [`infra/env/ai-service.env`](../../infra/env/ai-service.env)
chỉ ánh xạ các biến đó vào container:

```dotenv
AI_ENVIRONMENT=development
MOCK_TEST=true
AI_LLM_PROVIDER=litellm
AI_MODEL=gemini-3.8-flash-high
AI_LLM_API_BASE=http://host.docker.internal:8317/v1
```

Secret runtime giữ trong `.env` root theo
[mẫu root](../../.env.example): AI_LLM_API_KEY, AI_CREDENTIAL_KEY,
AI_IDENTITY_SERVICE_KEY. AI không nhận `AI_JWT_PUBLIC_KEY` hoặc URL JWKS riêng;
nó tải khóa công khai trực tiếp từ Identity khi xác minh từng access token.
Cấu hình thêm
`AI_IDENTITY_BASE_URL` (mặc định `http://identity-service:8000`); service key
phải trùng entry `ai` trong `IDENTITY_SERVICE_KEYS` của Identity. Compose root dùng `POSTGRES_USER`/`POSTGRES_PASSWORD`
chung với Django và database AI riêng theo `AI_DB_NAME` (mặc định `ai_context_db`);
`AI_DB_PASSWORD` chỉ dành cho Compose AI độc lập ở phần chạy bên dưới.
Xem [cấu hình Compose root](README.md#chạy-từ-compose-root) cho override URL.
Settings đọc config rồi secret;
biến process có ưu tiên cao nhất. Không có env riêng cho mock.
`host.docker.internal` được ánh xạ về host trong Compose vì `localhost` bên
trong container là chính container AI. `AI_LLM_API_KEY` phải khớp một key trong
CLIProxyAPI Management → `api-keys`; model ID được LiteLLM bọc thành route
`openai/` khi gọi endpoint.

| Cờ | Nguồn dữ liệu tại adapter |
| --- | --- |
| MOCK_TEST=true | Đọc fixture cục bộ; chỉ development/test |
| MOCK_TEST=false | Gọi REST quyền/context theo URL thật đã cấu hình |
| staging/production + mock true | Báo lỗi khi nạp cấu hình |

API và worker dùng cùng `build_context_adapter()`. Context Tool Pool không
biết nguồn là fixture hay REST; cả hai trả ContextDocument. Mỗi xác thực tải
raw JWKS của Identity; JWT và session vẫn được xác minh trước API/worker.
MOCK_TEST không bỏ qua xác thực.
Vì Work chưa có, quyền domain trong mock được kiểm tra
theo allowed_users của từng target, không dùng `allowed=true` cho mọi user.
`AI_WORK_SERVICE_AUTH_ENABLED=false` chỉ bỏ header service key Work; Bearer và
authorize theo target/intent vẫn giữ. Nếu bật cờ, cần `AI_WORK_SERVICE_KEY`;
Identity và Integration service key không đổi.

## Chạy như AI Service bình thường

Từ `apps/ai-service/`:

```sh
docker compose --project-name ai-mock --env-file ../../.env \
  --env-file ../../infra/env/ai-service.env up --build -d --wait --wait-timeout 60 --remove-orphans
curl http://127.0.0.1:8000/healthz
```

Cùng một Compose cho cả mock và thật. `--remove-orphans` dọn container
mock-domain cũ nếu còn từ cách chạy trước. Đổi cờ rồi chạy lại `up` để API và
worker nạp cùng nguồn. Nếu chạy bằng uv, không đổi entrypoint API/worker;
Settings tự đọc config, fixture đóng gói trong src.

Trong container, entrypoint API chạy `alembic upgrade head` trước Uvicorn;
migration lỗi thì API dừng, worker/dispatcher tiếp tục chờ API healthy.
Compose không còn process migration riêng. Với `uv`, vẫn chạy Alembic thủ
công như [hướng dẫn từng process](README.md#chạy-từng-process-bằng-uv).

Mock chỉ thay quyền/context Work/Integration. Muốn tạo proposal thành công,
CLIProxyAPI phải có credential provider/model hợp lệ và `api-keys` không còn
giá trị mẫu; `AI_LLM_API_KEY` phải nằm trong danh sách key đó. Thiếu cấu hình
hoặc provider từ chối vẫn kết thúc failed theo luồng error hiện có; mock data
không mock kết quả LLM.

## Fixture và request mẫu

Fixture nằm ở [domain.json](../../apps/ai-service/src/infrastructure/fixtures/domain.json).
Đó là dữ liệu giả cho Project `11111111-1111-4111-8111-111111111111`, Task
`22222222-2222-4222-8222-222222222222`, Sprint
`33333333-3333-4333-8333-333333333333`, team/progress và GitHub activity.
Deadline cố định tháng 10/2026; as_of được tạo khi đọc và warning đánh dấu mock.
Không ghi fixture vào database hoặc biến fixture thành nguồn dữ liệu thật.

| Intent | Payload |
| --- | --- |
| backlog_generation | [backlog.json](../../apps/ai-service/examples/requests/backlog.json) |
| task_decomposition | [task-decomposition.json](../../apps/ai-service/examples/requests/task-decomposition.json) |
| risk_analysis | [risk-analysis.json](../../apps/ai-service/examples/requests/risk-analysis.json) |

```sh
access_token='<access-token do Identity cấp cho user mock-owner>'
curl -sS \
  -H "Authorization: Bearer $access_token" \
  -H 'Content-Type: application/json' \
  -H "Idempotency-Key: mock-task-$(date +%s)" \
  --data-binary @examples/requests/task-decomposition.json \
  http://127.0.0.1:8000/api/ai/v1/requests
```

POST trả 200 khi succeeded, 202 với request_id/status_url khi chưa xong hoặc
error khi failed. Với 202, GET status_url bằng cùng JWT đến succeeded/failed.
Idempotency key mới để chạy lại; cùng user/key/payload replay request đã lưu.
Owner mẫu được phép; outsider bị từ chối, target không có trong fixture cũng
bị từ chối. Thiếu domain context trả lỗi thay vì dùng dữ liệu rỗng.

## Danh tính mẫu và token runtime

`setup_mock.py` tạo danh tính UUID ổn định cho fixture: owner
`00000000-0000-4000-8000-000000000001`, outsider
`00000000-0000-4000-8000-000000000002`, cùng JWT RS256 có claim
`token_type=access`. Public JWKS test được ghi vào `.env.mock/jwks.json`; script
không ghi `AI_JWT_PUBLIC_KEY` vào `.env`. JWKS/token này chỉ phục vụ test dùng
Identity HTTP giả; nó không được Identity runtime công nhận và AI không có
bypass xác thực.

Chạy từ `apps/ai-service/` để tạo dữ liệu test:

```sh
PYTHONPATH=src uv run python -m scripts.setup_mock
```

Chạy `setup_mock` riêng không tạo phiên dùng được cho API đang chạy, kể cả khi
`MOCK_TEST=true`. Test mock HTTP giả JWKS và session-status; xác thực runtime
luôn gọi Identity thật, không dùng fixture auth. Để gọi runtime, đăng nhập Identity trong môi trường đang
chạy, dùng access token thật do Identity cấp cho user có UUID tương ứng. Token
phải còn hạn và session còn active. Kiểm tra `AI_IDENTITY_BASE_URL` và
`AI_IDENTITY_SERVICE_KEY` đã khớp entry `ai` trong `IDENTITY_SERVICE_KEYS`;
nếu Identity không sẵn sàng, yêu cầu bị từ chối. Không lưu token vào repo.

## Kiểm thử

`test_mock_context.py` kiểm tra source selection, fixture/schema, permission,
REST context và ADK với model fake. Test auth/mock pipeline dùng Identity HTTP
giả để xác minh JWT và session-status mà không bỏ qua kiểm tra trong AI.
`test_mock_pipeline.py` đi qua API/JWT/PostgreSQL/dispatcher/Redis/Celery/
completion/polling với các dependency giả đã nêu; không phải bằng chứng cho
Identity hoặc LLM production.

```sh
uv run pytest
```

Test hạ tầng cần TEST_DATABASE_URL trỏ tới database riêng ai_test và
TEST_REDIS_URL; báo skip nếu thiếu. Integration domain/LLM production vẫn
chưa xác minh. Context chỉ ở bộ nhớ mỗi lần chạy theo
[chính sách context](architecture.md#chính-sách-context-hiện-tại-và-mở-rộng).
