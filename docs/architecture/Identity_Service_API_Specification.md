# UTask – Identity Service RESTful API Specification
## Đặc tả Giao diện Lập trình Ứng dụng (Enterprise API Specification) cho Dịch vụ Xác thực & Định danh Toàn cục

**Phiên bản:** 1.8 (trạng thái email và lockout thuộc thư viện; flags cho OAuth/R2)<br>
**Trạng thái: Một phần.** Cập nhật03/10/2026; API local có source/tests; provider/R2 và liên dịch vụ chưa nghiệm thu. Xem [phạm vi và cách tích hợp](../identity-service/README.md).<br>
**Dịch vụ sở hữu:** `apps/identity-service`<br>
**Cơ sở dữ liệu:** `identity_db` (PostgreSQL 16)<br>
**Cổng lắng nghe cục bộ (Local Port):** `8001`<br>
**Đường dẫn trong service:** `/api/v1/auth`, `/api/v1/users`, `/api/v1/admin/users`; đường nội bộ provisioning không công khai qua gateway.<br>
**Tài liệu tham chiếu:**
- [Kiến trúc hiện hành](../system/architecture.md), [ownership](../system/data-ownership.md), [Kafka](../system/kafka-events.md) (nguồn chuẩn sau pull)
- [UTask - Phân tích thiết kế yêu cầu.md](UTask%20-%20Phân%20tích%20thiết%20kế%20yêu%20cầu.md) (Epic 1: US-1.1 đến US-1.4, Quyền Giảng viên/Sinh viên/Admin)
- [erd.md](../diagram/identity-service/erd.md) (Sơ đồ CSDL và Từ điển dữ liệu `identity_db`)
- [Work_Service_API_Specification.md](Work_Service_API_Specification.md) (Quy chuẩn Single Unified Envelope và UserProjection contract)

---

## 1. Nguyên tắc Thiết kế & Chuẩn mực Kiến trúc Bắt buộc

**Quyết định ngày 2026-10-01:** Classroom nhận CSV/Excel và ghi danh; Identity tạo hoặc tìm tài khoản qua API nội bộ. Access token chỉ dùng RS256, issuer `https://identity.utask.internal`, audience `utask-platform`, TTL 15 phút. Refresh được xử lý trong ứng dụng, có khóa và giao dịch PostgreSQL. ERD và test specification dùng cùng tên trường và API bên dưới.

Use case và sequence bàn giao tại [usecase.md](../diagram/identity-service/usecase.md), [sequence.md](../diagram/identity-service/sequence.md) và [chỉ mục](../diagram/identity-service/README.md). Chi tiết kỹ thuật bổ sung được chốt ở mục 1.10. Các ví dụ mã là hướng dẫn triển khai, không phải mã đã chạy trong repo; kết quả kiểm thử nằm riêng trong báo cáo thực thi.

### 1.1. Single Unified Response Envelope (Khung Phản hồi Hợp nhất 100%)
Mọi phản hồi nghiệp vụ từ `identity-service` (thành công hoặc thất bại; JWKS là ngoại lệ tại mục 3.1.1) **bắt buộc** đóng gói trong khung chuẩn 5 trường duy nhất:

```json
{
  "success": true,
  "message": "Đăng nhập hệ thống thành công.",
  "data": {},
  "meta": {
    "page": 1,
    "limit": 20,
    "total_count": 100,
    "total_pages": 5,
    "has_next": true,
    "next_cursor": "eyJjcmVhdGVkX2F0IjoiMjAyNi0xMC0wMSJ9"
  },
  "error": null
}
```

`data={}` ở ví dụ khung chỉ minh họa vị trí payload; dữ liệu thực tế theo từng endpoint.

Khi phát sinh lỗi (HTTP 4xx / 5xx), trường `data` và `meta` mang giá trị `null`, trường `error` cung cấp chi tiết lỗi có cấu trúc:
```json
{
  "success": false,
  "message": "Thông tin đăng nhập không chính xác hoặc tài khoản đang bị khóa.",
  "data": null,
  "meta": null,
  "error": {
    "code": "INVALID_CREDENTIALS",
    "details": []
  }
}
```

---

### 1.2. JWT và phiên theo SimpleJWT (contract 1.7)

Access và refresh đều là JWT RS256 do SimpleJWT tạo/xác minh; access tối đa 15 phút,
refresh family tối đa 7 ngày từ login. Claims chuẩn gồm `token_type`, `jti`,
`iat`, `exp`, `sub`, `iss`, `aud`; `hash_password` do
`CHECK_REVOKE_TOKEN` quản lý. Adapter chỉ thêm `session_id`,
`token_family`, `family_exp`. Không yêu cầu exact claim set hoặc jti là UUID có dấu gạch.
Không đưa email/roles/MSSV vào token; quyền nghiệp vụ phải đọc từ nguồn sở hữu.

Một thiết bị giữ một hàng session ổn định khi rotation. SimpleJWT blacklist refresh cũ,
adapter cập nhật hash/jti hiện tại dưới khóa user và giữ nguyên hạn tuyệt đối.
Refresh đã rotate được dùng lại khi JWT còn hạn: commit thu hồi family/audit rồi trả
401 TOKEN_REPLAY_ATTACK_DETECTED. Hai request cùng refresh: một 200, một 401, family cuối
bị thu hồi; không có grace window. Token hết hạn bị thư viện từ chối trước kiểm replay.

Response dùng tên thư viện `access`, `refresh`, `user`. Chế độ web mặc định trả
`refresh=""` lúc login và không trả raw refresh trong body refresh; cookie
`refresh_token` HttpOnly/Secure/SameSite=Lax, path `/api/v1/auth`.
API client có thể gửi `{"refresh":"<JWT>"}`. Cookie và body khác nhau trả 400.
Khi có cookie, refresh/logout/logout-all kiểm CSRF/Origin qua dj-rest-auth/Django.
Không có route cấp raw refresh riêng cho mobile trong phiên bản này.

JWKS trả `keys` ở root, một khóa RSA công khai. SimpleJWT dùng header chuẩn không `kid`;
consumer chọn khóa duy nhất, không dùng parser/signature engine viết tay. Chưa hỗ trợ
overlap nhiều signing key; phải có kế hoạch chuyển khóa/consumer trước rollout.

### 1.3. Không dò tài khoản và vòng đời

Password login sai/không tồn tại/đã xóa/unusable trả 401 INVALID_CREDENTIALS.
Lookup, check/upgrade password và timing mitigation thuộc Django/allauth; chưa chứng minh
cân bằng thời gian giữa mọi trạng thái. Credentials đúng nhưng SUSPENDED/PENDING bị chặn.
Register STUDENT chuyển PENDING_ACTIVATION, xác minh email mới chuyển ACTIVE.
Email/username/MSSV xóa mềm vẫn được reserved; client không tự gán role/MSSV.

Forgot trả thông điệp trung tính, chỉ enqueue thư cho ACTIVE chưa xóa và có
password dùng được. Thiếu khóa mã hóa trả 503 cho cả email tồn tại/lạ.
Thông điệp enqueue không có nghĩa email đã được gửi.

### 1.4. Lockout thuộc django-axes

Axes database handler sở hữu counter và cooldown: 5 lần sai, 15 phút, không kéo dài
cooldown khi request tiếp theo bị chặn. Username/email cùng user được quy về UUID;
chặn riêng theo user và IP. Lần gây khóa và request trong cooldown trả 429
RATE_LIMIT_EXCEEDED; Retry-After=900 là thời gian chờ bảo thủ, không thay hạn DB.

`users` chỉ giữ trạng thái PENDING_ACTIVATION/ACTIVE/SUSPENDED; Axes lockout là trạng
thái riêng, không đổi account_status. Migration0005 bỏ counter/cooldown legacy;
khóa legacy còn hạn làm migration dừng/rollback, chỉ khóa đã hết hạn chuyển ACTIVE.
Axes lockout chỉ chặn password login, không thu hồi những phiên đang hoạt động.
Reset thành công gọi API reset của Axes cho user, không xóa lockout IP của user khác.

`is_email_verified` trong response vẫn là boolean nhưng được đọc từ
allauth EmailAddress khớp email hiện tại của user, không còn cột boolean lặp trong users.
Migration0005 giữ allauth hiện có; chỉ backfill từ cờ cũ nếu thiếu bản ghi email khớp.
Xung đột uniqueness khiến migration rollback; không tự lấy email của user khác.

### 1.5. Transactional Outbox Pattern & Phát sự kiện sang Apache Kafka
Mọi thay đổi dữ liệu người dùng (`CREATE`, `UPDATE`, `ROLE_ASSIGNED`, `STATUS_CHANGED`) đều được ghi đồng thời vào bảng `outbox_events` trong cùng Database Transaction.
- **Kafka Topic:** `utask.identity.events`
- **Partition Key:** `user_id` (Kafka giữ thứ tự broker nhận trong partition; producer/replay phải giữ thứ tự theo mục 1.10).
- **Celery Poller:** Chạy nền mỗi 1 giây quét các bản ghi `published_at IS NULL` và đẩy vào broker.

---


### 1.6. Verification/reset và mail secret

allauth tạo key xác minh email; adapter send_confirmation_mail lưu SHA-256(key) vào
`account_emailconfirmation.key` trước commit, raw key chỉ nằm trong thư mã hóa.
Resend xóa key cũ; verify dưới khóa user, single-use, hạn 7 ngày. Không thêm token generator.

Reset dùng generator có sẵn của allauth/Django và SetPasswordForm, uid theo allauth,
hạn 900 giây; không tạo bảng password_reset_tokens riêng. Token bị vô hiệu sau đổi
password/last_login theo thư viện. Nhiều yêu cầu forgot có thể tạo nhiều link cùng hợp lệ
đến khi password/last_login thay đổi; resend forgot không tự vô hiệu link trước.

Mail secret giữ định dạng AES-256-GCM: key_id/nonce/ciphertext/expires_at.
AAD là JSON array UTF-8 `[event_id,event_type,user_id,expires_at]` không khoảng trắng;
nonce 12 bytes, ciphertext gồm tag, base64 cho nonce/ciphertext.
Plaintext activation là `{"key":"..."}`; reset là `{"uid":"...","token":"..."}`.
Notification phải hiểu revision này; Identity không gửi SMTP trực tiếp.
Không log password/token/cookie/link; không lưu plaintext trong audit/outbox.

Outbox ghi toàn event envelope tại cột `data`, nghiệp vụ ở `event.data`.
Publisher/maintenance xóa secret hết hạn và Notification delivery chưa được nghiệm thu;
`published_at` giữ NULL đến Kafka ACK, không giả success.

