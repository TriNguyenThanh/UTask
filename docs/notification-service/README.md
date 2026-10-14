# Notification Service

**Trạng thái tài liệu: Thiết kế mục tiêu; hiện trạng triển khai chưa xác minh.**

Theo [baseline](<../architecture/UTask_Architecture_Technology_Baseline (1).md>)
mục 4.5, service dùng Python + Django. In-app và email là kênh mục tiêu ban
đầu; Web Push thuộc giai đoạn sau, Mobile Push chỉ khi có ứng dụng mobile.
Job gửi email/retry dùng Celery + Redis của Notification Service; Kafka
consumer nhận sự kiện nghiệp vụ. Xem [job nền](../infrastructure/background-jobs.md).

Notification Service sở hữu notification record, trạng thái gửi, template,
tuỳ chọn (nếu được chọn) và việc gửi qua in-app, email hoặc nhà cung cấp push.
Service nhận các sự kiện cần thông báo qua Kafka; Work Service không nhúng
toàn bộ logic gửi notification.

Các sự kiện có thể cần thông báo gồm `task.assigned`, `task.deadline.approaching`,
`github.pull_request.merged`, `ai.analysis.completed` và `ai.project.risk.detected`. Danh
sách chính thức, quy tắc người nhận, thử lại, kênh và API cần hợp đồng riêng; các
tên trên là ví dụ mục tiêu, không xác nhận sự kiện đã tồn tại.

Thông báo không liên quan AI tiếp tục hoạt động khi AI Service bị lỗi.
