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
  `apps/web/vercel.json` rewrite `/api/(.*)` sang `https://utask-api.u-code.dev`
  (không dùng `/api/:path*`: mẫu này không khớp đường dẫn có `/` cuối như
  `/api/classroom/courses/`, Vercel trả 404 `NOT_FOUND`)
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
| 12 | Work: epic (tạo/sửa/xóa), nhãn (quản lý + gán), liên kết task, lưu trữ/xóa/khôi phục task | Một phần (đã smoke API thật và giao diện Backlog trên staging; xem giới hạn) |
| 13 | Work: sprint (tạo/sửa/bắt đầu/kết thúc), thêm/bớt issue khỏi sprint (menu và kéo thả Backlog), tiến độ + burndown, tổng quan dự án, sửa capacity | Một phần (đã smoke API thật và giao diện tạo/bắt đầu sprint trên staging; xem giới hạn) |
| 14 | Work: bình luận, lịch sử hoạt động, tệp đính kèm, phản hồi của giảng viên cho dự án | Một phần (đã smoke API thật trên staging; giao diện chỉ có test thành phần; upload từ trình duyệt có thể bị CORS của R2 chặn, B30) |
| 14 (GitHub) | Work: repository, liên kết GitHub, username GitHub, tab Code thật | Chưa triển khai (hoãn theo yêu cầu, vẫn dùng dữ liệu mock) |
| 15 | Work: Trang chủ (My Work) và Sidebar dựng từ dự án thật, tiến độ dự án cho giảng viên | Một phần (đã kiểm API đọc trên staging; chưa smoke giao diện; xem giới hạn) |
| 16 | AI: nền (client, cờ `ai`, polling) và AI tách nhiệm vụ con (`task_decomposition`) | Một phần (đã smoke trình duyệt: Work thật trên staging + AI giả qua MSW; AI staging chưa dùng được, xem B32) |
| 17 | AI: gợi ý backlog (`backlog_generation`) | Một phần (AI thật bị chặn bởi B32; smoke với AI qua MSW) |
| 18 | AI: phân tích rủi ro (`risk_analysis`, chỉ đọc) | Hoãn, không làm theo yêu cầu (DTO `AiRiskRequest` và mock vẫn còn, không có UI) |
| 19+ | Admin | Chưa triển khai |

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
GitHub, AI (B14). Sidebar và My Work chạy thật từ Phase 15 (B20), nên
`CourseEnrollment.projectId` giờ có người tiêu thụ; dự án smoke chỉ lưu trữ
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

- Quyền: Leader ghi mọi task; thành viên chỉ task được giao cho mình và **chỉ sửa mô tả** (backend `require_member_fields(.., {"description_html"})`: gửi `title` hoặc `acceptance_criteria` bị 403 `LEADER_PERMISSION_REQUIRED`, nên hai ô đó chỉ đọc); giảng viên và dự án lưu trữ không có nút ghi. Backend chưa chặn thành viên thường tạo nhãn (`metadata.py`), UI chỉ cho Leader.
- `Idempotency-Key` chỉ ở tạo issue và tạo nhiệm vụ con; PATCH, transition, block, unblock không gửi. Block/unblock là `PATCH`.
- Đổi cột: server tính vị trí trên **cột đầy đủ** (gồm nhiệm vụ con và task ngoài sprint đang chạy), nên neighbor không lấy từ cột Board đang hiện. Client gọi `GET tasks?state_id=&fields=id,sort_order` rồi `planNeighbours` chọn hàng xóm liền kề; chuyển cột từ menu thì xếp cuối cột.
- Cập nhật lạc quan, hoàn tác và tải lại khi lỗi. Thành công chỉ ghi `version` và `sort_order` thật, không tải lại workspace.
- `VERSION_CONFLICT` ở form sửa: hiện "Dữ liệu đã được cập nhật bởi thao tác khác…" và nạp lại form theo bản mới.
- `description_html` gửi đúng text nhập, không render HTML.

Giới hạn:

- Backlog vẫn chỉ đọc: thêm/bớt sprint thuộc Phase 13, thứ tự trong section Backlog chưa có ngữ nghĩa neighbor hợp lệ.
- Chưa có nút chặn trong panel, dùng menu thẻ trên Board. Menu chặn ẩn với task COMPLETED/CANCELLED.
- Tick nhiệm vụ con chuyển sang state COMPLETED đầu tiên; bỏ tick chuyển sang state UNSTARTED đầu tiên (đặt cuối cột).
- Tạo issue từ Board khi có Sprint đang chạy: mặc định có ô "Thêm vào Sprint đang chạy" kèm "Lý do thêm vào Sprint" (bắt buộc, vì backend đòi `scope_change_reason` với sprint `ACTIVE`). Backend không có lệnh "tạo trong sprint" nên đây là hai lệnh: `POST /projects/{id}/tasks/` rồi `POST /sprints/{id}/tasks/` (`action: ADD`, hook `useAddTaskToSprint`). Lệnh thêm lỗi thì issue vẫn đã tạo, nằm ở Product Backlog; web báo rõ và không gửi lại lệnh tạo. Bỏ chọn ô thì issue vào Product Backlog như trước. Sprint đang chạy nhưng chưa có issue: Board hiện "Sprint chưa có issue" kèm link "Mở Backlog", thay vì "Không có issue khớp bộ lọc". Đã smoke trên staging (Leader, sprint đang chạy, issue hiện ngay trên Board; đã dọn dẹp).
- Kiểm tra trên: `tsc`, 70 file test cả khi có và không có `.env.local` (test đầu tiên của `RealWorkspace` có lần chậm khi cả bộ chạy song song), build. ESLint không chạy được (thiếu module).
- Smoke trình duyệt (staging): Leader tạo issue, đổi cột bằng menu và tải lại, chặn/bỏ chặn, sửa tiêu đề trong panel, tạo nhiệm vụ con; Teacher không có nút tạo issue hay menu thao tác. Chưa smoke: kéo thả bằng chuột, thành viên không phải Leader, `VERSION_CONFLICT` trên staging, tick nhiệm vụ con.

