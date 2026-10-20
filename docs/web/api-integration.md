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
- `.env.production` không được commit (bị `.gitignore`). Production đặt biến trên
  Vercel: `VITE_ENABLE_MOCKS=true` (phần chưa có backend vẫn dùng MSW) và
  `VITE_REAL_SERVICES=auth,classroom`; **không** đặt `VITE_API_BASE_URL`.
  `apps/web/vercel.json` rewrite `/api/*` sang `https://utask-api.u-code.dev`
  để trình duyệt gọi cùng origin (không cần CORS), kèm fallback SPA về
  `index.html`. Rewrite không bỏ được `Origin`, nên `refresh`/`logout-all` chỉ
  chạy khi backend xử lý xong B2.

## Hiện trạng theo Phase

| Phase | Nội dung | Nhãn |
|---|---|---|
| 0 | Proxy dev, client envelope, cờ `VITE_REAL_SERVICES`, cầu nối persona, helper idempotency/phân trang | Đã triển khai |
| 1 | Đăng nhập, đăng xuất (thu hồi phiên hiện tại), `GET /users/me` | Đã triển khai |
| 2 | Khôi phục phiên khi tải lại, tự làm mới access token, CSRF | Đã triển khai |
| 3 | Hồ sơ, đổi mật khẩu, danh sách thiết bị, đăng xuất mọi thiết bị | Đã triển khai (đã smoke trình duyệt, trừ đổi mật khẩu thành công và đăng xuất mọi thiết bị) |
| 4 | Đăng ký, kích hoạt, quên/đặt lại mật khẩu | Đã triển khai ở mức form + request (đã smoke trình duyệt kích hoạt link sai và quên mật khẩu; end-to-end email chưa xác minh, chờ B3; chưa submit đăng ký thật) |
| 5 | Classroom phía sinh viên: danh sách lớp, chi tiết lớp/nhóm của tôi, tham gia lớp bằng mã | Một phần (đã smoke trình duyệt trên staging; xem giới hạn) |
| 6 | Classroom: sinh viên tạo nhóm, vào nhóm bằng mã, cấp/tắt mã mời, rời nhóm, chuyển Trưởng nhóm, loại thành viên | Đã triển khai (đã smoke trình duyệt: tạo nhóm, bật mã mời, chuyển Trưởng nhóm, rời nhóm; chưa smoke giao diện vào nhóm bằng mã và loại thành viên) |
| 7 | Classroom: giảng viên đọc lớp, tạo lớp, sửa lớp, trạng thái lớp, mã tham gia, chốt lập nhóm, thêm giảng viên | Một phần (đã smoke trình duyệt trên staging; xem giới hạn) |
| 8 | Classroom: danh sách sinh viên, nhập danh sách, cho sinh viên rời lớp, chỉnh nhóm, lịch sử | Một phần (đã smoke API thật và trình duyệt; xem giới hạn) |
| 9 | Work Project: danh sách dự án của tôi, vỏ dự án + trang Thông tin & thành viên, tạo dự án từ trang nhóm (Leader), sửa/lưu trữ/mở lại dự án, lấp `project` ở trang giảng viên | Một phần (đã smoke trình duyệt trên staging; xem giới hạn) |
| 10 | Work: Board và Backlog chỉ đọc (cột theo `State` của dự án, sprint, epic, panel chi tiết task) | Một phần (đã smoke trình duyệt trên staging với Leader và Teacher; xem giới hạn) |
| 11 | Work: ghi task cốt lõi (tạo issue, kéo thả/menu đổi cột, chặn/bỏ chặn, sửa trong panel, tạo và tick nhiệm vụ con) | Một phần (đã smoke trình duyệt trên staging với Leader và Teacher; xem giới hạn) |
| 12+ | Work (epic/nhãn/quan hệ, sprint, comment, dashboard, GitHub), Admin; AI làm cuối trong plan riêng | Chưa triển khai |

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

## Giảng viên quản lý lớp (Phase 7)

