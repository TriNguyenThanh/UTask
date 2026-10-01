# Kafka

Kafka là kênh truyền sự kiện bất đồng bộ giữa các service trong kiến trúc mục
tiêu. REST vẫn được dùng khi bên gọi cần câu trả lời ngay.

Danh mục sự kiện mục tiêu nằm trong [tài liệu hệ thống](../system/kafka-events.md).
Schema máy đọc được chỉ đặt trong [`contracts/events/`](../../contracts/events/)
sau khi hợp đồng được chốt. Việc có Kafka trong hạ tầng không đồng nghĩa
service phát, service nhận hoặc transactional outbox đã được triển khai.
