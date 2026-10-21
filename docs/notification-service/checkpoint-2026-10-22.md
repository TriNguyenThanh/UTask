# Checkpoint Notification Service — 22/10/2026

## Kết luận bàn giao

**Trạng thái tổng thể: Một phần.** Backend, producer Identity/Work, API nội bộ,
Web và cấu hình local/staging **Đã triển khai trong source**. Smoke runtime
local với Kafka/PostgreSQL/Redis/Celery/SMTP STARTTLS đạt; Identity/Work HTTP
trong phép thử là stub. SMTP Gmail thật đã ACK ba thư thử được người dùng cho
phép. Staging/VPS, thư tới Inbox và toàn tuyến domain service thật → Kafka →
Gmail **Chưa xác minh**.

Snapshot thuộc nhánh `feat/notification-service`, HEAD nền `377183a`; phần
Notification đang nằm trong working tree, chưa có commit phát hành riêng tại
thời điểm viết. HEAD nền không đại diện cho toàn bộ source được bàn giao.
Các kết quả test dưới đây thuộc lượt triển khai trước trong cùng phiên;
lượt viết checkpoint chỉ đọc lại source, hợp đồng và kiểm tra tài liệu.

Đọc tiếp theo mục đích:

- Đội Identity/Work/Web: [hướng dẫn triển khai và tích hợp](implementation.md).
- Người vận hành: [cấu hình, rollout và replay](operations.md).
- Người nghiệm thu: [bằng chứng và giới hạn kiểm chứng](verification.md).
- Nguồn chuẩn hiện hành: [tổng quan service](README.md),
  [API public](../../contracts/api/notification-service-v1.yaml),
  [API nội bộ](../../contracts/api/notification-internal-v1.yaml),
  [schema event](../../contracts/events/README.md).

Checkpoint là ảnh chụp bàn giao theo ngày, không thay thế các nguồn chuẩn trên.

## Những phần đã triển khai

| Phần việc | Trạng thái | Bằng chứng source/cấu hình |
| --- | --- | --- |
| Django/DRF, PostgreSQL riêng, migration | Đã triển khai; migration image đã thử trên DB riêng | [models](../../apps/notification-service/notifications/models.py), [migrations](../../apps/notification-service/notifications/migrations/), [Dockerfile](../../apps/notification-service/Dockerfile) |
| Hai consumer Identity/Work, manual commit sau durable inbox/quarantine | Đã triển khai; Kafka local đã thử | [consumer](../../apps/notification-service/notifications/management/commands/consume_notifications.py), [persist/validation](../../apps/notification-service/notifications/services.py) |
| Dispatcher, lease, retry, quota, retention/replay | Đã triển khai; tranh lease/quota kiểm trên PostgreSQL | [tasks](../../apps/notification-service/notifications/tasks.py), [replay](../../apps/notification-service/notifications/management/commands/replay_notifications.py) |
| Giải mã mail Identity và SMTP TLS, template text/HTML | Đã triển khai; SMTP fixture và Gmail trực tiếp đã thử | [mail](../../apps/notification-service/notifications/mail.py), [template v1](../../apps/notification-service/notifications/templates/mail/v1/) |
| Identity contacts và kiểm phiên cho caller Notification | Đã triển khai; test provider qua | [contacts](../../apps/identity-service/accounts/views/notification_contacts.py), [service-key permission](../../apps/identity-service/accounts/permissions.py) |
| Work assignment event, transition bổ sung recipient, resolve đơn/lô | Đã triển khai; test provider/producer qua | [creation](../../apps/work-service/apps/tasks/services/creation.py), [mutations](../../apps/work-service/apps/tasks/services/mutations.py), [resolve](../../apps/work-service/apps/tasks/views/notification_resolution.py) |
| API in-app, count, trạng thái đọc, preferences | Đã triển khai; API local đã thử | [API](../../apps/notification-service/notifications/api.py), [auth](../../apps/notification-service/notifications/authentication.py) |
| Web, polling, cache theo tài khoản, tùy chọn email | Đã triển khai; build và test UI qua | [adapter](../../apps/web/src/features/notifications/api.ts), [hooks](../../apps/web/src/lib/query/studentFlowHooks.ts), [preferences](../../apps/web/src/features/notifications/components/NotificationPreferencesPanel.tsx) |
| Compose, migration gate, image discovery, gateway | Đã triển khai trong cấu hình; chưa deploy staging | [local](../../docker-compose.yml), [staging](../../docker-compose.staging.yml), [discovery](../../scripts/discover_services.py), [Nginx](../../infra/nginx/nginx.conf) |
| Notification từ Integration/AI, Web Push | Chưa triển khai trong Notification hiện tại | Consumer chỉ chấp nhận nguồn `identity` hoặc `work`; không tự subscribe nguồn mới |

