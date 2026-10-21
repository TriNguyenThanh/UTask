# Hướng dẫn tích hợp Notification Service

Tài liệu này hướng dẫn các service phát sự kiện, Notification xử lý và Web đọc thông báo. Contract máy đọc được là nguồn chuẩn về cấu trúc: [API public và schema Notification](../../contracts/api/notification-service-v1.yaml), [API nội bộ](../../contracts/api/notification-internal-v1.yaml), [danh mục schema event](../../contracts/events/README.md). Tài liệu vận hành về biến môi trường, lệnh và rollout nằm tại [operations.md](operations.md); không lặp cấu hình triển khai ở đây.

## Hiện trạng và phạm vi

| Phần | Trạng thái | Bằng chứng / giới hạn |
| --- | --- | --- |
| Consumer Identity và Work, kiểm schema, inbox chống trùng và quarantine | Đã triển khai | `notifications/services.py`, `management/commands/consume_notifications.py`; smoke local được ghi tại [verification.md](verification.md). |
| Resolve quyền hiện tại qua Identity/Work, in-app, preference email, API public | Đã triển khai | Client và API trong `notifications/`; endpoint domain trong Identity và Work. |
| Producer outbox cho ba event mail Identity và năm event Work | Đã triển khai | Schema chuẩn tại `contracts/events/`; contract tests producer trong từng service. |
| Web Notification với API thật | Đã triển khai | Bật bằng `notifications` trong `VITE_REAL_SERVICES`; polling khi tab hiển thị. |
| Toàn tuyến Kafka qua service thật đến Gmail, staging/VPS | Chưa xác minh | Smoke dùng HTTP stub cho Identity/Work; Gmail đã ACK ba thư gửi SMTP trực tiếp, không đi qua Kafka/Notification. Không xem là nghiệm thu toàn tuyến. |
| Producer/consumer cho service hoặc loại event mới ngoài Identity/Work | Chưa triển khai | Consumer chỉ nhận `--source identity|work`; không tự nhận topic/service mới. Cần triển khai có chủ đích theo checklist bên dưới. |

Quy trình xử lý hiện tại: producer ghi outbox cùng transaction nghiệp vụ; publisher chuyển event lên topic; consumer validate và lưu inbox/quarantine rồi commit Kafka offset. Beat mỗi 5 giây gọi dispatcher không kèm tham số; dispatcher đọc các inbox/delivery ID từ PostgreSQL và xử lý trực tiếp trong task. Redis/Celery là cơ chế job nội bộ, không phải nơi giữ payload event hay token.

## Trách nhiệm theo service

| Thành phần | Trách nhiệm |
| --- | --- |
| Identity | Sở hữu tài khoản, trạng thái và địa chỉ liên hệ; phát event mail qua outbox. Cung cấp danh bạ notification và endpoint kiểm phiên. Không giao Notification quyền đọc database Identity. |
| Work | Sở hữu Project, Task, Comment và quyền thành viên; phát event nghiệp vụ qua outbox và trả kết quả resolve theo quyền/trạng thái hiện tại. Không giao Notification quyền đọc database Work. |
| Notification | Sở hữu inbox, notification, preference email và delivery; validate event theo schema, chống trùng, gọi resolver trước khi hiển thị/gửi, quản lý API và gửi mail. Không trở thành nguồn sự thật cho domain. |
| Web | Gọi API public bằng phiên người dùng; hiển thị danh sách/badge, đánh dấu đọc và cập nhật preference. Không gọi API nội bộ bằng service token. |
| Service tương lai | Chỉ phát dữ liệu nghiệp vụ do service sở hữu. Cần đăng ký topic/consumer và hợp đồng cụ thể; không giả định Notification tự consume mọi topic. |

Integration Service là service duy nhất gọi GitHub API. Notification không gọi GitHub, không suy ra event GitHub/AI từ schema hiện có.

## Kafka và envelope

Cấu hình hiện tại dùng topic `utask.identity.events` và `utask.work.events`; consumer group mặc định lần lượt là `notification-identity-v1` và `notification-work-v1`. Đây là tên mặc định, không phải danh sách topic tự khám phá. Trong container,
settings đọc `KAFKA_IDENTITY_TOPIC`, `KAFKA_WORK_TOPIC`,
`NOTIFICATION_IDENTITY_KAFKA_GROUP`, `NOTIFICATION_WORK_KAFKA_GROUP`. Khi dùng
Compose, root `.env` đặt `IDENTITY_KAFKA_TOPIC` và `WORK_KAFKA_TOPIC`; mapping
`infra/env/notification-service.env` chuyển sang hai tên topic runtime trên. Offset chỉ commit sau khi event được bàn giao bền vững; lỗi gửi mail không giữ
Kafka offset lại. Event hợp lệ ngoài allowlist hiện được bỏ qua, không tạo
notification; event sai schema/version được cách ly bằng metadata/fingerprint,
không lưu raw payload không tin cậy.

