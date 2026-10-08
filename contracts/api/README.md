# API contracts

Đặt tại đây các hợp đồng API máy đọc được, nếu đã được chốt. Tài liệu giải
thích dành cho đội phát triển nằm trong `docs/<service>/`. Sự hiện diện của thư
mục này không khẳng định một endpoint đã được triển khai hoặc công bố.

Phân biệt API người dùng, API nội bộ, webhook và endpoint health. Đánh dấu rõ
hợp đồng mục tiêu chưa triển khai; không tạo schema giả để lấp đầy thư mục.


Identity OpenAPI 1.8 được sinh từ URLconf và serializers của
service bằng drf-spectacular. Artifact mặc định gồm 25 thao tác; OAuth/avatar tắt mặc định
không xuất thành route đang mở. Bật flags trong môi trường đủ cấu hình để xuất riêng.
Trách nhiệm, luồng và cách tích hợp: [Identity Service](../../docs/identity-service/README.md).
Khi Identity chạy local, Swagger UI ở `/api/schema/swagger/` và OpenAPI JSON ở
`/api/schema/`. Compose bind Identity tới loopback; Nginx không route hai URL này.

### Xuất hợp đồng Identity

- Thư mục hiện chưa có artifact OpenAPI hoặc collection Reqable của Identity.
- Khi cần artifact, xuất từ source/URLconf thật; không dùng schema giả hoặc coi collection là kết quả nghiệm thu.
- Lệnh xuất OpenAPI mới nhất từ source code:
  ```bash
  # Trong container:
  docker compose exec identity-service /app/.venv/bin/python manage.py export_identity_api --output /tmp/identity.openapi.json
  docker compose cp identity-service:/tmp/identity.openapi.json contracts/api/identity.openapi.json

  # Hoặc trên môi trường local có uv/python:
  cd apps/identity-service
  uv run --locked --env-file ../../.env python manage.py export_identity_api --output ../../contracts/api/identity.openapi.json
  ```
