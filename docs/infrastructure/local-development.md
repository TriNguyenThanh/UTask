# Chạy môi trường local

**Trạng thái: Một phần.** Theo [baseline](../architecture/README.md), local
dùng Docker Compose cho Nginx, PostgreSQL, Redis, Kafka và sáu service.
Checkout có package/Dockerfile của Identity và AI; các backend còn lại
chưa có đầu vào build đầy đủ. Compose root đã khai báo API, dispatcher,
Celery worker và migration AI, nhưng toàn bộ stack chưa được xác minh chạy được.

Các lệnh dưới đây dùng PowerShell. Trước khi chạy lần đầu, tạo cấu hình cục bộ:

```powershell
Copy-Item .env.example .env
docker compose config --quiet
docker compose up --build
```

## Chạy riêng pipeline AI từ root

Điền `AI_DB_PASSWORD`, `AI_CREDENTIAL_KEY`, credential JWT và LLM trong `.env`
theo [cấu hình AI](../ai-service/README.md#cấu-hình). Password DB phải dùng được
trong URL; nếu có ký tự đặc biệt, đặt `AI_DATABASE_URL` với password đã percent-encode.
Từ repository root:

```sh
docker compose up --build -d --wait --wait-timeout 120 ai-service ai-worker ai-dispatcher
docker compose exec ai-service python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8000/healthz').status)"
docker compose logs --tail 100 ai-service ai-worker ai-dispatcher
```

Compose tự khởi động `ai-postgres`, Redis và `ai-migrate`. Migration Alembic
phải thành công trước khi ba process chạy. Các process AI dùng chung image;
worker local dùng concurrency 2. API vẫn mang tên `ai-service` để Nginx định tuyến.
Lệnh chạy riêng trên chưa khởi động Nginx và không publish cổng API; kiểm tra
bằng `exec` như trên. Nếu cần gọi API trực tiếp từ host, dùng
[Compose riêng AI](../ai-service/README.md#chạy-bằng-compose-riêng-của-ai).

PostgreSQL AI là instance 17 riêng, user `ai_service`, database `ai_context_db`,
volume `ai_database`; không thay đổi PostgreSQL/volume của các service Django.
Broker dùng Redis chung tại DB1, còn request/result nằm trong PostgreSQL AI.
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
