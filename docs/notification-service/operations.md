# Vận hành Notification

## Cấu hình và khởi động

Dùng các biến mẫu trong [`.env.example`](../../.env.example); không commit secret.
Đặt `NOTIFICATION_DB_NAME` và `NOTIFICATION_DJANGO_SECRET_KEY`. Notification
nhận `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_USER`, `POSTGRES_PASSWORD`
từ `infra/env/database.env`, giống Identity/Work/Classroom; tên database được
mapping thành `DATABASE_NAME` trong container. Không dùng
`NOTIFICATION_DB_USER`/`NOTIFICATION_DB_PASSWORD`; các dòng cũ trong `.env`
có thể xóa vì không còn được đọc.

Bootstrap chỉ tạo database còn thiếu, không tạo role riêng, đổi owner hoặc
thu hồi quyền theo Notification. Không còn điều kiện bắt username Notification
khác tài khoản PostgreSQL chung, kể cả khi các biến legacy vẫn tồn tại.
Volume đã từng tạo role/ACL theo cấu hình trước được giữ nguyên; thay đổi này
không xóa dữ liệu, role hoặc tự phục hồi grant. Không cần xóa volume để cập nhật.

`NOTIFICATION_SERVICE_TOKEN` khớp giữa Notification, Work và Identity.
`IDENTITY_NOTIFICATION_SERVICE_KEY` khớp giữa Notification và Identity, dùng
riêng cho kiểm phiên qua `X-Service-Key`. Caller `notification` đọc setting
riêng này, không lấy key từ mapping `IDENTITY_SERVICE_KEYS`.
Hai key trên là credential dịch vụ, không dùng làm Bearer hoặc chuyển cho Web.
Production yêu cầu Django secret và cả hai key có ít nhất 32 ký tự ASCII,
không có khoảng trắng đầu/cuối, kể cả khi consumer/email đang tắt. Hai API nội bộ chỉ gọi trên
mạng backend; gateway đã chặn đường `/api/v1/internal` của Work và Identity.

Điền `NOTIFICATION_MAIL_KEYS` là JSON mapping `key_id` → base64 khóa AES-256,
khớp `IDENTITY_MAIL_KEY_ID`/`IDENTITY_MAIL_KEY`. `NOTIFICATION_FRONTEND_URL` phải
là frontend thật, cùng origin đã cấu hình cho luồng kích hoạt/reset Identity.

