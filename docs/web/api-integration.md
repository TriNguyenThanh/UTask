# Tích hợp API thật vào Web (Identity trước)

**Trạng thái: Một phần.** Đã nối Identity Service (đăng nhập, phiên, hồ sơ,
đổi mật khẩu, thiết bị) và phần đọc của Classroom cho sinh viên. Work và các màn còn lại vẫn chạy trên MSW.
Kế hoạch gốc theo từng Phase nằm trong lịch sử làm việc của đội; tài liệu này
chỉ ghi hiện trạng đã có mã nguồn và kiểm thử.

Mọi thay đổi tích hợp nằm trên nhánh `feat/web-real-api-integration`.

## Cách chạy với Identity thật

Tạo `apps/web/.env.local` (không commit):

```
VITE_ENABLE_MOCKS=true
VITE_REAL_SERVICES=auth,classroom   # chỉ "auth" nếu chưa cần Classroom thật
VITE_API_BASE_URL=
# VITE_API_PROXY_TARGET=https://utask-api.u-code.dev   (mặc định là staging)
```

- `VITE_REAL_SERVICES` là danh sách phân cách bằng dấu phẩy
  (`auth|classroom|work`). Service có trong danh sách không còn handler MSW; lỗi
  của service thật **không bao giờ** rơi về mock.
- Phần chưa có backend (GitHub, thông báo, Classroom…) vẫn do MSW trả. Cầu
  nối persona (`mocks/personaBridge.ts`) ánh xạ người dùng thật sang dữ liệu
  demo để các màn đó còn hiển thị được.
- Dev server chuyển tiếp `/api` sang staging qua proxy cùng origin
  (`vite.config.ts`) vì CORS của staging không cho `http://localhost:5173`.
  Proxy bỏ `Origin`/`Referer` và ghi lại `Domain` của cookie; nếu không,
  `refresh` và `logout-all` bị 403 `PERMISSION_DENIED`.
- `.env.production` giữ nguyên chế độ mock.

## Hiện trạng theo Phase

| Phase | Nội dung | Nhãn |
|---|---|---|
| 0 | Proxy dev, client envelope, cờ `VITE_REAL_SERVICES`, cầu nối persona, helper idempotency/phân trang | Đã triển khai |
| 1 | Đăng nhập, đăng xuất (thu hồi phiên hiện tại), `GET /users/me` | Đã triển khai |
| 2 | Khôi phục phiên khi tải lại, tự làm mới access token, CSRF | Đã triển khai |
| 3 | Hồ sơ, đổi mật khẩu, danh sách thiết bị, đăng xuất mọi thiết bị | Đã triển khai (chưa smoke trình duyệt) |
| 4 | Đăng ký, kích hoạt, quên/đặt lại mật khẩu | Đã triển khai ở mức form + request (end-to-end email chưa xác minh, chờ B3; chưa smoke trình duyệt) |
| 5 | Classroom phía sinh viên: danh sách lớp, chi tiết lớp/nhóm của tôi, tham gia lớp bằng mã | Một phần (xem giới hạn; chưa smoke trình duyệt) |
| 6 | Classroom: sinh viên tạo nhóm, vào nhóm bằng mã, cấp/tắt mã mời, rời nhóm, chuyển Trưởng nhóm, loại thành viên | Đã triển khai ở mức form + request (chưa smoke trình duyệt) |
| 7–8 | Classroom: quản lý lớp của giảng viên | Chưa triển khai |
| 9+ | Work, Admin | Chưa triển khai |

## Phiên và token (Phase 1–2)

- Đăng nhập: `POST /api/auth/login`. Access token giữ trong bộ nhớ; refresh
  token là cookie HttpOnly do backend đặt. Lỗi được dịch ở
  `features/auth/errorMessages.ts` (gồm `INVALID_CREDENTIALS`, khóa tài khoản,
  chưa kích hoạt, email chưa xác minh).
- Đăng xuất: `GET /sessions` để tìm phiên `is_current`, rồi `DELETE
  /sessions/{id}`. `SESSION_NOT_FOUND` coi như đã thu hồi. Trạng thái cục bộ
  luôn bị xóa; nếu máy chủ chưa thu hồi được thì hiện cảnh báo.
- Khôi phục phiên: khi tải trang, `AuthProvider` ở trạng thái `restoring` →
  `POST /refresh` → `GET /users/me`. Hẹn giờ làm mới trước hạn JWT 60 giây.
