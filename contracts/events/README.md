# Event contracts

Đặt schema Kafka máy đọc được tại đây khi service phát/nhận sự kiện và cấu trúc
sự kiện đã được chốt. Danh mục mục tiêu nằm trong
[docs/system/kafka-events.md](../../docs/system/kafka-events.md). Không lặp
schema trong tài liệu service và không tạo hợp đồng giả.

## Hợp đồng Integration đã chốt

- [`integration.project.connection.changed.v1.json`](integration.project.connection.changed.v1.json):
  **Đã triển khai phía producer outbox/publisher, flag mặc định tắt**;
  consumer Work thật chưa nghiệm thu. Topic `utask.integration.events`, key Project ID; Work là consumer
  đầu tiên. Event không cấp quyền hoặc tự xác nhận Task link. Quy tắc outbox,
  chống lặp, version và ACL tại [ADR-003](../../docs/adr/003-integration-auth-and-contracts.md);
  ranh giới Work/AI và thứ tự rollout tại
  [ADR-005](../../docs/adr/005-integration-work-ai-contracts.md).

## Hợp đồng thiết kế trước baseline mới

- [`ai-context-v1.yaml`](ai-context-v1.yaml): event context mà AI Service
  consume; đã chốt thiết kế, chưa có producer/consumer implementation được xác
  minh. Contract dùng producer Project/Progress và envelope cũ; cần đối chiếu
  baseline trước khi dùng với Work, không tạo Progress Service từ contract này.

Chuẩn event mục tiêu và những khác biệt nằm trong
[danh mục sự kiện](../../docs/system/kafka-events.md). Baseline nêu event kết
quả AI nhưng chưa chốt schema; không tự bổ sung tên/schema để lấp đầy thư mục.

## Notification: Identity và Work

Schema v1 theo producer hiện hành, envelope `data`; Notification validate trước lưu:

- [Kích hoạt](identity.activation.requested.v1.json),
  [nhập sinh viên](identity.student.imported.v1.json),
  [đặt lại mật khẩu](identity.password_reset.requested.v1.json).
- [Giao task](task.assigned.v1.json),
  [nhắc hạn](task.deadline.reminder.v1.json),
  [nhắc tên](comment.mentions.added.v1.json),
  [phản hồi giảng viên](teacher.feedback.added.v1.json),
  [chuyển trạng thái](task.transitioned.v1.json).

`task.assigned` chỉ chứa người mới được giao, trừ actor. `task.transitioned`
giữ dữ liệu Task hiện có và bổ sung actor/người nhận. Không suy ra schema
GitHub/AI từ các ví dụ mục tiêu. Quy tắc gửi và trạng thái nghiệm thu tại
[Notification Service](../../docs/notification-service/README.md).
