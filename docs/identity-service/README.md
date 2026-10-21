# Identity Service

Identity là nguồn dữ liệu gốc về tài khoản, hồ sơ, vai trò toàn hệ thống và phiên đăng
nhập của UTask. Tài liệu này hướng dẫn các service khác tích hợp; chi tiết request/response
nằm trong [đặc tả API](../architecture/Identity_Service_API_Specification.md).
Schema OpenAPI local được cung cấp tại `/openapi/`; qua gateway staging là
`/api/auth/openapi/`.

Theo [baseline](<../architecture/UTask_Architecture_Technology_Baseline (1).md>),
mục 4.1 và 7, service dùng Python + Django + DRF, Django Authentication,
JWT access token và refresh token; không dùng Keycloak ở giai đoạn hiện tại.

Identity Service sở hữu tài khoản, hồ sơ, vai trò toàn hệ thống, xác thực,
token và phiên/refresh token. Các service khác dùng `user_id` làm ID tham chiếu;
chúng không đọc Identity DB.
**Phạm vi:** API lõi có source và kiểm thử local. Google/GitHub OAuth và avatar R2 được
mở bằng feature flags khi đủ cấu hình. Publisher Kafka và avatar R2 đã có kiểm chứng
runtime local. Google/GitHub thật, gửi email và gateway/staging chưa được nghiệm thu.

<a id="trach-nhiem-va-du-lieu"></a>

Phạm vi bao gồm password reset và OAuth mở rộng Google/GitHub nếu sản phẩm
cần; `django-allauth` đã có trong manifest và được dùng qua các hook của Identity.
Mật khẩu dùng Django password hashing; login và endpoint nhạy cảm cần rate
limit. API phải dùng HTTPS ngoài môi trường local phù hợp.

