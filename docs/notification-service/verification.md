# Kiểm chứng Notification — 22/10/2026

Các kết quả role riêng dưới đây là lịch sử lượt triển khai ban đầu. Sau yêu
cầu đổi sang credential PostgreSQL chung, cấu hình hiện hành được ghi tại
[operations](operations.md); không suy ra credential riêng vẫn còn được dùng.

## Kiểm tra sau khi dùng credential chung

- 61 test backend chạy qua trên PostgreSQL riêng cho kiểm thử, gồm cấu hình
  `DATABASE_NAME`/`POSTGRES_*` và trường hợp biến credential Notification cũ
  còn tồn tại nhưng không được dùng.
- 182 test hạ tầng qua; Compose local/staging cấp cùng credential PostgreSQL
  cho toàn bộ process Notification, vẫn chọn database Notification riêng.
- Bootstrap đã chạy trên PostgreSQL thật với username legacy trùng tài khoản
  chung; không còn lỗi khác username và không tạo role/ACL Notification.
- Smoke runtime Kafka/PostgreSQL/Redis/Celery/API/SMTP STARTTLS đã chạy lại
  thành công với credential chung; Identity/Work HTTP vẫn là stub. Image
  `utask/notification-service:shared-credentials-check` build thành công.

## Đã xác minh trong lượt triển khai ban đầu

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

## Nghiệm thu tích hợp sau bàn giao ngày 22/10/2026

**Đã triển khai và kiểm chứng toàn tuyến local với Identity/Work thật.**
Kiểm trên `dev` nền `bb9c258`, gồm thay đổi worktree chưa commit. Giữ nguyên
chính sách tạm đăng ký/import và `.env`/`.env.staging`. Notification tiếp tục
dùng `DATABASE_NAME`/`POSTGRES_*` theo PR #76, không thêm credential riêng.

[Smoke domain](../../scripts/smoke_notification_domains.py) đã qua ở project
`utask-notification-smoke-6c71843308`: API Identity/Work thật → outbox → Kafka
→ inbox Notification → Celery/Redis → SMTP STARTTLS và API public qua Nginx.
Không dùng HTTP stub cho Identity hoặc Work. SMTP là mailbox kiểm thử cô lập,
có xác minh TLS, không gửi người nhận thật.

- Đăng ký vẫn ACTIVE/verified và không gửi mail kích hoạt; import vẫn ACTIVE,
  dùng email chuẩn hóa làm mật khẩu ban đầu và không phát mail kích hoạt.
- Giao việc tạo in-app/email; nhắc tên, nhắc hạn, chuyển trạng thái và tùy
  chọn email hoạt động. Mark-read/read-all và unread count đạt.
- Giao lại event không tạo thêm notification/email. Thu hồi membership khiến
  feed ẩn thông báo qua resolver Work thật.
- Đọc link reset từ nội dung thư text thực tế, confirm thành công, đăng nhập
  bằng mật khẩu mới được và phiên cũ trả 401. Link kích hoạt tài khoản pending
  cũ đọc từ thư cũng confirm và đăng nhập được.
- API gateway chặn đường nội bộ, kiểm auth/validation đạt.

Hai lỗi phát hiện và đã sửa: template text escape `&` thành `&amp;` làm hỏng
query link reset; consumer chạy trước khi Kafka local chuẩn bị topic xong.
Text template giữ URL nguyên vẹn, HTML vẫn escape. Consumer chờ Kafka healthy
khi profile local bật; Kafka ngoài không phụ thuộc container broker local.

Kiểm tra bổ sung:

- Notification: 66 test PostgreSQL qua sau pull; sau bổ sung regression link
  text, 66 test SQLite qua và một test khóa PostgreSQL bỏ qua. Smoke thật xác
  minh bản sửa template với thư nhận thực tế.
- Identity: 83 test PostgreSQL qua cho contacts, OpenAPI, provisioning và
  registration; thêm 15 test unit mail qua. Có một cảnh báo deprecated của
  allauth/dj-rest-auth, không có test lỗi.
