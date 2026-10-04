# Danh mục sự kiện Kafka

Đây là danh mục kiến trúc mục tiêu, chưa xác minh service phát/nhận sự kiện
(producer/consumer) nào đang chạy. Schema máy đọc được, nếu có, thuộc
`contracts/events/`. Tài liệu này chỉ làm mục lục; không sao chép schema.

| Sự kiện | Service phát | Service nhận | Mục đích |
| --- | --- | --- | --- |
| `group.member.added`, `group.member.removed` | Classroom Service | Project, Progress, AI khi cần | Báo thay đổi thành viên nhóm |
| `project.created`, `project.*`, `sprint.*`, `task.*` | Project Service | Progress, AI, Notification | Báo thay đổi công việc và dự án |
| `github.connected`, `github.commit.received`, `github.pull_request.opened`, `github.pull_request.merged`, `github.issue.updated` | Integration Service | Project nếu cần, Progress, AI, Notification | Chia sẻ hoạt động GitHub đã chuẩn hóa |
| `progress.*`, `progress.risk_detected` | Progress Service | Web, Notification, AI | Công bố chỉ số và tín hiệu tính theo luật |
| `ai.completed` | AI Service | Notification hoặc thành phần gọi | Ví dụ kết quả AI dùng cho notification |

Các sự kiện cụ thể ở trên là danh mục mục tiêu. Hợp đồng context v1 dành cho AI
đã được chốt riêng tại
[`contracts/events/ai-context-v1.yaml`](../../contracts/events/ai-context-v1.yaml),
bao gồm project, sprint, task, GitHub activity và progress metric. Các event
khác vẫn chưa phải hợp đồng máy đọc được. Không suy ra một sự kiện mới từ dấu
`*` trong bảng.

Envelope mục tiêu có các trường chung như `event_id`, `event_type`,
`event_version`, `occurred_at`, `producer` và `data`. Schema cuối cùng thuộc
`contracts/events/`; không tạo schema giả chỉ để lấp đầy thư mục.
