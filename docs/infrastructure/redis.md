# Redis

**Trạng thái: Thiết kế mục tiêu; đã có cấu hình Redis trong Compose.**

[Baseline](<../architecture/UTask_Architecture_Technology_Baseline (1).md>)
mục 11 chọn **Celery + Redis** cho job nền nội bộ: gửi email, retry, deadline
scan, outbox publishing, periodic task, dọn dữ liệu và đồng bộ theo lịch.
Redis cũng có thể phục vụ cache; không phải nơi lưu dữ liệu nghiệp vụ gốc.

Kafka truyền sự kiện giữa service; Redis làm broker (nơi chuyển job) cho
Celery. Mã worker và trạng thái job thuộc service sở hữu nghiệp vụ; xem
[job nền](background-jobs.md).

**Hiện trạng đã kiểm tra:** `docker-compose.yml` khai báo `redis:7-alpine`,
AOF, volume dữ liệu và healthcheck `redis-cli ping`. Chưa khai báo process
Celery worker/scheduler hoặc queue theo service; chưa xác minh job runtime.
AI bootstrap chưa có dependency Celery/Redis.

Khi triển khai, cần tách queue theo workload/service, giới hạn concurrency,
retry và thời gian thực thi. Production dùng Redis bên ngoài theo baseline;
cấu hình HA, retention và cơ chế phục hồi cần xác minh theo nền tảng vận hành.
