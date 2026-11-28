# Chạy môi trường local

**Trạng thái: Đã triển khai local cho Core Modular Monolith (`apps/core-service`: Identity + Classroom + Work).**
Theo [ADR-006](../adr/006-consolidate-core-monolith.md), `docker-compose.yml`
dùng cấu trúc mô-đun `include:` (Docker Compose v2.20+) trỏ tới 5 tệp trong
`infra/compose/{infra,core,integration,notification,ai}.yml` (kèm `logging`
rotation và `deploy.resources.limits`). Mặc định `docker compose up --build -d`
chỉ khởi động **5 container lõi** (`postgres`, `redis`, `nginx`, `core-service`,
`core-worker`); `core-consumer` gắn theo profile `integration-service` để không
tốn RAM khi chưa bật Integration, và các service biên (`kafka`, `integration-service`,
`notification-service`, `ai-service`) bật theo `COMPOSE_PROFILES` hoặc `--profile`
khi cần (cả local và staging 1 VPS đều nhúng `celery worker -B` để tiết kiệm tài
nguyên cho cấu hình đơn replica; production đa replica cần tách Beat singleton
riêng theo hướng dẫn Celery). Lệnh khởi động chuẩn từ
repository root là `docker compose up --build -d`. Khi PostgreSQL chấp nhận
kết nối, `start-postgres.sh` gọi `init-databases.sh` để bảo đảm bốn database
được khai báo (`core_db`, `integration_db`, `notification_db`, `ai_context_db`)
tồn tại, kể cả khi volume đã có dữ liệu. Kafka khởi động qua
`start-kafka.sh`, đọc cấu hình trong `kafka-startup.env` và tạo các topic đối ngoại
nếu còn thiếu (`utask.identity.events`, `utask.work.events`,
`utask.integration.events`, `utask.work.integration.dlq`). Hai bước chuẩn bị nằm
trong startup của PostgreSQL và Kafka, không có container chuẩn bị riêng. Compose
chỉ báo hai service này healthy sau khi đã chuẩn bị xong và kiểm tra kết nối thực.

Khi API container (`core-service`) khởi động, entrypoint chạy migration Django
trên `core_db` rồi mới chạy Gunicorn. `core-worker` và `core-consumer` dùng cùng
image nhưng bỏ qua migration; Compose đợi `core-service` healthy trước khi chạy
hai tiến trình này. Kết quả kiểm thử local không xác nhận staging hoặc các
provider bên ngoài.

## Khởi động Identity, Classroom và Work

*(Ba miền nghiệp vụ lõi nay chạy trong cùng `core-service` trên cổng nội bộ `8000`,
ánh xạ host `127.0.0.1:8001` và qua Nginx Gateway tại `/api/auth/`,
`/api/classroom/`, `/api/work/`.)*