- Request nhận 401 có token: refresh một lần (dùng chung một promise) rồi gọi
  lại đúng một lần với cùng `Idempotency-Key`. Refresh thất bại → về đăng nhập.
- CSRF: `refresh` và `logout-all` cần header `X-CSRFToken`. Frontend lấy cookie
  `csrftoken` bằng `GET /api/auth/docs/` (`lib/api/csrf.ts`). Đây là cách tạm
  chờ backend có endpoint riêng (mục B2).
- Mock dùng cookie qua `document.cookie` (`Path=/`) vì MSW 3 không lưu
  `Set-Cookie` trong Node.

## Hồ sơ và bảo mật (Phase 3)

Khi `isRealService("auth")`, hai route chọn component thật; ngược lại giữ trang
mock cũ (`routes/SettingsProfileRoute.tsx`, `SettingsSecurityRoute.tsx`).

- **Hồ sơ** (`IdentityProfilePage`): đọc `GET /users/me`; chỉ đọc: email,
  tên đăng nhập, MSSV. Sửa được: họ, tên, SĐT, khóa, khoa, giới thiệu, múi giờ.
  `PATCH /users/me` chỉ gửi trường đã đổi (trường tùy chọn để trống gửi
  `null`), sau đó đọc lại `GET /users/me` vì backend chỉ trả một phần hồ sơ.
  `VALIDATION_ERROR` hiện theo từng trường. Không cập nhật lạc quan. Trường
  "lớp sinh hoạt" không có ở Identity nên bị bỏ ở chế độ thật.
- **Thiết bị** (`IdentitySecurityPage`): `GET /sessions` hiển thị tên thiết
  bị, IP, thời điểm đăng nhập (không có "vị trí" hay "hoạt động gần nhất" vì
  API không cung cấp). Thu hồi thiết bị khác bằng `DELETE`; lỗi hiện toast,
  danh sách không đổi. Thiết bị hiện tại không có nút thu hồi, dùng nút
  "Đăng xuất".
- **Đổi mật khẩu**: `POST /password-change`. Thành công: backend thu hồi mọi
  phiên nên frontend xóa phiên cục bộ rồi chuyển `/login` kèm thông báo (router
  state `notice`). Sai mật khẩu cũ hiện lỗi ở ô tương ứng; lỗi không thuộc
  trường nào (ví dụ 503) hiện dưới form. Luật độ mạnh mật khẩu do backend
  quyết định, frontend không sao chép.
- **Đăng xuất mọi thiết bị**: hộp thoại xác nhận → `POST /logout-all` → `/login`
  kèm số phiên đã thu hồi. Nếu gọi lỗi, hiện cảnh báo máy chủ chưa thu hồi.
- Cài đặt GitHub/thông báo vẫn là demo MSW (`Chưa triển khai` ở backend).

## Đăng ký, kích hoạt, khôi phục mật khẩu (Phase 4)

Các route công khai (`app/router/router.tsx`), luôn gọi API thật qua client;
ở chế độ mock chúng gọi handler MSW cùng hợp đồng.

| Route | Hành vi |
|---|---|
| `/register` | `POST /register` (`email, username, first_name, last_name, password1, password2`). Thành công (201) hiện "Đăng ký thành công, kiểm tra email"; không tự đăng nhập. `VALIDATION_ERROR` hiện theo trường |
| `/auth/activate?key=` | `POST /activate {key}`. Thiếu `key` → màn "Liên kết kích hoạt không hợp lệ". Mục tùy chọn "Tài khoản do giảng viên tạo? Đặt mật khẩu" gửi thêm `new_password1/2` khi có điền. Link sai/hết hạn (404 `RESOURCE_NOT_FOUND` hoặc `INVALID_ACTIVATION_TOKEN`) kèm ô "Gửi lại email kích hoạt" (`POST /activation/resend`). `ACCOUNT_ALREADY_ACTIVE` hiện màn đã kích hoạt + link đăng nhập. Thành công → `/login` kèm thông báo |
| `/forgot-password` | `POST /password-reset/request`. Luôn hiện "Nếu email tồn tại, bạn sẽ nhận được hướng dẫn." khi 2xx (không lộ email có tồn tại). 503/429 hiện lỗi và **không** báo đã gửi |
| `/auth/reset?uid=&token=` | `POST /password-reset/confirm`. Thiếu `uid` hoặc `token` → màn link không hợp lệ. Token sai/hết hạn (lỗi trường `token`/`uid`) → thông báo kèm link "Yêu cầu liên kết mới". Thành công → `/login` kèm thông báo |