## Work epic, nhãn, liên kết, lưu trữ/xóa (Phase 12)

Trạng thái: **Một phần**. Mã: `lib/api/work/endpoints.tasks.ts` (epic, nhãn, `setTaskLabels`, `createRelation`/`deleteRelation`, `changeTaskLifecycle`, `listTasksInScope`), hook `lib/query/workMetaHooks.ts`, giao diện `EpicDialog`, `LabelManagerDialog`, `IssueExtras`, `RealBacklogTools`.

- **Epic** (cột Epics ở Backlog): Leader tạo/sửa/xóa. Người phụ trách epic (không phải Leader) chỉ sửa tên, mô tả, trạng thái; form tắt ô người phụ trách và hai ô ngày. Client chặn `start_date > target_date` trước khi gửi (server trả 400 `VALIDATION_ERROR` với `details` rỗng). Epic không có `version` nên không có hộp "nạp lại sau xung đột".
- **Nhãn**: Leader quản lý (tạo/đổi tên/màu/xóa) từ "Quản lý nhãn" ở Backlog; màu phải `#RRGGBB`. Xóa nhãn gỡ khỏi mọi task nên mọi cache Work được làm mới. Gán/bỏ nhãn ở panel dùng `POST tasks/{id}/labels/` (`ADD`/`REMOVE`) kèm `expected_version`; Leader hoặc người được giao đều làm được.
- **Liên kết** (panel): `BLOCKS`, `BLOCKED_BY`, `DUPLICATE`, `RELATES_TO`, hiển thị theo góc nhìn task đang xem (`expand=relations` chỉ có ở `getTask`). Mã lỗi vòng chặn thật là `DAG_CYCLE_DETECTED` (409), hiện "Liên kết này tạo vòng chặn."; liên kết trùng là 409 `INVALID_OPERATION`.
- **Lưu trữ/xóa/khôi phục** (Leader): nút trong panel kèm `ConfirmDialog`, sau thành công panel đóng. Backlog có bộ chọn "Đang hoạt động / Đã lưu trữ / Đã xóa" (`status=archived|deleted`), Leader mở lại hoặc khôi phục từ đó. Xóa mềm cascade cả nhiệm vụ con; khôi phục con khi cha còn bị xóa trả `INVALID_OPERATION`, UI hiện nguyên văn.
- Không gửi `Idempotency-Key` ở mọi lệnh Phase 12 (backend không đăng ký receipt cho chúng).

Giới hạn:

- Không có giao diện đổi cha hoặc đổi `type` của task: backend không có URL cho `reparent_task` và `type` bất biến.
- Danh sách "Đã lưu trữ/Đã xóa" là danh sách phẳng (mã, tiêu đề), không mở được panel.
- Nhãn hiện trên thẻ (tối đa 3, phần dư gộp "+n") lấy từ `expand=labels` của danh sách task; chưa lọc theo nhãn.
- Epic lỗi không làm hỏng Board/Backlog: workspace đặt `partial` và hiện "Một phần dữ liệu chưa tải được (danh sách epic)."; states, tasks, sprints lỗi vẫn là lỗi cả trang.
- Đích liên kết chỉ chọn trong issue đã tải ở Board/Backlog (không gồm nhiệm vụ con).
- Kiểm tra: `tsc`, 74 file / 980 test cả khi có và không có `.env.local`, build; ESLint không chạy được. Smoke staging: API thật cho epic (cả lỗi ngày), nhãn, gán nhãn, liên kết, vòng chặn, trùng, lưu trữ/mở lại/xóa/khôi phục; giao diện Backlog tạo epic (lỗi ngày rồi thành công), xóa epic, mở hộp nhãn, tab "Đã lưu trữ". Chưa smoke giao diện: gán nhãn và liên kết trong panel, xóa/lưu trữ từ panel, khôi phục từ tab, thành viên không phải Leader.

## Work sprint, tiến độ, tổng quan (Phase 13)