Envelope Work có các trường chuẩn như `event_id`, `event_type`, `event_version`, `aggregate_id`, `occurred_at`, `trace_id`, `producer`, `project_id`, `entity_version`, `project_sequence`, `data`. Ví dụ hợp lệ theo schema `task.assigned` (mọi UUID dưới đây là giá trị giả cố định):

```json
{
  "event_id": "11111111-1111-4111-8111-111111111111",
  "event_type": "task.assigned",
  "event_version": 1,
  "aggregate_id": "22222222-2222-4222-8222-222222222222",
  "occurred_at": "2026-10-20T09:30:00Z",
  "trace_id": "33333333-3333-4333-8333-333333333333",
  "producer": "work-service",
  "project_id": "44444444-4444-4444-8444-444444444444",
  "entity_version": 7,
  "project_sequence": 18,
  "data": {
    "task_id": "22222222-2222-4222-8222-222222222222",
    "actor_user_id": "55555555-5555-4555-8555-555555555555",
    "recipient_ids": ["66666666-6666-4666-8666-666666666666"]
  }
}
```

Đây là event domain; nó không phải request kiểm phiên. Identity mail cũng dùng envelope Kafka riêng, còn `data.secret` là ciphertext có hạn dùng, không phải bearer/session token. Ví dụ rút gọn dưới đây thể hiện hình dạng; giá trị base64 giả không dùng được để giải mã:

```json
{
  "event_id": "77777777-7777-4777-8777-777777777777",
  "event_type": "identity.activation.requested",
  "event_version": 1,
  "aggregate_id": "66666666-6666-4666-8666-666666666666",
  "occurred_at": "2026-10-20T09:30:00Z",
  "trace_id": "88888888-8888-4888-8888-888888888888",
  "producer": "identity-service",
  "aggregate_type": "user",
  "data": {
    "user_id": "66666666-6666-4666-8666-666666666666",
    "email": "user@example.test",
    "expires_at": "2026-10-20T10:30:00Z",
    "secret": {
      "key_id": "mail-key-v1",
      "expires_at": "2026-10-20T10:30:00Z",
      "nonce": "AAAAAAAAAAAAAAAA",
      "ciphertext": "AAAAAAAAAAAAAAAAAAAAAA=="
    }
  }
}
```

`contracts/events/README.md` liên kết schema chuẩn cho cả tám event hiện được nhận. Không sửa bản schema đóng gói trong Notification thay cho contract chuẩn, và không thêm schema giả cho event chưa được chốt.

## API nội bộ Identity và Work

Cả hai API nội bộ chỉ dành cho mạng backend. Request Notification gọi chúng bằng `X-Service-Token: <NOTIFICATION_SERVICE_TOKEN>`; Identity và Work cùng kiểm token này qua `NOTIFICATION_SERVICE_TOKEN`. Giới hạn danh sách user và batch là 100 phần tử. User không tồn tại/đã xóa có thể bị lược khỏi kết quả contacts; resolver Work trả `eligible: false` nếu không còn quyền hoặc event không còn đúng. Lỗi phụ thuộc khiến Notification fail closed và API public không trả nội dung chưa xác minh.

Lấy liên hệ hiện hành từ Identity:

```http
POST /api/v1/internal/users/notification-contacts
X-Service-Token: <NOTIFICATION_SERVICE_TOKEN>
Content-Type: application/json
```

```json
{"user_ids":["66666666-6666-4666-8666-666666666666"]}
```

```json
{"users":[{"user_id":"66666666-6666-4666-8666-666666666666","email":"user@example.test","display_name":"Nguyen An","account_status":"ACTIVE"}]}
```

Resolve một thông báo Work:

```http
POST /api/v1/internal/notifications/resolve
X-Service-Token: <NOTIFICATION_SERVICE_TOKEN>
Content-Type: application/json
```

```json
{"user_id":"66666666-6666-4666-8666-666666666666","event_type":"task.assigned","project_id":"44444444-4444-4444-8444-444444444444","data":{"task_id":"22222222-2222-4222-8222-222222222222","actor_user_id":"55555555-5555-4555-8555-555555555555","recipient_ids":["66666666-6666-4666-8666-666666666666"]}}
```

```json
{"eligible":true,"title":"Bạn được giao công việc","body":"UT-18: Chuẩn bị bản phát hành","target":{"kind":"board-issue","projectId":"44444444-4444-4444-8444-444444444444","issueKey":"UT-18"}}
```

Resolve batch giữ nguyên thứ tự từng item, tối đa 100:

```json
{"items":[{"user_id":"66666666-6666-4666-8666-666666666666","event_type":"task.assigned","project_id":"44444444-4444-4444-8444-444444444444","data":{"task_id":"22222222-2222-4222-8222-222222222222","actor_user_id":"55555555-5555-4555-8555-555555555555","recipient_ids":["66666666-6666-4666-8666-666666666666"]}}]}
```

