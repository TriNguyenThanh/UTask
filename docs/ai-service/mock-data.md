# Dùng mock data trong luồng AI Service

**Trạng thái: Đã triển khai.** Client vẫn gọi API AI thật; request đi qua
PostgreSQL, dispatcher, Redis/Celery, ADK và pipeline completion/polling hiện
có. Chỉ quyền/context từ các microservice chưa có được thay bằng fixture tại
adapter. LLM vẫn dùng provider thật; không có server mock, launcher riêng hay
Compose override cho mock.

## Cấu hình

[`infra/env/ai-service.env`](../../infra/env/ai-service.env) giữ biến thường:

```dotenv
AI_ENVIRONMENT=development
MOCK_TEST=true
AI_MODEL=gemini-flash-latest
```

Secret và credential xác minh JWT giữ trong `.env` root theo
[mẫu root](../../.env.example): GOOGLE_API_KEY, AI_CREDENTIAL_KEY,
AI_DB_PASSWORD và AI_JWT_PUBLIC_KEY. Settings đọc config rồi secret;
biến process có ưu tiên cao nhất. Không có env riêng cho mock.

| Cờ | Nguồn dữ liệu tại adapter |
| --- | --- |
| MOCK_TEST=true | Đọc fixture cục bộ; chỉ development/test |
| MOCK_TEST=false | Gọi REST quyền/context theo URL thật đã cấu hình |
| staging/production + mock true | Báo lỗi khi nạp cấu hình |

API và worker dùng cùng `build_context_adapter()`. Context Tool Pool không
biết nguồn là fixture hay REST; cả hai trả ContextDocument. JWT vẫn được xác
minh trước API/worker. Vì Work chưa có, quyền domain trong mock được kiểm tra
theo allowed_users của từng target, không dùng `allowed=true` cho mọi user.

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

GOOGLE_API_KEY phải thuộc project được phép dùng Gemini để tạo proposal
thành công. Thiếu key hoặc provider từ chối vẫn kết thúc failed theo luồng
error hiện có; mock data không mock kết quả LLM.

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
mock_token=$(cat ../../.env.mock/mock-owner.jwt)
curl -sS \
  -H "Authorization: Bearer $mock_token" \
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

## JWT local khi Identity chưa có

JWT cũ giữ nguyên trong `.env.mock/` root. Tiện ích
[setup_mock.py](../../apps/ai-service/scripts/setup_mock.py) chỉ sinh credential
và token local, không là một bước của pipeline hay cách khởi động service:

```sh
PYTHONPATH=src uv run python -m scripts.setup_mock
# Khi JWT đã có/hết hạn, thay JWT có chủ đích và giữ DB/Fernet/LLM key:
PYTHONPATH=src uv run python -m scripts.setup_mock --refresh
```

JWT có hạn 24 giờ; tùy chọn --token-hours nhận 1–24 giờ. Sau refresh, chạy lại
Compose up để nạp public key mới. Script không lưu private key hoặc in secret.
Root .env và token có quyền 0600; directory token 0700 và Git bỏ qua.

## Kiểm thử

`test_mock_context.py` kiểm tra source selection, fixture/schema, permission,
không gọi HTTP ở mode mock, REST ở mode thật và ADK với model fake.
`test_mock_pipeline.py` đi qua API/JWT/PostgreSQL/dispatcher/Redis/Celery/
completion/polling thật cho ba intent; chỉ fake LLM bên ngoài.

```sh
uv run pytest
```

Test hạ tầng cần TEST_DATABASE_URL trỏ tới database riêng ai_test và
TEST_REDIS_URL; báo skip nếu thiếu. Integration domain/LLM production vẫn
chưa xác minh. Context chỉ ở bộ nhớ mỗi lần chạy theo
[chính sách context](architecture.md#chính-sách-context-hiện-tại-và-mở-rộng).
