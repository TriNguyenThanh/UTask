# Danh mục sự kiện Kafka

**Trạng thái: Một phần (`Đã triển khai (local)` cho các topic đối ngoại của `core-service` theo [ADR-006](adr/006-consolidate-core-monolith.md); tổng thể hệ thống là thiết kế mục tiêu và staging `Chưa xác minh`).** Schema máy đọc được thuộc `contracts/events/`; xem [baseline](architecture-baseline.md).

## Các topic đang hoạt động với Core Service (`apps/core-service`)

Sau khi hợp nhất Identity, Classroom và Work theo [ADR-006](adr/006-consolidate-core-monolith.md),
Kafka chỉ giữ vai trò truyền sự kiện bất đồng bộ giữa `core-service` và các
service độc lập bên ngoài (`notification-service`, `integration-service`, và
`ai-service` khi mở rộng):

| Topic | Chiều | `producer` giữ nguyên hợp đồng | Bên nhận | Ghi chú |
| --- | --- | --- | --- | --- |
| `utask.identity.events` | Outbound từ `core-service` (`core-worker`) | `"identity-service"` | `notification-service` | Gửi sự kiện email kích hoạt, đặt lại mật khẩu, import sinh viên, đổi email (`identity.email_change.requested`) và vòng đời user |
| `utask.work.events` | Outbound từ `core-service` (`core-worker`) | `"work-service"` | `notification-service` | Gửi sự kiện giao task, đổi trạng thái, bình luận, nhắc hạn (`task.deadline.reminder`) và thay đổi thành viên dự án |
| `utask.integration.events` | Inbound vào `core-service` (`core-consumer`: `consume_integration`) | `"integration-service"` | `core-service` | Nhận `integration.project.connection.changed`, `integration.github.account.changed`, `integration.github.reference.detected` |
| `utask.work.integration.dlq` | DLQ của `core-consumer` | `"work-service"` | Vận hành / đối soát | Lưu bản ghi lỗi quá số lần thử từ `utask.integration.events` |

## Sự kiện nội bộ cũ đã chuyển sang gọi trong tiến trình (ADR-006)

Hai luồng Kafka cũ chỉ dùng giữa Classroom và Work nay **đã dừng ở runtime** vì
cả hai miền chạy trong cùng `apps/core-service` trên `core_db` và đồng bộ nguyên
tử qua `apps.groups.interface` / `apps.projects.interface`:

- `classroom.group.membership.changed` ([schema lưu trữ lịch sử](../../contracts/events/classroom.group.membership.changed.v1.json))
- `work.project.created` ([schema lưu trữ lịch sử](../../contracts/events/work.project.created.v1.json))
- Consumer nội bộ cũ `utask.identity.events` → `UserProjection` trong Work cũng đã bị loại bỏ (truy cập trực tiếp qua `apps.accounts.interface`).

Các tệp JSON Schema cũ vẫn được giữ nguyên trong `contracts/events/` để đối chiếu lịch sử.

## Danh mục sự kiện tham chiếu theo baseline

| Sự kiện ví dụ | Service / Miền phát | Service nhận dự kiến | Mục đích |
| --- | --- | --- | --- |
| `user.created` | Core (Identity) | Service cần thông tin user | Đồng bộ thông tin người dùng |
| `project.created`, `member.joined`, `sprint.started` | Core (Work) | AI, Notification; Analytics giai đoạn sau khi cần | Báo thay đổi dự án/thành viên/sprint |
| `task.created`, `task.assigned`, `task.status.changed`, `task.completed`, `comment.created` | Core (Work) | Notification, AI; Analytics khi được triển khai | Báo thay đổi công việc |
| `github.commit.received`, `github.pull_request.opened`, `github.pull_request.merged`, `github.issue.updated` | Integration | Core (Work), AI, Notification khi cần | Chia sẻ hoạt động GitHub đã chuẩn hóa |
| `ai.analysis.completed`, `ai.project.risk.detected` | AI | Notification hoặc service đã đăng ký nhận | Thông báo phân tích/rủi ro đã hoàn tất |

Baseline dùng cả ví dụ `comment.created` và `task.comment.created`; tên sự
kiện cuối cùng cần được chốt bằng hợp đồng cụ thể.

## Envelope và version

Baseline mục 15 minh họa envelope có `event_id`, `event_type`, `event_version`,
`aggregate_id`, `occurred_at`, `trace_id`, `payload`. Giai đoạn đầu ưu tiên JSON
Schema; AsyncAPI/Schema Registry/Avro/Protobuf chỉ thêm theo nhu cầu.
Đây là chuẩn mục tiêu, không phải schema thay thế tự động cho contract cũ.

Publish qua transactional outbox; consumer chống lặp theo `event_id`.
Truyền trace ID để liên kết API, job và event. Xem
[Kafka/outbox](infrastructure/kafka.md).

Kết nối repository của Project dùng contract
[`integration.project.connection.changed.v1`](../../contracts/events/integration.project.connection.changed.v1.json).
Contract này **đã có producer outbox/publisher phía Integration**, mặc định tắt;
Work đã có consumer và test hai backend qua HTTP/PostgreSQL/Kafka riêng với
GitHub/Identity stub; staging và GitHub live chưa nghiệm thu. Xem
[hướng dẫn Work](../project-service/github-integration.md). Thứ tự, receipt và ranh giới với
REST được chốt tại [ADR-005](adr/005-integration-work-ai-contracts.md).

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