### 1.7. Đường API trong service và qua Gateway

Các endpoint `/api/v1/...` bên dưới là đường trong service. Theo `infra/nginx/nginx.conf`, gateway bỏ tiền tố `/api/auth/` trước khi chuyển vào Identity: ví dụ client gọi `/api/auth/api/v1/auth/login` thì Identity nhận `/api/v1/auth/login`. Classroom tương tự: `/api/classroom/api/v1/classrooms/{classroom_id}/students/import`.

API `/api/v1/internal/users/provision-students` và resend nội bộ chỉ được gọi backend trực tiếp, dùng X-Service-Key và actor JWT theo mục 3.5. Cấu hình nginx chặn `/api/auth/api/v1/internal/` và path gốc; đã kiểm syntax, chưa nghiệm thu gateway đang chạy. Các API nội bộ đã được kiểm thử local, không phải endpoint public.

---

### 1.8. Kiểm tra JWT và trạng thái phiên liên dịch vụ

JWT dùng RS256, `iss=https://identity.utask.internal`, `aud=utask-platform`, TTL 15 phút; có sub/iat/exp/jti/session_id/token_family. Service vệ tinh xác minh chữ ký rồi gọi `POST /api/v1/internal/auth/session-status` của Identity. Giai đoạn đầu không cache kết quả cho phép; chấp nhận thêm một HTTP call để tránh dùng phiên đã bị thu hồi. Identity lỗi/timeout: 503 IDENTITY_UNAVAILABLE, không cấp quyền. Service vệ tinh không đọc DB Identity.

Endpoint nội bộ nhận Bearer access token cần kiểm tra và X-Service-Key riêng của caller Work/Classroom/AI; Identity kiểm JWT/key cục bộ, không gọi ngược chính endpoint này. Gateway chặn /internal/. Response 200 envelope với `data={"active":true}` hoặc `data={"active":false}`.

active=true chỉ khi user chưa xóa và ACTIVE, session_id thuộc đúng user/token_family, family còn session chưa thu hồi của cùng user_id và expires_at còn hạn. Session_id ổn định qua rotation; access cũ còn dùng đến exp nếu session/family vẫn live. LOGOUT/LOGOUT_ALL/PASSWORD_CHANGED/ADMIN_REVOKED/REPLAY_ATTACK thu hồi các session hoạt động trong family; kiểm tra sau commit trả active=false.

Đăng xuất tất cả chỉ thu hồi family cũ. Đăng nhập lại hợp lệ tạo family mới, dùng được ngay; không dùng khóa user_blocked cho logout-all. Đình chỉ dựa trên users.account_status. Mở lại tài khoản không phục hồi family cũ. Thu hồi global role cũng thu hồi mọi family để người dùng đăng nhập lại lấy roles mới.

Consumer phải dùng verifier JWT của thư viện, hỗ trợ token_type/sub/hash_password và
single-key JWKS của mục 1.2. API session-status đã kiểm tra local. Acceptance Project/Classroom/AI vẫn
là **Not Executed**; caller phải triển khai bước REST này mới có revocation liên dịch vụ.
Kiểm session trong Identity chặn access ngay sau revocation; blacklist refresh đơn thuần
không thu hồi access ở service chỉ kiểm chữ ký.

### 1.9. MSSV, Django Auth và xóa mềm

- Identity giữ student_id như mã đối soát tài khoản duy nhất trong phạm vi UTask hiện tại; MSSV nullable, chuẩn hóa upper(trim), trống thành NULL. Không dùng MSSV thay UUID user_id và không dùng nó để cấp quyền.
- Enrollment của Classroom chỉ liên kết user_id. Classroom lấy MSSV qua API/projection Identity khi cần hiển thị; không lưu bản sao MSSV có quyền chỉnh sửa trong từng enrollment.
- USERNAME_FIELD=email; UserManager kế thừa BaseUserManager chuẩn hóa email lower(trim), tạo username nếu thiếu, dùng set_password/set_unusable_password. is_active là property của account_status=ACTIVE và deleted_at=NULL. Login đi qua Django authenticate/allauth backend và status hooks theo mục 3.1.3; không viết lại check_password/timing mitigation. Global SYSTEM_ADMIN không tự là Django superuser và không tự có quyền project.
- MVP không xóa cứng user. Email/username/MSSV không được tái cấp sau xóa mềm. Register gặp danh tính đã xóa vẫn trả mã trùng tương ứng; provisioning trả ACCOUNT_UNAVAILABLE, không tự tạo user mới. Chỉ Admin khôi phục explicit qua PATCH users/{id}/status với restore_deleted=true và reason; giữ user_id, MSSV, roles và lịch sử, không phục hồi session cũ.
- Bảng user/profile/roles được tạo trong một transaction. Migration phải có CHECK và unique family theo ERD mục 4.1; không dùng validation ứng dụng thay thế các ràng buộc đó.

### 1.10. Chi tiết kỹ thuật được chốt để bàn giao (2026-10-02)

1. Refresh family7 ngày tuyệt đối; login/kích hoạt tạo family mới. Access15 phút. Cookie/body refresh khác nhau trả400; cookie mutation kiểm CSRF/Origin. Web dùng cookie không nhận raw refresh trong body; ví dụ token body dành cho API client.
2. Login sai được Axes signals/middleware lưu; không tự cập nhật counter users. Password đúng mới báo trạng thái. AXES_RESET_COOL_OFF_ON_FAILURE_DURING_LOCKOUT=false. Writer khóa user trước token; actor/target/batch theo UUID tăng dần. Phát sinh khóa ngoài thứ tự: rollback/retry toàn TX-I tối đa3 lần, hết mức lỗi hạ tầng chung, không success giả.
3. Receipt provisioning scope (actor_user_id,endpoint_path,key); Registration hiện từ chối Idempotency-Key400; không có receipt đăng ký. DB unique + transaction-level tuple lock claim trước nghiệp vụ; cùng canonical-body hash replay status/body, khác hash422. Canonical JSON sắp khóa cố định, normalize email/MSSV, giữ nguyên thứ tự students; password chỉ tham gia hash, không lưu raw request. Registration receipt không token. Không key: unique indexes chống account trùng, không hứa replay response. Giữ receipt ít nhất24 giờ; client chỉ retry trong24 giờ, sau đó key mới và resolve account hiện có. Classroom retry JSON đã cố định, không parse lại thành payload khác.
4. OAuth bước start phía server theo3.3.0; context Redis10 phút, atomic one-use, gắn provider/URI/browser và user_id khi link. Chỉ server giữ nonce/PKCE verifier. Client phải giữ cookie context; Redis outage503 IDENTITY_UNAVAILABLE, không bỏ qua context.
5. Avatar receipt Redis300 giây owner/key/type/size; confirm kiểm receipt, HEAD R2 thật ngoài TX-I. Key đã là avatar chính user trả200 no-op; confirm khác không receipt trả400. Public URL derive server. Orphan dùng lifecycle R2, không DELETE dữ liệu tài khoản.
6. Admin/internal delegated mutation kiểm role hiện tại trong DB sau khóa actor/target, không chỉ JWT roles. Role no-op không phát event/revoke mới; role đổi thật revoke mọi family target. Không project bypass cho Admin.
7. Outbox.data lưu **toàn Kafka envelope**, gồm trace_id và data nghiệp vụ lồng bên trong; id/type/version/aggregate/created_at mirror envelope phải khớp. Publisher gửi envelope đã lưu, không tạo event_id/occurred_at mới khi retry. Một Celery poller active không overlap, lease Redis owner/TTL được giữ khi publish. Read oldest (created_at,id); event lỗi cùng user không bị vượt. ACK rồi crash trước mark gây duplicate. Nhiều poller cần fencing/claim riêng trước triển khai, không hứa “thứ tự tuyệt đối” từ partition key.
8. GitHub reconcile theo3.7.1 trước update projection/replay/backfill; outage phải retry, không verified từ event cũ. Public/batch giữ policy Bearer toàn hệ thống hiện tại; không tự thêm quyền cùng lớp nếu sản phẩm chưa đổi contract.

### 1.11. Trạng thái API và thư viện ở phiên bản1.7

25 thao tác đang bật mặc định; 6 OAuth qua IDENTITY_GOOGLE_ENABLED/IDENTITY_GITHUB_ENABLED,
2 avatar qua IDENTITY_AVATAR_ENABLED (mặc định false, bật phải có đủ R2 configuration).
OpenAPI xuất bằng drf-spectacular từ config.urls và serializers thật qua
[export_identity_api](../../apps/identity-service/accounts/management/commands/export_identity_api.py). Schema mặc định không
tự mở routes gated hoặc chứng minh provider acceptance. Swagger UI và schema JSON có tại
`/api/schema/swagger/` và `/api/schema/` cho phát triển local; Nginx không route hai đường này.

Response giữ success/message/data/meta/error. Message là thông điệp hiển thị, client phân
nhánh bằng HTTP status/error.code. Library validation dùng400 VALIDATION_ERROR cho đăng ký,
password/reset. Access JWT lỗi dùng INVALID_TOKEN/TOKEN_EXPIRED; credentials đã thay hoặc
session revoked dùng401. Các mã riêng reset/weak-password/duplicate email trong bảng lịch
sử dưới đây không thay thế contract thư viện đã ghi tại3.1/3.2.

Provisioning nhận tối đa100 JSON rows/request. Lỗi từng dòng trả trong results; lỗi hạ tầng
rollback toàn batch. Receipt được giữ không xóa trong implementation hiện tại (ít nhất24h).
User/profile/role/activation/mail outbox/receipt cùng commit; retry không enqueue thư mới.
Không nhận CSV/XLSX hoặc tạo enrollment tại Identity. Backend key riêng mỗi caller cấu hình
qua IDENTITY_SERVICE_KEYS JSON (classroom/work/ai/integration), không có secret mặc định.
Snapshot current role sau user lock quyết định mutations, không Django staff/superuser.

Avatar dùng boto3 presigned PUT300 giây + Redis owner/session/key/type/size receipt.
HEAD R2 ngoài transaction, recheck user/session trước commit. HEAD không chứng minh nội dung
là ảnh an toàn và URL PUT còn hiệu lực có thể overwrite object trước hết hạn. Chưa chạy R2 thật.

## 2. Bảng Mã Lỗi Chuẩn Toàn cục (Global Identity Error Registry)

