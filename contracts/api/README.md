# API contracts

Đặt tại đây các hợp đồng API máy đọc được, nếu đã được chốt. Tài liệu giải
thích dành cho đội phát triển nằm trong `docs/<service>/`. Sự hiện diện của thư
mục này không khẳng định một endpoint đã được triển khai hoặc công bố.

Phân biệt API người dùng, API nội bộ, webhook và endpoint health. Đánh dấu rõ
hợp đồng mục tiêu chưa triển khai; không tạo schema giả để lấp đầy thư mục.

## Hợp đồng đã chốt

- [`integration-service-v1.yaml`](integration-service-v1.yaml): OpenAPI 1.4.0;
  public account/consent/installation/repository/webhook đã có trong source,
  internal Work/AI M5/M6 là **Thiết kế mục tiêu, chưa triển khai runtime**.
  Xem [ADR-004](../../docs/adr/004-integration-github-account-ownership.md) và
  [ADR-005](../../docs/adr/005-integration-work-ai-contracts.md).

- [`ai-service-v1.yaml`](ai-service-v1.yaml): API AI giai đoạn 1; đã chốt thiết
  kế, có bootstrap implementation một phần; chưa có provider/ADK hoặc runtime
  production. Xem [code map](../../docs/ai-service/code-map.md).

## Đối chiếu baseline mới

[Baseline](../../docs/architecture/README.md) không tự thay URL/payload hoặc
ngưỡng chờ của API v1. Quy tắc gateway-auth trong YAML cần đối chiếu với việc
service xác thực token theo baseline. Internal-context API của Work chưa có
contract. Các thay đổi cần version/quy tắc tương thích và kiểm thử riêng; xem
[ADR-001](../../docs/adr/001-adopt-architecture-baseline.md).

Identity OpenAPI 1.8 được sinh từ URLconf và serializers của
service bằng drf-spectacular. Artifact mặc định gồm 25 thao tác; OAuth/avatar tắt mặc định
không xuất thành route đang mở. Bật flags trong môi trường đủ cấu hình để xuất riêng.
Trách nhiệm, luồng và cách tích hợp: [Identity Service](../../docs/identity-service/README.md).
Khi Identity chạy local, Swagger UI ở `/docs/` và OpenAPI JSON ở
`/openapi/`. Trên staging qua Nginx, dùng `/api/auth/docs/` và
`/api/auth/openapi/`.

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