Chỉ có ở `VITE_REAL_SERVICES` chứa `classroom`; chế độ mock giữ nguyên giao
diện demo (nút "Tạo lớp" bị vô hiệu, mục Cài đặt chỉ xem). Mỗi lệnh gửi
`Idempotency-Key` mới cho mỗi lần bấm, không cập nhật lạc quan, refetch sau
thành công và cả khi 409 (xóa cache `teacher/<user>` và `classroom`).

**Đọc (Teacher)**: `useTeacherCourses/Course/Students/Teams` chọn nguồn Classroom
khi `classroom` là dịch vụ thật.

| Màn | Nguồn | Ghi chú |
|---|---|---|
| Danh sách lớp | `GET /classes/`, `GET /courses/`, và với mỗi lớp `enrollments/` + `groups/` với `page_size=1&status=ACTIVE` | Chỉ lấy `total_count` nên mỗi lớp 2 request nhẹ. `Chưa có nhóm` để trống (`—`) vì cần thành viên của mọi nhóm |
| Chi tiết lớp | `GET /classes/{id}/`, `enrollments/`, `groups/`, `groups/{id}/members/`, `teachers/` + `POST /users/batch` | Tải một lần rồi dùng chung cho Tổng quan, Sinh viên, Nhóm (30 giây). Thành viên các nhóm đọc theo lô 5 request |
| Sinh viên / Nhóm | cùng dữ liệu trên | Tên, email, mã sinh viên lấy từ `profile` (B4a) |
| Giám sát, chi tiết nhóm | Chưa có | Cần dữ liệu Work (B6/B7); trang nói rõ "chưa khả dụng", không hiện số 0 |

Các số liệu thuộc Work (`teamsWithoutProject`, `teamsWithSignals`, `overdue`,
`lastActivity`) là `null` ở chế độ thật: giao diện hiện "Chưa có dữ liệu" hoặc
`—`, tổng ở bàn làm việc để trống thay vì cộng thiếu. "Cần chú ý" ở bàn làm
việc bị ẩn. Mã tham gia thô không đọc lại được (backend chỉ lưu băm): lớp chỉ
hiện "Đang bật" khi `join_code_expires_at` còn hạn.

**Ghi**

| Thao tác | API | Ghi chú |
|---|---|---|
| Tạo lớp | (nếu môn mới) `POST /courses/ {code, name}` rồi `POST /classes/ {course_id, code, name, term, starts_on, ends_on, group_min_size, group_max_size}` | Chọn môn có sẵn hoặc tạo môn mới. Hai khóa idempotency riêng; khóa đổi khi người dùng sửa form. Lỗi theo trường hiện cạnh ô; thành công mở trang lớp. Người tạo thành giảng viên phụ trách chính |
| Sửa lớp | `PATCH /classes/{id}/ {version, name, term, starts_on, ends_on, group_min_size, group_max_size}` | Mã lớp và môn không đổi được. Form nạp lại khi `version` đổi |
| Trạng thái | `POST /classes/{id}/state/ {version, status}` | Đóng, mở lại, lưu trữ đều hỏi xác nhận; lưu trữ không mở lại được (`CLASS_ARCHIVED`) |
| Mã tham gia | `POST /classes/{id}/join-code/ {version, enabled}` | Mã thô hiện một lần kèm cảnh báo và nút sao chép, chỉ nằm trong state của thẻ. Thay mã hoặc tắt mã hỏi xác nhận. Hạn mặc định 7 ngày do backend đặt; giao diện chưa cho chọn hạn |
| Chốt lập nhóm | `POST /classes/{id}/lock-grouping/ {version}` | Hộp xác nhận nêu rõ không có cách mở lại |
| Thêm giảng viên | `POST /classes/{id}/teachers/assign/ {version, user_id, role: CO_TEACHER, status: ACTIVE}` | Nhập UUID người dùng, tra bằng `POST /users/batch` rồi hiện tên và email để xác nhận. Người được thêm phải có role `TEACHER` và tài khoản đang hoạt động (`INVALID_TEACHER` nếu không) |

