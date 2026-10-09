# Identity Service

Identity là nguồn dữ liệu gốc về tài khoản, hồ sơ, vai trò toàn hệ thống và phiên đăng
nhập của UTask. Tài liệu này hướng dẫn các service khác tích hợp; chi tiết request/response
nằm trong [đặc tả API](../architecture/Identity_Service_API_Specification.md).
Schema OpenAPI local được cung cấp tại `/openapi/`; qua gateway staging là
`/api/auth/openapi/`.

**Phạm vi:** API lõi có source và kiểm thử local. Google/GitHub OAuth và avatar R2 được
mở bằng feature flags khi đủ cấu hình. Provider thật, gửi email, publisher Kafka và
luồng tích hợp giữa các service chưa được nghiệm thu đầy đủ.

<a id="trach-nhiem-va-du-lieu"></a>

## Trách nhiệm và dữ liệu

- Identity sở hữu `identity_db`: user, profile, global role, session, audit, outbox và
  receipt phục vụ yêu cầu cấp tài khoản. Custom user là `accounts.User`.
- Service khác giữ `user_id` dạng UUID và lấy thông tin qua API hoặc bản sao dữ liệu
  cập nhật từ sự kiện. Không đọc database Identity hoặc tạo khóa ngoại xuyên service.
- `STUDENT`, `TEACHER`, `SYSTEM_ADMIN` là global roles. Quyền lớp, nhóm và dự án do
  Classroom/Project quản lý; global role không tự cấp quyền vào tài nguyên đó.
- MSSV (`student_id`) thuộc Identity, có thể chưa được gán. Classroom ghi danh bằng
  `user_id`; MSSV không thay thế UUID và không dùng làm quyền truy cập.
- Account có ba trạng thái: `PENDING_ACTIVATION`, `ACTIVE`, `SUSPENDED`. Xóa mềm dùng
  `deleted_at`; email/username/MSSV vẫn được giữ để tránh cấp lại nhầm danh tính.

Email xác minh do allauth quản lý; mật khẩu dùng Django password API và Argon2.
Axes quản lý chống thử mật khẩu: 5 lần sai, cooldown15 phút, trả429 và Retry-After.
Lockout không phải một trạng thái vòng đời của user.

<a id="cach-hoat-dong"></a>

## Cách hoạt động

1. **Đăng ký:** tạo user pending, profile và role STUDENT; tạo yêu cầu kích hoạt.
   Xác minh key hợp lệ chuyển user thành ACTIVE; đăng nhập riêng để nhận JWT.
2. **Đăng nhập:** dj-rest-auth/Django Auth/allauth kiểm email hoặc username/password;
   Identity kiểm trạng thái tài khoản rồi tạo phiên thiết bị và token SimpleJWT.
3. **Refresh:** SimpleJWT đổi refresh token và blacklist token trước; Identity giữ
   `session_id`/`token_family` ổn định, cập nhật hash/JTI trong transaction.
   Refresh đã rotate bị dùng lại khi còn hạn khiến toàn family bị thu hồi.
4. **Thu hồi:** logout thu hồi phiên hiện tại; logout-all thu hồi mọi phiên. Đổi/reset
   password, đổi role hoặc đình chỉ tài khoản thu hồi các credential liên quan.
   Login mới tạo family mới; mở lại tài khoản không phục hồi phiên cũ.
5. **Cấp sinh viên:** Classroom xử lý CSV/XLSX và quyền lớp, gọi Identity bằng JSON để
   tạo/tìm user, rồi tự ghi enrollment bằng `user_id` được trả về.

Thay đổi user/profile/role, audit và outbox được ghi trong cùng transaction.
Identity không ghi enrollment, project membership hoặc dữ liệu repository.

<a id="api-de-tich-hop"></a>

## API để tích hợp

Các đường dưới đây là đường **trong service**. Backend gọi `http://identity-service:8000`
trên mạng Compose; local là `http://localhost:8001`. Gateway bỏ tiền tố `/api/auth/`:
`/api/auth/login` được chuyển thành `/login`.
Các URL công khai cũ có tiền tố `/api/v1/auth`, `/api/v1/users` hoặc `/api/v1/admin` không còn được đăng ký. Routes `/api/v1/internal/` dành cho backend và bị chặn ở gateway.