| Mã lỗi (`error.code`) | HTTP Status | Ý nghĩa nghiệp vụ |
| :--- | :--- | :--- |
| `AUTHENTICATION_REQUIRED` | 401 | Yêu cầu Bearer Token hợp lệ trên header Authorization. |
| `INVALID_CREDENTIALS` | 401 | Email hoặc mật khẩu không chính xác. |
| `ACCOUNT_PENDING_ACTIVATION` | 403 | Tài khoản sinh viên được import từ danh sách lớp chưa hoàn tất kích hoạt. |
| `ACCOUNT_SUSPENDED` | 403 | Tài khoản đã bị Quản trị viên vô hiệu hóa toàn diện. |
| `REFRESH_TOKEN_EXPIRED` | 401 | Refresh Token đã hết hạn sử dụng. Cần đăng nhập lại. |
| `REFRESH_TOKEN_REVOKED` | 401 | Refresh Token đã bị thu hồi do đăng xuất. |
| `TOKEN_REPLAY_ATTACK_DETECTED`| 401 | Phát hiện token đã xoay vòng bị sử dụng lại; toàn bộ phiên bị hủy vì an ninh. |
| `EMAIL_ALREADY_EXISTS` | 409 | Địa chỉ email đã được đăng ký trong hệ thống. |
| `USERNAME_ALREADY_EXISTS` | 409 | Tên người dùng / username định danh đã tồn tại. |
| `STUDENT_ID_ALREADY_EXISTS` | 409 | Mã số sinh viên (MSSV) đã gắn với tài khoản khác. |
| `STUDENT_ID_NOT_FOUND` | 404 | Không tìm thấy sinh viên theo MSSV truy vấn. |
| `INVALID_ACTIVATION_TOKEN` | 400 | Mã kích hoạt tài khoản không hợp lệ hoặc đã qua sử dụng. |
| `ACTIVATION_TOKEN_EXPIRED` | 400 | Mã kích hoạt tài khoản đã hết hạn (quá 7 ngày). |
| `INVALID_RESET_TOKEN` | 400 | Mã khôi phục mật khẩu không hợp lệ hoặc đã sử dụng. |
| `RESET_TOKEN_EXPIRED` | 400 | Mã khôi phục mật khẩu đã quá hạn 15 phút. |
| `WEAK_PASSWORD` | 400 | Mật khẩu không đáp ứng chính sách bảo mật (tối thiểu 8 ký tự, chữ, số, ký tự đặc biệt). |
| `FORBIDDEN_TEACHER_OR_ADMIN` | 403 | Chỉ Giảng viên hoặc Quản trị viên hệ thống mới có quyền truy cập endpoint này. |
| `FORBIDDEN_ADMIN_ONLY` | 403 | Thao tác đặc quyền chỉ dành riêng cho Quản trị viên cấp cao (`SYSTEM_ADMIN`). |
| `RATE_LIMIT_EXCEEDED` | 429 | Gửi quá nhiều yêu cầu xác thực trong khoảng thời gian ngắn. |
| `IDEMPOTENT_REPLAY_ACTIVE` | 409 | Một yêu cầu mang Idempotency-Key này đang trong quá trình xử lý. |
| `VALIDATION_ERROR` | 400 | Dữ liệu đầu vào sai kiểu, thiếu trường bắt buộc hoặc vi phạm regex. |
| `INVALID_TOKEN` | 401 | Chữ ký/thuật toán/kid/claim JWT không hợp lệ. |
| `TOKEN_EXPIRED` | 401 | JWT Access Token hết hạn. |
| `TOKEN_REVOKED` | 401 | Access Token đã bị thu hồi. |
| `SESSION_NOT_FOUND` | 404 | Session không tồn tại trong phạm vi user. |
| `IDEMPOTENCY_KEY_REQUIRED` | 400 | Provisioning hoặc Classroom import thiếu key. |
| `IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD` | 422 | Cùng actor/path/key nhưng nội dung khác. |
| `SERVICE_ACCESS_DENIED` | 403 | API nội bộ thiếu/sai X-Service-Key. |
| `PERMISSION_DENIED` | 403 | Classroom: Student hoặc Teacher không phụ trách lớp. |
| `ACCOUNT_ALREADY_ACTIVE` | 400 | Resend kích hoạt cho user đã ACTIVE. |
| `INCORRECT_CURRENT_PASSWORD` | 400 | Mật khẩu hiện tại không khớp. |
| `PASSWORD_CANNOT_BE_SAME_AS_OLD` | 400 | Mật khẩu mới trùng mật khẩu hiện tại. |
| `STUDENT_ID_IMMUTABLE` | 403 | Tự sửa MSSV tại users/me. |
| `INVALID_IMAGE_TYPE` | 400 | Loại ảnh không thuộc whitelist. |
| `FILE_SIZE_EXCEEDS_LIMIT` | 400 | Ảnh vượt 5 MB. |
| `OAUTH_ACCOUNT_ALREADY_LINKED` | 409 | Provider account đã thuộc user khác. |
| `CANNOT_UNLINK_ONLY_AUTH_METHOD` | 400 | Chưa có mật khẩu dự phòng sử dụng được. |
| `CANNOT_REVOKE_OWN_ADMIN_ROLE` | 400 | Actor tự thu hồi SYSTEM_ADMIN. |
| `IDENTITY_UNAVAILABLE` | 503 | Không kiểm tra được trạng thái phiên qua Identity; không cấp quyền. |
| `RESOURCE_NOT_FOUND` | 404 | Không tìm thấy tài nguyên trong phạm vi được phép. |
| `OAUTH_STATE_INVALID` | 400 | State/context thiếu, sai, hết hạn, đã dùng hoặc không khớp actor/provider/URI. |
| `OAUTH_AUTHENTICATION_FAILED` | 400 | Provider code/token/nonce sai hoặc domain tạo account không được phép. |
| `OAUTH_PROVIDER_UNAVAILABLE` | 503 | Không liên lạc được provider; không link/cấp phiên. |
| `INVALID_UPLOAD_REFERENCE` | 400 | File key không do server cấp cho user hoặc receipt hết hạn. |
| `UPLOAD_NOT_FOUND` | 404 | R2 chưa có object cần confirm. |
| `UPLOAD_METADATA_MISMATCH` | 400 | Size/type thực tế không khớp receipt/policy. |
| `STORAGE_UNAVAILABLE` | 503 | Không xác minh được upload qua R2; không đổi avatar. |
| `API_ERROR` | Theo status | Lỗi API tổng quát ngoài mã nghiệp vụ đã khai báo. |
| `INTERNAL_SERVER_ERROR` | 500 | Lỗi nội bộ không xác định từ hạ tầng Identity Service. |

---

## 3. Đặc tả Chi tiết các Nhóm API Endpoints

---

### 3.1. Phân nhóm Xác thực & Quản lý Phiên (Authentication & Session)

#### 3.1.1. Lấy Khóa Công khai Xác thực Token (JWKS - JSON Web Key Set)
* **Phương thức:** `GET`
* **Đường dẫn:** `/api/v1/auth/.well-known/jwks.json`
* **Xác thực:** Công khai (Anonymous). Cache TTL: 24 giờ.
* **Ngoại lệ envelope:** JWKS trả đối tượng `{"keys": [...]}` trực tiếp theo chuẩn JWKS, không bọc envelope năm trường. JWT header bắt buộc có `alg=RS256` và `kid`; bên nhận chọn khóa theo `kid`, làm mới JWKS khi gặp kid chưa biết, chỉ chấp nhận kid có trong bộ khóa. Giữ khóa cũ ít nhất 15 phút sau lần cuối phát token bằng khóa đó.
* **Mô tả:** Cung cấp bộ khóa công khai (RSA Public Keys) theo chuẩn RFC 7517 để API Gateway và các satellite microservices (`work-service`, `classroom-service`, `ai-service`) tự xác thực chữ ký Access Token mà không cần gọi vào `identity_db`.

* **Phản hồi Thành công (HTTP 200 OK):**
```json
{
  "keys": [
    {
      "kty": "RSA",
      "use": "sig",
      "alg": "RS256",
      "kid": "utask-identity-key-2026",
      "n": "u1g...public_modulus...",
      "e": "AQAB"
    }
  ]
}
```

---

#### 3.1.2. Register Student

POST `/api/v1/auth/register`, Anonymous, dj-rest-auth RegisterView/RegisterSerializer.
Request: `email, username, password1, password2, first_name, last_name`.
Không nhận role/MSSV/extra field. Password qua validators Django (min 8, không common/numeric,
độ tương tự user và chữ hoa/chữ thường/số/ký tự đặc biệt).
201: `data={"user":{...},"account_status":"PENDING_ACTIVATION"}`, không cấp JWT.
User/profile/STUDENT/audit/outbox cùng transaction. Idempotency-Key chưa hỗ trợ, gửi key
trả 400 thay vì giả receipt. Email/username trùng trả 400 VALIDATION_ERROR, giữ unique DB.

#### 3.1.3. Login bằng email hoặc username

POST `/api/v1/auth/login`, Anonymous. Request: đúng một trong `email, username`,
`password`, `device_name` tùy chọn. Normalize lower/trim identifier.
200: `data={"access":"<JWT>","refresh":"","user":{...}}` và cookie refresh.
dj-rest-auth LoginView thực thi; Django authenticate/allauth backend kiểm password và
timing mitigation; Axes giữ lockout. User/session được recheck dưới khóa user trước cấp token.
Bearer cũ đã revoked không cản login mới. GET `/api/v1/users/me` dùng UserDetailsView; PATCH bổ sung qua profile service,
trả profile/roles của chính user, không cấp quyền Project/Classroom từ staff/global role.

#### 3.1.4. Refresh/rotation/replay

POST `/api/v1/auth/refresh`, Anonymous, body `{"refresh":"<JWT>"}` hoặc cookie.
200: `data={"access":"<JWT>","access_expiration":"..."}`, cookie refresh mới.
SimpleJWT TokenRefreshSerializer thực hiện rotation/blacklist, adapter khóa user và
cập nhật hash/jti session ổn định. Hạn session/cookie/token không vượt family 7 ngày.
Replay còn hạn thu hồi family và audit trước 401; lỗi DB rollback rotation/blacklist.
401 token không hợp lệ/đã revoke; 403 nếu cookie thiếu CSRF/Origin đúng; 400 khi hai nguồn khác nhau.

#### 3.1.5. Logout

POST `/api/v1/auth/logout`, Bearer bắt buộc; refresh body/cookie tùy chọn.
Nếu cung cấp refresh, thư viện xác minh và adapter kiểm cùng user/family.
Dưới khóa user, dùng refresh hiện tại trong outstanding tokens của SimpleJWT để dj-rest-auth
blacklist/xóa cookie rồi revoke session. Vì vậy logout vẫn thắng family khi refresh cạnh tranh
đã rotate trước. 200 `data=null`. Access cũ bị chặn ngay ở Identity sau commit.