`version` = `Class.version` của lớp đang hiển thị. `VERSION_CONFLICT` hiện "Lớp
học đã thay đổi, hãy xem lại dữ liệu mới rồi thử lại."; lỗi khác (ví dụ
`PERMISSION_DENIED` khi không phải giảng viên của lớp) giữ lời của server.
Giao diện chỉ ẩn nút theo trạng thái; quyền do backend quyết định.

Chưa làm trong Phase 7: sửa/lưu trữ môn học (`PATCH /courses/{id}/`,
`POST /courses/{id}/archive/`) vì không có màn nào cần; cho giảng viên nghỉ lớp
(`assign` với `status: LEFT`) và đổi giảng viên chính; chọn hạn của mã tham
gia. Các thao tác thêm/nhập/điều chỉnh sinh viên và nhóm làm ở Phase 8.

Đã smoke: API thật trên staging (tạo môn, tạo lớp, sửa, xung đột phiên bản
`VERSION_CONFLICT`, cấp mã, sinh viên vào lớp bằng mã, đếm `total_count`,
thêm giảng viên, thêm sinh viên làm giảng viên bị `INVALID_TEACHER`, sinh viên
đổi trạng thái bị `PERMISSION_DENIED`, chốt lập nhóm, đóng, lưu trữ) và
trình duyệt Chromium (đăng nhập giảng viên, danh sách lớp, tạo môn + lớp từ
form, mã hiện một lần, lưu sửa, hộp chốt lập nhóm, tab Sinh viên/Nhóm/Giám
sát). Hai tài khoản giảng viên trên staging:
`bachnhahuyen28@gmail.com` (đã có role TEACHER) và `vinhxuanan28@gmail.com`
(gán thêm role TEACHER ở Phase 7). Dữ liệu smoke là các lớp `SMK…`/`UI…` đã
lưu trữ.

## Giảng viên quản lý sinh viên, nhóm và lịch sử (Phase 8)

Cũng chỉ có ở `VITE_REAL_SERVICES` chứa `classroom`; chế độ mock giữ nút xem
trước bị vô hiệu như trước. Mỗi lệnh gửi `Idempotency-Key` sinh một lần cho mỗi
ý định của người dùng, dùng lại khi thử lại cùng nội dung, không cập nhật lạc
quan, và làm mới cache `classroom` + `teacher/<user>` khi thành công.

| Thao tác | API | Ghi chú |
|---|---|---|
| Thêm một sinh viên | `POST /classes/{id}/students/ {students:[{row_number, email?, student_id?, first_name?, last_name?}]}` | Hộp "Thêm sinh viên" gửi một dòng; kết quả từng dòng hiện ngay trong hộp. Email chưa có tài khoản sẽ được tạo tài khoản chờ kích hoạt (email kích hoạt do Identity gửi, B3) |
| Nhập danh sách | cùng API, mỗi lô tối đa 100 dòng | Chỉ gửi dòng không có lỗi định dạng; dòng trùng trong file vẫn gửi để backend đánh dấu `DUPLICATE_IN_LIST`. Các lô gửi tuần tự, mỗi lô một khóa idempotency tạo từ đầu lượt; lô lỗi dừng cả lượt, "Thử lại" chỉ gửi lại các lô chưa xong với đúng khóa cũ. Tóm tắt cộng gộp các lô, mỗi dòng có nhãn tiếng Việt theo `reason` |
| Loại sinh viên khỏi lớp | `POST /classes/{id}/enrollments/{enrollmentId}/exit/ {reason}` | Hộp lý do 3–500 ký tự; cảnh báo nếu sinh viên đang là Leader (server từ chối nếu chưa chỉ định Leader mới, B11) |
| Chuyển/xếp/bỏ khỏi nhóm | `POST /classes/{id}/adjust-member/ {user_id, target_group_id \| null, successor_user_id?, reason}` | Lý do bắt buộc. Leader rời nhóm phải chọn người kế nhiệm trong nhóm đó. `target_group_id: null` là bỏ khỏi nhóm |
| Chỉ định Leader | `POST /groups/{id}/transfer-leader/ {version, user_id, reason}` | `version` = `Group.source_version` của nhóm; Leader cũ thành thành viên thường |
| Tạo nhóm cho sinh viên | `POST /groups/ {class_id, name, leader_id}` | Giảng viên chọn một sinh viên chưa có nhóm làm Leader đầu tiên; không cần lý do |
| Lịch sử lớp | `GET /classes/{id}/activities/?page_size=50` | Thẻ "Lịch sử lớp" ở Tổng quan. Chỉ giảng viên của lớp hoặc admin đọc được |
| Lịch sử nhóm, chi tiết nhóm | `GET /groups/{id}/activities/`, dữ liệu nhóm đã tải | Trang nhóm hiện thành viên và lịch sử; project/tiến độ nói rõ là chưa có dữ liệu (cần Work) |