Chạy bằng Docker Compose không cần thêm biến IP vào `.env`: Nginx lấy IP người
dùng, Identity dùng IP đó cho session, audit, Axes và rate limit. Hạ tầng cấp sẵn
cấu hình để chỉ nhận header IP từ mạng proxy nội bộ; header giả từ nguồn khác
bị bỏ qua. Chạy app ngoài Compose mặc định dùng IP kết nối trực tiếp.
Chi tiết tại
[cấu hình proxy và IP client](../infrastructure/environment.md#ip-client-qua-proxy).
Các bản ghi lịch sử không tự đổi IP sau khi deploy bản sửa.

Các service xác thực token nhưng không truy cập Identity DB. Phân quyền kết
hợp global RBAC (Admin, Teacher, User) với quyền trên tài nguyên/project
(Leader/Owner, Member). Identity cấp danh tính và vai trò toàn hệ thống;
service sở hữu tài nguyên kiểm tra membership và quyền nghiệp vụ ở backend.
Cơ chế key/token verification cụ thể cần hợp đồng xác thực, không suy ra từ
identity header bootstrap.

Xem thêm: [kiến trúc](../system/architecture.md), [quyền sở hữu dữ liệu](../system/data-ownership.md).

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

1. **Đăng ký:** tạo user ACTIVE, profile và role STUDENT; email được đánh dấu đã xác
   minh ngay, không chờ email kích hoạt trong giai đoạn chưa có Resend.
   Đăng nhập riêng để nhận JWT. Tài khoản import vẫn dùng luồng kích hoạt hiện có.
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

Khi đăng ký, service đọc lại tên hồ sơ do trigger PostgreSQL sinh trước khi
phát `identity.user.created`; event và API dùng cùng tên đã lưu.

<a id="api-de-tich-hop"></a>

## API để tích hợp

Các đường dưới đây là đường **trong service**. Backend gọi `http://identity-service:8000`
trên mạng Compose; local là `http://localhost:8001`. Gateway bỏ tiền tố `/api/auth/`:
`/api/auth/login` được chuyển thành `/login`.
Các URL công khai cũ có tiền tố `/api/v1/auth`, `/api/v1/users` hoặc `/api/v1/admin` không còn được đăng ký. Routes `/api/v1/internal/` dành cho backend và bị chặn ở gateway.

| Nhóm           | API                                                                                                   | Quyền/đặc điểm                                                           |
| -------------- | ----------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------ |
| Đăng ký        | POST `/register`                                                                                      | Anonymous; không nhận role/MSSV, chưa hỗ trợ Idempotency-Key             |
| Kích hoạt      | POST `/activate`, `/activation/resend`                                                                | Anonymous; key dùng một lần, resend vô hiệu key cũ                       |
| Login/refresh  | POST `/login`, `/refresh`; GET `/csrf`                                                                | Login cấp CSRF cookie; refresh bằng body JWT hoặc cookie                  |
| Password       | POST `/password-reset/request`, `/password-reset/confirm`, `/password-change`                         | Request/confirm anonymous; change cần Bearer và password cũ              |
| Logout         | POST `/logout`, `/logout-all`                                                                         | Bearer                                                                   |
| Thiết bị       | GET `/sessions`; DELETE `/sessions/{session_id}`                                                      | Bearer; phiên thuộc user hiện tại                                        |
| Hồ sơ cá nhân  | GET/PATCH `/users/me`                                                                                 | Bearer; không tự đổi role/email/MSSV qua PATCH                           |
| Tra cứu        | GET `/users/{user_id}`; POST `/users/batch`                                                           | Bearer; batch `user_ids`, tối đa100, loại trùng và bỏ ID không tìm thấy  |
| Quản trị       | GET `/admin/users`; PATCH `/admin/users/{user_id}/status`; POST/DELETE `/admin/users/{user_id}/roles` | SYSTEM_ADMIN; không tự thu hồi role admin của chính mình                 |
| Kiểm tra phiên | POST `/api/v1/internal/auth/session-status`                                                           | Bearer cần kiểm tra + key của caller `work`, `classroom` hoặc `ai`       |
| Cấp sinh viên  | POST `/api/v1/internal/users/provision-students`                                                      | Classroom key + actor Bearer TEACHER/SYSTEM_ADMIN + Idempotency-Key UUID |
| Resend nội bộ  | POST `/api/v1/internal/users/{user_id}/resend-activation`                                             | Classroom key + actor Bearer; user pending đủ điều kiện                  |
| GitHub mapping | GET `/api/v1/internal/users/{user_id}/oauth/GITHUB`                                                   | Integration key; mapping có thể là null                                  |
| Khóa công khai | GET `/.well-known/jwks.json`                                                                          | Anonymous; `keys` ở root                                                 |

Gán và thu hồi role đều nhận JSON body `{"role_code":"TEACHER"}` tại
`POST`/`DELETE /admin/users/{user_id}/roles`. Swagger hiển thị request body bắt buộc
cho cả hai phương thức. POST thêm role, không ghi đè các role khác; DELETE chỉ gỡ
role được chỉ định. Gọi qua gateway thì thêm tiền tố `/api/auth`.

Tra cứu public/batch chỉ trả dữ liệu cho phép, không password/token/preferences của
user khác. Provisioning nhận tối đa100 JSON rows và trả kết quả từng row. Cùng actor,
path, key và body trả lại receipt; body khác với cùng key trả422. Classroom giữ payload
ổn định khi retry và chịu trách nhiệm enrollment; Identity chịu trách nhiệm danh tính.
User mới từ provisioning chưa có password dùng được; khi activate cần gửi
`new_password1` và `new_password2` cùng key kích hoạt.

Response nghiệp vụ có cùng envelope:

```json
{ "success": true, "message": "...", "data": {}, "meta": null, "error": null }
```

Lỗi có `success=false`, `data=null`, `meta=null`, `error={"code":"...","details":[]}`.
`details` luôn là mảng; giữ `WWW-Authenticate` và `Retry-After` khi áp dụng.
JWKS là ngoại lệ theo giao thức: `{"keys":[...]}`.

Thông báo thành công/lỗi và `error.details[].issue` dùng tiếng Việt. Django/DRF dùng
locale `vi`; thông báo nghiệp vụ được viết tại nơi phát sinh, thông báo đặc thù của
dj-rest-auth được chuẩn hóa trong `common`. HTTP status, mã lỗi và đường dẫn trường
giữ nguyên; lỗi đọc dữ liệu không trả nội dung thô của bộ phân tích JSON.

### Avatar R2

Đặt `IDENTITY_AVATAR_ENABLED=true` trong `.env` của môi trường đã có đủ
`IDENTITY_R2_ENDPOINT`, `IDENTITY_R2_BUCKET`, `IDENTITY_R2_ACCESS_KEY`,
`IDENTITY_R2_SECRET_KEY`, `IDENTITY_R2_PUBLIC_URL`. Các giá trị đi qua mapping hiện có;
tạo lại container sau khi thay đổi môi trường. PostgreSQL/Redis vẫn dùng hạ tầng chung.

Luồng client: gọi `POST /users/me/avatar/presigned-url` với tên, loại và dung lượng
ảnh; PUT byte ảnh vào `upload_url` với đúng `Content-Type`; sau đó gọi
`POST /users/me/avatar/confirm` với `file_key`. Backend kiểm HEAD trên R2 rồi cập nhật
hồ sơ và outbox. Ảnh chưa tồn tại hoặc metadata không khớp không được ghi vào hồ sơ.
Chỉ hỗ trợ JPEG/PNG/WebP, tối đa5 MB; URL tải lên có hạn300 giây.

Đã chạy luồng này với R2 thật, gồm GET ảnh public và confirm lặp không phát thêm
event; bằng chứng ở `artifacts/identity/localization-r2/runtime.json`. CORS preflight
cho `https://utask.u-code.dev` đạt204. `http://localhost:8080` hiện bị bucket từ chối403;
muốn upload từ origin local này cần bổ sung vào CORS của bucket, giữ các origin đang có.
Policy cần cho phép `PUT` và header `Content-Type`; `GET`/`HEAD` dùng cho đọc/kiểm tra
ảnh. Xem [hướng dẫn CORS của Cloudflare](https://developers.cloudflare.com/r2/buckets/cors/).
Credential R2 hiện có không cho đọc cấu hình CORS (`AccessDenied`); lượt kiểm chứng
không ghi đè policy của bucket hoặc thay cấu hình Cloudflare.

<a id="xac-thuc-va-quyen"></a>

## Xác thực và quyền ở service gọi

1. Nhận `Authorization: Bearer <access>`; dùng thư viện JWT kiểm RS256 bằng JWKS,
   `iss=https://identity.utask.internal`, `aud=utask-platform`, hạn token và `token_type=access`.
   `sub` là user_id; `session_id` và `token_family` định danh phiên cần kiểm tra.
   Access mặc định9.000 giây (2 giờ30 phút); refresh family tối đa7 ngày từ login,
   không gia hạn khi rotate. Access vẫn bị giới hạn bởi hạn tuyệt đối của family.
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

Login cấp và đổi CSRF cookie bằng Django; client không cần mở Swagger trước.
Client mới có thể gọi `GET /api/auth/csrf` với credentials để lấy `data.csrf_token`
và cookie. Sau login đọc lại `csrftoken` vì secret đã được đổi; gửi `X-CSRFToken`
cùng cookie khi refresh/logout/logout-all. Các response cấp token/CSRF không được cache.
`IDENTITY_CSRF_TRUSTED_ORIGINS` nhận các origin có scheme, cách nhau dấu phẩy; nếu để
trống dùng `IDENTITY_FRONTEND_URL`. Production cần cấu hình đúng origin HTTPS thực tế.

TTL cấu hình qua `IDENTITY_ACCESS_TOKEN_SECONDS` (mặc định9.000) và
`IDENTITY_REFRESH_TOKEN_SECONDS` (604800). Đổi setting cần phát hành/restart service;
token đã cấp không tự kéo dài và access mới vẫn bị chặn ở hạn family tuyệt đối.

<a id="su-kien-va-dong-bo"></a>

## Sự kiện và tích hợp bên ngoài

Event được ghi vào outbox cùng thay đổi nghiệp vụ. Envelope v1 gồm `event_id`,
`event_type`, `event_version`, `occurred_at`, `producer`, `aggregate_id`, `trace_id`, `data`.
Nghiệp vụ ở `event.data`; consumer xử lý lặp bằng `event_id`.

| Sự kiện                                                                                           | Mục đích                                            |
| ------------------------------------------------------------------------------------------------- | --------------------------------------------------- |
| `identity.user.created`, `identity.user.updated`, `identity.user.activated`                         | Cập nhật thông tin user và báo kích hoạt            |
| `identity.user.role_assigned`, `identity.user.role_revoked`                                       | Thông báo đổi global role                           |
| `identity.activation.requested`, `identity.student.imported`, `identity.password_reset.requested` | Notification gửi hướng dẫn; mail secret được mã hóa |
| `identity.oauth.github_linked`, `identity.oauth.github_unlinked`                                  | Thông báo liên kết GitHub cho Integration           |

Mail secret dùng AES-GCM/key ID; Notification cần cấu hình giải mã tương ứng.
`identity.student.imported` có thêm `student_id` nullable theo hợp đồng. Work cập nhật
projection từ `identity.user.created/updated`; các loại Identity đã chốt khác được
kiểm envelope rồi bỏ qua tại consumer hồ sơ, không đưa nhầm vào DLQ. Xem
[quy tắc phía Work](../project-service/identity-events.md).
`identity-publisher` dùng cùng image Identity và PostgreSQL chung; bật bằng Compose
profile `identity-service`. Command `publish_identity_outbox --watch` đọc outbox mỗi
giây rồi gửi thẳng Kafka dùng chung, không qua Celery/Beat hay hàng đợi Redis.
Publisher dùng row lock/skip-locked, chỉ gửi đầu hàng pending của mỗi user,
ghi `published_at` sau callback ACK. Lỗi lưu loại exception (không message chứa secret),
retry backoff tối đa300 giây; không cho event sau vượt event lỗi cùng user. Crash sau
ACK có thể gửi lại cùng event ID, consumer phải chống lặp. Event mail hết hạn được
đặt `secret=null`, giữ user/email/expiry trước publish. Đã chạy thử local với image
Identity, PostgreSQL dùng chung và Kafka Docker thật: đăng ký qua HTTP tạo outbox,
publisher gửi đúng envelope/ID và phục hồi sau lỗi kết nối. Bài thử dùng database/topic
riêng; kết quả tại `artifacts/identity/publisher-runtime/result.json`. Chưa nghiệm thu
Notification, mail provider hay staging; ACK Kafka không đồng nghĩa đã gửi mail.

Chạy một batch thủ công trong môi trường đã cấu hình:
`python manage.py publish_identity_outbox --batch-size 100`.
Chạy liên tục: `python manage.py publish_identity_outbox --watch`; dừng bằng Ctrl+C
hoặc dừng container. Lỗi tiến trình làm command thoát để Docker khởi động lại;
event chưa được Kafka xác nhận vẫn nằm trong outbox. Redis hiện có vẫn phục vụ
cache/giới hạn lượt gọi và OAuth, không phục vụ hàng đợi publisher.
Kiểm tra backlog/retry qua `published_at`, `retry_count`, `last_error`, `next_attempt_at`;
event lỗi giữ trong DB để điều tra, không bị bỏ qua hay tự đánh dấu thành công.
Xem log bằng `docker compose logs -f identity-publisher`. Logger `identity.outbox`
ghi `publish_succeeded` ở mức INFO sau Kafka ACK và DB commit, gồm `event_id`,
`event_type`, `topic`; lỗi gửi ghi `publish_failed` ở mức WARNING. Không ghi nội dung
event, email, mã kích hoạt hay token. Khi không có sự kiện chờ, publisher không in log.
Chi tiết event ở mục4 của đặc tả API. Consumer của từng service phải đăng ký đúng
event types trước rollout; chỉ có producer/test mock không chứng minh consumer đã áp dụng.

### Dọn dữ liệu kỹ thuật

Không có job dọn dữ liệu tự động. Lệnh thủ công xử lý tối đa500 bản ghi mỗi bảng;
chỉ chạy sau khi xác nhận thời gian lưu dữ liệu cho môi trường.
Preview: `python manage.py cleanup_identity`; chỉ thêm `--apply` mới xóa dữ liệu. Job
chỉ xóa session đã hết hạn thêm30 ngày, receipt cũ hơn7 ngày, outbox đã published
cũ hơn7 ngày và token/session/email-confirmation kỹ thuật đã quá hạn. Các ngưỡng
`IDENTITY_SESSION_RETENTION_DAYS`, `IDENTITY_RECEIPT_RETENTION_DAYS`,
`IDENTITY_OUTBOX_RETENTION_DAYS` tối thiểu một ngày; đây là mặc định kỹ thuật cấu hình
được, không phải chính sách xóa dữ liệu cá nhân. Không xóa user/profile, audit hoặc
event chưa publish. Audit được giữ nguyên đến khi có chính sách được phê duyệt.
Expired mail secret được redaction dù event còn pending; TTL Redis do Redis quản lý.

Theo [ADR-004](../adr/004-integration-github-account-ownership.md), luồng GitHub
mới thuộc Integration và dùng `GET /users/me` của Identity để xác thực actor.
Không cần sửa code/allowlist Identity. Nội dung GitHub sau đây mô tả **source
legacy còn giữ nguyên**, không phải dependency hoặc ownership của luồng mới.

Google dùng allauth xác minh danh tính đăng nhập. Source GitHub legacy dùng để liên kết tài khoản:
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