- Quyền: chỉ Leader tạo/sửa/bắt đầu/kết thúc sprint, đổi phạm vi sprint và sửa capacity. Thành viên và giảng viên chỉ xem. Dự án lưu trữ ẩn mọi nút ghi.
- Mọi lệnh ghi sprint đọc lại `version` của sprint ngay trước khi gửi (workspace không giữ `version` sprint). `start`, `tasks`, `close` gửi `Idempotency-Key`; tạo sprint, sửa sprint và capacity thì không.
- Bắt đầu cần đủ hai ngày và chưa có sprint đang chạy (nút tắt kèm lý do nếu thiếu ngày). Kết thúc chọn sprint nháp đích hoặc trả issue chưa xong về Product Backlog.
- Đổi sprint của issue dùng lại menu/kéo thả Backlog (`useIssueMover`). Backlog thật giờ ghi được. Đổi sprint là REMOVE rồi ADD, **không nguyên tử**; sprint đang chạy bắt buộc có lý do (`scope_change_reason`). Đổi sprint không đổi `version` của task.
- Tiến độ và burndown (theo điểm ước lượng) lấy từ server cho sprint đang chạy; đường lý tưởng tự vẽ phía client. Tổng quan dự án ở trang Thông tin; `GET .../dashboard/` **không nhận query param** (có param → 400 trên staging).
- Capacity sửa ngay trong bảng thành viên; chỉ Leader, dự án chưa lưu trữ. Bảng khối lượng có cột "Dùng capacity (ước lượng)" = điểm đã giao / capacity tuần, **tính phía client** (server không trả); "—" khi chưa đặt hoặc bằng 0. Đơn vị: capacity là giờ/tuần còn điểm là story point, nên chỉ để tham khảo.
- Giới hạn: workspace bỏ sprint đã hoàn thành; Backlog không có issue thì ẩn cả sprint và thanh công cụ sprint; chưa có giao diện lưu trữ/xóa sprint; kiểm tra thành viên phải còn hoạt động mới gán capacity (422 `MEMBER_NOT_ACTIVE`).
- Kiểm tra: `tsc`, 79 file / 1017 test cả khi có và không có `.env.local`, build; ESLint không chạy được. Smoke staging: API thật (tạo, bắt đầu thiếu ngày → 400 `INVALID_OPERATION`, thêm vào sprint đang chạy thiếu lý do → 422, có lý do → `is_scope_creep`, progress, burndown, dashboard, kết thúc có đích, capacity); giao diện tạo sprint và bắt đầu sprint (hiện tiến độ). Chưa smoke giao diện: menu đổi sprint, hộp kết thúc sprint, sửa capacity, thành viên không phải Leader (có test thành phần).

## Work cộng tác: bình luận, lịch sử, đính kèm (Phase 14)

- Phạm vi: **không gồm GitHub** (repository, liên kết, username, tab Code) — hoãn theo yêu cầu, giữ dữ liệu mock.
- Bình luận (panel issue, chế độ thật): gửi **text thuần** làm `content_html` (repo chưa có thư viện sanitize); không bao giờ gửi `is_teacher_feedback` (server tự gắn huy hiệu). Không dùng `Idempotency-Key`. Người nhắc (@) chọn từ thành viên, mention ngoài dự án → 422 và giữ nguyên nội dung. Chỉ tác giả sửa; tác giả hoặc Leader xóa. Dự án lưu trữ ẩn ô soạn.
- Lịch sử: `GET tasks/{id}/activities/`; giá trị cũ/mới là chuỗi thô, `parseActivityValue` thử JSON rồi trả nguyên văn. Chưa có lịch sử cấp dự án.
- Đính kèm: presign → `PUT` thẳng lên R2 bằng `fetch` (không gửi token) → confirm có `Idempotency-Key`. Client kiểm loại tệp (7 loại) và cỡ ≤ 25 MB trước. Link tải lấy mới ngay trước khi mở, không cache. 503 → "Kho lưu trữ chưa sẵn sàng", không tự thử lại; R2 từ chối → thông báo chọn lại tệp.
- Giảng viên: ô "Phản hồi cho nhóm" ở trang nhóm (Work thật) là bình luận cấp dự án (`POST /comments/` với `project_id`). Nhánh demo vẫn là bản nháp cục bộ.
- Kiểm tra: `tsc`, test cả khi có và không có `.env.local`, build; ESLint không chạy được. Smoke staging API thật: tạo/sửa/xóa bình luận, mention ngoài dự án → 422, activities, presign, `PUT` từ Node, confirm, link tải, xóa tệp. **Chưa smoke giao diện trình duyệt**; huy hiệu giảng viên và mention hợp lệ chưa thử trên staging (dự án smoke chỉ có 1 thành viên).

## Work Trang chủ, Sidebar, giảng viên (Phase 15)