Lịch sử hiện nhãn tiếng Việt cho các `verb` đã biết (`class.*`, `enrollment.*`,
`group.*`, `group.member.*`); `verb` lạ hiện nguyên mã để không che sự kiện.
Tên người làm tra bằng `POST /users/batch`; người không tra được hiện "Không rõ".

Đã smoke API thật trên staging (lớp tạm đã lưu trữ): nhập 3 tài khoản có sẵn
(`EXISTING`), email giảng viên (`FLAGGED_ROLE_CONFLICT`), dòng chỉ MSSV
(`STUDENT_ID_NOT_FOUND`), dòng trùng (`DUPLICATE_IN_LIST`), nhập lại cùng người
(`ALREADY_ENROLLED`), 101 dòng bị từ chối `VALIDATION_ERROR`, tạo nhóm với
`leader_id`, xếp thành viên, chuyển Leader có người kế nhiệm, Leader duy nhất bị
`LEADER_SUCCESSOR_REQUIRED` (B11), loại sinh viên, lịch sử mới nhất trước,
`page_size=50` được tôn trọng, sinh viên đọc lịch sử lớp bị 403, người đã rời
nhóm đọc lịch sử nhóm bị 404. Đã smoke trình duyệt Chromium (đăng nhập giảng
viên, danh sách sinh viên, hộp loại Leader bị server từ chối, thêm một sinh
viên đã bị loại, nhập file có 2 dòng với tóm tắt và nhãn lý do, hộp điều chỉnh
nhóm, trang nhóm và thẻ lịch sử). **Chưa smoke trình duyệt** cho di chuyển thật
một thành viên, chỉ định Leader, tạo nhóm và nhập quá 100 dòng (các luồng này có
test giao diện với MSW và đã kiểm tra API thật ở trên).

Chưa làm trong Phase 8: duyệt yêu cầu gia nhập chờ (B6), phân trang lịch sử
quá 50 dòng, nút "Bỏ khỏi nhóm" riêng ngoài hộp điều chỉnh, ghi danh lại sinh
viên đã bị loại (B12).

## Work Project (Phase 9)

Chạy khi `VITE_REAL_SERVICES` có `work`. Kế hoạch chi tiết:
[work-api-intergration-plan.md](work-api-intergration-plan.md). Kế hoạch các phần
Work còn lại (Phase 10–15, không gồm AI): [work-full-integration-plan.md](work-full-integration-plan.md).