Các sự kiện và quy tắc người nhận được giữ tại [tổng quan](README.md#luồng-và-quy-tắc-người-nhận),
không mở rộng phạm vi bằng danh sách ví dụ trong baseline.

## Hành vi cần giữ khi tiếp tục

- Inbox/DB Notification là nguồn bền vững. Beat giao task `dispatch` không có
  đối số qua Redis; worker đọc ID từ DB rồi xử lý inbox/email. Không đưa event,
  token hoặc nội dung đã giải mã vào broker job nội bộ.
- Kafka ACK/offset commit chỉ xác nhận đã bàn giao bền vững, không xác nhận
  đã tạo in-app hoặc gửi email. Offset mới dùng `earliest`; đổi group có thể
  đọc lại lịch sử còn retention.
- `accepted_by_smtp` chưa chứng minh thư tới Inbox. `delivery_unknown` không
  tự retry; xác minh trước replay thủ công. Identity đã bị dọn ciphertext
  phải phát event/token mới, không thể khôi phục bằng replay.
- Nội dung/target Work được resolve từ quyền và dữ liệu hiện tại khi đọc/gửi.
  Lỗi dependency không được biến thành cấp quyền hoặc trả nội dung cache cũ.
- Work tiếp tục sở hữu lịch nhắc hạn, task và comment; Notification không đọc
  DB domain khác. JWT/Bearer xác thực người dùng khác với service credential.
- Cờ nhận Identity, nhận Work và gửi email mặc định tắt độc lập; Web cần bật
  `notifications` trong `VITE_REAL_SERVICES` rồi build lại.

## Bằng chứng kiểm thử của lượt triển khai

| Kiểm tra | Kết quả đã ghi nhận | Giới hạn |
| --- | --- | --- |
| Backend Notification cuối lượt | 59 test qua trên PostgreSQL riêng; lint/format/check/migration drift qua | SMTP trong unit test dùng mock; tranh row lock/quota dùng PostgreSQL thật |
| Producer và internal provider | Các suite Identity/Work qua; đủ 8 schema kiểm trên outbox thật | Không phải smoke toàn bộ container domain qua Kafka/Gmail |
| Web | TypeScript/production build và các suite notification/student-flow qua | Chưa nghiệm thu UI bằng trình duyệt với domain backend thật |
| Hạ tầng | 182 test: 181 qua, 1 skip; fixture DB riêng chạy bổ sung qua | Không chứng minh staging đã triển khai |
| Runtime local | Kafka/PG/Redis/Celery/API/SMTP TLS thật qua [smoke script](../../scripts/smoke_notification_service.py) | Identity/Work HTTP là stub |
| Gmail | Ba thư riêng được SMTP Gmail ACK | Gọi SMTP trực tiếp; không đi qua Kafka/DB; Inbox/Spam người nhận chưa xác minh |

Container và database kiểm thử cô lập của lượt triển khai đã được dọn; image
kiểm tra được build với tag local `utask/notification-service:verification`.
Không coi tag này là image đã phát hành hoặc service đang chạy trên VPS.

## Điểm tiếp tục và tiêu chí nghiệm thu

1. Đội Identity/Work deploy provider đã có, cấu hình credential và xác minh
   contacts, session-status, resolve qua HTTP thật trên mạng backend.
2. Người vận hành chuẩn bị database/role, topic/ACL Kafka, Redis, key ring và
   Gmail; chạy migration trước API/worker/Beat/consumer theo [runbook](operations.md).
3. Nghiệm thu bằng user/task/comment thử: thao tác domain thật → outbox →
   Kafka → Notification DB → in-app/email, rồi kiểm quyền bị thu hồi và giao lại event.
4. Xác minh link activation/reset qua Gmail dùng được, hạn/địa chỉ đúng;
   không gửi thêm thư tới người nhận thử cũ khi chưa có yêu cầu mới.
5. Bật Web và kiểm danh sách/badge, mark-read, preferences, đổi tài khoản.
   Chỉ ghi staging đạt sau có bằng chứng image/config và luồng thực tế trên staging.

Giới hạn hiệu năng đã biết: feed/count vẫn duyệt các bản ghi ứng viên để lọc
quyền, gọi Work theo lô tối đa 100 mục; chưa benchmark lưu lượng lớn hoặc quota
Gmail dài hạn. GitNexus có cảnh báo rủi ro cao ở luồng Work dùng chung; review
và test regression đã chạy trong lượt triển khai, không dùng graph thay cho
source hoặc nghiệm thu runtime.