Nối repository Work với Integration là lựa chọn bật riêng; cấu hình mặc định
giữ tắt (`WORK_INTEGRATION_ADAPTER=infrastructure.integration.UnavailableIntegration`).
Xem [hướng dẫn Work GitHub](../../project-service/github-integration.md#cấu-hình-và-khởi-động).

Các lệnh dưới đây dùng PowerShell. Tạo `.env` từ mẫu nếu máy chưa có tệp này;
giữ lại `.env` hiện có để không ghi đè cấu hình local:

```powershell
if (-not (Test-Path -LiteralPath .env)) {
    Copy-Item -LiteralPath .env.example -Destination .env
}
New-Item -ItemType Directory -Force .local-secrets | Out-Null
```

Trước lần chạy đầu, sửa `.env`: thay các giá trị local mẫu cho mật khẩu
PostgreSQL, `CORE_DJANGO_SECRET_KEY` và `CLASSROOM_ACCESS_CODE_HMAC_KEY`. Sau
[ADR-006](../adr/006-consolidate-core-monolith.md), **không còn cần** cấu hình
các khóa caller nội bộ giữa Identity, Classroom và Work
(`IDENTITY_CLASSROOM_SERVICE_KEY`, `IDENTITY_WORK_SERVICE_KEY`,
`CLASSROOM_WORK_SERVICE_KEY`). Ví dụ tối thiểu cho Core local:

```dotenv
CORE_DB_NAME=core_db
CORE_DJANGO_SECRET_KEY=<local-django-secret>
CLASSROOM_ACCESS_CODE_HMAC_KEY=<local-hmac-key>
```

Đặt `CLASSROOM_ACCESS_CODE_HMAC_KEY` trước khi dùng mã lớp hoặc mã mời. Không
dùng các giá trị mẫu cho môi trường dùng chung.

Miền Identity trong `core-service` cần khóa riêng RSA tại đường dẫn
`IDENTITY_JWT_PRIVATE_KEY_HOST_PATH` (mặc định
`./.local-secrets/identity-jwt-private.pem`). Có thể tạo khóa local bằng OpenSSL:

```powershell
if (-not (Test-Path -LiteralPath .local-secrets/identity-jwt-private.pem)) {
    openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out .local-secrets/identity-jwt-private.pem
}
```

Giữ PEM trong `.local-secrets`, không commit khóa. Sau khi hoàn tất các giá trị
đầu vào, khởi động từ repository root:

```powershell
docker compose up --build -d
```

Lệnh này dùng Compose mặc định `utask`; không cần chọn tên service hoặc gọi
migration riêng. Docker build chỉ chuẩn bị image, không kết nối PostgreSQL.
Migration diễn ra lúc `core-service` khởi động. Nếu migration lỗi, Gunicorn
không chạy và API không đạt healthcheck, nên `core-worker` và `core-consumer`
cũng chưa khởi chạy. Lần khởi động sau chạy lại migration; Django bỏ qua
migration đã được ghi nhận là đã áp dụng. `core-worker` chạy Celery worker tích
hợp Beat (`-B`) cho outbox, deadline, dọn attachment và retention; `core-consumer`
chạy `python manage.py consume_integration` (chỉ kết nối consumer Integration khi
adapter thật được bật).

Compose không nạp tài khoản mẫu. Đăng ký và kích hoạt tài khoản là luồng Identity;
xem các điều kiện trong [tài liệu Identity](../../identity-service/README.md).
Thông tin cấu hình, secret và luồng áp dụng biến được mô tả tại
[biến môi trường](environment.md); hiện trạng kết quả kiểm tra nếu có
được ghi riêng trong nghiệm thu backend Classroom.

Staging tiếp tục chạy migration tuần tự trước khi cập nhật runtime theo
[quy trình deploy](ci-cd.md). Khi API staging khởi động, entrypoint chạy
migration lần nữa; Django bỏ qua migration đã áp dụng.

Integration và Notification có profile riêng; việc khai báo profile không có
nghĩa service tự khởi động. AI Service nằm trong profile `ai-service`; khi
kết nối Work thật, cấu hình caller key và URL map cho cả hai service. Xem
[hướng dẫn cấu hình và triển khai AI](../../ai-service/deployment-and-service-integration.md).
Các profile AI/Integration không cần cho lệnh khởi động Identity–Classroom–Work.

## Chạy riêng pipeline AI từ root

Điền `AI_DB_NAME`, `AI_DATABASE_URL`, `AI_BROKER_URL`, key AI→Identity/Work và cấu hình LLM trong
`.env` theo [hướng dẫn cấu hình AI](../../ai-service/deployment-and-service-integration.md).
Hai URL kết nối là bắt buộc; Compose không tự chọn theo stack. Mẫu root dùng
database AI trên `postgres:5432` và broker `redis://redis:6379/1`.
Tên database trong URL phải khớp `AI_DB_NAME`. Local đặt rõ
`AI_ENVIRONMENT=development`; chỉ bật `MOCK_TEST=true` khi dùng dữ liệu mẫu.
URL map Work mặc định nằm trong `config.py`; chỉ override nếu địa chỉ Work khác.
Password DB phải dùng được
trong URL; nếu có ký tự đặc biệt, đặt `AI_DATABASE_URL` với password đã percent-encode.
Từ repository root:

```sh
docker compose up --build -d --wait --wait-timeout 120 ai-service ai-worker ai-dispatcher
docker compose exec ai-service python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8000/healthz').status)"
docker compose logs --tail 100 ai-service ai-worker ai-dispatcher
```

Compose dùng container `postgres` chung và Redis. Entry point (script chạy trước
lệnh chính của container) của API chạy Alembic trước Uvicorn; migration phải
thành công thì API mới khởi động. Worker và dispatcher đợi API healthy, không
chạy migration. Không có container `ai-migrate`. Các process AI dùng chung image;
worker local dùng concurrency 2. API vẫn mang tên `ai-service` để Nginx định tuyến.
Lệnh chạy riêng trên chưa khởi động Nginx và không publish cổng API; kiểm tra
bằng `exec` như trên. Nếu cần gọi API trực tiếp từ host, dùng
[Compose riêng AI](../../ai-service/README.md#chạy-bằng-compose-riêng-của-ai).

AI dùng database riêng `AI_DB_NAME` (mặc định `ai_context_db`) trên container
PostgreSQL 16 chung, dùng `POSTGRES_USER`/`POSTGRES_PASSWORD` hiện có. Script
khởi tạo bổ sung database này nếu chưa có, không thay đổi dữ liệu các database
khác. Broker dùng Redis chung tại DB1, request/result nằm trong database AI.
Redis DB1 là phân vùng logic, không phải ranh giới phân quyền. API, worker và
dispatcher dùng cùng cấu hình/credential. Không chờ Work/Integration ở mức
Compose; khi tắt mock, REST adapter vẫn từ chối nếu domain thiếu cấu hình hoặc lỗi.

Compose root và Compose riêng AI có network/volume khác nhau. Không có chuyển
dữ liệu tự động giữa chúng; chọn môi trường cần dùng và giữ nguyên volume cũ.
Root dùng `/healthz` cho API và Celery ping cho worker. Dispatcher hiện chỉ có
restart policy, chưa có healthcheck; `--wait` chưa xác minh job hoàn tất hoặc LLM thật.

Không commit `.env`. Mỗi service giữ quyền sở hữu database riêng, kể cả khi
cùng dùng một PostgreSQL server. Nếu đổi tên database sau khi volume đã được
khởi tạo, cần xử lý volume có chủ đích.

Các biến chạy trong container được nạp qua cấu hình Compose. Xem [biến môi
trường](environment.md) để biết cách tách giá trị local và thông tin bí mật.

Dừng môi trường nhưng giữ dữ liệu:

```powershell
docker compose down
```

Môi trường local không đại diện cho cấu hình production. Cách triển khai
production cần được ghi riêng khi nền tảng và cách quản lý thông tin bí mật đã
được quyết định.
