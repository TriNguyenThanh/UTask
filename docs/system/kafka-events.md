# Danh mục sự kiện Kafka

**Trạng thái: Thiết kế mục tiêu.** Tên dưới đây là ví dụ theo baseline mục
9 và phạm vi service, không xác nhận producer/consumer đã chạy. Schema máy
đọc được thuộc `contracts/events/`; xem [baseline](../architecture/README.md).

| Sự kiện ví dụ                                                                                                | Service phát | Service nhận dự kiến                              | Mục đích                               |
| ------------------------------------------------------------------------------------------------------------ | ------------ | ------------------------------------------------- | -------------------------------------- |
| `user.created`                                                                                               | Identity     | Service cần thông tin user                        | Đồng bộ thông tin người dùng           |
| `project.created`, `member.joined`, `sprint.started`                                                         | Work         | AI, Notification; Analytics giai đoạn sau khi cần | Báo thay đổi dự án/thành viên/sprint   |
| `task.created`, `task.assigned`, `task.status.changed`, `task.completed`, `comment.created`                  | Work         | Notification, AI; Analytics khi được triển khai   | Báo thay đổi công việc                 |
| `github.commit.received`, `github.pull_request.opened`, `github.pull_request.merged`, `github.issue.updated` | Integration  | Work, AI, Notification khi cần                    | Chia sẻ hoạt động GitHub đã chuẩn hóa  |
| `ai.analysis.completed`, `ai.project.risk.detected`                                                          | AI           | Notification hoặc service đã đăng ký nhận         | Thông báo phân tích/rủi ro đã hoàn tất |

Classroom công bố sự kiện `classroom.group.membership.changed` khi thành viên
nhóm thay đổi; xem [hợp đồng JSON Schema](../../contracts/events/classroom.group.membership.changed.v1.json).
Work nhận ảnh chụp thành viên để cập nhật các dự án hoạt động của nhóm.

Work công bố sự kiện `work.project.created`; Classroom nhận sự kiện để ghi
liên kết nhóm–dự án. Xem [hợp đồng JSON Schema](../../contracts/events/work.project.created.v1.json).

Baseline dùng cả ví dụ `comment.created` và `task.comment.created`; tên sự
kiện cuối cùng cần được chốt bằng hợp đồng cụ thể.

## Envelope và version

Baseline mục 15 minh họa envelope có `event_id`, `event_type`, `event_version`,
`aggregate_id`, `occurred_at`, `trace_id`, `payload`. Giai đoạn đầu ưu tiên JSON
Schema; AsyncAPI/Schema Registry/Avro/Protobuf chỉ thêm theo nhu cầu.
Đây là chuẩn mục tiêu, không phải schema thay thế tự động cho contract cũ.

Publish qua transactional outbox; consumer chống lặp theo `event_id`.
Truyền trace ID để liên kết API, job và event. Xem
[Kafka/outbox](../infrastructure/kafka.md).

Kết nối repository của Project dùng contract
[`integration.project.connection.changed.v1`](../../contracts/events/integration.project.connection.changed.v1.json).
Contract này **đã có producer outbox/publisher phía Integration**, mặc định tắt;
Work đã có consumer và test hai backend qua HTTP/PostgreSQL/Kafka riêng với
GitHub/Identity stub; staging và GitHub live chưa nghiệm thu. Xem
[hướng dẫn Work](../project-service/github-integration.md). Thứ tự, receipt và ranh giới với
REST được chốt tại [ADR-005](../adr/005-integration-work-ai-contracts.md).

## Hợp đồng cũ cần đối chiếu

[`ai-context-v1.yaml`](../../contracts/events/ai-context-v1.yaml) đã mô tả
projection project/task/sprint/GitHub/progress cho AI theo thiết kế trước.
Nó dùng producer `project-service`/`progress-service` và envelope `producer`/
`data`, khác baseline mới dùng Work và envelope `payload` có trace/aggregate ID.
Giữ nguyên schema để truy nguyên; chưa dùng nó làm contract triển khai Work
mới trước khi có version/mapping chuyển đổi. Producer/consumer chưa có runtime.

`ai.completed` là ví dụ cũ, không tự coi là alias cho `ai.analysis.completed`.
Event kết quả AI chưa có schema được chốt; không tạo schema giả trong lần
cập nhật tài liệu này. AI API v1 vẫn chưa phát event kết quả.

## Notification Identity/Work đã triển khai trong source

Consumer Notification nhận ba sự kiện mail Identity và năm loại sự kiện Work
được chốt tại [Notification](../notification-service/README.md).
`task.assigned` là sự kiện bổ sung người được giao; tên nhắc hạn đang chạy là
`task.deadline.reminder`, không phải ví dụ `task.deadline.approaching`.
Schema chuẩn nằm trong [contracts/events](../../contracts/events/README.md).
Kafka commit sau inbox durable, gửi mail qua Celery/Redis riêng. SMTP Gmail thật đã ACK thư thử; staging và thư tới Inbox người nhận chưa xác minh.
Không suy từ producer ACK rằng thư đã tới người nhận.