| Việc | API | Ghi chú |
|---|---|---|
| Danh sách dự án | `GET /api/work/projects/?status=all` (tải hết, `page_size=100`) | Tab Đang hoạt động/Đã lưu trữ lọc phía client. `meta.scope.partial` hiện banner cảnh báo (giảng viên có thể thiếu dự án của lớp mình phụ trách) |
| Vỏ dự án, Thông tin & thành viên | `GET /projects/{id}/`, `GET /projects/{id}/members/?status=ACTIVE` | Tên lớp/môn/nhóm tra thêm từ Classroom, lỗi thì để trống. Người ngoài dự án nhận 404 → "Không tìm thấy dự án". Backlog, Board, Code, Cài đặt hiện "chưa khả dụng" |
| Tạo dự án | `POST /projects/` + `Idempotency-Key` | Chỉ Leader, nút ở trang nhóm. `identifier` `^[A-Z0-9]{2,10}$` duy nhất toàn hệ thống (`DUPLICATE_IDENTIFIER` → lỗi ở ô mã). Gửi lại cùng khóa khi bấm thử lại |
| Sửa dự án | `PATCH /projects/{id}/` + `expected_version` | Chỉ Leader, chỉ gửi trường đổi. `VERSION_CONFLICT` tải lại dữ liệu |
| Lưu trữ / mở lại | `POST /projects/{id}/archive/`, `/unarchive/` + `expected_version` | Không gửi `Idempotency-Key` (backend không dedupe). `version` lấy từ phản hồi |
| Giảng viên | Nhóm → dự án qua `GET /projects/` | `TeacherTeam.project` và `teamsWithoutProject` chỉ có khi `partial` không bật; ngược lại giữ "chưa có dữ liệu" |

Đã smoke trình duyệt trên staging (STUDENT Leader và TEACHER): `/projects` rỗng,
tạo dự án từ trang nhóm, chuyển hướng sang `/projects/{id}/info`, danh sách có
dự án, sửa tên, lưu trữ rồi mở lại, `/projects/{id}/board` hiện "chưa khả dụng",
tạo trùng `identifier` hiện lỗi ở ô mã, giảng viên thấy "Chế độ chỉ xem" không
có nút sửa/lưu trữ và thấy tên dự án ở trang nhóm. Quan sát: `GET
/projects/{id}/members/` mất khoảng 5 giây trên staging (lệnh ghi chờ tải lại
xong mới hết "Đang lưu…"); `weekly_capacity` của Leader mới tạo là 0. Chưa
smoke: 503 `CLASSROOM_UNAVAILABLE`, `partial`, dự án của lớp đã `ARCHIVED`,
nhiều dự án một nhóm, tạo dự án khi `CONCURRENT_MUTATION_IN_PROGRESS`.

Chưa làm trong Phase 9: Board, Backlog, Sprint, Task, Comment, Dashboard,
GitHub, AI (B14); sidebar và My Work vẫn chạy MSW (B20), nên ở chế độ thật
`CourseEnrollment.projectId` không có người tiêu thụ; dự án smoke chỉ lưu trữ
được vì Work không có API xóa (B18).

## Work Board và Backlog chỉ đọc (Phase 10)

Chạy khi `VITE_REAL_SERVICES` có `work`. Kế hoạch: [work-full-integration-plan.md](work-full-integration-plan.md).
Mã ở `lib/api/work/` (`endpoints.{projects,tasks,sprints}.ts`, `workspaceAdapters.ts`,
`loaders.ts` → `loadWorkspace`) và hook `useWorkspaceReal`, `useTaskReal` trong
`lib/query/workHooks.ts`. Board/Backlog dùng lại component demo qua
`ProjectWorkspaceContext`; `RealWorkspaceBoundary` nạp dữ liệu thật. Mọi thao
tác ghi tắt (`canWrite=false`) cho đến Phase 11; thanh AI và liên kết AI key ẩn.

Quyết định: cột Board là các `State` của dự án theo `sequence` (cột `CANCELLED` ẩn);
`rank` là số `sort_order`; Board/Backlog đọc `GET /projects/{id}/tasks/?expand=…`;
quan hệ task↔sprint dựng từ `tasks?sprint_id=<id>` cho sprint chưa `COMPLETED`;
mô tả hiển thị `description_stripped`, không render `description_html`.

Đã smoke trình duyệt trên staging (Leader, Teacher): Board có đủ 5 cột theo state,
thẻ đúng cột, Backlog tách sprint/Product Backlog, lọc theo epic, panel `?issue=`
hiện trạng thái thật của task. Tải workspace mất khoảng 8–11 giây (phần lớn do
`members` chậm, B21).