```json
{"results":[{"eligible":true,"title":"Bạn được giao công việc","body":"UT-18: Chuẩn bị bản phát hành","target":{"kind":"board-issue","projectId":"44444444-4444-4444-8444-444444444444","issueKey":"UT-18"}}]}
```

Header `X-Service-Key` phục vụ endpoint Identity kiểm phiên ở `/api/v1/internal/auth/session-status`; request đó dùng Bearer JWT người dùng và `IDENTITY_NOTIFICATION_SERVICE_KEY`. Giá trị dedicated này không lấy từ `IDENTITY_SERVICE_KEYS` cho caller Notification. Không tráo `X-Service-Key` với `X-Service-Token`.

## API public và Web

Web dùng prefix `/api/notifications/`, Bearer phiên người dùng: `GET /` trả 25 mục/trang và nhận `page`, `read=true|false`; `GET /unread-count`, `POST /{notification_id}/read`, `POST /read-all`, `GET/PATCH /preferences` là các thao tác còn lại. Chi tiết request/response và schema theo [OpenAPI public](../../contracts/api/notification-service-v1.yaml). API xác minh phiên với Identity và kiểm quyền Work trước khi trả nội dung; khi không gọi được dependency thì trả lỗi thay vì nội dung cũ.

Để Web dùng API thật, thêm `notifications` vào danh sách phân tách dấu phẩy `VITE_REAL_SERVICES` rồi build lại ứng dụng. Danh sách và unread count polling mỗi 30 giây khi tab hiển thị; dừng polling nền. UI hỗ trợ badge, danh sách, đánh dấu đọc và preference. Không có WebSocket/SSE.

## Thêm service hoặc event mới

Trước khi triển khai, chốt chủ sở hữu dữ liệu, ý nghĩa người nhận, quyền hiện hành, retention và schema/version. Với mỗi event mới cần hoàn tất đồng bộ:

1. Producer ghi outbox cùng transaction thay đổi nghiệp vụ, phát envelope theo quy ước service và có test producer/outbox.
2. Đặt schema chuẩn trong `contracts/events/` sau khi contract được chốt; cập nhật kiểm tra schema Notification và adapter xử lý event.
3. Cung cấp resolver/domain endpoint để xác minh quyền và dữ liệu hiện tại; không để Notification đọc database service khác. Bổ sung contract, integration và failure tests.
4. Thêm cấu hình topic, ACL, consumer source/group riêng và cờ bật/tắt rõ ràng; sửa lệnh/điểm khởi chạy consumer có chủ đích. Hiện `consume_notifications --source` chỉ chấp nhận `identity` hoặc `work`, không có wildcard tự khám phá topic.
5. Cập nhật runbook, tài liệu trạng thái, Web nếu contract public thay đổi; rollout producer và resolver đã deploy/kiểm tra trước khi bật consumer tương ứng.

Nếu event mới cần đổi ranh giới service, quyền dữ liệu hoặc luồng đồng bộ/bất đồng bộ, phải có quyết định kiến trúc trong tài liệu/ADR hiện hành trước khi coi là mục tiêu triển khai.

## Credential database hiện hành

Notification dùng `POSTGRES_USER`/`POSTGRES_PASSWORD` chung từ `database.env`,
như Identity/Work/Classroom; database nghiệp vụ vẫn tách bằng
`NOTIFICATION_DB_NAME` → `DATABASE_NAME`. Không cung cấp hoặc kiểm tra
`NOTIFICATION_DB_USER`/`NOTIFICATION_DB_PASSWORD` riêng. Cấu hình này theo yêu
cầu đơn giản hóa hiện tại; không suy ra đã tách quyền PostgreSQL theo service.
Chạy Python ngoài Compose dùng `DATABASE_NAME` và `POSTGRES_*` tương tự Work.

## Triển khai theo thứ tự

1. Chuẩn bị contract/schema, outbox và resolver; kiểm tra ACL/topic, network backend và cấu hình secrets theo [runbook](operations.md).
2. Deploy provider Identity/Work có endpoint tương thích trước, rồi migration và các process Notification theo runbook. Giữ các cờ nhận event tắt.
3. Kiểm tra health, dependency và producer/outbox. Bật cờ consumer Identity hoặc Work tương ứng sau khi producer, topic và resolver đã sẵn sàng; bật email riêng theo kế hoạch vận hành.
4. Thêm `notifications` vào `VITE_REAL_SERVICES` sau khi API public sẵn sàng, giữ các service đang bật, ví dụ `auth,classroom,work,notifications`; build/deploy lại Web.
5. Theo dõi lag, inbox/delivery status và lỗi resolver. Nghiệm thu Gmail hoặc staging riêng theo [verification.md](verification.md); SMTP ACK riêng không chứng minh thư tới inbox hay toàn tuyến đã đạt.

Lệnh khởi động, migrations, biến môi trường đầy đủ, cấu hình broker/SMTP và replay được duy trì duy nhất trong [operations.md](operations.md).