#### 3.1.6. Logout-all

POST `/api/v1/auth/logout-all`, Bearer. Recheck current session dưới khóa user,
blacklist token live bằng model SimpleJWT, revoke mọi device, xóa cookie.
200 `data={"revoked_sessions_count":N}`. Login mới tạo family mới và hoạt động ngay.

#### 3.1.7. Danh sách phiên/thiết bị

GET `/api/v1/auth/sessions`, Bearer. Chỉ session live/chưa hết hạn của user hiện tại.
Mỗi hàng: `id, token_family, device_name, ip_address, is_current, created_at, expires_at`.
`id` và `token_family` đều ổn định qua rotation; is_current so family.

#### 3.1.8. Thu hồi thiết bị

DELETE `/api/v1/auth/sessions/{session_id}`, Bearer. Lookup trong scope request.user,
khóa user/recheck current session rồi revoke family. 200 `data=null`,
404 SESSION_NOT_FOUND nếu không có/không thuộc user. Không hồi sinh phiên đã revoked.

### 3.2. Recovery/activation theo thư viện

#### 3.2.1. Forgot password

POST `/api/v1/auth/password-reset/request`, Anonymous, `{"email":"..."}`.
dj-rest-auth PasswordResetView + AllAuthPasswordResetForm; chọn user đủ điều kiện dưới khóa user.
200 trung tính, `data=null`; thư được enqueue mã hóa vào outbox, chưa hứa delivery.

#### 3.2.2. Reset confirm

POST `/api/v1/auth/password-reset/confirm`, Anonymous.
Request: `uid, token, new_password1, new_password2`.
dj-rest-auth PasswordResetConfirmSerializer kiểm generator và SetPasswordForm;
adapter kiểm lại token/trạng thái dưới khóa user để hai request không cùng đổi password.
Chỉ ACTIVE chưa xóa; Axes lockout không đổi trạng thái user. Không restore suspended/pending/deleted.
200 `data=null`; revoke mọi session với PASSWORD_CHANGED; reset Axes counter của user.
Mã sai/hết hạn/đã dùng và mật khẩu yếu trả 400 VALIDATION_ERROR theo thư viện.

#### 3.2.3. Activation/verification và resend

POST `/api/v1/auth/activate`, Anonymous, `{"key":"<allauth key>"}`.
Imported user có unusable password phải thêm `new_password1,new_password2` qua SetPasswordForm.
allauth xác minh email, adapter chuyển PENDING → ACTIVE, đồng bộ is_email_verified,
consume mọi key cũ, audit/outbox cùng transaction. 200 `data=null`, không tự login/cấp JWT.
Mã sai/hết hạn/đã dùng: 404; trạng thái không phù hợp: 400; validation password: 400.

POST `/api/v1/auth/activation/resend`, Anonymous, `{"email":"..."}`.
200 trung tính; chỉ user PENDING chưa xóa được enqueue key mới, key cũ bị vô hiệu.
Provisioning/internal resend đã có route backend theo3.5; không công khai qua gateway, không thay Classroom enrollment acceptance.

#### 3.2.4. Change password

POST `/api/v1/auth/password-change`, Bearer.
Request: `old_password,new_password1,new_password2`.
dj-rest-auth PasswordChangeView/Serializer + SetPasswordForm; adapter recheck credential/session
dưới khóa user. Password cũ sai/mới yếu/trùng cũ trả 400 VALIDATION_ERROR.
200 `data=null`; **thu hồi mọi phiên, gồm thiết bị hiện tại**, yêu cầu login lại.
Đây là đổi contract từ chính sách cũ giữ family hiện tại.

### 3.3. Phân nhóm Tích hợp Đăng nhập Mạng xã hội (OAuth 2.0 Integration)

#### 3.3.0. Khởi tạo OAuth phía server

* **Phương thức:** POST
* **Đường dẫn:** `/api/v1/auth/oauth/{provider}/start`; provider lowercase google/github.
* **Xác thực:** google Anonymous; github Bearer/current session bắt buộc. Rate limit10 requests/phút/IP.
* **Request:** `{"redirect_uri":"https://utask.edu.vn/auth/callback/google"}`; URI khớp chính xác whitelist theo provider.
* **Success200:** envelope chuẩn với `data={"authorization_url":"https://accounts.google.com/o/oauth2/v2/auth?...","expires_in":600}`.
* **Server:** state ngẫu nhiên256 bit; Redis key SHA256(state), value gồm provider/URI/context-cookie hash/actor_user_id(github)/nonce(google)/PKCE verifier. Context cookie ngẫu nhiên HttpOnly/Secure/SameSite=Lax. Authorization URL có state, nonce(google), code_challenge S256, không trả verifier.
* **Exchange:** POST google/github nhận code/state/redirect_uri + context cookie. Validate binding rồi consume context **atomic** một lần; sai400 OAUTH_STATE_INVALID và chưa gọi provider. Google verify signature/iss/aud/exp/nonce/email_verified; GitHub: Identity gửi code/code_verifier qua API backend Integration theo3.3.2.1; chỉ Integration đổi code và gọi GitHub /user. Network ngoài TX-I. Context consumed nhưng exchange/commit lỗi: start mới.
* **Fail:** provider/URI/input sai400 VALIDATION_ERROR; session github401; Redis503 IDENTITY_UNAVAILABLE; provider theo registry. Không lưu token/code vào DB/log.
* Redis TTL600 giây, không thêm bảng OAuth context. API client giữ cookie context; GitHub chỉ link, không login.

#### 3.3.1. Đăng nhập / Liên kết Tài khoản Google (Google OAuth2 Callback / Exchange)
* **Phương thức:** `POST`
* **Đường dẫn:** `/api/v1/auth/oauth/google`
* **Xác thực:** Công khai (Rate Limit: 10 requests/phút/IP).
* **Mô tả:** Đổi Google Authorization Code lấy thông tin người dùng từ Google IdP. Nếu email thuộc tên miền trường đại học (`@*.edu.vn`) và chưa có tài khoản, hệ thống tự động khởi tạo tài khoản mới với vai trò `STUDENT`.

* **Request Body:**
```json
{
  "code": "4/0AdLIrYcbvQ...",
  "state": "server-issued-oauth-state",
  "redirect_uri": "https://utask.edu.vn/auth/callback/google"
}
```

* **Quy trình Xử lý Nghiệp vụ:**
  1. Verify/consume OAuth context theo3.3.0; thiếu/sai state trả400 trước provider. Gửi request sang Google Token API để đổi `code` lấy `id_token` và `access_token`.
  2. Giải mã và xác thực chữ ký của Google `id_token`: lấy `sub` (Google User ID), `email`, `email_verified`, `name`, `picture`.
  3. Chỉ chấp nhận Google token đã kiểm chữ ký, iss/aud/exp/nonce và email_verified=true. Sau khi resolve user, kiểm trạng thái trước khi liên kết/cấp token: user đã xóa bị từ chối; SUSPENDED trả 403 ACCOUNT_SUSPENDED; PENDING_ACTIVATION trả 403 ACCOUNT_PENDING_ACTIVATION, không tự kích hoạt. Khóa user và kiểm lại trong giao dịch. Axes chỉ chặn password login, không tự chặn Google hoặc thay đổi account_status.
   4. Tra cứu `socialaccount_socialaccount` của allauth với `provider = 'GOOGLE'` và `provider_user_id = sub`:
     - **Trường hợp A: Đã liên kết trước đó:** Lấy tài khoản `User` tương ứng, cập nhật `last_login_at`, cấp Access/Refresh Token và đăng nhập thành công.
     - **Trường hợp B: Chưa liên kết nhưng Email đã tồn tại trong `users`:** Tự động tạo bản ghi liên kết mới trong `socialaccount_socialaccount`, cập nhật `is_email_verified = TRUE`, cấp token đăng nhập.
     - **Trường hợp C: Chưa tồn tại cả tài khoản lẫn liên kết:**
       - Kiểm tra chính sách tên miền trường học (Domain Whitelist: `@*.edu.vn`).
       - Tự động tạo bản ghi `users` với `account_status = 'ACTIVE'`, `is_email_verified = TRUE`, mật khẩu Django không sử dụng được (set_unusable_password), cho đến khi người dùng tự đặt mật khẩu.
       - Tự động tạo `user_profiles` với tên từ Google và `avatar_url = picture`.
       - Gán vai trò mặc định `STUDENT` trong `user_global_roles`.
       - allauth tạo SocialAccount; không lưu provider token.
       - Ghi bản ghi transactional outbox `identity.user.created` để đồng bộ sang Kafka.
       - Cấp cặp Access/Refresh Token đăng nhập.

* **Phản hồi Thành công (HTTP 200 OK):**
```json
{
  "success": true,
  "message": "Đăng nhập bằng tài khoản Google thành công.",
  "data": {
    "access": "<SimpleJWT access>",
    "refresh": "",
    "user": {
      "id": "b2c1d3e4-5f6a-7b8c-9d0e-1f2a3b4c5d6e",
      "email": "sinhvien.k16@university.edu.vn",
      "display_name": "Nguyễn Văn Sinh Viên",
      "avatar_url": "https://lh3.googleusercontent.com/a/ACg8oc...",
      "roles": ["STUDENT"]
    }
  },
  "meta": null,
  "error": null
}
```

---

#### 3.3.2. Liên kết Tài khoản GitHub (GitHub OAuth2 Link)
* **Phương thức:** `POST`
* **Đường dẫn:** `/api/v1/auth/oauth/github`
* **Xác thực:** Bearer Token bắt buộc (Người dùng phải đã đăng nhập UTask).
* **Mô tả:** Liên kết tài khoản GitHub cá nhân vào hồ sơ UTask để chứng thực đóng góp code tự động theo PRD Mục 7.4.

* **Request Body:**
```json
{
  "code": "gho_16C7e42F292c6912E771...",
  "state": "server-issued-oauth-state",
  "redirect_uri": "https://utask.edu.vn/settings/integrations/github"
}
```