Giới hạn đã biết:

- Ưu tiên `URGENT` hiển thị là "Cao"; chỉ hiện người được giao đầu tiên; `hasPullRequest` luôn `false`.
- Người được giao hiện "?" khi `display_name` rỗng (B21).
- Bình luận, lịch sử và liên kết GitHub trong panel trống cho đến Phase 14.
- Task đã xong trong sprint `COMPLETED` hiện như nằm ngoài sprint (D4).
- Dòng Backlog hiện trạng thái suy ra từ nhóm state ("Cần làm" cho cả Backlog và To Do); Board và panel hiện đúng tên state.

## Work ghi task cốt lõi (Phase 11)

Trạng thái: **Một phần**. Mã: `lib/api/work/endpoints.tasks.ts` (`createTask`, `createSubtask`, `patchTask`, `transitionTask`, `blockTask`, `unblockTask`, `listTaskOrderInState`), hook `lib/query/workWriteHooks.ts`, `features/projects/lib/transitionNeighbours.ts`.

- Quyền: Leader ghi mọi task; thành viên chỉ task được giao cho mình (và chỉ sửa title/mô tả/tiêu chí); giảng viên và dự án lưu trữ không có nút ghi.
- `Idempotency-Key` chỉ ở tạo issue và tạo nhiệm vụ con; PATCH, transition, block, unblock không gửi. Block/unblock là `PATCH`.
- Đổi cột: server tính vị trí trên **cột đầy đủ** (gồm nhiệm vụ con và task ngoài sprint đang chạy), nên neighbor không lấy từ cột Board đang hiện. Client gọi `GET tasks?state_id=&fields=id,sort_order` rồi `planNeighbours` chọn hàng xóm liền kề; chuyển cột từ menu thì xếp cuối cột.
- Cập nhật lạc quan, hoàn tác và tải lại khi lỗi. Thành công chỉ ghi `version` và `sort_order` thật, không tải lại workspace.
- `VERSION_CONFLICT` ở form sửa: hiện "Dữ liệu đã được cập nhật bởi thao tác khác…" và nạp lại form theo bản mới.
- `description_html` gửi đúng text nhập, không render HTML.

Giới hạn:

- Backlog vẫn chỉ đọc: thêm/bớt sprint thuộc Phase 13, thứ tự trong section Backlog chưa có ngữ nghĩa neighbor hợp lệ.
- Chưa gán nhãn trong panel (nhãn chưa vào workspace; Phase 12). Chưa có nút chặn trong panel, dùng menu thẻ trên Board. Menu chặn ẩn với task COMPLETED/CANCELLED.
- Tick nhiệm vụ con chuyển sang state COMPLETED đầu tiên; bỏ tick chuyển sang state UNSTARTED đầu tiên (đặt cuối cột).
- Task tạo mới không thuộc sprint nên chỉ hiện ở Backlog, không hiện trên Board.
- Kiểm tra trên: `tsc`, 70 file test cả khi có và không có `.env.local` (test đầu tiên của `RealWorkspace` có lần chậm khi cả bộ chạy song song), build. ESLint không chạy được (thiếu module).
- Smoke trình duyệt (staging): Leader tạo issue, đổi cột bằng menu và tải lại, chặn/bỏ chặn, sửa tiêu đề trong panel, tạo nhiệm vụ con; Teacher không có nút tạo issue hay menu thao tác. Chưa smoke: kéo thả bằng chuột, thành viên không phải Leader, `VERSION_CONFLICT` trên staging, tick nhiệm vụ con.

## Việc cần backend (tổng hợp)

