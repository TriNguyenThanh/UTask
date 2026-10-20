# Kiểm thử Identity Service

**Trạng thái ngày20/10/2026:**383 ca pytest đạt,0 lỗi/skip, gồm ba ca hồi quy UUID sai.
Bộ Work liên quan ở lượt kiểm chứng trước cũng chạy
đầy đủ:718 đạt,2 ca external/E2E không nằm trong lệnh mặc định. Kết quả local không
thay nghiệm thu staging hoặc Google/GitHub/Resend thật.

Nguồn chuẩn: [API Identity](Identity_Service_API_Specification.md),
[hướng dẫn service](../identity-service/README.md), [ERD](../diagram/identity-service/erd.md).

## Phạm vi và quy ước

- Unit: serializer, policy, message/renderer, token contract; không gọi database khi
  ca không cần. Lỗi và thành công trả tiếng Việt, giữ error code/status/field path.
- API batch kiểm UUID sai trả `VALIDATION_ERROR` với thông báo "Mã định danh không
  hợp lệ."; giữ đường dẫn phần tử như `user_ids.1`, không trả câu tiếng Anh của thư viện.
- Integration/APIClient: PostgreSQL thật, transaction/rollback, audit/outbox, role,
  session, Axes và provisioning. Redis dùng DB kiểm thử riêng, không flush Redis chung.
- HTTP: Requests Session + Django live_server kiểm đăng ký→login→me→refresh→logout,
  forgot/reset và đổi mật khẩu. Tự đăng ký hiện ACTIVE/email verified, không yêu cầu
  mail key và không gửi mail activation. Imported/pending user vẫn có test kích hoạt,
  hết hạn, key sai, đình chỉ và xóa mềm.
- Concurrency: refresh/replay/logout, reset hai request, actor role và admin suspend
  dùng các kết nối PostgreSQL độc lập; không gọi mock là bằng chứng khóa DB.
- Contract: URLconf/OpenAPI/envelope, JWKS root, body gán/thu hồi role, header xác thực,
  Retry-After và lỗi framework. Ma trận26 thao tác mặc định nằm ở
  `tests/fixtures/api_operations.py`; test không import module test khác để lấy fixture.
- Adapter Google/GitHub/R2 có test giả cho nhánh lỗi/policy; nghiệm thu provider tách riêng.
  Source OpenAPI ở `config/api_documentation.py`; không tạo schema runtime thứ hai.

## Hành vi được kiểm chứng

| Nhóm | Source test chính | Điều được kiểm tra |
| --- | --- | --- |
| User/profile/role/bootstrap | test_accounts, test_me, test_account_api | Ràng buộc, chuẩn hóa, quyền và không lộ mật khẩu |
| Đăng ký mới | test_flows, test_registration | ACTIVE/verified, STUDENT, không mail activation/JWT, rollback lỗi input |
| Kích hoạt pending/import | test_password_errors, test_provisioning, test_flows | Key một lần, hết hạn, mật khẩu import và không tự khôi phục tài khoản |
| Login/lockout/JWT | test_login, test_jwt, test_lifetimes | Django/Auth/Axes, access mặc định9000s, refresh7 ngày, reset/cooldown900s |
| Rotation/logout/devices | test_rotation, test_concurrency, test_sessions, test_devices | Thu hồi/replay và family hết hạn tuyệt đối |
| Password | test_flows, test_password_errors | Generator thư viện, đổi/reset và thu hồi mọi phiên |
| Admin/public/provisioning | test_account_api, test_account_concurrency, test_provisioning | Vai trò, status, allowlist, idempotency và rollback |
| Cookie/IP/CSRF | test_cookie_security, test_client_ip, test_csrf_login | Cookie Secure/HttpOnly, Origin và không tin header proxy giả |
| Sự kiện/publisher | test_mail_events, test_publisher, test_outbox_command | Import có student_id nullable, ACK/retry/order/commit/log |
| Tiếng Việt/envelope | test_vietnamese_messages, test_responses, test_http_errors | Success/business/framework errors và không lộ nội bộ |
| R2/OAuth | test_avatars, test_oauth_* | Nhánh adapter, binding, rollback; giới hạn test giả được giữ |

Work: `tests/unit/test_profile_consumer_boundary.py` kiểm bỏ qua9 loại Identity
ngoài projection sau kiểm envelope v1. Không ghi profile/receipt hoặc giải mã mail.
Dữ liệu hỏng/loại lạ/version sai vẫn vào DLQ, chờ ACK rồi mới commit offset.
`tests/integration/test_membership_consumer.py` kiểm receipt/projection/rollback và replay.