Route cũ `/reset-password` đã bị xóa (không giữ alias); link email của backend
dùng `/auth/reset` và `/auth/activate`. Trang đăng nhập có link "Đăng ký".
Frontend chỉ kiểm tra tối thiểu (bắt buộc, ≥ 8 ký tự, khớp xác nhận); luật độ
mạnh mật khẩu do backend quyết định và lỗi hiện theo trường.

Link demo khi chạy mock: `/auth/activate?key=mock-activation-key` và
`/auth/reset?uid=mock&token=mock-reset-token`.

Chưa xác minh: email thật có tới hộp thư và đúng định dạng link không (B3);
`ACCOUNT_ALREADY_ACTIVE` chỉ thấy trong mã provisioning của backend, còn kích
hoạt lại link đã dùng thực tế có thể trả 404.

## Classroom phía sinh viên (Phase 5)

Bật bằng `VITE_REAL_SERVICES=auth,classroom`. Mã nằm ở `lib/api/classroom/`
(`dto.ts`, `endpoints.ts`, `adapters.ts`, `loaders.ts`) và
`lib/query/classroomHooks.ts`. `/courses` và `/courses/:courseId` chọn nguồn
dữ liệu bằng `isRealService("classroom")`; lỗi không rơi về mock.

| Màn | Nguồn thật | Ghi chú |
|---|---|---|
| `/courses` | `GET /classes/` + `GET /courses/` | Nhóm theo `Class.term`. `courseId` = `Class.id`; `courseCode` lấy từ `Course.code` (nối qua `Class.course`), thiếu thì dùng `Class.code`; `courseName` = `Class.name` |
| Nhóm của tôi | `GET /classes/{id}/groups/` rồi `GET /groups/{id}/members/` từng nhóm | Không có API "nhóm của tôi": dò từng nhóm ACTIVE (tối đa 50, 5 request song song); 404 nghĩa là không phải nhóm của mình |
| Giảng viên | `GET /classes/{id}/teachers/` + `POST /auth/users/batch` | ACTIVE, PRIMARY trước. Lỗi tra cứu → để trống, không làm hỏng trang |
| Tham gia lớp | `POST /classes/join/ {code}` + `Idempotency-Key` | Khóa sinh mới mỗi lần mở hộp thoại; lỗi hiện `error.message` (mã sai, hết hạn 409…). Thành công → refetch danh sách |

Giới hạn khi chạy thật (mỗi mục là dữ liệu mà API hiện không cung cấp):

- Không có đề tài (`team.topic = null`): mục Đề tài ẩn.
- Không có kỹ năng/trách nhiệm: hai cột ẩn khi không ai có dữ liệu.
- Không có trạng thái chờ duyệt, không có hạn đăng ký nhóm.
- Sinh viên không đọc được danh sách ghi danh (403) và không đọc được thành
  viên nhóm khác (404): `classSize = null` (ẩn "Sĩ số lớp"), `formation = null`
  (thay hai bảng "nhóm còn chỗ" và "bạn học chưa có nhóm" bằng thông báo).
- `repository`, `projectId`, `projectKey` = `null` (chưa nối Work/Integration).

Chưa xác minh: chạy thật với sinh viên đã ghi danh (chưa có tài khoản/mã lớp
trên staging); enum trạng thái suy ra từ ràng buộc DB vì OpenAPI không khai báo.

## Sinh viên thao tác nhóm (Phase 6)

Chỉ có ở `VITE_REAL_SERVICES` chứa `classroom`; chế độ mock giữ form cũ. Mọi
lệnh gửi `Idempotency-Key` mới (UUID) cho mỗi ý định: hộp thoại tạo nhóm/tham
gia nhóm sinh khóa khi mở, các lệnh có lý do sinh khóa khi bấm xác nhận. Không
cập nhật lạc quan; chỉ refetch sau thành công và cả khi gặp 409.