| Mã | Nội dung |
|---|---|
| B1 | Chưa có tài khoản TEACHER sẵn trên staging; Phase 7 phải gán role qua API Admin cho hai tài khoản sinh viên. Cần tài khoản giảng viên cố định và quy trình cấp role |
| B2 | Endpoint CSRF sạch và `CSRF_TRUSTED_ORIGINS`/`SECURE_PROXY_SSL_HEADER`; nếu không, refresh từ origin production có `Origin` sẽ bị 403 |
| B3 | Xác nhận gửi email và định dạng link kích hoạt/đặt lại mật khẩu, `IDENTITY_FRONTEND_URL` |
| B4 | Schema Classroom: khai báo enum trong OpenAPI; khóa của `profile` (`display_name, email, student_id, avatar_url`); cấu trúc `Activity.changes` (khóa `students[]`/`results[]` của import đã xác định từ mã nguồn và đã kiểm trên staging ở Phase 8, nhưng chưa có trong OpenAPI); khóa lạ trong một dòng import bị đánh dấu lỗi ở dòng đó (`VALIDATION_ERROR`) chứ không từ chối cả yêu cầu |
| B5 | Thêm vào API: `Group.member_count`, `Group.leader_id`, `Class.enrolled_count`, `Class.grouped_count`, `Class.primary_teacher_id`, course `{id, code, name}` nhúng trong Class, và "nhóm của tôi" của lớp. Hiện sinh viên không biết số thành viên/trưởng nhóm của nhóm khác và phải dò từng nhóm; giảng viên phải tải thành viên của từng nhóm để biết sinh viên chưa có nhóm |
| B6 | Tính năng UI chưa có API: đề tài, yêu cầu gia nhập chờ duyệt, hạn đăng ký nhóm, kỹ năng cần/trách nhiệm, giám sát của giảng viên (tín hiệu, quá hạn, hoạt động gần nhất, project của nhóm), tổng quan My Work, thông báo, GitHub |
| B7 | Khoảng trống Work: xem B14–B21 |
| B8 | Ngữ nghĩa `preferences`; giá trị `refresh` trong body đăng nhập (frontend bỏ qua) |
| B9 | Tra cứu người dùng theo email (Phase 7 buộc phải nhập UUID để thêm giảng viên đồng phụ trách) |
| Mới | Đăng nhập email chưa xác minh trả `VALIDATION_ERROR` "E-mail is not verified." thay vì `ACCOUNT_PENDING_ACTIVATION`; đăng ký mật khẩu nhận mọi tên miền trong khi OAuth sinh viên yêu cầu `.edu.vn` |
| Mới | `PATCH /users/me` chỉ trả một phần hồ sơ; hành vi xoay/phát hiện tái dùng refresh token khi nhiều tab chưa xác minh |
| B11 | Giảng viên không đưa được Trưởng nhóm duy nhất của một nhóm ra khỏi nhóm hoặc lớp: `adjust-member` và `enrollments/{id}/exit/` trả 409 `LEADER_SUCCESSOR_REQUIRED`, mà người kế nhiệm phải là thành viên cùng nhóm (nếu không có thì 404). Hiện phải xếp thêm một người vào nhóm trước. Cần cho phép giải thể/bỏ nhóm một người hoặc cho nhóm không có Leader khi nó chỉ còn một người |
| B12 | Sinh viên đã rời hoặc bị loại khỏi lớp không ghi danh lại được bằng thêm/nhập danh sách (`ENROLLMENT_INACTIVE`); chưa có API khôi phục ghi danh. Giảng viên bấm "Loại khỏi lớp" nhầm thì không hoàn tác được trên giao diện |
| B13 | Lịch sử lớp/nhóm chỉ lấy trang đầu (50 dòng mới nhất); chưa có cách lọc theo loại sự kiện hay người làm. `Activity.changes` (B4f) chưa có hợp đồng nên giao diện chỉ hiện việc gì, ai, lúc nào |
| B14 | Work không có API cấu hình AI key (BYOK) → tab Cài đặt ở chế độ thật không nối được |
| B15 | `Project` thiếu tên môn/lớp/nhóm và tóm tắt sprint/tiến độ; đề nghị nhúng `class {code,name}`, `group {name}`, `active_sprint {name,end_date,done_points,total_points}` để bỏ N+1 (danh sách dự án hiện gọi thêm `getClass`, `listClassGroups`, `members` cho từng dự án) |
| B16 | STUDENT gọi `GET /projects/?classroom_group_id=` bị 403; đề nghị cho thành viên lọc nhóm của chính mình. Frontend tải hết rồi lọc phía client |
| B17 | `tech_stack` là object tự do, chưa có cấu trúc hay tài liệu; frontend luôn gửi `{}` |
| B18 | Một nhóm có nhiều dự án nhưng không có khái niệm "dự án chính"; `identifier` duy nhất toàn hệ thống dễ trùng giữa các lớp; chưa có API xóa dự án |
| B19 | Liên kết Classroom↔Work (`GET /api/classroom/groups/{id}/projects/`) cập nhật bất đồng bộ qua Kafka; cần xác nhận consumer chạy trên staging và độ trễ tối đa. Phase 9 hỏi thẳng Work |
| B20 | Sidebar và My Work vẫn chạy MSW (`/api/work/api/v1/my-work/overview`); Work chưa có API tổng quan công việc của tôi |
| B21 | `GET /projects/{id}/members/` chậm (~5 giây trên staging); `ProjectMember.display_name` có thể rỗng khi `UserProjection` chưa đồng bộ, frontend tra lại qua `users/batch` |

