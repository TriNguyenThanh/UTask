# Work nhận sự kiện hồ sơ từ Identity

**Đã triển khai và kiểm chứng runtime local ngày20/10/2026.** Work đọc topic Identity
trên broker dùng chung; chỉ ghi projection hiển thị trong database Work, không đọc
database Identity và không lấy event làm quyền truy cập tài nguyên.

Nguồn: [consumer](../../apps/work-service/apps/messaging/consumer.py),
[command](../../apps/work-service/apps/messaging/management/commands/consume_identity.py),
[test biên nhận](../../apps/work-service/tests/unit/test_profile_consumer_boundary.py),
[test giao dịch](../../apps/work-service/tests/integration/test_membership_consumer.py).

## Phân loại sự kiện

- `identity.user.created`, `identity.user.updated`: kiểm envelope và payload hồ sơ;
  ghi receipt chống trùng và `UserProjection` trong cùng transaction. Event cũ không
  ghi đè dữ liệu mới; cùng ID nhưng payload khác bị từ chối. Chỉ commit Kafka sau DB.
- Chín loại đã chốt ngoài projection: `identity.user.activated`,
  `identity.user.status_changed`, `identity.user.role_assigned`,
  `identity.user.role_revoked`, `identity.activation.requested`,
  `identity.student.imported`, `identity.password_reset.requested`,
  `identity.oauth.github_linked`, `identity.oauth.github_unlinked`.
  Work kiểm envelope v1 (producer, loại, UUID/event-user binding, thời gian có múi giờ),
  rồi commit offset; không ghi profile/receipt hoặc giải mã mail. Consumer sở hữu mail
  và GitHub vẫn chịu trách nhiệm xử lý payload tương ứng.
- JSON hỏng, loại không biết, phiên bản không hỗ trợ hoặc envelope sai: đưa vào DLQ
  `utask.work.profile.dlq`, chờ Kafka ACK rồi mới commit offset. DLQ lỗi hoặc DB lỗi:
  giữ record hiện tại và thử lại, không nhảy qua offset sau.

## Cấu hình và vận hành

`WORK_IDENTITY_KAFKA_TOPIC` đi từ `.env` qua `infra/env/work-service.env`, Compose
`env_file`, settings rồi Consumer. Khi để trống, mapping lấy `IDENTITY_KAFKA_TOPIC`,
mặc định `utask.identity.events`; có thể override topic riêng khi kiểm thử.
Kết nối dùng cùng nhóm `KAFKA_*` của producer, không tạo broker riêng.

Command `python manage.py consume_identity` dùng group `work-profile-v1`; tắt auto
commit và auto offset store. Tạo topic, quyền consumer/DLQ trên broker trước khi chạy.
Thay env phải tạo lại container; chỉ restart không nạp giá trị Compose mới.

## Bằng chứng và giới hạn

Đã chạy HTTP đăng ký, PATCH hồ sơ và provisioning thật tại Identity; outbox gửi qua
Kafka Docker thật rồi `process_record` của Work ghi DB riêng.12 event hợp lệ tạo3
receipt hồ sơ,2 projection;9 non-profile không vào DLQ. Replay giữ nguyên số hàng.
Event phiên bản2 được phát lên Kafka thật, vào DLQ và offset mới được commit sau ACK.
Không dừng hay thay dữ liệu broker/DB đang dùng của người dùng; bài thử dùng DB/topic riêng.

Kết quả local: `artifacts/identity/event-handoff/runtime.json`. Bộ Work718 ca đạt,
2 ca external/E2E được loại theo cấu hình pytest mặc định, không đổi thành Pass.
Không xác nhận staging, Google/GitHub, Notification hoặc Resend từ kết quả này.