## Chạy kiểm tra

Từ `apps/identity-service`, dùng dependency khóa trong `uv.lock`:

```powershell
uv sync --locked
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
uv run pytest -q -m unit
uv run pytest -q -m http tests/test_flows.py
uv run python manage.py check --settings=tests.settings
```

Full suite cần PostgreSQL test connection có quyền tạo database; pytest-django tạo
và dọn database test riêng. Windows có thể dùng PostgreSQL dùng chung của Compose qua
port55432; cấu hình POSTGRES_HOST/PORT/USER/PASSWORD và IDENTITY_TEST_DB_NAME riêng.
Nạp credential an toàn từ môi trường của máy, không in giá trị ra log. Redis test
được chọn qua `IDENTITY_TEST_REDIS_URL`; mặc định local port56379/DB15. Không giả định
Redis được publish nếu không có port mapping kiểm thử trên máy.

```powershell
uv run coverage run -m pytest -q
uv run coverage report --skip-empty
uv run coverage json -o ../../artifacts/identity/coverage.json
```

## Kết quả và giới hạn

Lượt380 test ngày20/10/2026 có JUnit và coverage local tại
`artifacts/identity/event-handoff/identity_coverage_pytest.xml` và `coverage.json`.
Coverage tổng hợp **93.52%**, line **95.44%**, branch **82.55%**;
ngưỡng90 áp dụng chỉ số tổng hợp. Migration/management/config/thư viện không nằm
trong metric coverage; chúng có kiểm tra thích hợp riêng. Artifact bị Git bỏ qua,
không có sẵn trên checkout mới; chạy lại lệnh để thu kết quả môi trường đó.

Đã có runtime local HTTP→outbox→Kafka, lỗi kết nối/khôi phục và success log; avatar R2
thật đã qua PUT/HEAD/confirm/public GET với origin `https://utask.u-code.dev`.
Notification/Resend, Google/GitHub thật, gateway/staging và CORS localhost8080 nằm ngoài
lượt hoàn thiện này. Không nâng những mục đó thành Pass từ kết quả pytest/provider giả.

## Ma trận26 thao tác mặc định

Đường dưới đây là trong service; gateway thêm `/api/auth`. Bật riêng avatar có28
thao tác; bật đủ Google/GitHub/avatar có34. Test flags kiểm URLconf thực tế.

| Method | Path | Status thành công |
| --- | --- | --- |
| GET | `/csrf` | 200 |
| GET | `/.well-known/jwks.json` | 200 |
| POST | `/register` | 201 |
| POST | `/activate` | 200 |
| POST | `/activation/resend` | 200 |
| POST | `/login` | 200 |
| POST | `/refresh` | 200 |
| POST | `/logout` | 200 |
| POST | `/logout-all` | 200 |
| GET | `/sessions` | 200 |
| DELETE | `/sessions/{session_id}` | 200 |
| POST | `/password-reset/request` | 200 |
| POST | `/password-reset/confirm` | 200 |
| POST | `/password-change` | 200 |
| GET | `/users/me` | 200 |
| PATCH | `/users/me` | 200 |
| GET | `/users/{user_id}` | 200 |
| POST | `/users/batch` | 200 |
| GET | `/admin/users` | 200 |
| PATCH | `/admin/users/{user_id}/status` | 200 |
| POST | `/admin/users/{user_id}/roles` | 200 |
| DELETE | `/admin/users/{user_id}/roles` | 200 |
| POST | `/api/v1/internal/users/provision-students` | 201 |
| POST | `/api/v1/internal/users/{user_id}/resend-activation` | 200 |
| POST | `/api/v1/internal/auth/session-status` | 200 |
| GET | `/api/v1/internal/users/{user_id}/oauth/GITHUB` | 200 |

## Truy vết thiết kế cũ

[Ma trận138 TC lịch sử](../identity-service/testing-history.md) chỉ giữ snapshot để
truy vết. Các URL/key/bảng và nhãn cũ không phải chuẩn thực thi hiện tại. Những ca
chưa mapping không đồng nghĩa120 chức năng thiếu; không ghi lại số Pass mà chưa
đối chiếu từng ca. Marker `case_id` trong source là điểm nối, JUnit là kết quả chạy.