## Kiểm tra đã chạy

Từ `apps/web`: `tsc --noEmit`, `vitest run`, `tsc -b && vite build` đều đạt
(53 file test). Chạy `vitest` phải không có `apps/web/.env.local`, vì file này
bật `VITE_REAL_SERVICES` và làm hàng chục test mock thất bại.

Smoke trình duyệt thật (Chrome qua relay, staging, `VITE_REAL_SERVICES=auth,classroom`):

- Phase 1–2: đăng nhập, F5 khôi phục phiên (`refresh` rồi `users/me`), đăng
  xuất rồi F5 (`refresh` 401, về `/login`).
- Phase 3: lưu hồ sơ (`PATCH /users/me`), đổi mật khẩu với mật khẩu cũ sai
  (hiện "Mật khẩu hiện tại không đúng."), danh sách và thu hồi thiết bị.
- Phase 4: kích hoạt với key sai (404, báo liên kết không hợp lệ), quên mật khẩu
  (trả thông báo trung tính).
- Phase 5–6: vào lớp bằng mã sai (404) và đúng (201), tạo nhóm, bật mã mời,
  chuyển Trưởng nhóm, rời nhóm.
- Phase 7–8: giảng viên đọc bàn làm việc và danh sách sinh viên của lớp thật;
  nhập CSV (3 dòng: 1 dòng sai email bị chặn ở giao diện, 1 thêm vào lớp, 1 đã
  thuộc lớp); tạo lớp từ môn có sẵn; sửa tên lớp; tạo mã tham gia.
  Chưa smoke giao diện: hộp "Thêm sinh viên" từng người (Chrome ngắt debugger
  khi mở hộp thoại), chốt lập nhóm, đóng/lưu trữ lớp, thêm giảng viên, chỉnh
  nhóm, lịch sử, `VERSION_CONFLICT`, nhập trên 100 dòng.

Hiệu năng danh sách lớp của sinh viên: API không có "nhóm của tôi" (B5) nên
`loadCourseEnrollments` dò `groups/` rồi `members/` của từng lớp. Mỗi request
trên staging mất khoảng 330 ms. Các lớp được dò song song tối đa
`CLASS_CONCURRENCY` (3) lớp; trang `/courses` với 4 lớp tải xong sau khoảng
4,5 giây thay vì 6,8 giây (đo trên Chrome qua relay, gồm cả `refresh` và
`users/me`). Phần còn lại là chuỗi request nối tiếp; chỉ hết hẳn khi backend
thêm `my_group` hoặc `member_count` (B5). Chưa smoke trình duyệt cho refresh
khi 401 hoặc hết hạn 15 phút.