| Nhóm | API | Quyền/đặc điểm |
| --- | --- | --- |
| Đăng ký | POST `/register` | Anonymous; không nhận role/MSSV, chưa hỗ trợ Idempotency-Key |
| Kích hoạt | POST `/activate`, `/activation/resend` | Anonymous; key dùng một lần, resend vô hiệu key cũ |
| Login/refresh | POST `/login`, `/refresh` | Login email/username; refresh bằng body JWT hoặc cookie |
| Password | POST `/password-reset/request`, `/password-reset/confirm`, `/password-change` | Request/confirm anonymous; change cần Bearer và password cũ |
| Logout | POST `/logout`, `/logout-all` | Bearer |
| Thiết bị | GET `/sessions`; DELETE `/sessions/{session_id}` | Bearer; phiên thuộc user hiện tại |
| Hồ sơ cá nhân | GET/PATCH `/users/me` | Bearer; không tự đổi role/email/MSSV qua PATCH |
| Tra cứu | GET `/users/{user_id}`; POST `/users/batch` | Bearer; batch `user_ids`, tối đa100, loại trùng và bỏ ID không tìm thấy |
| Quản trị | GET `/admin/users`; PATCH `/admin/users/{user_id}/status`; POST/DELETE `/admin/users/{user_id}/roles` | SYSTEM_ADMIN; không tự thu hồi role admin của chính mình |
| Kiểm tra phiên | POST `/api/v1/internal/auth/session-status` | Bearer cần kiểm tra + key của caller `work`, `classroom` hoặc `ai` |
| Cấp sinh viên | POST `/api/v1/internal/users/provision-students` | Classroom key + actor Bearer TEACHER/SYSTEM_ADMIN + Idempotency-Key UUID |
| Resend nội bộ | POST `/api/v1/internal/users/{user_id}/resend-activation` | Classroom key + actor Bearer; user pending đủ điều kiện |
| GitHub mapping | GET `/api/v1/internal/users/{user_id}/oauth/GITHUB` | Integration key; mapping có thể là null |
| Khóa công khai | GET `/.well-known/jwks.json` | Anonymous; `keys` ở root |

Tra cứu public/batch chỉ trả dữ liệu cho phép, không password/token/preferences của
user khác. Provisioning nhận tối đa100 JSON rows và trả kết quả từng row. Cùng actor,
path, key và body trả lại receipt; body khác với cùng key trả422. Classroom giữ payload
ổn định khi retry và chịu trách nhiệm enrollment; Identity chịu trách nhiệm danh tính.
User mới từ provisioning chưa có password dùng được; khi activate cần gửi
`new_password1` và `new_password2` cùng key kích hoạt.

Response nghiệp vụ có cùng envelope:

```json
{"success":true,"message":"...","data":{},"meta":null,"error":null}
```

Lỗi có `success=false`, `data=null`, `meta=null`, `error={"code":"...","details":[]}`.
`details` luôn là mảng; giữ `WWW-Authenticate` và `Retry-After` khi áp dụng.
JWKS là ngoại lệ theo giao thức: `{"keys":[...]}`.

<a id="xac-thuc-va-quyen"></a>

## Xác thực và quyền ở service gọi

1. Nhận `Authorization: Bearer <access>`; dùng thư viện JWT kiểm RS256 bằng JWKS,
   `iss=https://identity.utask.internal`, `aud=utask-platform`, hạn token và `token_type=access`.
   `sub` là user_id; `session_id` và `token_family` định danh phiên cần kiểm tra.
   Access tối đa15 phút; refresh family tối đa7 ngày từ login, không gia hạn khi rotate.
   JWKS hiện có một khóa RSA; token SimpleJWT không có `kid`.
2. Work/Project, Classroom và AI chuyển access tới `session-status`, kèm key backend
   riêng trong header `X-Service-Key`. Map key theo caller `work`, `classroom`, `ai`
   trong `IDENTITY_SERVICE_KEYS`.
   Response200 có `data={"active":true}` hoặc `{"active":false}`.
3. Chỉ cho phép tiếp tục khi phiên active. Identity lỗi/timeout trả503 IDENTITY_UNAVAILABLE,
   không cấp quyền; giai đoạn đầu không cache kết quả cho phép để bảo đảm thu hồi phiên.