* **Xử lý:**
  1. Identity verify/consume context bước start gắn đúng user đang login; sinh operation_id và gửi request backend tới Integration theo3.3.2.1 ngoài TX-I. Identity không gọi GitHub token API hoặc /user.
  2. Integration dùng PKCE verifier để đổi code và gọi GitHub /user; trả immutable github_user_id/login cùng operation_id/user_id. Identity kiểm response schema/binding/expiry rồi mới mở TX-I và recheck current session. Email có thể null; không cần quyền đọc email riêng.
  3. Kiểm tra xem GitHub ID này đã bị liên kết bởi tài khoản UTask khác hay chưa (`uq_oauth_provider_uid`). Nếu đã có $\rightarrow$ trả về `409 OAUTH_ACCOUNT_ALREADY_LINKED` *"Tài khoản GitHub này đã được liên kết với một tài khoản UTask khác."*
  4. Link lại đúng ID đã có trả200 no-op; user đã link ID khác trả409 OAUTH_ACCOUNT_ALREADY_LINKED, cần unlink trước. Lưu bản ghi mới vào `oauth_accounts` (`provider = 'GITHUB'`).
  5. Cập nhật `user_profiles(github_username)`.
  6. Ghi identity.user.updated cho display github_username; phát identity.oauth.github_linked với user_id/github_username/github_user_id. Integration nhận bằng chứng danh tính từ Identity, lưu projection rồi phát github.account.verified; Work chỉ nhận sự kiện đã chuẩn hóa của Integration để xác minh project_members. Identity không trực tiếp bật cờ xác minh member hay liên kết commit.

* **Phản hồi Thành công (HTTP 200 OK):**
```json
{
  "success": true,
  "message": "Liên kết tài khoản GitHub thành công.",
  "data": {
    "provider": "GITHUB",
    "github_username": "octocat-student",
    "linked_at": "2026-10-01T09:15:00Z"
  },
  "meta": null,
  "error": null
}
```

---

#### 3.3.2.1. Identity → Integration: xác minh GitHub cá nhân

**Hợp đồng thiết kế đích, chưa triển khai.** Integration sở hữu provider HTTP; Identity sở hữu OAuth context, liên kết tài khoản và quyền ghi identity_db.

* **POST** `/api/v1/internal/oauth/github/exchange` trong Integration; gateway không công khai. HTTPS/backend network, `X-Service-Key` riêng Identity→Integration, allowlist chỉ caller Identity. Không nhận trực tiếp từ UI; key sai/thiếu403 SERVICE_ACCESS_DENIED.
* Identity đã xác thực Bearer và consume state hợp lệ trước gọi. user_id lấy từ token đã xác minh, không từ body UI. Code/verifier chỉ chuyển backend, không log/raw request receipt.
* Request:
```json
{
  "operation_id": "7a9513e2-2222-4333-8444-555555555555",
  "user_id": "b2c1d3e4-5f6a-7b8c-9d0e-1f2a3b4c5d6e",
  "provider": "GITHUB",
  "code": "provider-authorization-code",
  "code_verifier": "server-held-pkce-verifier",
  "redirect_uri": "https://utask.edu.vn/settings/integrations/github",
  "expires_at": "2026-10-02T09:10:00Z"
}
```
* Integration kiểm UUID, provider=GITHUB, redirect_uri exact allowlist, expires_at UTC còn hạn và không quá600 giây từ hiện tại. operation_id scoped caller/user; ghi nhận canonical request hash + trạng thái in-flight/success để serialize cùng operation. Chỉ Integration gọi token endpoint rồi /user ngoài transaction DB dài; provider access token chỉ RAM.
* Response200 envelope chuẩn:
```json
{
  "success": true,
  "message": "Đã xác minh tài khoản GitHub.",
  "data": {
    "operation_id": "7a9513e2-2222-4333-8444-555555555555",
    "user_id": "b2c1d3e4-5f6a-7b8c-9d0e-1f2a3b4c5d6e",
    "provider": "GITHUB",
    "github_user_id": "12345678",
    "github_username": "octocat-student",
    "verified_at": "2026-10-02T09:05:00Z",
    "expires_at": "2026-10-02T09:10:00Z"
  },
  "meta": null,
  "error": null
}
```
* Identity chỉ tin response từ endpoint backend cấu hình của Integration: operation_id/user_id/provider/expiry phải khớp request, github_user_id là string numeric, username hợp lệ; reply thiếu/sai/binding lệch503 OAUTH_PROVIDER_UNAVAILABLE, không OAuth/session/outbox mutation. UI không được gửi github_user_id/username/proof thay code.
* Same operation/same hash khi đã success: trả receipt200 đã lưu trong window600 giây, không provider call lần nữa; hash khác422 IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD; còn in-flight409 IDEMPOTENT_REPLAY_ACTIVE. Receipt chỉ normalized identity + binding/hash/status, không code/verifier/provider token; code/verifier góp vào hash nhưng không lưu bản rõ.
* Hết hạn400 OAUTH_STATE_INVALID; code/provider proof sai400 OAUTH_AUTHENTICATION_FAILED; provider/network/Internal Integration5xx503 OAUTH_PROVIDER_UNAVAILABLE. Internal key lỗi là lỗi cấu hình backend, Identity trả503 không tiết lộ secret.
* Identity timeout tối đa5 giây, không blind-retry token exchange. Nếu chưa biết operation đã success, có thể retry cùng operation trong window để đọc receipt; nếu provider exchange đã xảy ra nhưng kết quả chưa được lưu bền vững thì trả503 và start OAuth mới. Không nhận replay callback state cũ đã consume hoặc coi code dùng lại là idempotent.
* Nhận proof không tạo link ở Integration hoặc verified membership ở Project. Identity khóa user/recheck session rồi commit OAuth/profile/audit/outbox; normalized github.account.* chỉ phát qua luồng3.7 sau link commit.
* Đây là thêm hợp đồng backend cho luồng đã có, không thêm service/công nghệ. Schema/receipt implementation thuộc Integration và phải có tests tương ứng; không sao chép receipt table Identity sang DB khác để giả đã triển khai.

#### 3.3.3. Hủy Liên kết Tài khoản Mạng xã hội (Unlink OAuth Provider)
* **Phương thức:** `DELETE`
* **Đường dẫn:** `/api/v1/auth/oauth/{provider}`
* **Tham số URL:** `provider` = `GOOGLE` hoặc `GITHUB`.
* **Xác thực:** Bearer Token bắt buộc.
* **Quy tắc An toàn:** Không cho phép hủy liên kết Google nếu has_usable_password() = False; trả 400 CANNOT_UNLINK_ONLY_AUTH_METHOD. Không dùng password_hash IS NULL vì Django unusable password vẫn là chuỗi NOT NULL.
* Không có OAuth row trả404 RESOURCE_NOT_FOUND; provider sai400 VALIDATION_ERROR.
* **GITHUB:** Khóa user, xóa OAuth account, clear github_username hiển thị, ghi identity.user.updated và identity.oauth.github_unlinked với user_id/github_user_id trước khi xóa. Integration phát github.account.unverified; Work chỉ clear xác minh của mapping cùng GitHub ID, không xóa bằng chứng task/commit cũ.

* **Phản hồi Thành công (HTTP 200 OK):**
```json
{
  "success": true,
  "message": "Đã hủy liên kết tài khoản GITHUB thành công.",
  "data": null,
  "meta": null,
  "error": null
}
```

---

### 3.4. Phân nhóm Hồ sơ Người dùng & Tải lên Avatar

#### 3.4.1. Lấy Thông tin Bản thân (Get Current User Profile)
* **Phương thức:** `GET`
* **Đường dẫn:** `/api/v1/users/me`
* **Xác thực:** Bearer Token bắt buộc.
* **Mô tả:** Trả về toàn diện thông tin cá nhân, vai trò toàn cục, thông số sinh viên và cài đặt giao diện.

* **Phản hồi Thành công (HTTP 200 OK):**
```json
{
  "success": true,
  "message": "Lấy thông tin người dùng thành công.",
  "data": {
    "id": "b2c1d3e4-5f6a-7b8c-9d0e-1f2a3b4c5d6e",
    "email": "sinhvien.k16@university.edu.vn",
    "username": "sinhvienk16",
    "student_id": "20210001",
    "first_name": "Sinh Viên",
    "last_name": "Nguyễn Văn",
    "display_name": "Nguyễn Văn Sinh Viên",
    "avatar_url": "https://pub-r2.utask.edu.vn/avatars/user_1.png",
    "phone_number": "0987654321",
    "bio": "Sinh viên ngành Kỹ thuật Phần mềm K16. Định hướng Backend & AI.",
    "github_username": "octocat-student",
    "academic_year": "K16",
    "faculty": "Khoa Công nghệ Thông tin",
    "timezone": "Asia/Ho_Chi_Minh",
    "roles": ["STUDENT"],
    "preferences": {
      "theme": "dark",
      "notification_email": true
    },
    "created_at": "2026-09-01T00:00:00Z"
  },
  "meta": null,
  "error": null
}
```

---

#### 3.4.2. Cập nhật Hồ sơ Bản thân (Update Profile)
* **Phương thức:** `PATCH`
* **Đường dẫn:** `/api/v1/users/me`
* **Xác thực:** Bearer Token bắt buộc.
* **Mô tả:** Cập nhật thông tin họ tên, số điện thoại, tiểu sử, cài đặt. Không cho phép sửa `email` tại endpoint này (400 VALIDATION_ERROR); gửi `student_id` trả 403 STUDENT_ID_IMMUTABLE.

* **Request Body:**
```json
{
  "first_name": "Văn A",
  "last_name": "Nguyễn",
  "phone_number": "0912345678",
  "bio": "Cập nhật định hướng Full-stack Engineer.",
  "preferences": {
    "theme": "system",
    "notification_email": false
  }
}
```

* **Xử lý:** Cập nhật bảng `user_profiles`. Kích hoạt Trigger tạo lại `display_name = "Nguyễn Văn A"`. Ghi Outbox `identity.user.updated` sang Kafka để `work-service` đồng bộ `user_projections`.

* **Phản hồi Thành công (HTTP 200 OK):**
```json
{
  "success": true,
  "message": "Cập nhật hồ sơ cá nhân thành công.",
  "data": {
    "display_name": "Nguyễn Văn A",
    "phone_number": "0912345678",
    "bio": "Cập nhật định hướng Full-stack Engineer.",
    "preferences": {
      "theme": "system",
      "notification_email": false
    }
  },
  "meta": null,
  "error": null
}
```

---

#### 3.4.3. Yêu cầu Presigned URL Tải lên Avatar (Cloudflare R2 Direct Upload)
* **Phương thức:** `POST`
* **Đường dẫn:** `/api/v1/users/me/avatar/presigned-url`
* **Xác thực:** Bearer Token bắt buộc.
* **Mô tả:** Sinh URL ký trước (Presigned PUT URL) để client tải ảnh trực tiếp lên Cloudflare R2, tránh nghẽn băng thông backend UTask.