- Điều kiện: chỉ khi **cả Work và Classroom** là thật (`VITE_REAL_SERVICES` có `work` và `classroom`); thiếu một trong hai vẫn dùng MSW.
- Tổng quan (`useMyWorkOverview`, dùng cho Trang chủ và Sidebar) dựng phía client: môn học lấy từ Classroom, việc của tôi lấy bằng fan-out `GET projects/{id}/tasks/?assignee_id=<tôi>` cho từng dự án chưa lưu trữ mà tôi là thành viên (đợt 5 song song), tiến độ sprint đang chạy lấy từ `sprints/{id}/progress/`. Một dự án lỗi bị bỏ qua và trang hiện "Một phần dữ liệu chưa tải được."; lỗi tiến độ sprint chỉ làm mất thẻ sprint đó.
- Sidebar: môn học có dự án chưa lưu trữ thì mở thẳng dự án (gắn theo `class_id`).
- Task chưa có hạn không thuộc bộ lọc Hôm nay/Tuần này/Quá hạn nên thêm tab "Chưa đặt hạn"; `MyTask.dueAt` có thể `null`. Hạn `due_date` chỉ có ngày, coi là hết ngày đó.
- Thẻ sprint: điểm lấy từ server; "sức khỏe" (đúng tiến độ/rủi ro/trễ) là **ước lượng phía client** (quá hạn chưa xong → trễ; chậm hơn thời gian trôi trên 20 điểm % → rủi ro). Không có tên giảng viên (Work không cấp) nên ẩn dòng GVHD.
- Giảng viên: trang nhóm có thẻ "Tiến độ dự án" (số task, % hoàn thành, quá hạn, đang bị chặn từ `dashboard`) và "Phản hồi cho nhóm" (bình luận cấp dự án). Các màn Board/Backlog đã chỉ đọc cho giảng viên từ Phase 10–13.
- Không có ở chế độ thật: khối GitHub của Trang chủ, số PR (`openPullRequests` luôn 0, UI không hiện), tab Code và Settings (`WorkModuleNotIntegrated`, chờ GitHub và plan AI).
- Kiểm tra: `tsc`, test cả khi có và không có `.env.local`, build; ESLint không chạy được. Staging chỉ có dự án smoke đã lưu trữ nên fan-out Trang chủ chưa chạy với dữ liệu sống; đã kiểm `tasks?assignee_id`, `dashboard` và `comments` đọc được bằng cả hai tài khoản. Chưa smoke giao diện.

## AI Service (Phase 16–17)

- Cờ: thêm `ai` vào `VITE_REAL_SERVICES` để gọi AI Service thật. Không có `ai` thì `src/mocks/handlers/ai.ts` trả gợi ý cố định (dùng được cùng Work thật). Chỉ hiện ở chế độ Work thật; AI demo cũ (`AiSubtaskAction`, thanh "Trợ lý AI Scrum Copilot") giữ nguyên cho chế độ mock.
- URL từ trình duyệt là `/api/ai/v1/requests`: nginx chuyển nguyên đường dẫn cho AI Service (trước đây cắt tiền tố nên URL cũ `/api/ai/api/ai/v1/...` nay trả 404 `{"detail":"Not Found"}`). Phản hồi AI **không** bọc `{success, data}`; lỗi là `{error:{code,message,details:{...},request_id,retryable}}`. `client.ts` đọc được cả hai dạng (Work: `details` là mảng, `message` ở ngoài; AI: `details` là object, `message` trong `error`, thời gian chờ ở `details.retry_after_seconds`).
- Luồng: `POST /requests` (bắt buộc `Idempotency-Key`) trả 200 khi xong trong 10 giây hoặc 202 kèm `status_url`. Sau 202, web hỏi lại bằng `GET` với khoảng chờ tăng dần: 2 giây, 3 giây, 4,5 giây, sau đó cố định 5 giây (`pollDelayMs` trong `src/lib/api/ai/endpoints.ts`). Web hỏi tới khi server trả `succeeded` hoặc `failed`. Hạn 30 giây của server chỉ tính từ lúc worker bắt đầu chạy; trước đó request có thể chờ trong hàng đợi tới 300 giây (`QUEUE_TIMEOUT`), vì worker chỉ chạy 2 việc cùng lúc cho mọi người dùng. Vì vậy web chỉ tự dừng sau 360 giây (`AI_MAX_WAIT_MS`), lâu hơn toàn bộ vòng đời của server. Trước đây web dừng cứng ở 45 giây kể từ lúc gửi, nên báo "AI xử lý quá lâu" trong khi request vẫn đang chờ hoặc đang chạy. Đóng hộp thoại chỉ dừng chờ ở trình duyệt; request vẫn chạy ở server và vẫn tính vào giới hạn 2 yêu cầu đang chạy / 5 yêu cầu mỗi phút.
- AI tách nhiệm vụ con: nút "AI tách nhiệm vụ con" cạnh mục Nhiệm vụ con trong panel issue, cho Leader hoặc người được giao task (dự án chưa lưu trữ, không phải giảng viên). AI chỉ **đề xuất**; người dùng bỏ chọn/sửa tiêu đề rồi bấm Accept thì web tạo từng nhiệm vụ con qua `POST /tasks/{id}/subtasks/`, tuần tự, mỗi mục một `Idempotency-Key`. Dừng ở lỗi đầu tiên; "Thử lại phần còn lại" chỉ gửi các mục chưa tạo, giữ nguyên khóa. Người không phải Leader chỉ gửi title, mô tả, tiêu chí (backend tự giao cho họ, bỏ điểm); Leader gửi thêm `story_points = round(estimate_points)`.
- Không dùng `bulk-apply-ai` của Work: nó cần `VerifiedProposal` từ `ai_client().verify()`, mà adapter mặc định `WORK_AI_ADAPTER` là `UnavailableProposals` (luôn 503) và AI Service không có endpoint verify, kết quả cũng thiếu `local_id`, `ai_revision`, `context_version` kiểu số (xem B31). Logic apply gom trong `src/lib/api/ai/applyProposal.ts`; khi backend xong chỉ cần thay module này. Hệ quả: nhiệm vụ con tạo ra có `source=MANUAL`, không có `ai_proposal_id`.
- `dependencies` AI trả là chuỗi tự do, chỉ hiện dạng văn bản, không tạo liên kết task. Gợi ý không lưu khi đóng hộp thoại.
- AI gợi ý backlog (Phase 17): nút "AI gợi ý backlog" cạnh "Tạo sprint" ở trang Backlog, chỉ Leader, dự án chưa lưu trữ. Form điền sẵn mô tả (hoặc tên nếu mô tả trống) và mục tiêu từ dự án; công nghệ để trống vì `tech_stack` của Work là object tự do (B17). Mỗi danh sách một mục mỗi dòng, tối đa 30 mục (vượt thì chặn gửi); `deadline` = hết ngày `end_date` giờ Việt Nam (+07:00); khóa rỗng không gửi vì AI Service từ chối. Accept tạo từng issue qua `POST /projects/{id}/tasks/` (loại TASK, `priority` low/medium/high/critical → LOW/MEDIUM/HIGH/URGENT, điểm = làm tròn `estimate_points`), cùng cơ chế tuần tự/thử lại như tách nhiệm vụ con; issue tạo ra có `source=MANUAL`. Logic form ở `features/projects/lib/aiBacklogForm.ts`.
- Kiểm tra: `tsc`, test cả khi có và không có `.env.local` (97 file, 1147 test), build. ESLint không chạy được. Smoke trình duyệt (Chrome, Vite `VITE_REAL_SERVICES=auth,classroom,work`, AI qua MSW): Phase 16 hộp gợi ý hiện sau ~3 giây, Accept tạo 3 nhiệm vụ con thật; Phase 17 form điền sẵn mô tả, gợi ý hiện sau ~3 giây, Accept tạo 3 issue thật hiện trong Backlog trên dự án smoke staging; đã xóa sau khi kiểm. Lưu ý WSL: `node.exe` không thấy biến môi trường của WSL nếu thiếu `WSLENV=VITE_REAL_SERVICES:VITE_ENABLE_MOCKS`.