4. Kiểm quyền lớp/dự án/tài nguyên bằng dữ liệu do chính service sở hữu.

Blacklist refresh không tự thu hồi access ở consumer chỉ kiểm chữ ký. Session-status
giúp consumer thấy logout, đổi password/role, suspended/deleted hoặc replay sau commit.
Private signing key chỉ ở Identity; service khác dùng public JWKS và caller key riêng.

Web nhận refresh qua cookie HttpOnly/Secure/SameSite=Lax, path `/api/auth`.
Mutation dùng cookie phải qua CSRF/Origin của Django; cookie và body khác nhau trả400.
Backend service không giữ refresh token thay người dùng.

<a id="su-kien-va-dong-bo"></a>

## Sự kiện và tích hợp bên ngoài

Event được ghi vào outbox cùng thay đổi nghiệp vụ. Envelope v1 gồm `event_id`,
`event_type`, `event_version`, `occurred_at`, `producer`, `aggregate_id`, `trace_id`, `data`.
Nghiệp vụ ở `event.data`; consumer xử lý lặp bằng `event_id`.

| Sự kiện | Mục đích |
| --- | --- |
| `identity.user.created`, `identity.user.updated` | Cập nhật bản sao thông tin user |
| `identity.user.role_assigned`, `identity.user.role_revoked` | Thông báo đổi global role |
| `identity.activation.requested`, `identity.student.imported`, `identity.password_reset.requested` | Notification gửi hướng dẫn; mail secret được mã hóa |
| `identity.oauth.github_linked`, `identity.oauth.github_unlinked` | Thông báo liên kết GitHub cho Integration |

Mail secret dùng AES-GCM/key ID; Notification cần cấu hình giải mã tương ứng.
Outbox có code ghi dữ liệu; publisher/ACK Kafka, gửi mail và consumer liên service cần
triển khai/nghiệm thu riêng. Chi tiết event ở mục4 của đặc tả API.

Google dùng allauth xác minh danh tính đăng nhập. GitHub dùng để liên kết tài khoản:
Identity quản lý OAuth context/link, chỉ Integration đổi code và gọi GitHub API qua
`POST /api/v1/internal/oauth/github/exchange`. Identity kiểm binding của proof trước khi
ghi link. Avatar dùng presign/upload/confirm với R2. Các luồng này phụ thuộc feature flags
và cấu hình/provider thật; route hoặc test mock chưa chứng minh tích hợp đã hoạt động.

<a id="cau-hinh-va-kiem-thu"></a>

## Cấu hình và kiểm thử

Stack: Django/DRF, dj-rest-auth, allauth, SimpleJWT, Axes, Argon2; PostgreSQL và Redis.
Compose local và staging cùng dùng mapping `infra/env/identity-service.env`.
Điền giá trị tại `.env` của từng máy theo `.env.example`: signing key host path,
caller keys, mail encryption và nhóm Google/GitHub/R2. Giữ secrets ngoài source;
xem [cấu hình môi trường](../infrastructure/environment.md).
Swagger local `/docs/`; qua gateway staging là
`/api/auth/docs/`. OpenAPI JSON local `/openapi/`, qua gateway là
`/api/auth/openapi/`; health `/healthz`.

Source: `accounts` sở hữu user/profile/roles; `authentication` quản lý credential/session
và hooks thư viện; `messaging` ghi event/mã hóa mail; `common` xử lý response/error;
`config` cấu hình/routes; `tests` chứa pytest.

Kiểm thử bao phủ register→activate→login→me→refresh→logout, recovery/change password,
quyền, lockout, replay/concurrency và rollback. Unit không cần DB; integration dùng
PostgreSQL/Redis kiểm thử riêng. Lệnh và ma trận ở
[đặc tả kiểm thử](../architecture/Identity_Service_Test_Specification.md#5-chạy-test-bằng-pytest).

Tài liệu chi tiết: [API](../architecture/Identity_Service_API_Specification.md),
[ERD](../diagram/identity-service/erd.md),
[use case](../diagram/identity-service/usecase.md), [sequence](../diagram/identity-service/sequence.md),
[kiến trúc](../system/architecture.md), [quyền sở hữu dữ liệu](../system/data-ownership.md).