- Work: 61 test PostgreSQL qua cho resolver, collaboration, deadline và
  project collaboration; bao gồm producer/AI apply, feedback và rollback.
- Web: 14 test Notification API, badge và service configuration qua;
  TypeScript qua. Chưa nghiệm thu tương tác trình duyệt với backend thật.
- Compose/smoke helpers/local startup/Kafka profile: 23 test, 20 qua và ba
  trường hợp Kafka cần môi trường riêng bỏ qua. Service discovery qua.
  Windows cần UTF-8 và
  shim `python3` tạm cho shell fixture; không sửa cấu hình máy.

Người dùng cho phép tạm dừng cụm `utask-staging-local-20261021` để kiểm thử.
Đã khởi động lại đúng 20 container sau lượt thử. Project smoke và các project
thử lỗi trước đó đã được dọn; không xóa volume/cấu hình của cụm phát triển.

**Chưa xác minh:** gửi Gmail toàn tuyến, Inbox/Spam, staging/VPS và tải lớn.
Project/membership có sẵn và tài khoản pending cũ là fixture của service sở
hữu. Teacher feedback/AI apply và event import lịch sử có test producer/provider
riêng, không khẳng định đã smoke toàn tuyến các đường đó. Phạm vi hiện tại
không thêm thông báo Integration/AI, Web Push hoặc thay chính sách tạm.

GitNexus đã chạy impact và detect-changes. Báo cáo toàn worktree trả CRITICAL
và 634 flow vì chứa cạnh tài liệu/quy tắc dùng chung cùng thay đổi AGENTS có
sẵn; không coi đó là bản đồ chính xác phạm vi nghiệp vụ hoặc kết quả an toàn.
Một số symbol mới không phân giải được và đã đối chiếu source/callers trực
tiếp. Bằng chứng nghiệp vụ ở trên đến từ test và smoke thật, không từ graph.

## Gmail gửi tới người nhận được xác nhận

Ngày 22/10/2026, người dùng xác nhận gửi tới địa chỉ Gmail người nhận thử
nghiệm (đã ẩn khỏi tài liệu theo quy tắc bảo mật). Dùng cụm thử riêng
`utask-notification-smoke-52a449fafc`, giữ nguyên `.env.staging`; đọc SMTP
credential hiện có nhưng không đưa vào log hoặc báo cáo.

Gmail SMTP chấp nhận bảy thư: giao việc, nhắc tên, hai thư nhắc hạn cho hai
task khác nhau, nhận xét giảng viên, reset mật khẩu và kích hoạt tài khoản
pending cũ. Bản ghi trạng thái, Message-ID và thời điểm lưu cục bộ tại
`gmail-delivery-evidence-20261022.json` (đã loại khỏi Git theo `.gitignore`).

Luồng qua Work/Identity → outbox → Kafka → Notification → Gmail STARTTLS.
Nhận xét giảng viên dùng Work domain command thật với proof Classroom fixture;
không coi là nghiệm thu Classroom HTTP. Đăng ký/import mới giữ chính sách tạm.
Một bản ghi SMTP fixture trước bước Gmail đã được loại khỏi báo cáo bảy thư.

Assertion cuối runner dự kiến sáu thư đã lỗi vì quét hạn có hai task hợp lệ,
thực tế bảy thư đều `accepted_by_smtp`. Không chạy lại để tránh gửi thêm.
Kafka redelivery không tạo thêm delivery cho event giao việc đã xử lý; không
khẳng định toàn bộ runner đạt do assertion đếm thư nói trên.

Chưa xác nhận Inbox/Spam; người nhận cần kiểm tra mailbox. Link trong thư trỏ
frontend/tài khoản kiểm thử cô lập và không dùng được sau khi dọn cụm thử,
không phải link của tài khoản thật hoặc bằng chứng deployment staging.
