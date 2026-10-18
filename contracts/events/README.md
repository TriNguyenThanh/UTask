# Event contracts

Đặt schema Kafka máy đọc được tại đây khi service phát/nhận sự kiện và cấu trúc
sự kiện đã được chốt. Danh mục mục tiêu nằm trong
[docs/system/kafka-events.md](../../docs/system/kafka-events.md). Không lặp
schema trong tài liệu service và không tạo hợp đồng giả.

## Hợp đồng Integration đã chốt

- [`integration.project.connection.changed.v1.json`](integration.project.connection.changed.v1.json):
  schema M0, **Thiết kế mục tiêu — producer/consumer chưa triển khai**, chỉ
  bật từ M6. Topic `utask.integration.events`, key Project ID; Work là consumer
  đầu tiên. Event không cấp quyền hoặc tự xác nhận Task link. Quy tắc outbox,
  chống lặp, version và ACL tại [ADR-003](../../docs/adr/003-integration-auth-and-contracts.md).

## Hợp đồng thiết kế trước baseline mới

- [`ai-context-v1.yaml`](ai-context-v1.yaml): event context mà AI Service
  consume; đã chốt thiết kế, chưa có producer/consumer implementation được xác
  minh. Contract dùng producer Project/Progress và envelope cũ; cần đối chiếu
  baseline trước khi dùng với Work, không tạo Progress Service từ contract này.

Chuẩn event mục tiêu và những khác biệt nằm trong
[danh mục sự kiện](../../docs/system/kafka-events.md). Baseline nêu event kết
quả AI nhưng chưa chốt schema; không tự bổ sung tên/schema để lấp đầy thư mục.