| Thao tác | API | Ghi chú |
|---|---|---|
| Tạo nhóm | `POST /groups/ {class_id, name}` | Chỉ nhập tên nhóm: cỡ nhóm cấu hình theo lớp; mô tả và kỹ năng cần tuyển chưa có API. Nút tạo bị vô hiệu khi lớp đã chốt nhóm hoặc không mở. Lỗi `name` hiện dưới ô nhập |
| Tham gia nhóm | `POST /groups/join/ {code}` | Nút "Tham gia nhóm bằng mã" ở màn chưa có nhóm. Lỗi (`ACCESS_CODE_EXPIRED`, `GROUP_FULL`, `ALREADY_IN_GROUP`…) hiện lời của server |
| Mã mời | `POST /groups/{id}/invite-code/ {version, enabled}` | Chỉ Trưởng nhóm thấy. Mã thô chỉ có trong kết quả lúc cấp: hiện một lần kèm nút sao chép và cảnh báo, không lưu; tải lại trang là mất. Trạng thái bật/tắt lấy từ `invite_expires_at` |
| Rời nhóm | `POST /groups/{id}/leave/ {version, reason}` | Trưởng nhóm bị vô hiệu nút (backend trả `LEADER_SUCCESSOR_REQUIRED`); lớp đã chốt nhóm trả `GROUPING_LOCKED` |
| Chuyển Trưởng nhóm / Loại thành viên | `POST .../transfer-leader/`, `.../remove-member/ {version, reason, user_id}` | Chỉ Trưởng nhóm thấy nút, trên hàng của thành viên khác |

`version` = `Group.source_version` của nhóm đang hiển thị. `VERSION_CONFLICT`
hiện "Dữ liệu nhóm đã thay đổi, hãy thử lại." và refetch; lỗi khác giữ lời của
server. Lý do dùng `components/feedback/ReasonDialog` (chuyển từ
`features/projects`, đã có sẵn trước đó): bắt buộc 3–500 ký tự, chặt hơn mức tối
thiểu 1 ký tự của backend. UI chỉ ẩn nút theo vai trò; quyền do backend quyết
định.

`patchGroup` (đổi tên/lưu trữ nhóm) đã có hàm gọi và test nhưng chưa có giao
diện vì màn hiện tại không có chức năng đổi tên nhóm.

Chưa xác minh: chạy thật với staging (chưa có sinh viên đã ghi danh để thử).

## Việc cần backend (tổng hợp)

| Mã | Nội dung |
|---|---|
| B1 | Chưa có tài khoản TEACHER trên staging |
| B2 | Endpoint CSRF sạch và `CSRF_TRUSTED_ORIGINS`/`SECURE_PROXY_SSL_HEADER`; nếu không, refresh từ origin production có `Origin` sẽ bị 403 |
| B3 | Xác nhận gửi email và định dạng link kích hoạt/đặt lại mật khẩu, `IDENTITY_FRONTEND_URL` |
| B4 | Schema Classroom: khai báo enum trong OpenAPI; khóa của `profile` (`display_name, email, student_id, avatar_url`); khóa `students[]`/`results[]` khi import; cấu trúc `Activity.changes` |
| B5 | Thêm vào API: `Group.member_count`, `Group.leader_id`, `Class.enrolled_count`, `Class.grouped_count`, `Class.primary_teacher_id`, course `{id, code, name}` nhúng trong Class, và "nhóm của tôi" của lớp. Hiện sinh viên không biết số thành viên/trưởng nhóm của nhóm khác và phải dò từng nhóm |
| B6 | Tính năng UI chưa có API: đề tài, yêu cầu gia nhập chờ duyệt, hạn đăng ký nhóm, kỹ năng cần/trách nhiệm, giám sát của giảng viên, tổng quan My Work, thông báo, GitHub |
| B7 | Khoảng trống Work (xem kế hoạch Phase 9+ khi tới lượt) |
| B8 | Ngữ nghĩa `preferences`; giá trị `refresh` trong body đăng nhập (frontend bỏ qua) |
| B9 | Tra cứu người dùng theo email |
| Mới | Đăng nhập email chưa xác minh trả `VALIDATION_ERROR` "E-mail is not verified." thay vì `ACCOUNT_PENDING_ACTIVATION`; đăng ký mật khẩu nhận mọi tên miền trong khi OAuth sinh viên yêu cầu `.edu.vn` |
| Mới | `PATCH /users/me` chỉ trả một phần hồ sơ; hành vi xoay/phát hiện tái dùng refresh token khi nhiều tab chưa xác minh |

## Kiểm tra đã chạy

Từ `apps/web`: `tsc --noEmit`, `vitest run`, `tsc -b && vite build` đều đạt
sau Phase 6 (47 file / 689 test). Smoke trên trình duyệt thật (Chromium, staging) đã làm cho
Phase 1–2: sai mật khẩu, đăng nhập, F5 giữ phiên, đăng xuất. **Chưa smoke
trên trình duyệt** cho Phase 3–6 và cho refresh khi 401 hoặc hết hạn 15 phút.
