# Lộ trình frontend (Frontend Roadmap): tích hợp Identity trước

**Trạng thái tài liệu: Kế hoạch (Thiết kế mục tiêu).** Phần hiện trạng (§2–§4)
đã đối chiếu với mã nguồn nhánh `dev`, HEAD `933f785` (merge PR #20
`feat/web-kanban-dnd`), ngày 17/10/2026. Các đợt ở §5 **chưa được triển khai**.
Lần rà soát này chỉ đọc mã, cấu hình và test; **không chạy test hay service nào**.
Số test ghi trong tài liệu là số hàm/khối test đếm được trong mã, không phải kết
quả chạy.

**Quyết định ưu tiên (17/10/2026):** đội ưu tiên nối **Identity Service** vào
frontend trước. Work, AI, Classroom, Integration, Notification **làm sau**. Trong
lúc đó các màn của những service này tiếp tục chạy **Demo MSW**. Hiện trạng của
chúng được giữ ở [Phụ lục A](#phụ-lục-a-hiện-trạng-các-service-làm-sau) để
không phải khảo sát lại.

Chi tiết màn hình nằm ở [student-flow.md](student-flow.md),
[teacher-flow.md](teacher-flow.md) và [kanban-board.md](kanban-board.md); tài liệu
này chỉ trỏ tới.

## 1. Cách đọc

- **Nguồn ranh giới service**: [kiến trúc](../system/architecture.md),
  [quyền sở hữu dữ liệu](../system/data-ownership.md),
  [giao tiếp REST và Kafka](../system/communication.md). Nguồn nghiệp vụ tài khoản:
  [đặc tả API Identity](../architecture/Identity_Service_API_Specification.md) (đối
  chiếu với mã; khi lệch, mã nguồn là sự thật hiện tại).
- **Nhãn trạng thái** theo [quy ước chung](../system/README.md): `Đã triển khai`,
  `Một phần`, `Chưa triển khai`, `Thiết kế mục tiêu`, `Chưa xác minh`; thêm
  **Demo MSW** = chạy được với mock (MSW — Mock Service Worker, chặn request ngay
  trong trình duyệt), chưa có backend thật.
- **Ba loại câu**: **Sự thật** (có dẫn file trong repo), **Khuyến nghị** (đề xuất
  của roadmap), **Câu hỏi mở** (cần đội khác quyết định, gom ở §6 và §9).
- **Thuật ngữ**:
  - *Envelope*: lớp bọc chung của phản hồi JSON `{success, message, data, meta, error}`.
  - *DTO* (Data Transfer Object): kiểu dữ liệu đúng hình dạng backend trả về.
  - *Adapter*: lớp mã đổi DTO sang kiểu dữ liệu giao diện (UI model).
  - *Access token*: JWT ngắn hạn gửi trong header `Authorization: Bearer`.
  - *Refresh token*: token dài hạn để lấy access token mới; ở đây nằm trong cookie
    HttpOnly mà JavaScript không đọc được.
  - *CSRF*: tấn công giả mạo request; Django đòi token CSRF khi xác thực bằng cookie.
  - *Single-flight refresh*: nhiều request cùng gặp 401 chỉ gây **một** lần refresh.
  - *Persona demo*: tài khoản giả trong dữ liệu MSW (Leader, Member, Teacher…).
- **Hợp đồng**: Identity sinh OpenAPI lúc chạy (`GET /api/auth/openapi/`), **chưa
  commit file spec** vào `contracts/`
  ([contracts/api/README.md](../../contracts/api/README.md)). Nhu cầu gửi backend ở
  §6 là yêu cầu, **không phải schema**.

### 1.1 Thay đổi so với bản trước

| Bản trước | Bản này | Lý do |
| --- | --- | --- |
| HEAD `83af5e7`; Work, AI "chưa có mã" | HEAD `933f785`; Work và AI đã merge (Phụ lục A) | PR #17, #19 |
| Identity là một trong nhiều mảng; Đợt 2 dựng P0 trên MSW | Identity là trọng tâm duy nhất của giai đoạn này; các service khác làm sau | Quyết định ưu tiên của đội |
| "Chế độ lai" ghi là cần thử nghiệm | Có thiết kế cụ thể: cầu nối persona (§5, Đợt 0) | Handler MSW chỉ nhận token `mock-access:<id>:`; token Identity thật làm mọi trang mock trả 401 |
| Đăng xuất phải chờ giải pháp CSRF | Đăng xuất thật bằng `DELETE /api/auth/sessions/{id}`, không cần CSRF | [views/devices.py](../../apps/identity-service/authentication/views/devices.py) |
| Đăng ký → kích hoạt "chạy với Identity thật" | Chưa làm được end-to-end vì email chỉ ghi vào outbox mã hóa, không có bên gửi | [messaging/outbox.py](../../apps/identity-service/messaging/outbox.py) |

Giữ lại: adapter riêng cho Identity, tách DTO khỏi UI model, MSW cho phần chưa
nối, không thành công giả, backend quyết định quyền, test hồi quy theo từng bước.

## 2. Hiện trạng backend

### 2.1 Bảng service

Đường dẫn trình duyệt = tiền tố gateway + route của service, vì
[nginx.conf](../../infra/nginx/nginx.conf) cắt tiền tố (`rewrite ^/api/<svc>/(.*)$ /$1`).

| Service | Mức sẵn sàng | Mã nguồn | URL trình duyệt (ví dụ) | Test (đếm `def test_`) | Trong giai đoạn này |
| --- | --- | --- | --- | --- | --- |
| **Identity** | **Đã triển khai, có test** (chưa chạy lại) | [apps/identity-service](../../apps/identity-service) | `POST /api/auth/login` | 134 | **Nối thật** |
| Work | Đã triển khai, xác minh một phần | [apps/work-service](../../apps/work-service) | `GET /api/work/projects/` | 276 | Làm sau, giữ Demo MSW |
| AI | Một phần | [apps/ai-service](../../apps/ai-service) | — (gateway lệch path) | 122 | Làm sau |
| Classroom, Integration, Notification | Chưa triển khai (không có thư mục mã) | — | — | — | Làm sau, giữ Demo MSW |

### 2.2 Identity — route và hợp đồng thực tế

Service không thêm tiền tố;
[authentication/urls.py](../../apps/identity-service/authentication/urls.py),
[accounts/urls.py](../../apps/identity-service/accounts/urls.py). Bảng dưới ghi
đường dẫn trình duyệt.

| Nhóm | Endpoint | Body/tham số chính | Xác thực |
| --- | --- | --- | --- |
| Đăng nhập | `POST /api/auth/login` | `email` **hoặc** `username` (đúng một), `password`, `device_name?` | Không (`authentication_classes = []`) |
| Phiên | `POST /api/auth/refresh` | Body rỗng; refresh token từ cookie | Cookie + **CSRF** |
| | `POST /api/auth/logout` | `refresh?` (hoặc cookie) | Bearer; **CSRF nếu có cookie** |
| | `POST /api/auth/logout-all` | — ; trả `revoked_sessions_count` | Bearer; **CSRF nếu có cookie** |
| | `GET /api/auth/sessions` | Trả `id, token_family, device_name, ip_address, is_current, created_at, expires_at` | Bearer |
| | `DELETE /api/auth/sessions/{id}` | Thu hồi một thiết bị; nếu là phiên hiện tại thì xóa cookie | Bearer, **không cần CSRF** |
| Đăng ký | `POST /api/auth/register` | `email`, `username`, `password1`, `password2`, `first_name`, `last_name` | Không; cần khóa mail |
| | `POST /api/auth/activate` | `key`; thêm `new_password1/2` với tài khoản được import | Không |
| | `POST /api/auth/activation/resend` | `email` | Không; cần khóa mail |
| Mật khẩu | `POST /api/auth/password-reset/request` | `email` | Không; cần khóa mail |
| | `POST /api/auth/password-reset/confirm` | `uid`, `token`, `new_password1`, `new_password2` | Không |
| | `POST /api/auth/password-change` | `old_password`, `new_password1`, `new_password2`; sau đó mọi phiên bị thu hồi | Bearer |
| Hồ sơ | `GET /api/auth/users/me` | Trả `id, email, username, student_id, display_name, avatar_url, roles, first_name, last_name, phone_number, bio, github_username, academic_year, faculty, timezone, preferences, created_at` | Bearer |
| | `PATCH /api/auth/users/me` | Sửa được `first_name, last_name, phone_number, bio, academic_year, faculty, timezone, preferences`; không sửa email, MSSV | Bearer |
| | `GET /api/auth/users/{id}`, `POST /api/auth/users/batch` | Hồ sơ công khai của người khác | Bearer |
| Admin | `GET /api/auth/admin/users` | `search`, `role`, `status`, phân trang `limit` | Bearer, `SYSTEM_ADMIN` |
| | `PATCH /api/auth/admin/users/{id}/status` | Đổi `account_status` (kèm lý do) | như trên |
| | `POST`/`DELETE /api/auth/admin/users/{id}/roles` | `role_code` | như trên |
| Khác | `GET /api/auth/healthz`, `/.well-known/jwks.json`, `/openapi/`, `/docs/` | — | Không |

Quy tắc đã có trong mã:

- **Envelope**: `{success, message, data, meta, error}`; lỗi có
  `error: {code, details: [{field, issue}]}`, `data` và `meta` bằng `null`
  ([responses.py](../../apps/identity-service/common/responses.py),
  [exception_handler.py](../../apps/identity-service/common/exception_handler.py)).
  Phân trang theo trang: `meta: {page, limit, total_count, total_pages, has_next}`,
  `limit` mặc định 20, tối đa 100
  ([pagination.py](../../apps/identity-service/common/pagination.py)).
- **Mã lỗi frontend cần xử lý**:
  - Đăng nhập:
    - `INVALID_CREDENTIALS` (401).
    - `ACCOUNT_PENDING_ACTIVATION` (403), `ACCOUNT_SUSPENDED` (403).
    - `RATE_LIMIT_EXCEEDED` (429): khóa sau 5 lần sai, trong 15 phút (django-axes,
      [settings.py](../../apps/identity-service/config/settings.py)).
  - Token và quyền: `TOKEN_EXPIRED`, `INVALID_TOKEN`, `TOKEN_REVOKED`,
    `AUTHENTICATION_REQUIRED`, `PERMISSION_DENIED`, `RESOURCE_NOT_FOUND`,
    `SESSION_NOT_FOUND`.
  - Dữ liệu: `VALIDATION_ERROR` (kèm `details[].field`).
  - Kích hoạt: `INVALID_ACTIVATION_TOKEN`, `ACCOUNT_ALREADY_ACTIVE`.
  - Hạ tầng: `IDENTITY_UNAVAILABLE` (503).
  - Admin: `CANNOT_REVOKE_OWN_ADMIN_ROLE`, `ACCOUNT_UNAVAILABLE`.
  - Header `Retry-After` trên 429 **Chưa xác minh**.
- **Token**:
  - Login trả `data.access`, còn `data.refresh` là chuỗi rỗng. Refresh token chỉ nằm
    trong cookie `refresh_token` (HttpOnly, `Secure` cố định, SameSite=Lax, path
    `/api/auth`).
  - Access token sống 15 phút, refresh 7 ngày, có xoay vòng; dùng lại refresh token
    cũ sẽ thu hồi cả họ token.
  - JWT ký RS256, **không chứa roles** (roles lấy từ `users/me`); có claim
    `session_id`, `token_family`.
- **CSRF**:
  - `refresh` luôn đòi CSRF; `logout` và `logout-all` đòi CSRF khi request mang
    cookie ([serializers/auth.py](../../apps/identity-service/authentication/serializers/auth.py),
    [views/devices.py](../../apps/identity-service/authentication/views/devices.py)).
  - Không endpoint nào cấp cookie `csrftoken`; `CSRF_TRUSTED_ORIGINS` chưa đặt.
  - Test của Identity tự gắn cookie CSRF, nên không phát hiện thiếu sót này.
- **Email**:
  - `register`, `activation/resend`, `password-reset/request` gọi `mail_key()`; thiếu
    `IDENTITY_MAIL_KEY` thì trả 503 `IDENTITY_UNAVAILABLE`
    ([mail_crypto.py](../../apps/identity-service/messaging/mail_crypto.py)).
  - Nếu có khóa, nội dung email (link kích hoạt/đặt lại) được **mã hóa và ghi vào
    outbox**. Repo không có relay hay service gửi mail, nên **không email nào được
    gửi thật**.
  - Link trong email: `{IDENTITY_FRONTEND_URL}/auth/activate?key=` và
    `/auth/reset?uid=&token=`, mặc định `https://localhost`.
- **Tài khoản dev**:
  - Có lệnh `seed_global_roles` và `bootstrap_identity_admin` (tạo `SYSTEM_ADMIN`).
  - **Không có lệnh** tạo sẵn tài khoản Student/Teacher đã kích hoạt.
- **Cờ tính năng**: OAuth Google/GitHub và upload avatar tắt mặc định
  (`IDENTITY_GOOGLE_ENABLED`, `IDENTITY_GITHUB_ENABLED`, `IDENTITY_AVATAR_ENABLED`).

### 2.3 Hạ tầng liên quan Identity

- **Gateway**:
  - nginx chặn `/api/auth/api/v1/internal` bằng 404.
  - Cho phép CORS kèm credentials với `http://localhost:*` và `127.0.0.1:*`; trả 204
    cho preflight ở `/api/auth/`.
  - Chuyển `Host` gốc tới service.
- **Compose**:
  - [docker-compose.yml](../../docker-compose.yml) gốc build cả các service chưa có
    thư mục, và nginx chờ tất cả healthy, nên không dựng được gateway.
  - [docker-compose.staging.yml](../../docker-compose.staging.yml) có nginx chỉ phụ
    thuộc Identity (dùng image, không build).
  - Lệnh chạy Identity + nginx ở máy dev **Chưa xác minh** (G2).
  - Identity cũng mở `127.0.0.1:8001` trực tiếp.
- **Cookie `Secure` trên `http://localhost`**: Chrome và Firefox thường chấp nhận vì
  coi localhost là ngữ cảnh an toàn; **Chưa xác minh** với cấu hình của dự án và
  Safari.
- **CI**: [ci.yml](../../.github/workflows/ci.yml) chỉ chạy cho `main`; job web
  chạy `pnpm lint`, `typecheck`, `test`, `build`.

## 3. Hiện trạng frontend (phần xác thực)

- **File liên quan**:
  - API và trạng thái phiên: [auth.ts](../../apps/web/src/features/auth/api/auth.ts),
    [AuthProvider.tsx](../../apps/web/src/features/auth/AuthProvider.tsx),
    [types.ts](../../apps/web/src/features/auth/types.ts),
    [utils.ts](../../apps/web/src/features/auth/utils.ts).
  - Màn auth: `features/auth/routes/{Login,ForgotPassword,ResetPassword}Route.tsx`
    và form tương ứng.
  - Guard: [RequireAuth.tsx](../../apps/web/src/app/router/RequireAuth.tsx),
    [RequireTeacherSpace.tsx](../../apps/web/src/app/router/RequireTeacherSpace.tsx).
  - Màn cài đặt: `features/notifications/components/Settings{Profile,Security,Integrations}Page.tsx`.
  - Client: [client.ts](../../apps/web/src/lib/api/client.ts),
    [errors.ts](../../apps/web/src/lib/api/errors.ts),
    [ApiClientProvider.tsx](../../apps/web/src/lib/api/ApiClientProvider.tsx).
  - Mock: [mocks/handlers/auth.ts](../../apps/web/src/mocks/handlers/auth.ts).
- **Hành vi hiện tại**:
  - Gọi `/api/auth/api/v1/auth/{login,refresh,logout}`, đọc `access_token`,
    `refresh_token`, `user` ở gốc JSON.
  - Refresh token lưu ở `sessionStorage` chỉ khi bật mock; tắt mock thì tải lại
    trang là mất phiên.
  - User có `global_role`, `capabilities`, `roles?`; khoảng 25 file đọc user hoặc
    `useAuth`.
  - Client không đọc envelope, không có `error.code`, không gửi `credentials`, không
    refresh khi gặp 401 (chỉ xóa phiên).
  - Trang cài đặt đọc/ghi `/api/work/api/v1/me/settings` (MSW), không phải
    `users/me`. Đổi mật khẩu chỉ hiện toast. "Quên mật khẩu" và "Đặt lại mật khẩu"
    không gọi API.
  - Chưa có màn đăng ký, kích hoạt, danh sách thiết bị, Admin.
- **Ràng buộc của MSW** (quan trọng cho chế độ lai):
  - Mọi handler domain xác định người dùng bằng regex
    `^Bearer mock-access:([^:]+):`, viết lặp lại ở
    [studentFlow.ts](../../apps/web/src/mocks/handlers/studentFlow.ts),
    [myWork.ts](../../apps/web/src/mocks/handlers/myWork.ts),
    [teacherFlow.ts](../../apps/web/src/mocks/handlers/teacherFlow.ts) và `auth.ts`.
    Token JWT thật không khớp, nên mọi trang mock sẽ trả 401.
  - Persona demo đăng nhập bằng `leader@utask.test`, `member@utask.test`,
    `student@utask.test`… ([mocks/data/database.ts](../../apps/web/src/mocks/data/database.ts)).
  - [enableMocking.ts](../../apps/web/src/mocks/enableMocking.ts) bật toàn bộ hoặc
    tắt toàn bộ (`VITE_ENABLE_MOCKS`); request không có handler đi thẳng ra mạng.
- **Kiểm thử**: Vitest, Testing Library, MSW node; 18 file, khoảng 375 khối
  `it(`/`test(`. `pnpm lint` chỉ là `tsc --noEmit`; không có ESLint, Prettier,
  Playwright, proxy Vite.
- **Nợ kỹ thuật liên quan**:
  - MSW có thể bật ở bản build production khi `VITE_ENABLE_MOCKS=true`, trái với
    `apps/web/README.md`.
  - [HomeRoute.tsx](../../apps/web/src/app/routes/HomeRoute.tsx) không được tham
    chiếu.
  - `@vitejs/plugin-react` nằm ở `dependencies`.

## 4. Điểm lệch và ma trận năng lực

### 4.1 Điểm lệch frontend ↔ Identity

| # | Chủ đề | Frontend hiện tại | Identity thật | Xử lý ở |
| --- | --- | --- | --- | --- |
| M1 | Đường dẫn | `/api/auth/api/v1/auth/login` | `/api/auth/login` | Đợt 1 |
| M2 | Envelope | Đọc JSON thô | `{success, message, data, meta, error}` | Đợt 0 |
| M3 | Lỗi | `detail`, `non_field_errors` | `error.code`, `error.details[]` | Đợt 0 |
| M4 | Body login | `{email, password}` | `email` hoặc `username`, `password`, `device_name?` | Đợt 1 |
| M5 | Token | `access_token`, `refresh_token`, `expires_in` ở gốc | `data.access`; refresh trong cookie HttpOnly | Đợt 1, 3 |
| M6 | User | `global_role`, `capabilities` | `roles[]` và hồ sơ trong `users/me` | Đợt 1 |
| M7 | Refresh, khôi phục phiên | Body `{refresh_token}`, `sessionStorage` | Cookie path `/api/auth` + CSRF | Đợt 3 (chờ G1) |
| M8 | Đăng xuất | Body `{refresh_token}` | `logout` cần CSRF khi có cookie; `DELETE sessions/{id}` thì không | Đợt 1 |
| M9 | Cùng origin | Không có proxy Vite; `credentials` mặc định | Cookie path `/api/auth`; CORS chỉ localhost | Đợt 0 |
| M10 | Hồ sơ | `/api/work/api/v1/me/settings` (MSW) | `GET`/`PATCH /api/auth/users/me` | Đợt 2 |
| M11 | Link email | `/reset-password` (đã thay bằng `/auth/reset`; xem [api-integration.md](api-integration.md)) | `/auth/activate?key=`, `/auth/reset?uid=&token=` | Đợt 4 |
| M12 | Mock dùng token giả | Handler chỉ nhận `mock-access:<id>:` | JWT RS256 thật | Đợt 0 (cầu nối persona) |

### 4.2 Ma trận năng lực

Phân loại: **Sẵn sàng** = nối thật được ngay; **Sau đổi nhỏ** = cần sửa client/adapter;
**Chặn backend** = thiếu hoặc chưa đủ ở backend; **FE chưa có** = chưa có màn;
**Làm sau** = ngoài giai đoạn Identity, giữ Demo MSW.

| Năng lực | UI/route hiện có | Dữ liệu hiện tại | Endpoint Identity | Khoảng trống | Phân loại — Đợt |
| --- | --- | --- | --- | --- | --- |
| Đăng nhập, điều hướng theo role | `/login`, `HomeRedirect` | MSW | `POST login`, `GET users/me` | M1–M6 | **Sau đổi nhỏ** — 1 |
| Thông báo lỗi đăng nhập | `LoginForm` | MSW | mã lỗi §2.2 | M3 | **Sau đổi nhỏ** — 1 |
| Đăng xuất (thu hồi phiên) | Menu người dùng | MSW | `DELETE sessions/{id}` | M8 | **Sau đổi nhỏ** — 1 |
| Trang khác khi đã đăng nhập thật | Mọi màn | MSW | — | M12 | **Sau đổi nhỏ** (cầu nối) — 0 |
| Hồ sơ đọc/sửa | `/settings/profile` | MSW `me/settings` | `GET`/`PATCH users/me` | M10; trường khác nhau | **Sau đổi nhỏ** — 2 |
| Đổi mật khẩu | `/settings/security` | Chỉ toast | `POST password-change` | — | **Sau đổi nhỏ** — 2 |
| Thiết bị đăng nhập, thu hồi | — | — | `GET sessions`, `DELETE sessions/{id}` | — | **FE chưa có** — 2 |
| Đăng xuất mọi thiết bị | — | — | `POST logout-all` | Cần CSRF khi có cookie (G1) | **FE chưa có** — 3 |
| Khôi phục phiên khi tải lại, tự refresh | `RequireAuth` | MSW `sessionStorage` | `POST refresh` | G1 | **Chặn backend** — 3 |
| Đăng ký, kích hoạt, gửi lại kích hoạt | — | — | `register`, `activate`, `activation/resend` | G3 (không gửi được email) | **FE chưa có** + **Chặn backend** — 4 |
| Quên/đặt lại mật khẩu | `/forgot-password`, `/auth/reset`, `/auth/activate`, `/register` | Đã gọi API thật (Phase 4, xem [api-integration.md](api-integration.md)) | `password-reset/request`, `confirm` | G3; M11 | **Sau đổi nhỏ** + **Chặn backend** — 4 |
| Quản trị tài khoản | — | — | `admin/users`… | Quyết định nghiệp vụ Admin | **FE chưa có** — 5 |
| Liên kết GitHub (OAuth), avatar | Nút ngắt GitHub (MSW) | MSW | OAuth/avatar sau cờ | Cờ tắt; cấu hình OAuth | **Chặn backend** (cấu hình) — 6 |
| Project, Board, Backlog, task, Sprint, comment | Workspace | Demo MSW | — (Work) | Phụ lục A | **Làm sau** |
| Lớp, nhóm, Teacher T01–T10 | `/courses`, `/teacher` | Demo MSW; `/courses` có chế độ Classroom thật (một phần, xem [api-integration](api-integration.md)) | — (Classroom) | Phụ lục A | **Làm sau** |
| Thông báo, My Work, GitHub, AI, khóa AI dự án | Nhiều màn | Demo MSW | — | Phụ lục A | **Làm sau** |

## 5. Lộ trình tích hợp Identity

| Đợt | Nội dung | Bắt đầu được ngay? | Phụ thuộc backend |
| --- | --- | --- | --- |
| 0 | Nền API client, proxy, cầu nối persona cho MSW, môi trường Identity | **Có** | Không cho mã; G2 để thử với Identity thật |
| 1 | Đăng nhập thật, user từ `users/me`, điều hướng theo role, đăng xuất | Sau 0 | Không |
| 2 | Hồ sơ, đổi mật khẩu, thiết bị | Sau 1 | Không |
| 3 | Khôi phục phiên, refresh tự động, đăng xuất mọi thiết bị | Sau 1 | **G1** |
| 4 | Đăng ký, kích hoạt, quên/đặt lại mật khẩu | Sau 1 | Khóa mail; **G3** |
| 5 | Khu quản trị Admin | Sau 2 | Quyết định nghiệp vụ Admin (§9) |
| 6 | Tùy chọn: OAuth GitHub/Google, avatar | Sau 2 | Bật cờ và cấu hình OAuth/lưu trữ |

Đợt 2, 3, 4 độc lập với nhau sau Đợt 1. Có thể làm song song, nhưng chỉ một người
sửa file hạ tầng dùng chung.

**Quy tắc chung**

- **File hạ tầng dùng chung** ([client.ts](../../apps/web/src/lib/api/client.ts),
  [errors.ts](../../apps/web/src/lib/api/errors.ts),
  [ApiClientProvider.tsx](../../apps/web/src/lib/api/ApiClientProvider.tsx),
  `vite.config.ts`, [mocks/handlers.ts](../../apps/web/src/mocks/handlers.ts),
  [AuthProvider.tsx](../../apps/web/src/features/auth/AuthProvider.tsx)) có một
  người phụ trách. Không hai PR song song cùng sửa.
- **Không thành công giả**: khi Identity là thật, lỗi ghi phải hiện lỗi, không bao
  giờ rơi về MSW. Không hiển thị "đã gửi email" nếu backend trả 503.
- **Phân quyền**: frontend dùng `roles` từ `users/me` chỉ để hiển thị khu vực.
  Backend là nơi quyết định (403 `PERMISSION_DENIED`).
- **Bảo mật**: access token chỉ giữ trong bộ nhớ. Không lưu token Identity vào
  `localStorage`/`sessionStorage`. Thông báo lỗi đăng nhập không cho biết email có
  tồn tại hay không.
- **Kiểm tra bắt buộc** (theo [AGENTS.md](../../AGENTS.md)): `pnpm lint`,
  `pnpm typecheck`, `pnpm test`, `pnpm build`; hàm mới có unit test cho đường thành
  công và các nhánh lỗi; tài liệu và nhãn trạng thái cập nhật cùng thay đổi.
- Commit nhỏ dạng `feat(web): …`, `fix(web): …`, `docs(web): …`.

### Đợt 0 — Nền API client, cầu nối persona, môi trường

1. **Mục tiêu và phạm vi**:
   - Client hiểu envelope và mã lỗi của Identity.
   - Web gọi Identity qua gateway cùng origin.
   - Chọn được "Identity thật, phần còn lại MSW" mà các màn mock vẫn chạy.
   - Chưa đổi màn auth nào.
2. **Điều kiện vào**: không.
3. **Việc frontend**:
   - `vite.config.ts`: proxy `/api` tới gateway (mặc định `http://localhost:8080`);
     không đổi `Host`, để Django so Origin với Host đúng.
   - `client.ts`:
     - Tùy chọn bóc envelope và trả `{data, meta}`.
     - Gửi `credentials: "include"`; hỗ trợ header tùy chọn (dùng cho
       `X-CSRFToken` ở Đợt 3).
     - 429 thì đọc `Retry-After` nếu có.
     - Hook `onUnauthorized` có thể trả "đã refresh, gọi lại" (bật ở Đợt 3).
   - `errors.ts`: `ApiError` thêm `code` và `details[]` lấy từ `error`; vẫn đọc
     `detail` để MSW cũ chạy trong thời gian chuyển.
   - Chọn mock theo service:
     - Thêm biến môi trường liệt kê service chạy thật, ví dụ
       `VITE_REAL_SERVICES=auth`; tên biến chốt trong đợt này.
     - Khi `auth` là thật, không đăng ký handler `mocks/handlers/auth.ts`.
   - **Cầu nối persona** (khuyến nghị; chốt trong đợt này):
     - Gom bốn bản regex nhận dạng người dùng trong handler MSW thành **một** helper
       `resolveMockUserId(request)`.
     - Helper vẫn nhận token `mock-access:<id>:` như cũ.
     - Khi Identity là thật, helper dùng persona đã đăng ký sau đăng nhập. Persona
       được chọn theo `users/me.email` khớp email của `MOCK_USERS`
       (`leader@utask.test`…).
     - Không khớp thì trả 403 với thông điệp rõ "tài khoản chưa ánh xạ dữ liệu demo",
       không trả trang trắng.
     - Mã cầu nối chỉ nằm trong `src/mocks/` và chỉ chạy khi MSW được bật; không vào
       bản build production.
   - Adapter `src/lib/api/identity/`: `dto.ts` (đúng shape §2.2), `mappers.ts`,
     `endpoints.ts`.
   - `apps/web/README.md`: cách chạy Identity + nginx và cách tạo tài khoản demo (G2),
     ghi đúng lệnh sau khi đã chạy thử.
   - Chính sách MSW ở production: chặn khi `import.meta.env.PROD`, hoặc sửa README
     cho khớp mã.
4. **Phụ thuộc backend**: không cho mã. G2 (đội Identity/hạ tầng) để thử với
   Identity thật.
5. **Ngoài phạm vi**: đổi màn sang API thật; ESLint/Prettier; Playwright; Work và
   các service khác.
6. **Tiêu chí chấp nhận**:
   - Toàn bộ test hiện có đạt khi mọi service là mock.
   - Unit test client:
     - Bóc envelope thành công.
     - Lỗi có `code`/`details`.
     - 204 và phản hồi không phải JSON.
     - Lỗi mạng (status 0).
     - 429.
     - Có gửi `credentials`.
   - Unit test `resolveMockUserId`: token mock hợp lệ; persona đã đăng ký; không có
     persona trả 403; không có header trả 401.
   - Với `VITE_REAL_SERVICES=auth` và gateway đang chạy, `GET /api/auth/healthz` qua
     proxy Vite trả 200, và MSW không chặn `/api/auth/*`.
7. **Kiểm thử**: Vitest như trên; test hồi quy kéo thả và luồng sinh viên/giảng viên
   phải đạt nguyên trạng.
8. **Rủi ro và rollback**: client ảnh hưởng mọi màn. Giữ hành vi cũ làm mặc định
   (envelope là tùy chọn theo adapter); revert một PR là quay lại được.
9. **Hoàn tất khi**: `pnpm lint`, `typecheck`, `test`, `build` đạt; README có lệnh
   chạy đã thử; tài liệu này cập nhật nhãn Đợt 0.

### Đợt 1 — Đăng nhập, người dùng hiện tại, đăng xuất

1. **Mục tiêu**:
   - Đăng nhập bằng Identity thật, lấy user từ `users/me`, điều hướng theo `roles`.
   - Đăng xuất thu hồi phiên thật.
   - Tải lại trang thì mất phiên; điều này được chấp nhận đến Đợt 3.
2. **Điều kiện vào**: Đợt 0.
3. **Việc frontend**:
   - `features/auth/api/auth.ts` dùng adapter Identity: `POST /api/auth/login` với
     `{email, password, device_name}` (tên trình duyệt), rồi `GET /api/auth/users/me`.
   - `features/auth/types.ts`: thay `global_role`, `capabilities` bằng `roles` và các
     trường hồ sơ cần dùng. Cập nhật các file đọc `user`, gồm guard, sidebar,
     top navigation và hook teacher.
   - `AuthProvider`: giữ access token trong bộ nhớ; bỏ đọc `refresh_token` ở body.
   - Lỗi đăng nhập theo `error.code`:
     - `INVALID_CREDENTIALS`: "email hoặc mật khẩu không đúng".
     - `ACCOUNT_PENDING_ACTIVATION`: hướng dẫn kích hoạt.
     - `ACCOUNT_SUSPENDED`: liên hệ quản trị.
     - `RATE_LIMIT_EXCEEDED`: báo thử lại sau.
     - 503: Identity tạm không sẵn sàng.
   - Đăng xuất (khuyến nghị):
     - `GET /api/auth/sessions` lấy phiên `is_current`, rồi
       `DELETE /api/auth/sessions/{id}`.
     - Endpoint này thu hồi họ token và xóa cookie mà không cần CSRF.
     - Lỗi mạng vẫn xóa phiên cục bộ nhưng báo "chưa thu hồi được trên máy chủ".
   - 401 `TOKEN_EXPIRED`/`TOKEN_REVOKED` thì xóa phiên, về `/login?returnTo=…`
     (chưa refresh).
   - Handler MSW auth đổi sang đúng path và envelope thật, để chế độ full-mock và
     test không lệch.
4. **Phụ thuộc backend**: không.
5. **Ngoài phạm vi**: khôi phục phiên và refresh (Đợt 3); hồ sơ (Đợt 2); đăng ký
   (Đợt 4).
6. **Tiêu chí chấp nhận** (với Identity thật qua gateway):
   - Tài khoản `TEACHER` vào `/teacher`, tài khoản `STUDENT` vào `/my-work`.
   - Sai mật khẩu 5 lần thì nhận thông báo khóa tạm.
   - Đăng xuất xong, `GET /api/auth/sessions` từ thiết bị khác không còn phiên đó.
   - Với cầu nối persona, đăng nhập bằng `leader@utask.test` thật vẫn mở workspace
     demo.
7. **Kiểm thử**:
   - Unit test mapper `users/me` → user giao diện.
   - Unit test map mã lỗi → thông điệp.
   - Test `LoginForm` với MSW trả envelope và từng mã lỗi.
   - Test guard theo role.
   - Test đăng xuất (thành công, `SESSION_NOT_FOUND`, lỗi mạng).
8. **Rủi ro và rollback**:
   - Đổi kiểu `AuthUser` chạm khoảng 25 file; làm trong một PR có `tsc` bảo vệ.
   - Rollback: bỏ `auth` khỏi `VITE_REAL_SERVICES`.
9. **Hoàn tất khi**: kiểm tra bắt buộc đạt; đã thử thủ công với Identity thật và ghi
   lại môi trường đã thử; [student-flow.md](student-flow.md) cập nhật nhãn đăng nhập.

### Đợt 2 — Hồ sơ, đổi mật khẩu, thiết bị

1. **Mục tiêu**:
   - `/settings/profile` đọc/sửa `users/me`.
   - `/settings/security` đổi mật khẩu thật, xem và thu hồi thiết bị.
2. **Điều kiện vào**: Đợt 1.
3. **Việc frontend**:
   - Hồ sơ:
     - Form dùng đúng trường sửa được (§2.2); email, MSSV, username chỉ đọc.
     - `VALIDATION_ERROR` hiện lỗi theo `details[].field`.
   - Đổi mật khẩu:
     - Gửi `old_password`, `new_password1`, `new_password2`.
     - Thành công thì mọi phiên bị thu hồi; báo cho người dùng và đưa về `/login`.
   - Thiết bị:
     - Danh sách `GET sessions` (tên thiết bị, IP, thời điểm, nhãn "thiết bị này").
     - Thu hồi từng thiết bị bằng `DELETE sessions/{id}`; thu hồi thiết bị hiện tại
       thì đăng xuất.
   - Phần đang dựa trên `me/settings` mà Identity không có (ngắt GitHub, tùy chọn
     thông báo) giữ Demo MSW và ghi nhãn rõ.
   - `preferences` có ý nghĩa gì **Chưa xác minh**; chưa dùng cho đến khi Identity mô
     tả.
4. **Phụ thuộc backend**: không.
5. **Ngoài phạm vi**: avatar, liên kết GitHub (Đợt 6); đăng xuất mọi thiết bị (Đợt 3).
6. **Tiêu chí chấp nhận**:
   - Sửa tên rồi tải lại dữ liệu thấy tên mới.
   - Mật khẩu mới trùng mật khẩu cũ bị từ chối, lỗi hiện tại trường.
   - Đổi mật khẩu xong, thiết bị khác bị đăng xuất ở request kế tiếp.
   - Thu hồi một thiết bị thì danh sách cập nhật.
7. **Kiểm thử**: unit test mapper và form (thành công, lỗi trường, 401, 503); test
   danh sách thiết bị (rỗng, nhiều, thu hồi lỗi).
8. **Rủi ro và rollback**: trang cài đặt đang lấy cả dữ liệu không thuộc Identity; tách
   rõ nguồn từng khối, rollback theo `VITE_REAL_SERVICES`.
9. **Hoàn tất khi**: như quy tắc chung.

### Đợt 3 — Phiên bằng cookie: khôi phục, refresh, đăng xuất mọi thiết bị

1. **Mục tiêu**:
   - Tải lại trang vẫn còn phiên.
   - Refresh chủ động trước khi access token hết hạn (15 phút).
   - Single-flight refresh khi nhiều request cùng gặp 401.
   - Đăng xuất mọi thiết bị.
2. **Điều kiện vào**: Đợt 1; **G1 đã chốt và triển khai**.
3. **Việc frontend**:
   - `AuthProvider` gọi `POST /api/auth/refresh` khi khởi động, kèm `X-CSRFToken`
     theo cách G1 quy định.
   - Client giữ một promise refresh dùng chung; mỗi request chỉ được gọi lại tối đa
     một lần.
   - Bỏ hoàn toàn việc lưu refresh token phía JavaScript.
   - `POST /api/auth/logout-all` hiện số phiên đã thu hồi.
   - Có thể chuyển đăng xuất sang `POST logout` khi CSRF đã có (không bắt buộc).
4. **Phụ thuộc backend** (Identity):
   - Cách SPA lấy CSRF token.
   - `CSRF_TRUSTED_ORIGINS` gồm origin web khi dev và staging.
   - Xác nhận cookie `Secure` khi dev trên `http://localhost`.
5. **Ngoài phạm vi**: OAuth.
6. **Tiêu chí chấp nhận**:
   - Đăng nhập → tải lại → vẫn đăng nhập.
   - Để access token hết hạn → request kế tiếp tự refresh và thành công.
   - Hai request đồng thời gặp 401 chỉ gây một lần refresh.
   - Dùng lại refresh token cũ thì UI về `/login`.
   - `logout-all` làm mọi thiết bị khác mất phiên.
7. **Kiểm thử**: unit test single-flight (thành công; refresh lỗi; 401 lặp không vòng
   vô hạn; request song song); test khởi động khi có hoặc không có cookie.
8. **Rủi ro và rollback**:
   - Vòng lặp refresh; giới hạn một lần thử lại.
   - Lệch đồng hồ máy; refresh dựa trên 401, không chỉ dựa trên thời gian.
   - Rollback: tắt refresh khi khởi động (quay về hành vi Đợt 1).
9. **Hoàn tất khi**: như quy tắc chung; dòng M7 ở §4.1 chuyển thành "đã giải quyết".

### Đợt 4 — Đăng ký, kích hoạt, quên và đặt lại mật khẩu

1. **Mục tiêu**:
   - Trang đăng ký.
   - `/auth/activate?key=`: tài khoản được import phải đặt mật khẩu.
   - Gửi lại email kích hoạt.
   - Quên mật khẩu; `/auth/reset?uid=&token=` (không giữ alias `/reset-password`).
2. **Điều kiện vào**:
   - Đợt 1.
   - Môi trường Identity có `IDENTITY_MAIL_KEY`.
   - Có cách lấy link kích hoạt/đặt lại khi dev (G3).
3. **Việc frontend**:
   - Form và adapter cho `register`, `activate`, `activation/resend`,
     `password-reset/request`, `password-reset/confirm`.
   - Báo "nếu email tồn tại, bạn sẽ nhận được hướng dẫn", không lộ email.
   - 503 `IDENTITY_UNAVAILABLE` thì báo tính năng tạm không dùng được, **không** báo
     đã gửi.
   - Xử lý `INVALID_ACTIVATION_TOKEN`, `ACCOUNT_ALREADY_ACTIVE`, token đặt lại hết
     hạn.
4. **Phụ thuộc backend**:
   - G3: không có bên gửi mail. Cần relay/Notification gửi email, hoặc cách dev lấy
     link (ví dụ lệnh in link). Đội Identity/hạ tầng phụ trách.
   - Xác nhận `IDENTITY_FRONTEND_URL` trỏ đúng origin web.
5. **Ngoài phạm vi**: Notification Service đầy đủ.
6. **Tiêu chí chấp nhận**:
   - Khi đã có G3: đăng ký → nhận link → kích hoạt → đăng nhập.
   - Tài khoản import kích hoạt kèm đặt mật khẩu.
   - Quên mật khẩu → link → đặt lại → đăng nhập bằng mật khẩu mới.
   - Chưa có G3: form gửi đúng request, xử lý đúng 503 và lỗi; ghi rõ phần
     end-to-end **Chưa xác minh**.
7. **Kiểm thử**: unit test form và mapper lỗi; test route đọc `key`, `uid`, `token` từ
   URL (thiếu tham số, tham số sai).
8. **Rủi ro**: email không bao giờ tới nếu G3 chưa xong. Không bật đăng ký công khai ở
   môi trường demo khi chưa có G3.
9. **Hoàn tất khi**: như quy tắc chung.

### Đợt 5 — Khu quản trị Admin

1. **Mục tiêu**: route `/admin/users` chỉ cho `SYSTEM_ADMIN`.
   - Bảng người dùng: tìm kiếm, lọc theo role và trạng thái, phân trang theo `meta`.
   - Đổi trạng thái tài khoản kèm lý do; gán và gỡ role.
2. **Điều kiện vào**: Đợt 2; nghiệp vụ chốt quyền Admin (§9).
3. **Việc frontend**:
   - Route và sidebar Admin.
   - Hộp thoại xác nhận nói rõ phiên của người dùng đó có thể bị thu hồi.
   - Xử lý `CANNOT_REVOKE_OWN_ADMIN_ROLE`, `ACCOUNT_UNAVAILABLE`.
4. **Phụ thuộc backend**: không (đã có); lệnh `bootstrap_identity_admin` để tạo Admin
   đầu tiên.
5. **Ngoài phạm vi**: Admin xem nội dung project
   ([phân tích vai trò](utask-role-analysis.md) §1.3); import sinh viên (thuộc
   Classroom).
6. **Tiêu chí chấp nhận**:
   - Admin khóa một tài khoản → tài khoản đó đăng nhập nhận `ACCOUNT_SUSPENDED`.
   - Không phải Admin vào `/admin` thì thấy trang bị chặn, backend trả 403.
7. **Kiểm thử**: test guard; bảng (rỗng, phân trang, lọc); hộp thoại và lỗi.
8. **Rủi ro**: thao tác nhạy cảm; luôn xác nhận, không cập nhật lạc quan.
9. **Hoàn tất khi**: như quy tắc chung.

### Đợt 6 — Tùy chọn: OAuth và avatar

- Chỉ làm khi đội bật `IDENTITY_GITHUB_ENABLED`/`IDENTITY_GOOGLE_ENABLED`/
  `IDENTITY_AVATAR_ENABLED` và cung cấp cấu hình (client OAuth, lưu trữ avatar).
- Khi cờ tắt, frontend ẩn nút hoặc vô hiệu hóa kèm lý do.
- Phải có cách frontend biết cờ nào đang bật; hiện **chưa có** endpoint cấu hình công
  khai. Khi cần, ghi vào G-list cho Identity.
- Liên kết GitHub ở mức tài khoản **không** thay cho kết nối repository (thuộc
  Integration, làm sau).

## 6. Sổ khoảng trống backend

### 6.1 Khoảng trống của Identity (giai đoạn này)

| # | Ưu tiên | Use case | Thiếu gì | Bằng chứng | Vì sao frontend không tự làm được | Thay đổi tối thiểu | Tạm thời |
| --- | --- | --- | --- | --- | --- | --- | --- |
| G1 | Cao | Khôi phục phiên, refresh, `logout-all` | Cách SPA lấy CSRF token; `CSRF_TRUSTED_ORIGINS` | `enforce_csrf` ở `serializers/auth.py`, `views/devices.py`; không view nào cấp `csrftoken` | Token CSRF do Django phát | Một GET cấp cookie `csrftoken` (ví dụ `ensure_csrf_cookie`), cấu hình trusted origins, test với cookie thật | Đợt 1–2 chạy được; tải lại thì mất phiên |
| G2 | Cao | Mọi thử nghiệm với Identity thật | Cách chạy Identity + nginx ở dev; tài khoản demo đã kích hoạt (gồm `leader@utask.test`, `member@utask.test`, `student@utask.test` và một Teacher) | Compose gốc không dựng được gateway; chỉ có `bootstrap_identity_admin` | Frontend không cấu hình được backend và DB | Profile compose hoặc override chạy Identity + nginx; lệnh seed tài khoản demo và role | Admin tạo bằng lệnh, role gán qua API Admin (**Chưa xác minh**) |
| G3 | Cao cho Đợt 4 | Đăng ký, kích hoạt, đặt lại mật khẩu | Bên gửi email; cách lấy link khi dev | `messaging/outbox.py` chỉ ghi sự kiện mã hóa; không có relay/consumer | Frontend không nhận được `key`, `uid`, `token` | Relay gửi mail (hoặc Notification), hoặc lệnh dev in link | Form gửi được; end-to-end chờ |
| G4 | Trung bình | Kiểm tra hợp đồng | File OpenAPI Identity trong `contracts/api/` | [contracts/api/README.md](../../contracts/api/README.md) | Không có nguồn shape ổn định để đối chiếu | Chạy `export_identity_api --output` và commit | Đối chiếu `/api/auth/openapi/` lúc chạy |
| G5 | Thấp | Ẩn/hiện OAuth, avatar | Endpoint công khai cho biết cờ nào bật | Cờ chỉ trong settings | Frontend không biết cấu hình server | Endpoint cấu hình công khai hoặc biến build chung | Ẩn mặc định |
| G6 | Thấp | Chất lượng | CI không chạy trên `dev` | `ci.yml` chỉ `main` | — | Thêm `dev` vào trigger | Chạy kiểm tra cục bộ |

### 6.2 Khoảng trống của giai đoạn sau (chỉ ghi nhận)

- Classroom Service chưa có. Nó chặn tạo project từ nhóm, lớp, nhóm và Teacher.
- Work cần môi trường chạy (service key, Classroom adapter, seed dữ liệu). Card Board
  thiếu trường, task không có `sprint_id`, chuyển Sprint không nguyên tử, tên người
  phụ thuộc Kafka consumer.
- AI lệch tiền tố gateway, lệch issuer/audience JWT, chưa có CORS `OPTIONS`, chưa nối
  context với Work.
- Integration và Notification chưa có. My Work chưa có endpoint tổng hợp. Khóa AI
  (BYOK) chưa có service sở hữu.
- Chi tiết bằng chứng: Phụ lục A.

## 7. Chiến lược hợp đồng và kiểm thử

- **Nguồn hợp đồng**:
  - OpenAPI Identity lúc chạy (`/api/auth/openapi/`); file commit khi G4 xong.
  - Mỗi DTO trong `lib/api/identity/dto.ts` ghi chú ngày và HEAD đã đối chiếu.
- **DTO, envelope, lỗi**: unit test mapper với fixture JSON chép từ phản hồi thật
  hoặc ví dụ OpenAPI:
  - Thành công.
  - Lỗi có `error.code`, lỗi trường `details[].field`.
  - 429, 503.
  - Danh sách phân trang (Admin).
- **MSW**:
  - Handler `auth.ts` trả đúng path, envelope, mã lỗi như Identity. Mỗi lần đổi DTO,
    cập nhật fixture trong cùng PR.
  - Cầu nối persona có test riêng (§5, Đợt 0).
- **Xác thực và phân quyền**: test component cho 401 (`TOKEN_EXPIRED`,
  `TOKEN_REVOKED`), 403 (`PERMISSION_DENIED`, tài khoản bị khóa), 429, 503. UI chỉ
  ẩn hoặc vô hiệu hóa; backend quyết định.
- **Tích hợp với Identity thật**: kịch bản thủ công có ghi lại cho mỗi đợt, chạy trên
  môi trường G2. Không ghi "đã kiểm thử" nếu chưa chạy.
- **E2E**:
  - Hiện không có công cụ. Refresh bằng cookie HttpOnly và CSRF (Đợt 3) không kiểm
    được trong jsdom.
  - Đề xuất Playwright cho Đợt 3, sau khi đội đồng ý: một smoke "đăng nhập → tải lại
    → vẫn đăng nhập → đăng xuất" chạy với Identity thật.
- **Hồi quy bắt buộc giữ xanh** (vì cầu nối persona và đổi `AuthUser` chạm mọi màn):
  - Kéo thả và cập nhật lạc quan (`projectIssues.test.ts`, test Board/Backlog).
  - Luồng sinh viên (`StudentFlowRegression.test.tsx`).
  - Luồng giảng viên (`TeacherFlow.test.tsx`, `teacherFlow.test.ts`).
  - Dữ liệu mock (`graphConsistency.test.ts`).

## 8. Thứ tự thực hiện

**Đợt nên làm đầu tiên: Đợt 0.** Mọi đợt Identity đều cần client hiểu envelope và
`error.code`, proxy cùng origin cho cookie, và cầu nối persona để các màn còn chạy
MSW không vỡ khi đăng nhập thật. Đợt 0 không phụ thuộc backend.

Checklist:

1. [ ] Gửi đội Identity/hạ tầng ngay: G1 (CSRF), G2 (chạy dev + tài khoản demo),
   G3 (gửi email hoặc lấy link khi dev), G4 (commit OpenAPI).
2. [ ] Đợt 0. Đo bằng tiêu chí ở §5: test hiện có đạt, unit test client và cầu
   nối, `healthz` qua proxy.
3. [ ] Đợt 1 với Identity thật.
4. [ ] Đợt 2; Đợt 3 khi G1 xong; Đợt 4 khi G3 xong.
5. [ ] Đợt 5 sau khi nghiệp vụ chốt quyền Admin; Đợt 6 nếu bật cờ.
6. [ ] Khi giai đoạn Identity xong: lập kế hoạch chi tiết cho Work dựa trên Phụ lục A.

## 9. Rủi ro và câu hỏi mở

| Câu hỏi hoặc rủi ro | Chặn gì | Người quyết định |
| --- | --- | --- |
| Cách cấp CSRF cho SPA; cookie `Secure` khi dev trên `http://localhost` | Đợt 3 | Identity + Frontend |
| Lệnh chạy Identity + gateway và seed tài khoản demo | Thử nghiệm mọi đợt | Identity + hạ tầng |
| Gửi email (relay/Notification) hay lệnh dev in link | Đợt 4 | Identity + hạ tầng |
| Cầu nối persona: ánh xạ theo email hay cách khác | Đợt 0–1 | Frontend |
| Ý nghĩa của `preferences` trong hồ sơ | Đợt 2 | Identity |
| Mâu thuẫn trong [phân tích vai trò](utask-role-analysis.md): §2.2 cho Admin mọi quyền, §1.3 nói Admin không mặc định đọc project | Đợt 5 | Nghiệp vụ |
| Cách deploy web (build tĩnh sau nginx cùng origin?) | Release | Đội phát triển |
| Mock lệch khi Identity đổi shape | Mọi đợt | Frontend, đối chiếu OpenAPI mỗi PR |

## 10. Cách cập nhật tài liệu này

- Khi xong một đợt: cập nhật nhãn ở §3–§4 và checklist §8; ghi HEAD và ngày đối chiếu
  ở đầu tài liệu.
- Khi backend đóng một khoảng trống ở §6: xóa dòng đó, cập nhật ma trận §4.2.
- Khi bắt đầu giai đoạn Work: chuyển phần liên quan ở Phụ lục A thành các đợt có đủ
  mục tiêu, điều kiện vào, tiêu chí chấp nhận, kiểm thử như §5.
- Chi tiết từng màn ghi vào [student-flow.md](student-flow.md),
  [teacher-flow.md](teacher-flow.md), [kanban-board.md](kanban-board.md) hoặc tài
  liệu luồng mới (ví dụ `auth-flow.md`, `admin-flow.md`); không để roadmap phình ra.
- Luôn kiểm tra lại hiện trạng theo mã nguồn; không suy ra từ thiết kế.

## Phụ lục A. Hiện trạng các service làm sau

Ghi lại để giai đoạn sau không phải khảo sát lại. Đối chiếu tại HEAD `933f785`;
cần kiểm tra lại trước khi lập kế hoạch chi tiết.

### A.1 Work

- **Route**:
  - Không có tiền tố trong service; trình duyệt gọi `/api/work/<route>`.
  - Frontend hiện gọi `/api/work/api/v1/...`, và test
    `tests/contract/test_auth_contract.py:63` khẳng định đường này trả 404.
  - Danh mục chuẩn ở OpenAPI lúc chạy `/api/work/openapi/`, sinh từ
    [config/urls.py](../../apps/work-service/config/urls.py) và:
    - [projects/urls.py](../../apps/work-service/apps/projects/urls.py): project,
      thành viên, state, `kanban/`, `dashboard/`.
    - [tasks/urls.py](../../apps/work-service/apps/tasks/urls.py): task,
      `transition/`, `block/`, subtask, epic/label, AI apply.
    - [sprints/urls.py](../../apps/work-service/apps/sprints/urls.py): Sprint, scope,
      `close/`, `progress/`, `burndown/`.
    - [collaboration/urls.py](../../apps/work-service/apps/collaboration/urls.py):
      comment, activity, attachment.
    - [integrations/urls.py](../../apps/work-service/apps/integrations/urls.py):
      dữ kiện GitHub.
- **Envelope** giống Identity; phân trang theo cursor
  (`meta.pagination.next_cursor`).
- **Xác thực**: JWKS Identity cộng `internal/auth/session-status`; thiếu
  `IDENTITY_WORK_SERVICE_KEY` thì mọi request trả 503.
- **Quyền**:
  - Leader/Member; Member chỉ thao tác task được giao.
  - Ngoài project trả 404; thiếu quyền trả 403; giảng viên chỉ đọc qua Classroom.
- **Mô hình**:
  - State do từng project tự định nghĩa, có `group`.
  - Task có UUID `id` và `code`; nhiều assignee; `due_date` là ngày.
  - `sort_order` số thực; không có `sprint_id` trong task.
  - Kéo thả bằng `PATCH tasks/{id}/transition/`
    `{expected_version, target_state_id, previous_task_id, next_task_id}`.
  - Scope Sprint bằng `POST sprints/{id}/tasks/` ADD/REMOVE; bắt buộc
    `scope_change_reason` khi Sprint ACTIVE.
  - `Idempotency-Key` bắt buộc ở các lệnh tạo.
- **Chặn**:
  - Classroom adapter mặc định `UnavailableClassroom` nên không tạo được project.
    Dev dùng `LocalClassroom` +
    [dev_data/classroom.json](../../apps/work-service/dev_data/classroom.json).
  - GitHub và AI adapter mặc định trả 503 (`infra/env/work-service.env`).
- **Test**: 29 unit, 218 integration, 27 contract, 2 external (Postgres).
- **Tài liệu lệch**: [apps/work-service/README.md](../../apps/work-service/README.md)
  trỏ tới ba file không tồn tại.

### A.2 AI

- Route `POST /api/ai/v1/requests` (bắt buộc `Idempotency-Key`; 202 kèm `Location`) và
  `GET /api/ai/v1/requests/{id}` ([routes.py](../../apps/ai-service/src/api/routes.py)).
- Gateway cắt `/api/ai/` nên gọi từ trình duyệt bị 404.
- Issuer/audience `utask-local-mock`/`utask-ai` khác Identity
  ([ai-service.env](../../infra/env/ai-service.env)).
- Lỗi dạng `{"error": {...}}` riêng; context URL để trống.
- Hợp đồng [ai-service-v1.yaml](../../contracts/api/ai-service-v1.yaml)
  (`partially-implemented`); tài liệu [docs/ai-service/api.md](../ai-service/api.md).

### A.3 Classroom, Integration, Notification

- Không có thư mục mã trong `apps/`; nginx và compose vẫn tham chiếu.
- Các màn lớp, nhóm, Teacher T01–T10, tab Code, thông báo, My Work giữ **Demo MSW**.
  Lời gọi lớp/nhóm sau này đi qua `/api/classroom/`, không đặt dưới `/api/work/`.