* **Request Body:**
```json
{
  "file_name": "profile_photo.png",
  "content_type": "image/png",
  "file_size": 1048576
}
```

* **Quy tắc Kiểm tra:**
  1. `content_type` bắt buộc thuộc whitelist: `image/jpeg`, `image/png`, `image/webp`; sai trả 400 INVALID_IMAGE_TYPE.
  2. `file_size` không được vượt quá **5 MB** (5,242,880 bytes); vượt trả 400 FILE_SIZE_EXCEEDS_LIMIT.
  3. file_size phải >0; extension sinh từ MIME whitelist. Lưu receipt Redis300 giây owner/key/type/size trước trả URL; Redis lỗi503 IDENTITY_UNAVAILABLE.
  4. Định dạng S3 Key: `avatars/{user_id}/{timestamp}_{uuid}.png`.

* **Phản hồi Thành công (HTTP 200 OK):**
```json
{
  "success": true,
  "message": "Khởi tạo URL tải ảnh đại diện thành công.",
  "data": {
    "upload_url": "https://r2-upload.utask.edu.vn/avatars/user_1/1759276800_photo.png?X-Amz-Signature=...",
    "public_url": "https://pub-r2.utask.edu.vn/avatars/user_1/1759276800_photo.png",
    "file_key": "avatars/user_1/1759276800_photo.png",
    "expires_in": 300
  },
  "meta": null,
  "error": null
}
```

---

#### 3.4.4. Xác nhận Đã Tải lên Avatar Hoàn tất (Confirm Avatar Upload)
* **Phương thức:** `POST`
* **Đường dẫn:** `/api/v1/users/me/avatar/confirm`
* **Xác thực:** Bearer Token bắt buộc.
* **Mô tả:** Sau khi client hoàn tất lệnh HTTP PUT ảnh lên Cloudflare R2, gọi API này để backend kiểm tra và lưu chính thức vào CSDL.

* **Request Body:**
```json
{
  "file_key": "avatars/user_1/1759276800_photo.png"
}
```

* **Xử lý:**
  1. Key đã là avatar hiện tại cùng user trả200 no-op. Nếu chưa: kiểm receipt300 giây/owner/prefix/session; sai400 INVALID_UPLOAD_REFERENCE.
  2. HEAD R2 ngoài TX-I; không có404 UPLOAD_NOT_FOUND; mạng503 STORAGE_UNAVAILABLE; size/type không đúng receipt/policy400 UPLOAD_METADATA_MISMATCH.
  3. Khóa user, recheck session; derive URL server; update profile + outbox identity.user.updated cùng TX-I. Confirm race cùng key đã cập nhật là no-op. Xóa receipt sau commit best-effort; không xóa avatar cũ trong request.

* **Phản hồi Thành công (HTTP 200 OK):**
```json
{
  "success": true,
  "message": "Cập nhật ảnh đại diện thành công.",
  "data": {
    "avatar_url": "https://pub-r2.utask.edu.vn/avatars/user_1/1759276800_photo.png"
  },
  "meta": null,
  "error": null
}
```

---

#### 3.4.5. Truy vấn Thông tin Công khai Người dùng theo ID (Get Public User Profile)
* **Phương thức:** `GET`
* **Đường dẫn:** `/api/v1/users/{user_id}`
* **Xác thực:** Bearer Token bắt buộc.
* **Mô tả:** Cho phép các dịch vụ vệ tinh (`work-service`, `classroom-service`) hoặc thành viên trong hệ thống xem thông tin công khai (avatar, display name, roles, student_id) của một thành viên đồ án/lớp học.

* **Phản hồi Thành công (HTTP 200 OK):**
```json
{
  "success": true,
  "message": "Lấy thông tin người dùng thành công.",
  "data": {
    "id": "b2c1d3e4-5f6a-7b8c-9d0e-1f2a3b4c5d6e",
    "email": "sinhvien.k16@university.edu.vn",
    "student_id": "20210001",
    "display_name": "Nguyễn Văn Sinh Viên",
    "avatar_url": "https://pub-r2.utask.internal/avatars/b2c1d3e4.webp",
    "bio": "Sinh viên K16 ngành Kỹ thuật Phần mềm",
    "roles": ["STUDENT"]
  },
  "meta": {
    "timestamp": "2026-10-01T08:00:00Z",
    "request_id": "req-prof-lookup-01"
  },
  "error": null
}
```

---

#### 3.4.6. Truy vấn Hàng loạt Thông tin Người dùng theo Danh sách IDs (Batch Enrich Users)
* **Phương thức:** `POST`
* **Đường dẫn:** `/api/v1/users/batch`
* **Xác thực:** Bearer Token bắt buộc.
* **Batch:** Validate toàn request; sai UUID/quá100 trả400. Dedup IDs; user không có/đã xóa bỏ khỏi data.users; meta.total là số trả được. Single public user không có/đã xóa404. Không trả preferences/password/token. Policy là mọi Bearer hợp lệ xem allowlist, không claim cùng lớp/project.
* **Mô tả:** Hỗ trợ các microservice vệ tinh (đặc biệt là `work-service` khi render danh sách thành viên dự án, task assignee) truy vấn đồng thời thông tin tối đa 100 người dùng trong 1 request duy nhất, giải quyết triệt để vấn đề N+1 HTTP calls.

* **Request Body:**
```json
{
  "user_ids": [
    "b2c1d3e4-5f6a-7b8c-9d0e-1f2a3b4c5d6e",
    "e5f6a7b8-9c0d-1e2f-3a4b-5c6d7e8f9a0b"
  ]
}
```

* **Phản hồi Thành công (HTTP 200 OK):**
```json
{
  "success": true,
  "message": "Truy vấn danh sách người dùng thành công.",
  "data": {
    "users": [
      {
        "id": "b2c1d3e4-5f6a-7b8c-9d0e-1f2a3b4c5d6e",
        "email": "sinhvien.k16@university.edu.vn",
        "display_name": "Nguyễn Văn Sinh Viên",
        "avatar_url": "https://pub-r2.utask.internal/avatars/b2c1d3e4.webp",
        "student_id": "20210001",
        "roles": ["STUDENT"]
      },
      {
        "id": "e5f6a7b8-9c0d-1e2f-3a4b-5c6d7e8f9a0b",
        "email": "giangvien.cntt@university.edu.vn",
        "display_name": "ThS. Hoàng Văn Giáo Viên",
        "avatar_url": "https://pub-r2.utask.internal/avatars/e5f6a7b8.webp",
        "student_id": null,
        "roles": ["TEACHER"]
      }
    ]
  },
  "meta": {
    "total": 2,
    "timestamp": "2026-10-01T08:00:00Z",
    "request_id": "req-batch-enrich-01"
  },
  "error": null
}
```

---

### 3.5. Cấp tài khoản phục vụ import lớp học (US-1.4)

#### 3.5.1. Hợp đồng Classroom → Identity đã chốt

**API công khai do Classroom sở hữu:** `POST /api/v1/classrooms/{classroom_id}/students/import`.
- Nhận `multipart/form-data` gồm `file` CSV hoặc XLSX; nhận `Idempotency-Key` bắt buộc. Teacher phải phụ trách đúng lớp, hoặc actor có vai trò SYSTEM_ADMIN.
- Classroom kiểm tra quyền trước khi đọc file/gọi Identity; chuẩn hóa email/MSSV, đánh số dòng bằng `row_number`, đánh dấu `DUPLICATE_IN_FILE` cho dòng trùng. Student và Teacher của lớp khác nhận 403 PERMISSION_DENIED.
- Classroom gọi API nội bộ bên dưới với JSON, `Idempotency-Key` và token của actor đã xác thực. Identity không đọc file và không lưu enrollment.
- Sau khi có `user_id` hợp lệ, Classroom kiểm tra lại quyền lớp rồi lưu enrollment bằng ràng buộc duy nhất `(classroom_id, user_id)`; ghi audit trong cùng giao dịch classroom_db. Đã thuộc lớp trả `ALREADY_ENROLLED`.
- Không mở một giao dịch DB xuyên hai service. Nếu Identity đã tạo user nhưng ghi danh lỗi, giữ user đó; Classroom trả dòng `ENROLLMENT_FAILED`, không tuyên bố đã thêm vào lớp. Retry cùng key dùng lại kết quả Identity và chỉ xử lý những dòng ghi danh chưa thành công; không gửi lại thư kích hoạt.
- Phản hồi công khai là 200 khi có báo cáo từng dòng; 503 khi chưa có kết quả Identity do mất kết nối. Báo cáo có `summary` gồm `total_records, created_accounts, existing_accounts, enrolled_count, already_enrolled_count, flagged_records, duplicates_in_file, failed_records`; mỗi `results[]` có `row_number, user_id, account_result, enrollment_result, reason`. Đếm riêng tài khoản và enrollment; thông báo hoàn tất chỉ áp dụng cho dòng ENROLLED/ALREADY_ENROLLED.

