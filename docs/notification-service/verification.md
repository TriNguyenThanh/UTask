# Kiểm chứng Notification — 22/10/2026

## Đã xác minh

- Docker image build được; migration chạy thành công trong container bằng role
  Notification riêng trên PostgreSQL kiểm thử.
- Bootstrap database chạy lặp an toàn. Role không có superuser/createdb/
  createrole/replication/bypassrls và bị từ chối kết nối Work DB.
- Test backend chạy PostgreSQL thật: dedupe, collision, savepoint rollback,
  tranh lease/quota, expiry, template, SMTP classification, API và quyền.
- Test producer validate đủ 8 schema bằng envelope thực từ outbox Identity/Work;
  đường manual/AI, transition đơn/lô, deadline, mention và teacher feedback có
  kiểm tra tương ứng.
- Web qua TypeScript/production build; test danh sách, badge, mark read/all,
  preferences, phân trang, polling/visibility/unmount và đổi tài khoản qua.
- Bộ hạ tầng gồm 182 test: 181 qua, một test cần fixture PostgreSQL riêng bị
  skip khi chạy mặc định; test fixture này được chạy riêng và qua PostgreSQL thật.
- Hai OpenAPI mới validate được; schema runtime so khớp schema chuẩn. Link nội
  bộ và file rỗng trong tài liệu thay đổi được kiểm tra.

## Smoke runtime local

Chạy [script](../../scripts/smoke_notification_service.py) với Kafka,
PostgreSQL, Redis, Celery worker/Beat, API Gunicorn và SMTP STARTTLS thật.
Chứng chỉ SMTP fixture được xác minh qua CA tạm; không tắt kiểm tra TLS.

Kết quả: Identity mail accepted; duplicate không gửi thêm; mail hết hạn không
gửi; mất phản hồi sau DATA chuyển `delivery_unknown` và không tự retry; Work
assignment tạo in-app/email; mark-read hoạt động; Work thu hồi eligibility thì
feed ẩn nội dung; event lỗi được cách ly trước commit Kafka.

**Giới hạn:** Identity/Work HTTP trong phép thử này là stub. Quyền và producer
thật được kiểm riêng qua integration test PostgreSQL, chưa có smoke ghép tất
cả container domain service. Không coi SMTP fixture là kết quả Gmail.

## Gmail thật

Người dùng cho phép gửi ba thư riêng có tiêu đề và nội dung `đi ngủ đi`.
Sau khi cập nhật username thành Gmail đầy đủ, SMTP Gmail trả ACK nhận thành
công cho cả ba người nhận. Credential đọc từ môi trường, không đưa vào source
hoặc log. Thử này gọi SMTP trực tiếp với cùng cấu hình STARTTLS để kiểm chứng
kết nối/quyền gửi; không phải toàn tuyến Kafka → Gmail và không tạo notification
nghiệp vụ trong database.

**Chưa xác minh:** thư đã tới Inbox/Spam phía người nhận; link kích hoạt/reset
Identity qua Gmail; staging/VPS; throughput/quota thực tế dài hạn. Không gửi
thêm thư để kiểm tra lại khi chưa có yêu cầu mới.