## GitHub qua Integration và Work (Phase 18)

Trạng thái: **Một phần** (đang làm theo từng giai đoạn; mục dưới ghi phần đã có). Kế hoạch: nối web với Integration Service (liên kết tài khoản, cài GitHub App, xem repo) và các route GitHub của Work (username, repository dự án, link task). Theo ADR-004, Integration sở hữu liên kết tài khoản GitHub, nên web dùng luồng consent của Integration, **không** dùng `/api/auth/oauth/github` của Identity.

### Nền tảng client Integration (giai đoạn 1)

- Bật bằng `VITE_REAL_SERVICES=...,integration`. Không có `integration` thì phần GitHub vẫn dùng dữ liệu demo như cũ.
- Mã: `lib/api/integration/dto.ts`, `lib/api/integration/endpoints.ts`. Gateway `/api/integrations/` chuyển nguyên đường dẫn; nginx chặn `/api/integrations/api/v1/internal/*`.
- Phản hồi dạng `{success:true,data}`, lỗi `{success:false,error:{code,message}}`; `client.requestEnvelope` đọc được cả hai.
- Hai route `start` từ chối mọi body và query: client không gửi `body` (nên cũng không có header `Content-Type`). Hai route `complete` chỉ nhận đúng bộ key của nó, thiếu hoặc thừa đều bị từ chối.

| Endpoint (tiền tố `/api/integrations/api/v1/github`) | Hàm client | Nhãn (source) | Nhãn (staging) |
|---|---|---|---|
| `GET /account` | `getGitHubAccount` | Đã triển khai | Chưa xác minh (không token → 401 `NOT_AUTHENTICATED`; cờ App chưa rõ) |
| `DELETE /account` | `unlinkGitHubAccount` | Đã triển khai | Chưa xác minh |
| `POST /authorizations/start` | `startGitHubAuthorization` | Đã triển khai | Chưa xác minh |
| `POST /authorizations/complete` body `{code,state}` | `completeGitHubAuthorization` | Đã triển khai | Chưa xác minh |
| `POST /installations/start` | `startGitHubInstallation` | Đã triển khai | Chưa xác minh |
| `POST /installations/complete` body `{state,installation_id,setup_action}` | `completeGitHubInstallation` | Đã triển khai | Chưa xác minh |
| `GET /installations?page=&per_page=` | `listGitHubInstallations` | Đã triển khai | Chưa xác minh |
| `GET /installations/{id}/repositories?page=&per_page=` | `listGitHubRepositories` | Đã triển khai | Chưa xác minh |

Khi `INTEGRATION_GITHUB_APP_ENABLED=false`, mọi route trả 503 `GITHUB_UNAVAILABLE`. `/api/integrations/healthz` trả 200 trên staging (ngày 21/10/2026).

Test dùng `src/test/integrationHandlers.ts` (MSW): handler `start` trả 400 nếu request có body hoặc query, handler `complete` trả 400 nếu thiếu hoặc thừa key.

### Liên kết tài khoản GitHub (giai đoạn 2)

