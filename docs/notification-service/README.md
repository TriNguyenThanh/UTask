# Notification Service

**Trạng thái: Đã triển khai và smoke runtime local đạt; SMTP Gmail thật đã ACK thư thử. Staging và luồng nghiệp vụ đầy đủ qua Gmail chưa nghiệm thu.**
Service Django/DRF sở hữu inbox Kafka, thông báo in-app, tùy chọn email và trạng
thái giao thư trong PostgreSQL riêng. Redis/Celery chuyển job nội bộ; Kafka
chỉ truyền sự kiện giữa service. GitHub/AI và Web Push chưa thuộc phạm vi này.

Notification dùng database riêng `notification_db` và credential `POSTGRES_*`
chung như Identity/Work/Classroom theo yêu cầu cấu hình hiện tại. Không còn
kiểm tra hoặc tạo role riêng từ `NOTIFICATION_DB_USER`/`NOTIFICATION_DB_PASSWORD`.
Chi tiết tại [vận hành](operations.md).

## Tài liệu bàn giao

- [Checkpoint 22/10/2026](checkpoint-2026-10-22.md): hiện trạng, bằng chứng và phần việc tiếp tục.
- [Triển khai và tích hợp cho các service](implementation.md): trách nhiệm Identity/Work/Web, hợp đồng và cách thêm nguồn thông báo.
- [Vận hành](operations.md): cấu hình môi trường, rollout, theo dõi và replay.
- [Kiểm chứng](verification.md): phân biệt test, runtime local, Gmail và staging.

## Luồng và quy tắc người nhận

```text
Identity/Work DB + outbox → Kafka → consumer Notification → inbox PostgreSQL
  → Beat mỗi 5 giây → Redis → worker Notification
    → xác minh người nhận qua Identity/Work → in-app hoặc Gmail STARTTLS
Web → Nginx /api/notifications/ → API Notification → xác minh quyền qua Work
```

| Sự kiện | Người nhận | Kênh mặc định |
| --- | --- | --- |
| `identity.activation.requested`, `identity.student.imported`, `identity.password_reset.requested` | User của sự kiện, địa chỉ hiện tại phải khớp mail trong sự kiện | Email bắt buộc |
| `task.assigned` | Người mới được giao task, trừ actor | Email + in-app |
| `task.deadline.reminder` | Người phụ trách còn hoạt động, hạn/revision còn đúng, task chưa kết thúc | Email + in-app |
| `comment.mentions.added` | Người còn được nhắc trong bình luận, trừ tác giả | Email + in-app |
| `teacher.feedback.added` | Thành viên project còn quyền, trừ tác giả | Email + in-app |
| `task.transitioned` | Người phụ trách còn quyền, trừ actor; trạng thái hiện tại còn khớp | In-app |

Không tạo thêm thông báo từ `comment.created`. Work tiếp tục sở hữu lịch quét
hạn và dữ liệu Task/Comment; Notification không đọc database Work/Identity.
Thông báo đã mất quyền hoặc không còn áp dụng được ẩn khỏi danh sách và count.
Không xác minh được dịch vụ phụ thuộc thì API trả lỗi, không trả nội dung cũ.

## Hợp đồng

- [API public](../../contracts/api/notification-service-v1.yaml): Bearer RS256,
  kiểm phiên qua Identity; danh sách 25 mục/trang, lọc `read=true|false`, count,
  đánh dấu đọc và tùy chọn `assignment`, `deadline`, `mention`, `feedback`.
- [API nội bộ](../../contracts/api/notification-internal-v1.yaml): contacts
  Identity tối đa 100 UUID; resolve Work đơn/lô tối đa 100 mục. Resolve trả
  dữ liệu hiện tại và không cấp quyền cho service/client khác.
- [Schema Kafka](../../contracts/events/README.md): giữ envelope `data` của
  producer. Notification đóng gói bản sao schema trong image; test đối chiếu
  với contract chuẩn để tránh lệch.
- [Mã nguồn](../../apps/notification-service/): API, consumer, worker và Beat
  dùng chung image. Consumer group Identity/Work riêng, offset commit đồng bộ
  sau lưu inbox hoặc cách ly bền vững; không chờ SMTP mới commit Kafka.

UI hiện có dùng API thật khi thêm `notifications` vào `VITE_REAL_SERVICES`;
phải build lại Web sau đổi biến Vite. Poll mỗi 30 giây khi tab hiển thị, cache
phân biệt tài khoản và hủy request cũ khi đổi user. Chưa có WebSocket/SSE.

## Tin cậy và bảo vệ dữ liệu

Inbox chống trùng bằng nguồn/event ID và fingerprint. Cùng ID khác nội dung
bị cách ly. Worker claim có lease/version token; retry lỗi tạm thời tối đa 5
lần với backoff. Dispatcher giao lại job khi Redis hoặc worker lỗi. Task dispatcher qua Redis không có đối số; worker đọc ID từ DB, không đưa
token mail vào broker. Quota gửi theo ngày được khóa trong DB;
reservation của kết quả không rõ được giữ bảo thủ để tránh vượt giới hạn.

Email Identity giải mã AES-GCM ngay trước gửi, AAD khớp producer, key ring theo
`key_id`. Không ghi token/body giải mã vào DB, Redis, log hoặc CLI. Template
text/HTML version hóa cùng source. Mail hết hạn không gửi; ciphertext được dọn
sau trạng thái cuối hoặc hết hạn. Link lấy từ frontend origin cấu hình, không
lấy URL tùy ý từ event. Giữ khóa cũ trong key ring cho đến khi các mail còn hiệu
lực dùng khóa đó đã kết thúc.

`accepted_by_smtp` nghĩa là SMTP đã xác nhận nhận thư, chưa chứng minh thư tới
inbox. Mất kết nối sau khi bắt đầu DATA hoặc worker chết trong khoảng này dẫn
đến `delivery_unknown`, không tự gửi lại. `Message-ID` ổn định phục vụ điều tra,
không bảo đảm SMTP gửi đúng một lần. Xem [vận hành](operations.md).

Thông báo và fingerprint chống trùng giữ 90 ngày. Payload lỗi được dọn sau 7
ngày; không giữ token để tiện replay. Tùy chọn email không chặn mail tài khoản.

## Kiểm chứng

Unit/integration test thuộc service; test producer và quyền nằm tại Identity/
Work. [Smoke runtime](../../scripts/smoke_notification_service.py) chạy Kafka,
PostgreSQL, Redis, Celery, API và SMTP STARTTLS thật trong môi trường kiểm thử;
Identity/Work HTTP là stub, không thay nghiệm thu hai domain service thật.
SMTP Gmail thật đã xác nhận nhận ba thư thử được người dùng cho phép; chưa xác
minh thư tới Inbox hay link Identity qua Gmail. Xem
[kết quả kiểm chứng](verification.md) và [runbook](operations.md).