Gmail dùng `NOTIFICATION_SMTP_HOST=smtp.gmail.com`, port `587`, STARTTLS và
`NOTIFICATION_SMTP_USERNAME`, `NOTIFICATION_SMTP_PASSWORD` (App Password),
`NOTIFICATION_FROM_EMAIL`. Tài khoản phải bật xác minh hai bước và cho phép
App Password. `NOTIFICATION_SMTP_USERNAME` phải là địa chỉ Gmail đầy đủ, không
chỉ tên trước dấu `@`. Không dùng mật khẩu đăng nhập Google thông thường.
[Thiết lập Google](https://support.google.com/mail/answer/185833).
Với host `smtp.gmail.com`, service bỏ dấu cách ASCII giữa các nhóm App Password;
password SMTP host khác được giữ nguyên. Không cần ghi secret vào tài liệu.
Quota `NOTIFICATION_EMAILS_PER_DAY` mặc định 100 là giới hạn vận hành bảo thủ,
không phải quota Google; chọn theo loại tài khoản và lưu lượng thực tế.

Kafka dùng `KAFKA_*` chung, `IDENTITY_KAFKA_TOPIC`, `WORK_KAFKA_TOPIC` và các
nhóm `NOTIFICATION_IDENTITY_KAFKA_GROUP`, `NOTIFICATION_WORK_KAFKA_GROUP`.
Chuẩn bị topic/ACL trên Kafka ngoài; broker local đã có topic Identity/Work.
Không đổi group tùy ý vì có thể đọc lại lịch sử còn trong retention.

```bash
docker compose --profile notification-service up -d --build
```

Migration chạy trước API/worker/Beat/consumer. `healthz` kiểm kết nối DB;
healthcheck consumer/Beat chỉ kiểm process, không chứng minh đã gửi thư.
Staging dùng cùng profile với `docker-compose.staging.yml` và image release;
CI/release discovery tự nhận service từ manifest, không cần matrix viết tay.

Mặc định ba cờ đều tắt. Bật lần lượt, khởi động lại process sau đổi cấu hình:

1. `NOTIFICATION_IDENTITY_ENABLED=true`: nhận mail Identity, kiểm inbox/expiry.
2. `NOTIFICATION_EMAIL_ENABLED=true`: kiểm thư tới mailbox thử và kết quả SMTP.
3. `NOTIFICATION_WORK_ENABLED=true`: nghiệm thu assignment/mention/deadline/feedback.
4. Thêm `notifications` vào `VITE_REAL_SERVICES`, build/deploy Web, kiểm badge/list.

Tắt `NOTIFICATION_EMAIL_ENABLED` dừng gửi mới, vẫn nhận/lưu sự kiện và in-app;
SMTP đang thực hiện có thể hoàn tất. Khi bật lại, mail quá hạn vẫn bị bỏ qua.
Không bật nhận lịch sử Identity để gửi hàng loạt trước kiểm tra expiry/quota.

## Điều tra và replay

Chạy `docker compose exec notification-service python manage.py notification_status`
để xem số lượng theo trạng thái và thời điểm pending lâu nhất, không xuất payload.
Theo dõi Kafka consumer lag, tuổi inbox/job pending, `failed`, `expired`,
`delivery_unknown`, retry và quota. Dùng status/counter, không xuất envelope
hoặc nội dung mail ra log. Log lỗi chỉ giữ mã phân loại, không giữ SMTP password.

```bash
docker compose exec notification-service python manage.py replay_notifications <inbox-id>
docker compose exec notification-service python manage.py replay_notifications <delivery-id> --email
```

Replay đi qua validation, quyền hiện tại và quota; chỉ áp dụng bản ghi lỗi còn
payload và còn trong thời hạn lưu. Với `delivery_unknown`, xác minh provider/
mailbox trước; `--confirm-unknown` là thao tác thủ công chấp nhận rủi ro gửi trùng,
không phải bước phục hồi tự động. Mail Identity đã bị dọn ciphertext hoặc hết
hạn phải được yêu cầu phát lại từ Identity để có event/token mới; không phục hồi
secret bằng chỉnh DB. Không replay trạng thái đã SMTP accept.

Không sửa event ID hoặc ghi trực tiếp DB để bỏ qua chống trùng. Bản ghi sai
schema/quarantine không tự replay vì không lưu payload không tin cậy; sửa
producer và phát sự kiện hợp lệ theo nghiệp vụ.

## Nghiệm thu

Chạy formatter/lint, pytest và `makemigrations --check --dry-run` bằng uv trong
service. Chỉ dùng database test riêng. Smoke runtime cần Kafka, Redis và
PostgreSQL kiểm thử riêng; script từ chối tên DB không kết thúc `_smoke_test`:

```bash
NOTIFICATION_SMOKE_DB_NAME=notification_smoke_test \
NOTIFICATION_SMOKE_DB_PASSWORD='<test-only-password>' \
apps/notification-service/.venv/bin/python scripts/smoke_notification_service.py
```

Port mặc định: PostgreSQL 55447, Redis 56387, Kafka 55449; cấu hình lại qua
`NOTIFICATION_SMOKE_DB_*`, `NOTIFICATION_SMOKE_REDIS`, `NOTIFICATION_SMOKE_KAFKA`.
Script tạo topic ngẫu nhiên và process tạm, không gửi Gmail. Cần tạo DB rỗng
trước mỗi lần chạy. SMTP fixture cấp chứng chỉ TLS tạm, không tắt xác minh TLS.

Gmail thật: gửi một yêu cầu reset/kích hoạt tới user kiểm thử, xác nhận người
nhận, link đúng frontend, token dùng được và không gửi lại khi Kafka giao trùng.
Ghi kết quả Gmail/staging riêng; SMTP fixture không chứng minh khả năng gửi Gmail.
