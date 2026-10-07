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

Classroom có thể cần event nhóm/thành viên; tên, payload và service nhận phải
chốt theo use case, không suy ra schema từ wildcard. Baseline dùng cả ví dụ
`comment.created` và `task.comment.created`; tên cuối cùng cần event contract.

## Envelope và version

Baseline mục 15 minh họa envelope có `event_id`, `event_type`, `event_version`,
`aggregate_id`, `occurred_at`, `trace_id`, `payload`. Giai đoạn đầu ưu tiên JSON
Schema; AsyncAPI/Schema Registry/Avro/Protobuf chỉ thêm theo nhu cầu.
Đây là chuẩn mục tiêu, không phải schema thay thế tự động cho contract cũ.

Publish qua transactional outbox; consumer chống lặp theo `event_id`.
Truyền trace ID để liên kết API, job và event. Xem
[Kafka/outbox](../infrastructure/kafka.md).

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