- Trang `/settings/integrations` chọn component theo cờ: `integration` bật thì `RealGitHubIntegration`, ngược lại giữ `SettingsIntegrationsPage` (demo MSW). Hook ở `lib/query/integrationHooks.ts`.
- Luồng: bấm "Liên kết GitHub" → `POST authorizations/start` → trình duyệt chuyển sang `authorization_url` → GitHub quay về `/settings/integrations/github/callback?code=&state=` → route `GitHubAuthorizationCallbackRoute` gọi `POST authorizations/complete` đúng một lần (khóa theo `state` để StrictMode không gọi lại, vì `state` chỉ dùng được một lần) → về `/settings/integrations`. GitHub trả `error` (ví dụ `access_denied`) thì chỉ báo hủy, không gọi API; thiếu `code` hoặc `state` thì báo callback không hợp lệ.
- Trạng thái hiển thị: chỉ `status=LINKED` là đã liên kết. `authorization_status` `ACTIVE` → "Đã liên kết @…" kèm nút "Ngắt liên kết"; `REAUTH_REQUIRED` → "Cần cấp quyền lại"; `REVOKED`/`NOT_AUTHORIZED` → "Quyền GitHub đã bị thu hồi"; còn lại (kể cả giá trị lạ) → "Chưa liên kết GitHub", không làm vỡ giao diện.
- Lỗi dịch bằng `githubErrorMessage` (503 `GITHUB_UNAVAILABLE` → "Máy chủ chưa bật kết nối GitHub.", 409 `GITHUB_CONSENT_CONFLICT`/`GITHUB_REAUTH_REQUIRED`, 429 `GITHUB_RATE_LIMITED`, 403 `GITHUB_ACCESS_DENIED`, 400 → phiên hết hạn; lỗi khác giữ message của server).
- Luồng Identity `/api/auth/oauth/github` **không dùng** (ADR-004: Integration sở hữu liên kết; route Identity đó đang tắt trên staging). Staging: **Chưa xác minh** cho tới khi B33 xong.
- Smoke staging ngày 21/10/2026 (Vite local trỏ `utask-api.u-code.dev`, đăng nhập sinh viên thật, `VITE_REAL_SERVICES=auth,classroom,work,ai,integration`): `GET account` trả 200 (tài khoản chưa liên kết → "Chưa liên kết GitHub"); bấm "Liên kết GitHub" → `POST authorizations/start` 200 → trình duyệt chuyển tới `github.com/login/oauth/authorize` (đăng nhập GitHub). Cờ App trên staging **đang bật**. Nhưng `redirect_uri` trong URL là `https://utask-api.u-code.dev/api/integrations/healthz` (giá trị tạm), nên GitHub sẽ không quay về callback của web: cần B33. Chưa xác minh: bước `complete` thật và việc khôi phục phiên sau redirect (không có tài khoản GitHub để thử).

### Cài GitHub App và xem repository (giai đoạn 3)

- Card "GitHub App" nằm dưới card tài khoản ở `/settings/integrations`. Tài khoản chưa `ACTIVE` thì nút "Cài GitHub App" bị vô hiệu kèm "Cần liên kết GitHub trước." và không gọi `GET installations`.
- Khi `ACTIVE`: liệt kê installation (`account.login (account.type)`, `repository_selection`: `all` → "Tất cả repo", `selected` → "Repo được chọn"); bấm một installation để mở danh sách repository (`full_name`, nhãn "Private", nút "Tải thêm" gọi `page` kế tiếp); danh sách rỗng → "Chưa cài GitHub App cho tài khoản/tổ chức nào.". Hook: `useGitHubInstallations`, `useGitHubRepositories` (`useInfiniteQuery`, theo `next_page`).
- Luồng cài đặt: "Cài/cập nhật GitHub App" → `POST installations/start` → chuyển sang `installation_url` → GitHub quay về `/settings/integrations/github/setup?installation_id=&setup_action=&state=` → route `GitHubInstallationCallbackRoute` gọi `POST installations/complete` đúng một lần (khóa theo `state`). `ACTIVE` → về settings; `PENDING_APPROVAL` → thông báo chờ chủ tổ chức duyệt; `setup_action=request` không có `installation_id` → thông báo đã gửi yêu cầu, không gọi API; thiếu `state`, `setup_action` ngoài `install|update|request` hoặc thiếu `installation_id` → "Liên kết callback không hợp lệ."
- Staging: **Chưa xác minh** luồng cài đặt thật (chặn bởi B33 và cần tài khoản GitHub).
- Smoke staging ngày 21/10/2026 (tài khoản sinh viên chưa liên kết): card hiện "Cần liên kết GitHub trước." và nút "Cài GitHub App" bị vô hiệu; mở `/settings/integrations/github/setup?state=x&installation_id=1&setup_action=install` gọi `POST installations/complete` thật, server trả 400 và web hiện "Phiên cấp quyền đã hết hạn hoặc không hợp lệ." kèm nút "Thử lại cài đặt".

### Username GitHub của thành viên dự án (giai đoạn 4)

- Tab Thông tin dự án (`ProjectInfoRoute`, `MembersTable`) có cột "GitHub" (component `MemberGitHubCell`). Hàng của chính mình: ô nhập username → `PATCH /api/work/projects/{id}/members/{uid}/github/` body `{github_username}` (bỏ `@` đầu, không gửi `Idempotency-Key`). Hàng người khác: `@username` kèm nhãn "Đã xác minh"/"Chưa xác minh"; Leader thấy thêm "Yêu cầu xác minh" cho người chưa xác minh → `POST .../github/request-verification/` (không body, `Idempotency-Key` mới mỗi lần bấm), sau đó nút thành "Đã gửi yêu cầu".
- Lỗi hiện nguyên message server (ví dụ `INVALID_OPERATION` khi dự án chỉ đọc hoặc username đã xác minh). Thành công thì `workKeys.all` được tải lại. Hook: `lib/query/workGithubHooks.ts`; client: `lib/api/work/endpoints.github.ts`.
- Staging: **Chưa xác minh**. Nguồn cập nhật `is_github_verified`: B37.

