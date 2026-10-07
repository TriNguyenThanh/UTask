# Giao tiếp giữa các service

**Trạng thái: Thiết kế mục tiêu.** Theo baseline mục 2, 9–11 và 13–15; xem
[nguồn baseline](../architecture/README.md).

## REST, job nội bộ và sự kiện

| Nhu cầu                                   | Cơ chế         | Ví dụ                                                              |
| ----------------------------------------- | -------------- | ------------------------------------------------------------------ |
| Command/query cần phản hồi trực tiếp      | REST           | Work kiểm tra Group; AI lấy Project/Task context qua internal API  |
| Công việc nền nội bộ service              | Celery + Redis | Đồng bộ GitHub, gửi email, retry, deadline scan, outbox publishing |
| Thông báo việc đã xảy ra cho service khác | Kafka          | Work phát `task.assigned`, Integration phát hoạt động GitHub       |

Không chuyển mọi giao tiếp sang Kafka và không tạo chuỗi hỏi–đáp Kafka cho
query đồng bộ. Job nội bộ là lệnh thực thi; domain event thông báo thay đổi
đã xảy ra. Worker thuộc service sở hữu nghiệp vụ, có thể chạy process/container
riêng; số worker không được ấn định là singleton.

## Quy tắc theo service

- REST chỉ qua API công bố, không truy cập database service khác. Internal API
  vẫn phải kiểm tra danh tính, quyền và giới hạn dữ liệu.
- Identity cấp JWT access/refresh token; các service xác thực token và kiểm tra
  quyền tài nguyên ở backend, không đọc Identity DB.
- Work quản lý Project/Task/Sprint và tính tiến độ bằng quy tắc; có thể gọi
  Classroom đồng bộ để xác minh nhóm/lớp.
- Integration là service duy nhất gọi trực tiếp GitHub; service khác dùng
  internal API hoặc event GitHub đã chuẩn hóa.
- AI nhận ý định, lấy context qua domain tool/Context Layer có adapter internal
  API. Agent không được gọi URL tùy ý, Kafka hay database. Context projection
  qua event có thể bổ sung khi có nhu cầu, không phải đường lấy context duy nhất.
- AI chỉ đề xuất; service sở hữu dữ liệu xác thực và áp dụng sau user xác nhận.
- Notification consume Kafka; job gửi email/retry dùng Celery + Redis nội bộ.

## API và client

Nginx là reverse proxy theo prefix service. URL version và rewrite phải khớp
contract từng service; các URL ví dụ trong baseline không xác nhận endpoint
đã chạy. Không đổi breaking API mà không version/quy tắc chuyển đổi.

Job dài có thể trả ID/status để client GET hoặc dùng SSE/WebSocket khi đã
thiết kế kênh đó. Kafka không tự trả thêm HTTP response cho client sau `202`.
AI v1 hiện quy định ngưỡng chờ và polling riêng trong
[API AI](../ai-service/api.md); baseline không chốt các ngưỡng này.

## Tin cậy và xử lý lặp

Domain service lưu thay đổi và outbox cùng transaction, publisher gửi Kafka
sau commit; consumer phải xử lý an toàn khi nhận lại cùng `event_id`.
Job cần timeout, retry có giới hạn và kiểm soát tác động lặp. Xem
[Kafka/outbox](../infrastructure/kafka.md) và
[job nền](../infrastructure/background-jobs.md).