**API nội bộ do Identity sở hữu:** `POST /api/v1/internal/users/provision-students`.
- Chỉ Classroom gọi qua mạng backend; gateway không công khai đường `/internal/`. Header `X-Service-Key` là secret riêng Classroom → Identity do backend thêm và kiểm bằng so sánh constant-time; không gửi secret xuống trình duyệt hoặc log. Đồng thời chuyển tiếp `Authorization: Bearer <actor_access_token>`; Identity xác minh RS256/iss/aud và role TEACHER hoặc SYSTEM_ADMIN. Có token người dùng nhưng thiếu/sai service key: 403 SERVICE_ACCESS_DENIED.
- Header `Idempotency-Key: <UUID>` bắt buộc. Receipt dùng khóa duy nhất `(user_id, endpoint_path, idempotency_key)` với user_id là actor từ token. Cùng key/body trả lại receipt; khác body trả 422 IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD. Claim và receipt được xử lý trong cùng transaction với các tài khoản/outbox; khóa giao dịch theo tuple này, không chỉ SELECT rồi chạy nghiệp vụ. Mất phản hồi sau commit: đọc receipt trước khi thực thi lại.
- Không gọi HTTP/gửi mail trong transaction. Dùng savepoint cho từng dòng; lỗi dữ liệu một dòng được báo trong dòng đó, lỗi hạ tầng rollback cả batch. Username cho tài khoản mới do server sinh và giải quyết trùng theo unique index; password dùng Django unusable password đến khi kích hoạt.
- Tra cứu email/MSSV kể cả user xóa mềm để không tái cấp danh tính. Email và MSSV cùng trỏ một user: dùng user đó. Nếu hai mã trỏ hai user, hoặc MSSV có user nhưng email gửi lên khác email đang lưu: IDENTITY_CONFLICT; không tự đổi email/MSSV.
- Khi email đã có user STUDENT ACTIVE/PENDING_ACTIVATION với student_id=NULL và MSSV gửi lên chưa thuộc ai: khóa user, gán mã được Classroom xác nhận, ghi audit/outbox identity.user.updated và trả EXISTING với user_id cũ. MSSV đã có chỉ được giữ nguyên; mã khác trả IDENTITY_CONFLICT. Email-only hợp lệ được tìm/tạo user với MSSV NULL; MSSV-only chỉ tìm user có sẵn, không tạo mới khi thiếu email.
- User đã xóa/SUSPENDED: ACCOUNT_UNAVAILABLE, không khôi phục hay ghi danh. Axes lockout không đổi account_status hoặc chặn provisioning. User TEACHER/SYSTEM_ADMIN: FLAGGED_ROLE_CONFLICT, không thêm STUDENT. User STUDENT đủ điều kiện trả EXISTING; người chưa có tài khoản tạo CREATED/PENDING_ACTIVATION.
- Nếu hai batch khác key cùng tạo/gán một định danh, unique index giải quyết tranh chấp. Bắt IntegrityError trong savepoint, đọc lại danh tính rồi trả EXISTING hoặc IDENTITY_CONFLICT; không đổi chủ sở hữu mã hoặc trả nhầm một user_id.
- Tạo user/profile/STUDENT role/activation hash/audit; hai outbox identity.user.created (projection không secret) và identity.student.imported (mail secret mã hóa) cho tài khoản mới; token gửi thư dùng secret mã hóa theo mục 1.6. Mỗi dòng hợp lệ trả `user_id`; Identity không trả activation token trong HTTP response. Classroom dùng kết quả này để tạo enrollment.
- Trả 201 nếu batch tạo ít nhất một tài khoản; trả 200 nếu không tạo mới. Các dòng lỗi vẫn nằm trong `results`.

Request nội bộ:
```json
{
  "students": [
    {"row_number": 2, "student_id": "20210001", "email": "nguyenvana@university.edu.vn", "first_name": "A", "last_name": "Nguyễn Văn"}
  ]
}
```

Response nội bộ (HTTP 201):
```json
{
  "success": true,
  "message": "Đã xử lý danh sách tài khoản.",
  "data": {
    "summary": {"total_records": 1, "created_accounts": 1, "existing_accounts": 0, "flagged_records": 0, "failed_records": 0},
    "results": [{"row_number": 2, "user_id": "a1b2c3d4-0001-4000-8000-000000000001", "email": "nguyenvana@university.edu.vn", "student_id": "20210001", "account_status": "PENDING_ACTIVATION", "account_result": "CREATED", "reason": null}]
  },
  "meta": null,
  "error": null
}
```

Endpoint công khai cũ `/api/v1/admin/users/batch-import-students` không thuộc hợp đồng được chốt. Các test file CSV/XLSX và enrollment thuộc Classroom; test JSON provisioning thuộc Identity.

#### 3.5.2. Gửi Lại Email Kích hoạt cho Sinh viên (Resend Activation Email)
* **Phương thức:** `POST`
* **Đường dẫn nội bộ:** `/api/v1/internal/users/{user_id}/resend-activation`
* **Xác thực:** X-Service-Key của Classroom và Bearer token actor. Classroom xác minh actor phụ trách lớp có enrollment của user, hoặc actor là SYSTEM_ADMIN, trước khi gọi. User phải PENDING_ACTIVATION; đã ACTIVE trả 400 ACCOUNT_ALREADY_ACTIVE.
* **Mô tả:** Giảng viên hỗ trợ sinh viên khi sinh viên làm thất lạc hoặc hết hạn liên kết kích hoạt 7 ngày.

* **Xử lý:** Khóa actor/target theo UUID tăng dần, recheck current role/session; target chỉ PENDING chưa xóa; audit + outbox identity.activation.requested. Vô hiệu hóa mã cũ, sinh mã mới và chỉ lưu hash trong bảng activation. Outbox gửi thư dùng secret mã hóa theo mục 1.6.

* **Phản hồi Thành công (HTTP 200 OK):**
```json
{
  "success": true,
  "message": "Đã gửi lại email kích hoạt tài khoản thành công cho sinh viên.",
  "data": null,
  "meta": null,
  "error": null
}
```

---

### 3.6. Phân nhóm Quản trị Người dùng Toàn cục (SYSTEM_ADMIN)

#### 3.6.1. Danh sách Người dùng Toàn Hệ thống (Admin List Users)
* **Phương thức:** `GET`
* **Đường dẫn:** `/api/v1/admin/users`
* **Xác thực:** Bearer Token (Quyền `SYSTEM_ADMIN`).
* **Query Parameters:**
  - `search`: Tìm theo email, display_name, username hoặc student_id.
  - `role`: Lọc theo vai trò (`SYSTEM_ADMIN`, `TEACHER`, `STUDENT`).
  - `status`: Lọc theo trạng thái (`ACTIVE`, `PENDING_ACTIVATION`, `SUSPENDED`); `LOCKED` trả lỗi validation.
  - `page`: Số trang (mặc định 1).
  - `limit`: Số bản ghi mỗi trang (mặc định 20, tối đa 100).

* **Phản hồi Thành công (HTTP 200 OK):**
```json
{
  "success": true,
  "message": "Lấy danh sách người dùng thành công.",
  "data": [
    {
      "id": "b2c1d3e4-5f6a-7b8c-9d0e-1f2a3b4c5d6e",
      "email": "giangvien@university.edu.vn",
      "username": "giangvien_cntt",
      "student_id": null,
      "display_name": "TS. Lê Giảng Viên",
      "account_status": "ACTIVE",
      "is_email_verified": true,
      "roles": ["TEACHER"],
      "last_login_at": "2026-10-01T08:00:00Z",
      "created_at": "2026-08-15T00:00:00Z"
    }
  ],
  "meta": {
    "page": 1,
    "limit": 20,
    "total_count": 1,
    "total_pages": 1,
    "has_next": false,
    "next_cursor": null
  },
  "error": null
}
```

---

#### 3.6.2. Thay đổi Trạng thái Tài khoản (Update User Status - Suspend/Unlock)
* **Phương thức:** `PATCH`
* **Đường dẫn:** `/api/v1/admin/users/{user_id}/status`
* **Xác thực:** Bearer Token (Quyền `SYSTEM_ADMIN`).
* **Mô tả:** SYSTEM_ADMIN đổi ACTIVE/SUSPENDED hoặc khôi phục tài khoản xóa mềm bằng restore_deleted=true và reason bắt buộc. Hai dạng lệnh không được gửi cùng nhau; import/register/reset không được khôi phục user.

* **Request Body:**
```json
{
  "status": "SUSPENDED",
  "reason": "Vi phạm quy chế thi và bảo mật đồ án học phần."
}
```

* **Xử lý:**
  1. Khóa user. Lệnh đổi status không áp dụng cho user đã xóa; chỉ nhận ACTIVE/SUSPENDED. Không đổi PENDING_ACTIVATION sang ACTIVE thay luồng kích hoạt. Khi mutation đưa user về ACTIVE, reset Axes cho UUID của user theo API thư viện.
  2. Lệnh khôi phục có body `{"restore_deleted":true,"reason":"..."}`, không nhận status; clear deleted_at, giữ account_status/email/MSSV/roles/user_id và không phục hồi session.
  3. Đình chỉ thu hồi mọi session hoạt động; khôi phục cũng giữ session cũ vô hiệu. Ghi identity.user.status_changed với dữ liệu mới và audit trong cùng transaction.
  4. Response 200 trả user_id, account_status và deleted_at mới. Mọi lỗi dữ liệu/giao dịch rollback toàn bộ.

* **Phản hồi Thành công (HTTP 200 OK):**
```json
{
  "success": true,
  "message": "Cập nhật trạng thái tài khoản người dùng thành công.",
  "data": {
    "user_id": "b2c1d3e4-5f6a-7b8c-9d0e-1f2a3b4c5d6e",
    "account_status": "SUSPENDED",
    "deleted_at": null
  },
  "meta": null,
  "error": null
}
```

---

#### 3.6.3. Gán / Thu hồi Vai trò Toàn cục (Assign / Revoke Global Role)
* **Phương thức:** `POST` / `DELETE`
* **Đường dẫn:** `/api/v1/admin/users/{user_id}/roles`
* **Xác thực:** Bearer Token (Quyền `SYSTEM_ADMIN`).

* **Hợp đồng:** POST gán, DELETE thu hồi; cùng nhận body role_code, không nhận trường action. Thu hồi SYSTEM_ADMIN của chính actor trả 400 CANNOT_REVOKE_OWN_ADMIN_ROLE. Đã đúng trạng thái role yêu cầu trả200 no-op; đổi thật ghi identity.user.role_assigned/identity.user.role_revoked, audit/outbox, thu hồi các family hiện có để token cũ không giữ quyền đã bị gỡ.
* **Request Body (POST/DELETE):**
```json
{
  "role_code": "TEACHER"
}
```

* **Phản hồi Thành công (HTTP 200 OK):**
```json
{
  "success": true,
  "message": "Gán vai trò toàn cục thành công.",
  "data": {
    "user_id": "b2c1d3e4-5f6a-7b8c-9d0e-1f2a3b4c5d6e",
    "roles": ["STUDENT", "TEACHER"]
  },
  "meta": null,
  "error": null
}
```

---

### 3.7. Handoff xác minh GitHub đã thống nhất

- Integration thực hiện OAuth provider proof qua API3.3.2.1; Identity ghi liên kết user đã được chứng minh; Integration là nguồn sự kiện chuẩn hóa tới Work. identity.oauth.github_linked → github.account.verified; identity.oauth.github_unlinked → github.account.unverified.
- Envelope dùng event_id/event_type/event_version/aggregate_id/occurred_at/trace_id/data. Key của các sự kiện account là user_id; consumer deduplicate event_id.
- Data verified có user_id/github_user_id/github_username; unverified có user_id/github_user_id. Work lọc membership ACTIVE theo user_id; chỉ bật verified khi mapping đã có cùng ID hoặc username đang chờ trùng username đã xác minh (không phân biệt hoa/thường). Không gán bằng chứng của user A cho user B.
- Sự kiện account cần được xử lý theo thứ tự thay đổi của cùng user, gồm cả link/unlink. Nếu khôi phục/replay từ lịch sử phải đối soát trạng thái mapping hiện tại trước khi bật lại; không lấy event cũ làm bằng chứng hiện hành.
- github_username trong UserProfile là display projection. Username nhập ở Work không phải bằng chứng sở hữu account; Teacher/Leader không tự bật verified.

