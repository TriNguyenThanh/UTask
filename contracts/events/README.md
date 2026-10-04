# Event contracts

Đặt schema Kafka máy đọc được tại đây khi service phát/nhận sự kiện và cấu trúc
sự kiện đã được chốt. Danh mục mục tiêu nằm trong
[docs/system/kafka-events.md](../../docs/system/kafka-events.md). Không lặp
schema trong tài liệu service và không tạo hợp đồng giả.

## Hợp đồng đã chốt

- [`ai-context-v1.yaml`](ai-context-v1.yaml): event context mà AI Service
  consume; đã chốt thiết kế, chưa có producer/consumer implementation được xác
  minh.