### Kết nối repository cho dự án — tab Code (giai đoạn 5)

- Tab Code (`ProjectCodeRoute` → `RealProjectCode` khi `work` bật) đọc `GET /api/work/projects/{id}/github/repository/`: hiện `owner/name` (link `https://github.com/...`), nhánh mặc định, `synced_at` và nhãn `status` (`CONNECTED` "Đã kết nối", `PENDING` "Đang kết nối", còn lại "Chưa kết nối"). Dòng "Hoạt động commit/PR chưa có API (B36)."
- Leader (dự án chưa lưu trữ) có nút "Chọn repository": hộp thoại dùng lại `useGitHubInstallations`/`useGitHubRepositories` của Integration (chọn installation → "Kết nối"). `integration` tắt → "Cần bật Integration để chọn repo."; GitHub chưa `ACTIVE` → liên kết tới `/settings/integrations`.
- `POST` body `{github_repo_id, operation_id, expected_connection_generation}` (`expected_connection_generation = connection_generation ?? 0`), `Idempotency-Key = operation_id`. `operation_id` sinh một lần cho mỗi repo, giữ khi thử lại cùng repo, sinh mới khi đổi repo, sau khi thành công hoặc sau 409. `requestEnvelope` không trả HTTP status nên nhận diện 202 bằng `data.status === "PENDING"`; web hỏi lại `GET` mỗi 2000ms tối đa 15 lần, dừng khi `status` hết `PENDING` hoặc `operation_id` đã khác; hết hạn → "Kết nối đang chờ xử lý, tải lại sau."
- Lỗi: 409 → "Kết nối repo đã thay đổi, đã tải lại."; 503 `INTEGRATION_UNAVAILABLE` → thông báo B34. Không có nút ngắt kết nối (B35). Staging: **Chưa xác minh** (B34 chặn); đã kiểm bằng MSW.
- Smoke staging ngày 21/10/2026 (Leader `aunhathuy28`, dự án PRJ1): `GET .../github/repository/` thật trả bản ghi rỗng → tab hiện "Chưa kết nối" và nút "Chọn repository"; vì tài khoản chưa liên kết GitHub nên hộp thoại hiện "Cần liên kết GitHub trước." kèm link tới cài đặt. Chưa xác minh: `POST` chọn repo thật (cần tài khoản GitHub đã liên kết, B33, và B34).

### Link GitHub của task trong IssuePanel (giai đoạn 6)

