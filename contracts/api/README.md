# API contracts

Đặt tại đây các hợp đồng API máy đọc được, nếu đã được chốt. Tài liệu giải
thích dành cho đội phát triển nằm trong `docs/<service>/`. Sự hiện diện của thư
mục này không khẳng định một endpoint đã được triển khai hoặc công bố.

Phân biệt API người dùng, API nội bộ, webhook và endpoint health. Đánh dấu rõ
hợp đồng mục tiêu chưa triển khai; không tạo schema giả để lấp đầy thư mục.

## Hợp đồng đã chốt

- [`ai-service-v1.yaml`](ai-service-v1.yaml): API AI giai đoạn 1; đã chốt thiết
  kế, có bootstrap implementation một phần; chưa có provider/ADK hoặc runtime
  production. Xem [code map](../../docs/ai-service/code-map.md).

## Đối chiếu baseline mới

[Baseline](../../docs/architecture/README.md) không tự thay URL/payload hoặc
ngưỡng chờ của API v1. Quy tắc gateway-auth trong YAML cần đối chiếu với việc
service xác thực token theo baseline. Internal-context API của Work chưa có
contract. Các thay đổi cần version/quy tắc tương thích và kiểm thử riêng; xem
[ADR-001](../../docs/adr/001-adopt-architecture-baseline.md).
