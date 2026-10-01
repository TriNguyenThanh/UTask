# Notification Service

**Trạng thái tài liệu: Thiết kế mục tiêu; hiện trạng triển khai chưa xác minh.**

Notification Service sở hữu notification record, trạng thái gửi, template,
tuỳ chọn (nếu được chọn) và việc gửi qua in-app, email hoặc nhà cung cấp push.
Service nhận các sự kiện cần thông báo qua Kafka; Project Service không nhúng
toàn bộ logic gửi notification.

Các sự kiện có thể cần thông báo gồm `task.assigned`, `task.deadline.approaching`,
`github.pull_request.merged`, `progress.risk_detected` và `ai.completed`. Danh
sách chính thức, quy tắc người nhận, thử lại, kênh và API cần hợp đồng riêng; các
những tên trên là ví dụ mục tiêu, không xác nhận sự kiện đã tồn tại.

Thông báo không liên quan AI tiếp tục hoạt động khi AI Service bị lỗi.