- Khối "GitHub Development" của `IssuePanel` nhận prop `githubSlot`; `IssuePanelHost` truyền `RealGitHubLinks` khi chạy Work thật (nhánh demo vẫn render `detail.gitLinks`). Client: `listTaskGitHubLinks` (`GET tasks/{id}/github-links/`, bỏ link có `deleted_at`), `createTaskGitHubLink` (`POST`, body `{link_type, github_ref_id}`, luôn gửi `Idempotency-Key`), `confirmTaskGitHubLink` (`POST .../{lid}/confirm/`, không body, key bắt buộc), `deleteTaskGitHubLink` (`DELETE .../{lid}/`).
- Mỗi link hiện loại (Nhánh/Commit/Pull Request), `github_title` hoặc `github_ref_id` (PR thêm `#`), `github_status`, link `github_url`, nhãn "Chờ xác nhận"/"Đã xác nhận". "Xác nhận" chỉ hiện khi `PENDING` và `is_verified`. Form thêm link và nút "Xóa" chỉ hiện khi `canEditRealIssue` (Leader hoặc người được giao, dự án chưa lưu trữ, không phải giảng viên).
- Client chỉ kiểm PR phải là số nguyên dương (bỏ `#` đầu); `github_ref_id` gửi nguyên văn, server chuẩn hóa. `Idempotency-Key` giữ nguyên khi thử lại cùng input, sinh mới khi input đổi hoặc sau khi thành công.
- Lỗi: 503 `INTEGRATION_UNAVAILABLE` → thông báo B34; `INVALID_OPERATION` (ví dụ dự án chưa nối repo, link chưa `is_verified`) → hiện message server kèm link tới tab Code. Staging: **Chưa xác minh** thao tác ghi (B34 chặn); đã kiểm bằng MSW.

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
| B20 | Work chưa có API "việc của tôi" xuyên dự án; Trang chủ và Sidebar gom bằng N+1 lời gọi (Phase 15), chậm khi sinh viên có nhiều dự án. Cần endpoint tổng hợp nếu số dự án lớn |
| B21 | `GET /projects/{id}/members/` chậm (~5 giây trên staging); `ProjectMember.display_name` có thể rỗng khi `UserProjection` chưa đồng bộ, frontend tra lại qua `users/batch` |
| B30 | Preflight `OPTIONS` từ origin web tới URL presign R2 trả 403, không có header `access-control-*`; `PUT` từ Node thì qua. Nếu bucket chưa cho origin của web (method `PUT`, header `Content-Type`) thì upload từ trình duyệt sẽ bị chặn. Cần backend/ops cấu hình CORS bucket và xác nhận trên trình duyệt; nếu không, ẩn khối đính kèm |
| B31 | `bulk-apply-ai` của Work chưa dùng được đầu-cuối: `WORK_AI_ADAPTER` mặc định `UnavailableProposals` (luôn 503 `AI_DEPENDENCY_UNAVAILABLE`); AI Service không có endpoint verify; kết quả AI thiếu `local_id`/`ai_revision` cho từng mục và `context_version` kiểu số (hiện chỉ có `fingerprint` dạng chuỗi). Cần backend thống nhất hợp đồng verify/apply và bật adapter thật; sau đó web đổi `applyProposal.ts` sang bulk để có provenance (`source=AI_*`, `ai_proposal_id`) và tạo nguyên tử |
| B32 | AI staging từ chối access token thật: `/api/ai/v1/requests` trả 500 `INTERNAL_ERROR` (`details.reason=AUTH_UNAVAILABLE`, "Chưa thể xác minh identity.") ngày 2026-10-21. Đã khoanh vùng từ bên ngoài: token sửa chữ ký trả 401, nên AI đã có issuer/audience và tải được JWKS; token thật qua bước kiểm chữ ký rồi lỗi ở bước gọi Identity `POST /api/v1/internal/auth/session-status` (`apps/ai-service/src/infrastructure/security.py`, `_session_active`). AI ở `AI_ENVIRONMENT=staging` không khởi động được nếu `AI_IDENTITY_SERVICE_KEY` rỗng, và Work dùng cùng endpoint vẫn chạy, nên nguyên nhân khả dĩ nhất là Identity trả 403: `IDENTITY_SERVICE_KEYS` trong `.env` staging thiếu mục `"ai"` hoặc giá trị khác `AI_IDENTITY_SERVICE_KEY` (Chưa xác minh, cần xem `.env` trên VPS). Backend thêm `"ai":"<cùng giá trị AI_IDENTITY_SERVICE_KEY>"` vào `IDENTITY_SERVICE_KEYS` rồi khởi động lại `identity-service` |
| B33 | Luồng GitHub thật của Integration chưa chạy đầu-cuối trên staging (**Chưa xác minh**; ngày 21/10/2026 `authorizations/start` trả 200 nhưng `redirect_uri` còn là giá trị tạm `https://utask-api.u-code.dev/api/integrations/healthz`). Cần backend/devops: (1) `INTEGRATION_GITHUB_APP_ENABLED=true` cùng đủ credential của GitHub App (tắt thì mọi route trả 503 `GITHUB_UNAVAILABLE`; trên staging đã bật); (2) `INTEGRATION_GITHUB_REDIRECT_URI=https://utask.u-code.dev/settings/integrations/github/callback` (dev: `http://localhost:5173/settings/integrations/github/callback`), và Callback URL của GitHub App phải trùng giá trị này; (3) `INTEGRATION_GITHUB_SETUP_URI=https://utask.u-code.dev/settings/integrations/github/setup`, Setup URL của GitHub App phải trùng giá trị này và bật "Redirect on update"; nếu GitHub không trả `state` về Setup URL (cần bật "Request user authorization during installation"), route setup báo "Liên kết callback không hợp lệ" vì web không bỏ qua bước kiểm `state`; (4) nếu `complete` trả 400 dù vừa `start` xong, kiểm `INTEGRATION_CONSENT_COOKIE_SECURE` (dev chạy http thì phải `false`); cookie nonce HttpOnly, SameSite=Lax, `path=/`, TTL 600 giây nên web và `/api` phải cùng origin |
| B34 | Work chưa chọn được repository và chưa tạo được link GitHub cho task trên bất kỳ môi trường nào (**Chưa xác minh** trên staging): adapter mặc định của Work vẫn là `UnavailableIntegration`, nên `GET\|POST projects/{id}/github/repository/` và các route link task trả 503 `INTEGRATION_UNAVAILABLE`. Cần backend viết HTTP adapter gọi Integration Service và trỏ `WORK_INTEGRATION_ADAPTER` tới nó. Web đã làm đủ theo contract Work và kiểm bằng MSW; khi gặp 503 web hiện "Work chưa kết nối được Integration (chờ backend, B34)." |
| B35 | Work không có API public để ngắt kết nối repository: input `POST projects/{id}/github/repository/` chỉ nhận `github_repo_id`, `operation_id`, `expected_connection_generation`, còn Integration `prepare` có `action: DISCONNECT` mà Work chưa nhận. Web không hiện nút ngắt kết nối. Cần backend thêm `action` (hoặc route riêng) cho Work |
| B36 | Chưa có API public cho hoạt động mã nguồn (commit, PR, contributor, thống kê) để dựng tab Code. Web chỉ hiện trạng thái repository và dòng "Hoạt động commit/PR chưa có API (B36)."; không dựng số liệu giả. Cần backend quyết định nguồn dữ liệu (Integration hay Work) và công bố contract |
| B37 | Chưa rõ ai cập nhật `is_github_verified` của `ProjectMember` ở Work (**Chưa xác minh**). Work có `apply_account_fact` (apps/work-service/apps/integrations/services/accounts.py) nhận fact tài khoản GitHub từ Integration, nhưng chưa thấy consumer/event nào gọi nó trong luồng chạy thật. Cần backend xác nhận nguồn fact (event Kafka hay REST) và khi nào `is_github_verified` thành `true` sau khi thành viên liên kết GitHub ở Integration; nếu chưa có, cột GitHub luôn hiện "Chưa xác minh" |

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
