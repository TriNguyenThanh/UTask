# Giao tiếp giữa các service

**Trạng thái: Một phần (`Đã triển khai (local)` cho giao tiếp nội bộ trong `core-service` theo [ADR-006](adr/006-consolidate-core-monolith.md); thiết kế mục tiêu cho toàn hệ thống).** Theo baseline mục 2, 9–11 và 13–15; xem [nguồn baseline](architecture-baseline.md).

## Giao tiếp trong tiến trình, REST, job nội bộ và sự kiện

| Nhu cầu | Cơ chế | Ví dụ |
| --- | --- | --- |
| Tương tác giữa Identity, Classroom và Work trong `core-service` | Gọi hàm nội bộ qua `interface.py` (in-process, cùng transaction `core_db`) | Work kiểm tra nhóm/quyền giảng viên qua `apps.groups.interface`; Classroom tra cứu/tạo user qua `apps.accounts.interface` |
| Command/query xuyên service cần phản hồi trực tiếp | REST nội bộ | AI kiểm tra phiên và quyền/context qua `identity-service`/`work-service` (Docker aliases của `core-service`); Work gọi Integration |
| Công việc nền nội bộ service | Celery + Redis | Xuất outbox (`core-worker`), đồng bộ GitHub, gửi email, retry, quét deadline |
| Thông báo việc đã xảy ra cho service ngoài | Kafka | Core phát `utask.identity.events` và `utask.work.events` cho Notification; Integration phát `utask.integration.events` cho Core |

Không chuyển mọi giao tiếp sang Kafka và không tạo chuỗi hỏi–đáp Kafka cho
query đồng bộ. Job nội bộ là lệnh thực thi; domain event thông báo thay đổi
đã xảy ra. Worker thuộc service sở hữu nghiệp vụ, có thể chạy process/container
riêng; số worker không được ấn định là singleton.

## Quy tắc theo service

- **Bên trong `core-service`:** Identity, Classroom và Work chỉ tương tác chéo qua
  `apps.accounts.interface`, `apps.groups.interface` và `apps.projects.interface`,
  không gọi vòng lặp HTTP hay đẩy sự kiện Kafka nội bộ giữa ba miền này.
- **Giữa `core-service` và service ngoài (`ai-service`, `integration-service`,
  `notification-service`):** REST chỉ đi qua API công bố, không truy cập database
  service khác. Internal API vẫn phải kiểm tra danh tính, service key, quyền và
  giới hạn dữ liệu. Docker network aliases `identity-service`, `classroom-service`,
  `work-service` trên `core-service` giữ nguyên toàn bộ URL nội bộ cho các đội
  ngoài ([ADR-006](adr/006-consolidate-core-monolith.md)).
- Miền Identity trong `core-service` cấp JWT access/refresh token (RS256) và công
  bố `/.well-known/jwks.json`; các service ngoài xác thực token và kiểm tra quyền
  tài nguyên ở backend, không đọc `core_db`.
- Miền Work trong `core-service` quản lý Project/Task/Sprint và tính tiến độ bằng
  quy tắc; gọi trực tiếp Classroom qua `apps.groups.interface` để xác minh nhóm/lớp.
- Integration là service duy nhất gọi trực tiếp GitHub; service khác dùng
  internal API hoặc event GitHub đã chuẩn hóa. Hợp đồng REST nội bộ Work/AI
  hiện **đã triển khai phía provider**, flags mặc định tắt và Work/AI thật
  chưa nghiệm thu tích hợp; xem
  [ADR-005](adr/005-integration-work-ai-contracts.md).
- AI nhận ý định, lấy context qua domain tool/Context Layer có adapter internal
  REST API. Kiểm tra quyền trên target cũng gọi service sở hữu qua REST; không
  dùng Kafka hỏi–đáp cho permission/context. Nếu chưa xác minh được quyền thì
  không giao job. Agent không được gọi URL tùy ý, Kafka hay database. Context
  projection qua event có thể bổ sung khi có nhu cầu; bản sao hoặc event đổi
  quyền không tự cấp quyền truy cập.
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

AI API lưu request và ý định giao job trước khi xác nhận đã nhận job; dispatcher
giao task qua Redis tới Celery worker của AI. Worker lưu kết quả qua application/
repository vào PostgreSQL của AI, API đọc persistence để trả cho client.
Không cần event Kafka về API process để cập nhật kết quả. Kênh SSE/WebSocket
nếu được bổ sung vẫn phải cho phép client đọc lại trạng thái qua API.
Xem [pipeline AI](../ai-service/architecture.md) và
[ADR-002](adr/002-ai-request-pipeline.md).

## Tin cậy và xử lý lặp

Domain service lưu thay đổi và outbox cùng transaction, publisher gửi Kafka
sau commit; consumer phải xử lý an toàn khi nhận lại cùng `event_id`.
Job cần timeout, retry có giới hạn và kiểm soát tác động lặp. Xem
[Kafka/outbox](infrastructure/kafka.md) và
[job nền](infrastructure/background-jobs.md).

Với job AI, idempotency phải áp dụng ở cả bước nhận POST và worker khi nhận lại
task. Ghi database và gửi Redis không phải transaction chung; cần bản ghi chờ
giao job và cơ chế phục hồi. Thông điệp không xử lý được được cách ly theo quy
tắc dead-letter; request hết retry phải có trạng thái lỗi cuối để client không
chờ vô hạn. Retry phát event kết quả không làm chạy lại workflow AI.