#### 3.7.1. Đối soát GitHub mapping hiện tại

* **GET** `/api/v1/internal/users/{user_id}/oauth/GITHUB`; chỉ Integration bằng X-Service-Key riêng, không actor Bearer; gateway không công khai.
* **200** envelope chuẩn, `data={"user_id":"uuid","mapping":{"provider_user_id":"12345","github_username":"octocat"}}`. User không có/đã xóa/chưa link trả200 mapping:null để clear projection; không email/metadata/provider token.
* Key sai403 SERVICE_ACCESS_DENIED; UUID sai400; outage503 IDENTITY_UNAVAILABLE. Caller outage retry, không tự verified.
* Integration dedup và reconcile trước update projection/normalized outbox/replay/backfill. Historical link không còn cùng ID hiện tại không verified; unlink chỉ clear matching old ID, không clear mapping mới.
* Snapshot không phải distributed lock. Stream same-user live giữ thứ tự; event mới hiệu chỉnh projection. Repository installation/webhook không nằm trong endpoint này.

## 4. Hợp đồng Sự kiện Apache Kafka (Event Contract Specification)

* **Topic:** `utask.identity.events`
* **Partition Key:** `user_id` (thứ tự broker nhận trong partition, không phải exactly-once/thứ tự nghiệp vụ giữa nhiều producer).

**Chuẩn v1 đã chọn cho thiết kế:** trường nghiệp vụ là `data`, không chấp nhận đồng thời hoặc thay thế bằng `payload`. Cột JSONB của outbox Identity cũng tên `data`, giữ kiểu JSONB; không đổi `payload_hash` của receipt/request. event_id/time/trace không đổi khi retry. Chưa có migration/producer triển khai trong checkout; đây không phải ALTER TABLE đã thực thi. Nếu phát hiện môi trường khác đang dùng tên cũ, lập migration/consumer compatibility trước rollout, không tự xóa dữ liệu.

### 4.1. Sự kiện `identity.user.created`
Được phát khi có tài khoản mới được tạo (qua Đăng ký, Google OAuth, hoặc Import sinh viên).
```json
{
  "event_id": "9a8b7c6d-5e4f-3a2b-1c0d-e9f8a7b6c5d4",
  "event_type": "identity.user.created",
  "aggregate_type": "user",
  "aggregate_id": "b2c1d3e4-5f6a-7b8c-9d0e-1f2a3b4c5d6e",
  "occurred_at": "2026-10-01T08:00:00Z",
  "event_version": 1,
  "trace_id": "trace-uuid",
  "producer": "identity-service",
  "data": {
    "user_id": "b2c1d3e4-5f6a-7b8c-9d0e-1f2a3b4c5d6e",
    "email": "sinhvien.k16@university.edu.vn",
    "username": "sinhvienk16",
    "student_id": "20210001",
    "display_name": "Nguyễn Văn Sinh Viên",
    "avatar_url": "https://pub-r2.utask.edu.vn/avatars/user_1.png",
    "account_status": "ACTIVE",
    "roles": ["STUDENT"]
  }
}
```

---

### 4.2. Sự kiện `identity.user.updated`
Được phát khi người dùng thay đổi Họ tên, Ảnh đại diện, Username hoặc GitHub Username. `work-service` lắng nghe sự kiện này để cập nhật bảng chiếu đọc `user_projections`.
```json
{
  "event_id": "8b7c6d5e-4f3a-2b1c-0d9e-f8a7b6c5d4e3",
  "event_type": "identity.user.updated",
  "aggregate_type": "user",
  "aggregate_id": "b2c1d3e4-5f6a-7b8c-9d0e-1f2a3b4c5d6e",
  "occurred_at": "2026-10-01T08:30:00Z",
  "event_version": 1,
  "trace_id": "trace-uuid",
  "producer": "identity-service",
  "data": {
    "user_id": "b2c1d3e4-5f6a-7b8c-9d0e-1f2a3b4c5d6e",
    "display_name": "Nguyễn Văn A (Cập nhật)",
    "student_id": "20210001",
    "avatar_url": "https://pub-r2.utask.edu.vn/avatars/user_1_new.png",
    "github_username": "octocat-student"
  }
}
```

---

### 4.3. Schema version1 cho các luồng còn lại

Envelope theo4.1: event_id/type/aggregate_type/aggregate_id/occurred_at/event_version/trace_id/producer/data. aggregate_type=user; aggregate_id=data.user_id; UUID user/event, time ISO8601 UTC. **Cột JSONB outbox_events.data lưu toàn envelope; dữ liệu nghiệp vụ là event.data, tức outbox_events.data["data"].**

| event_type | Khi phát / data nghiệp vụ bắt buộc | Consumer |
| --- | --- | --- |
| identity.user.created | Register/Google/new imported user; snapshot user_id,email,username,student_id(nullable),display_name,avatar_url(nullable),account_status,roles | Work/Classroom projection |
| identity.user.updated | Profile/avatar/MSSV/display GitHub đổi thật; user_id,display_name,student_id,avatar_url,github_username(nullable) | Work/Classroom projection |
| identity.user.activated | Activation; user_id,account_status=ACTIVE,is_email_verified=true | Work/Classroom projection |
| identity.user.status_changed | Admin status/restore; user_id,account_status,deleted_at(nullable) | Projection; không thay session-status runtime |
| identity.user.role_assigned / identity.user.role_revoked | Role đổi thật; user_id,role_code,roles(sau đổi),actor_id | Projection; không cấp quyền project |
| identity.password_reset.requested | Reset eligible; user_id,email,expires_at,secret(AES-GCM) | Notification reset template |
| identity.student.imported | New imported account; user_id,email,student_id(nullable),expires_at,secret(AES-GCM) | Notification activation template |
| identity.activation.requested | Resend eligible; user_id,email,expires_at,secret(AES-GCM) | Notification activation template |
| identity.oauth.github_linked | Link mới; user_id,github_user_id(string numeric immutable),github_username | Integration → github.account.verified |
| identity.oauth.github_unlinked | Unlink; user_id,github_user_id(captured trước delete) | Integration → github.account.unverified |

Mail secret null **chỉ khi expires_at hết hạn** theo1.6; consumer skip trước decrypt. user.created không có mail secret, kể cả import. Non-mail snapshot không phone/bio/preferences/password/IP/audit reason. Unsupported version/malformed không cập nhật projection; retry/DLQ có audit, không skip như success.

## 5. Cấu trúc Mã nguồn Mẫu & Middleware Thực thi (Framework Implementation)

### 5.1. Bộ Xử lý Ngoại lệ Hợp nhất (`unified_exception_handler`)
Bảo đảm 100% các lỗi sinh ra từ validation, database constraint hoặc authentication đều trả về Single Unified Envelope chuẩn mực:

```python
# apps/identity-service/common/exceptions.py
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework.exceptions import (
    AuthenticationFailed, NotAuthenticated, PermissionDenied,
    ValidationError, ParseError, NotFound, Throttled,
)

def unified_identity_exception_handler(exc, context):
    response = exception_handler(exc, context)
    status_code = response.status_code if response is not None else 500
    error_code = "INTERNAL_SERVER_ERROR"
    message = "Hệ thống gặp lỗi nội bộ. Vui lòng thử lại sau."
    details = []
    detail = getattr(exc, "detail", None)

    if isinstance(exc, (ValidationError, DjangoValidationError, ParseError)):
        status_code, error_code = 400, "VALIDATION_ERROR"
        message = "Dữ liệu đầu vào không hợp lệ."
        values = detail if isinstance(detail, dict) else getattr(exc, "message_dict", None)
        if isinstance(values, dict):
            details = [
                {"field": str(field), "issue": str(issues[0] if isinstance(issues, list) and issues else issues)}
                for field, issues in values.items()
            ]
        else:
            details = [{"issue": "Dữ liệu đầu vào không hợp lệ."}]
    elif isinstance(exc, (NotAuthenticated, AuthenticationFailed)):
        status_code, error_code = 401, "AUTHENTICATION_REQUIRED"
        message = "Yêu cầu xác thực tài khoản."
    elif isinstance(exc, PermissionDenied):
        status_code, error_code = 403, "PERMISSION_DENIED"
        message = "Bạn không có quyền thực hiện thao tác này."
    elif isinstance(exc, NotFound):
        status_code, error_code = 404, "RESOURCE_NOT_FOUND"
        message = "Không tìm thấy tài nguyên."
    elif isinstance(exc, Throttled):
        status_code, error_code = 429, "RATE_LIMIT_EXCEEDED"
        message = "Quá nhiều yêu cầu. Vui lòng thử lại sau."
    elif response is not None:
        error_code = str(getattr(exc, "default_code", "API_ERROR")).upper()
        message = str(detail) if isinstance(detail, str) else "Yêu cầu thất bại."

    # Mã nghiệp vụ nằm trong detail, không đọc getattr(exc, "code").
    if isinstance(detail, dict) and "code" in detail:
        error_code = str(detail["code"])
        message = str(detail.get("message", message))
        provided_details = detail.get("details", [])
        details = provided_details if isinstance(provided_details, list) else []

    envelope = {
        "success": False, "message": message, "data": None, "meta": None,
        "error": {"code": error_code, "details": details},
    }
    # Giữ header Retry-After/WWW-Authenticate của DRF khi có.
    headers = dict(response.items()) if response is not None else {}
    return Response(envelope, status=status_code, headers=headers)
```

---

### 5.2. Renderer Đóng gói Khung Phản hồi (`UnifiedJSONRenderer`)
Đảm bảo các View viết thông thường tự động được bọc trong Single Unified Envelope:

```python
# apps/identity-service/common/renderers.py
from rest_framework.renderers import JSONRenderer

class UnifiedJSONRenderer(JSONRenderer):
    def render(self, data, accepted_media_type=None, renderer_context=None):
        response = renderer_context.get("response") if renderer_context else None

        # Nếu đã được bọc bởi exception_handler hoặc view đóng gói sẵn
        if isinstance(data, dict) and "success" in data and "error" in data:
            return super().render(data, accepted_media_type, renderer_context)

        status_code = response.status_code if response else 200
        is_success = 200 <= status_code < 300

        envelope = {
            "success": is_success,
            "message": "Thao tác thực hiện thành công." if is_success else "Yêu cầu thất bại.",
            "data": data if is_success else None,
            "meta": None,
            "error": None if is_success else {"code": "API_ERROR", "details": []}
        }
        return super().render(envelope, accepted_media_type, renderer_context)
```
