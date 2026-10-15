# Lộ trình frontend (Frontend Roadmap) — từ hiện trạng tới MVP

**Trạng thái tài liệu: Thiết kế mục tiêu (kế hoạch). Phần "hiện trạng" ở §2 đã đối chiếu với mã nguồn nhánh `dev`, HEAD `83af5e7`, ngày 13/10/2026. Các đợt ở §5 và các mảng ở §4 chưa được triển khai; không đọc chúng như tính năng đã chạy.**

Tài liệu này trả lời ba câu hỏi: backend đang có gì, frontend đang đứng ở đâu so
với backend đó, và nên làm gì tiếp theo theo thứ tự nào. Chi tiết từng màn đã làm
nằm ở [student-flow.md](student-flow.md) và [teacher-flow.md](teacher-flow.md);
tài liệu này chỉ trỏ tới, không chép lại.

## 1. Mục đích và cách đọc

- **Phạm vi**: đưa `apps/web` từ trạng thái "toàn bộ chạy trên mock" tới MVP P0,
  rồi P1, theo [phân tích vai trò §8](utask-role-analysis.md#8-phạm-vi-mvp-nên-ưu-tiên).
- **Nguồn ranh giới service**: [kiến trúc](../system/architecture.md),
  [quyền sở hữu dữ liệu](../system/data-ownership.md),
  [giao tiếp REST và Kafka](../system/communication.md).
- **Nhãn trạng thái** theo [quy ước chung](../system/README.md#quy-ước-trạng-thái):
  `Đã triển khai`, `Một phần`, `Chưa triển khai`, `Thiết kế mục tiêu`,
  `Chưa xác minh`. Thêm nhãn **Demo MSW** như [student-flow.md](student-flow.md):
  chạy được với mock (MSW — Mock Service Worker, thư viện chặn request ngay trong
  trình duyệt), chưa có backend thật.
- **Thuật ngữ**: *adapter* = lớp mã đứng giữa component và API, đổi dữ liệu của
  backend sang kiểu dữ liệu mà giao diện dùng; *envelope* = lớp bọc chung quanh
  mọi phản hồi của Identity; *viewer context* = tư cách của người xem đối với một
  project (thành viên nhóm hay giảng viên của lớp).
- **Nhu cầu API** ở §4 là yêu cầu của frontend gửi cho backend, **không phải
  schema và không phải hợp đồng**. Không đưa chúng vào `contracts/`.

## 2. Ảnh chụp hiện trạng

### 2.1 Backend

| Service | Trạng thái | Nơi có mã | Tiền tố gateway | Hợp đồng | Ảnh hưởng tới frontend |
| --- | --- | --- | --- | --- | --- |
| Identity | **Đã triển khai** (auth, hồ sơ, phiên, admin; 35 module test) | `apps/identity-service` trên `dev` | `/api/auth/` | [Đặc tả API v1.8](../architecture/Identity_Service_API_Specification.md) (trạng thái tự ghi "Một phần"); chưa có artifact OpenAPI trong `contracts/` | Là backend duy nhất nối được ngay |
| Classroom | **Một phần**: chỉ có khung và `/healthz` | `feat/classroom-service`, chưa merge | `/api/classroom/` | Không (tài liệu ở [classroom-service](../classroom-service/README.md) là thiết kế mục tiêu) | Dữ liệu lớp/nhóm chưa nối được |
| Project (`work-service`) | **Chưa triển khai** | Không có mã ở nhánh nào | `/api/work/` | Không | Backlog, Kanban, Sprint, task, comment chưa nối được |
| Integration | **Chưa triển khai** | Không có mã | `/api/integrations/` | Không | GitHub chưa nối được |
| Notification | **Chưa triển khai** | Không có mã | `/api/notifications/` | Không | Thông báo chưa nối được |
| Progress | **Chưa triển khai** | Không có mã, không có trong compose và nginx | Chưa có | Không | Chỉ số, rủi ro chưa nối được |
| AI | **Một phần**: có API và worker, 97 test | `origin/feat/ai-service`, chưa merge | `/api/ai/` | `contracts/api/ai-service-v1.yaml` trên nhánh đó ghi `designed-not-implemented` | Chưa nối được |

Ghi chú:

- `contracts/` hiện chỉ có hai file README; không có hợp đồng máy đọc được.
- **Kafka**: Identity mới ghi sự kiện vào bảng outbox, chưa có producer, relay
  hay consumer nào chạy. Frontend không nên giả định thông báo hay đồng bộ dữ
  liệu liên service đã hoạt động.
- Gateway (`infra/nginx/nginx.conf`) cắt tiền tố rồi chuyển vào service, chặn
  `/api/auth/api/v1/internal` bằng 404, **không cấu hình CORS**. Trình duyệt
  phải gọi cùng origin với gateway.
- `docker-compose.yml` ở gốc build các thư mục `apps/work-service`,
  `classroom-service`, `integration-service`, `notification-service`,
  `ai-service` không tồn tại trên `dev`, và nginx phụ thuộc vào chúng. Môi
  trường staging (`docker-compose.staging.yml`) chỉ chạy PostgreSQL, Redis,
  Identity và nginx.
- AI: gateway biến `/api/ai/v1/requests` thành `/v1/requests`, trong khi route
  của service là `/api/ai/v1/requests`, nên gọi qua gateway sẽ 404. Phản hồi lỗi
  của AI cũng có dạng khác envelope của Identity.

### 2.2 Frontend

Toàn bộ dữ liệu của `apps/web` hiện đi qua MSW. Không trang nào gọi backend thật.

| Nhóm màn | Trạng thái | Dữ liệu | Thao tác ghi | Còn disabled |
| --- | --- | --- | --- | --- |
| Đăng nhập, quên và đặt lại mật khẩu | **Demo MSW** | Login qua MSW; quên và đặt lại mật khẩu không gọi API | Chỉ login | SSO Google/GitHub, gửi email, đặt lại mật khẩu |
| My Work, danh sách môn | **Demo MSW** | `my-work/*` | Không | Tham gia môn, duyệt PR, kết nối GitHub, tạo task |
| Trang nhóm của môn | **Demo MSW** | `courses/:id` | Tạo nhóm | Xin tham gia, hủy yêu cầu, nộp đề tài |
| Workspace (Backlog, Board, Code, Issue) | **Demo MSW** | `projects/*` | Board và Backlog: kéo thả, menu di chuyển, đổi trạng thái, cờ bị chặn ([kanban-board.md](kanban-board.md)); checkbox subtask vẫn chỉ đổi state cục bộ | Tạo Epic/issue, sửa nội dung, hoàn thành Sprint, AI, đồng bộ |
| Settings dự án | **Demo MSW** | `projects/:id/settings` | Lưu khóa AI | Kiểm tra kết nối, xóa khóa |
| Thông báo | **Demo MSW** | `notifications` | Đánh dấu đã đọc | — |
| Settings tài khoản | **Demo MSW** | `me/settings` | Sửa hồ sơ, ngắt GitHub | Đổi mật khẩu (chỉ toast), đăng xuất thiết bị khác, OAuth |
| Teacher T01–T10, Giám sát | **Demo MSW**, chỉ đọc | `teacher/*` | Không | Tạo lớp, thêm và import sinh viên, đổi mã, điều chỉnh nhóm, gửi phản hồi |

Chi tiết từng màn: [student-flow.md](student-flow.md),
[teacher-flow.md](teacher-flow.md). Frontend chưa có: màn đăng ký, màn kích hoạt
tài khoản, danh sách thiết bị đăng nhập, khu quản trị Admin, màn tham gia lớp
bằng mã, màn cấu hình project, màn AI sinh backlog, màn kết nối repository.

### 2.3 Những chỗ frontend lệch với backend thật

| # | Điểm lệch | Frontend | Backend (Identity) |
| --- | --- | --- | --- |
| L1 | Đường dẫn | `/api/auth/api/v1/auth/login\|refresh\|logout` ([auth.ts](../../apps/web/src/features/auth/api/auth.ts)) | `/api/auth/login\|refresh\|logout` (commit `a824187` đã bỏ phiên bản khỏi route công khai) |
| L2 | Hình dạng phản hồi | Đọc `access_token`, `refresh_token`, `expires_in`, `user` ở gốc | Envelope `{success, message, data, meta, error}`; token ở `data.access` |
| L3 | Chuyển refresh token | Gửi `{refresh_token}` trong body, lưu ở `sessionStorage` khi bật mock | Cookie `refresh_token` HttpOnly, path `/api/auth`; body `refresh` luôn rỗng |
| L4 | Hình dạng `user` | `global_role`, `capabilities`, `roles?` ([types.ts](../../apps/web/src/features/auth/types.ts)) | `roles[]` cùng nhiều trường hồ sơ; JWT **không** chứa roles |
| L5 | CSRF | Chưa có | Refresh và logout dùng cookie phải qua `enforce_csrf` (cần header `X-CSRFToken`), nhưng không endpoint nào cấp cookie `csrftoken` |
| L6 | Link email | Dùng `/reset-password`; chưa có trang kích hoạt | Email trỏ tới `${IDENTITY_FRONTEND_URL}/auth/activate?key=` và `/auth/reset?uid=&token=` |
| L7 | Cùng origin | Vite chưa có proxy; `VITE_API_BASE_URL` mặc định rỗng | Không có CORS |
| L8 | Dữ liệu lớp học | Gọi `/api/work/api/v1/courses/...` và `/teacher/...` | Theo kiến trúc, lớp/nhóm thuộc Classroom (`/api/classroom/`) |
| L9 | Phiên | Không khôi phục được phiên khi tải lại nếu tắt mock; không có refresh chủ động | Access token sống 15 phút |

### 2.4 Nợ kỹ thuật

- Không có ESLint, Prettier hay `.editorconfig`; `pnpm lint` chỉ là `tsc --noEmit`.
- Không có test e2e. Không có `Dockerfile` hay bước deploy cho web.
- Test `MyWork.test.tsx` "surfaces overdue tasks…" sai khi chạy trong khoảng
  00:00–12:00 giờ địa phương ([teacher-flow.md §16.10](teacher-flow.md#1610-sửa-sau-review)).
- `@vitejs/plugin-react` nằm ở `dependencies`.
- [HomeRoute.tsx](../../apps/web/src/app/routes/HomeRoute.tsx) không được tham
  chiếu ở đâu.
- [enableMocking.ts](../../apps/web/src/mocks/enableMocking.ts) bật MSW trong cả
  bản build production khi `VITE_ENABLE_MOCKS=true`, trái với câu "Production builds
  never register MSW" trong `apps/web/README.md`. Phải thống nhất một trong hai.
- Tài liệu lỗi thời: [teacher-flow.md](teacher-flow.md) §1–2 mô tả HEAD `c9df96b`
  khi `apps/` chưa có Identity; một số số liệu test (328) lệch với số đếm hiện tại
  (khoảng 316 khối `it(`).

## 3. Nguyên tắc cho giai đoạn tích hợp

1. **Một adapter cho mỗi service**: thêm `lib/api/<service>/` chứa DTO đúng shape
   backend và hàm đổi sang kiểu dữ liệu của giao diện. Chuyển từ mock sang thật
   chỉ chạm adapter và handler, không chạm component.
2. **Mock bám backend thật** nơi backend đã có: handler MSW của Identity trả đúng
   envelope, path và cookie như Identity. Mock của service chưa có hợp đồng giữ
   nhãn Demo MSW và không đưa vào `contracts/`.
3. **Tiền tố đúng service**: `/api/auth`, `/api/classroom`, `/api/work`,
   `/api/integrations`, `/api/notifications`, `/api/ai`. Dữ liệu lớp/nhóm tách
   dần khỏi `/api/work` (L8).
4. **Chế độ lai**: cho phép chọn service nào dùng mock (ví dụ Identity thật,
   phần còn lại MSW; MSW đã bỏ qua request không có handler qua
   `onUnhandledFrame: "bypass"`). Cách một tài khoản Identity thật ánh xạ vào
   graph mock dựa trên tài khoản demo là **Thiết kế mục tiêu** và cần thử nghiệm
   ở Đợt 0.
5. **Hai lớp quyền** giữ nguyên như [teacher-flow.md §6](teacher-flow.md#6-ma-trận-quyền-theo-tài-nguyên):
   role toàn cục chỉ quyết định hiển thị khu vực; quyền theo lớp/project do
   Classroom/Project quyết định. Frontend chỉ ẩn hoặc vô hiệu hóa; backend là
   nơi quyết định cuối. Giữ chính sách 404 cho tài nguyên ngoài quyền và 403 cho
   thiếu quyền hành động.
6. **Không thành công giả**: nút ghi chỉ bật khi có hợp đồng, **trừ** các thao tác ghi
   của Board và Backlog chạy trên Demo MSW, chỉ bật khi `VITE_ENABLE_MOCKS=true` và
   tắt với backend thật ([kanban-board.md §1](kanban-board.md#1-phạm-vi-và-nhãn-trạng-thái)); mọi mutation xử lý
   lỗi theo HTTP status và `error.code`, không theo `message`.
7. **AI chỉ đề xuất**: mọi kết quả AI là bản nháp; chỉ API của service sở hữu dữ
   liệu mới tạo hoặc đổi dữ liệu thật, sau khi người dùng xác nhận.

## 4. Các mảng công việc

Mỗi mảng ghi: user story, hiện trạng, việc frontend, nhu cầu API, tiêu chí hoàn
tất và kiểm thử. Mảng A–C làm được ngay với Identity; D–I cần hợp đồng từ
service tương ứng nên giai đoạn đầu chỉ dựng giao diện trên Demo MSW.

### A. Nền tảng và chất lượng

- **Hiện trạng**: xem §2.3 (L7), §2.4.
- **Việc frontend**:
  - Thêm proxy `/api` tới gateway (`:8080`) trong `vite.config.ts` để giữ cùng origin khi phát triển.
  - Viết hướng dẫn chạy gateway cùng Identity bằng cấu hình staging (hoặc profile) vì compose gốc không dùng được; cập nhật `apps/web/README.md`.
  - Quyết định và ghi rõ chính sách MSW trong bản build production; sửa README hoặc mã cho khớp.
  - Thêm ESLint và Prettier (hoặc công cụ tương đương) và đưa vào CI; sửa test phụ thuộc giờ; dọn `HomeRoute.tsx`; chuyển `@vitejs/plugin-react` sang `devDependencies`.
  - Thêm Playwright smoke test chạy trên MSW cho đường đăng nhập → Home → mở workspace.
  - Quyết định cách deploy web (ví dụ build tĩnh do nginx phục vụ cùng origin). **Chưa quyết định.**
  - Cập nhật tài liệu lỗi thời ở §2.4.
- **Nhu cầu backend**: không.
- **Hoàn tất khi**: `pnpm lint`, `typecheck`, `test`, `build` và e2e smoke đạt trong CI; chạy được web với Identity thật bằng một lệnh được tài liệu hóa.

### B. Xác thực và tài khoản (Identity, nối thật)

- **User story**: US-1.1; phần đăng ký, kích hoạt, khôi phục tài khoản của [phân tích vai trò §3](utask-role-analysis.md#3-epic-1-account-and-class-access) và [đặc tả Identity](../architecture/Identity_Service_API_Specification.md).
- **Backend**: **Đã triển khai** (endpoint ở bảng dưới). Một số phần phụ thuộc cấu hình: đăng ký, gửi lại kích hoạt, đặt lại mật khẩu trả 503 nếu thiếu `IDENTITY_MAIL_KEY`; OAuth và avatar chỉ có khi bật feature flag; việc gửi email thật **Chưa xác minh** vì chưa có consumer.
- **Việc frontend**:
  - `ApiClient` bóc envelope, đổi `error.code` thành `ApiError`, xử lý 429 kèm `Retry-After`, gửi `credentials: "include"`.
  - Adapter auth mới theo path và shape thật (L1–L4). Bỏ `global_role`, `capabilities`; dùng `roles`.
  - Khôi phục phiên bằng cookie khi tải lại trang; refresh trước khi access token hết hạn; chỉ một refresh chạy tại một thời điểm khi nhiều request cùng gặp 401.
  - Trang mới: đăng ký; kích hoạt `/auth/activate?key=` (nhánh tài khoản được import phải đặt mật khẩu); gửi lại email kích hoạt; quên mật khẩu; đặt lại mật khẩu ở `/auth/reset?uid=&token=` (giữ `/reset-password` làm alias).
  - Hồ sơ: đọc và sửa `users/me` (không đổi được email và MSSV). Đổi mật khẩu: sau khi thành công mọi phiên bị thu hồi, đưa người dùng về trang đăng nhập. Danh sách thiết bị, thu hồi từng thiết bị, đăng xuất mọi thiết bị.
  - Thông báo lỗi riêng cho tài khoản chưa kích hoạt, bị khóa, bị khóa tạm do đăng nhập sai nhiều lần, phiên bị thu hồi do dùng lại refresh token. Thông báo lỗi đăng nhập không tiết lộ email có tồn tại hay không.
  - Liên kết GitHub qua OAuth và upload avatar: chỉ bật khi feature flag bật; nếu không thì ẩn hoặc vô hiệu hóa kèm lý do.
  - Đổi handler MSW auth sang đúng shape thật để test và demo không lệch.
- **Endpoint dùng** (qua gateway, tiền tố `/api/auth`): `POST /login`, `/refresh`, `/logout`, `/logout-all`, `/register`, `/activate`, `/activation/resend`, `/password-reset/request`, `/password-reset/confirm`, `/password-change`; `GET /sessions`, `DELETE /sessions/{id}`; `GET`/`PATCH /users/me`; `GET /users/{id}`; `POST /users/batch`.
- **Nhu cầu gửi Identity**:
  - Cách SPA lấy CSRF token để refresh và logout bằng cookie (L5): cấp cookie `csrftoken` hoặc một endpoint.
  - Cấu hình `CSRF_TRUSTED_ORIGINS` cho origin của web.
  - Xác nhận cách chạy cookie `Secure` khi phát triển trên `http://localhost`.
  - Xác nhận `IDENTITY_FRONTEND_URL` và các đường `/auth/activate`, `/auth/reset` là đường chuẩn của web.
- **Hoàn tất khi**: đăng ký → kích hoạt → đăng nhập → tải lại trang vẫn còn phiên → đổi mật khẩu → đăng xuất chạy với Identity thật qua gateway; test tự động phủ các `error.code` chính.

### C. Khu quản trị System Admin (Identity, nối thật; làm ở đợt sau)

- **Backend**: **Đã triển khai** (`GET /admin/users`, `PATCH /admin/users/{id}/status`, `POST`/`DELETE /admin/users/{id}/roles`).
- **Việc frontend**:
  - Route `/admin/users`, chỉ mở cho role `SYSTEM_ADMIN`; sidebar riêng cho Admin.
  - Bảng người dùng: tìm kiếm, lọc theo role và trạng thái, phân trang theo `meta`.
  - Khóa, mở khóa (kèm lý do), khôi phục tài khoản đã xóa mềm, gán và gỡ role. Mỗi thao tác có hộp thoại xác nhận, nói rõ phiên của người dùng đó sẽ bị thu hồi.
  - Admin **không** đọc nội dung project của sinh viên ([phân tích vai trò §1.3](utask-role-analysis.md#13-quy-tắc-vai-trò)).
- **Nhu cầu backend**: không. Cần nghiệp vụ chốt mâu thuẫn Admin ở §7.
- **Hoàn tất khi**: Admin thực hiện đủ các thao tác trên với Identity thật; tài khoản không phải Admin vào `/admin` thấy trang bị chặn.

### D. Lớp học, ghi danh và nhóm (Classroom)

- **User story**: US-1.2, 1.3, 1.4, 2.1, 2.2, 2.3, 2.5 (US-2.5 thuộc P1).
- **Backend**: **Một phần** (khung); không có endpoint nghiệp vụ.
- **Hiện trạng frontend**: Teacher T01–T10 chỉ đọc, các form tạo lớp, import, thêm sinh viên, điều chỉnh nhóm đã có giao diện nhưng nút gửi bị vô hiệu hóa ([teacher-flow.md §16](teacher-flow.md#16-kết-quả-phase-3-4-5--tổ-chức-lớp-phản-hồiđiều-chỉnh-nhóm-rủi-ro)). Student tạo nhóm đã có trên MSW.
- **Việc frontend**:
  - Làm mới trên MSW: Student tham gia lớp bằng mã; tham gia nhóm bằng mã hoặc lời mời; Leader mời, tạo hóa mã mời, kick thành viên, chuyển quyền Leader; rời nhóm kèm điều kiện.
  - Khi có hợp đồng: bật T03 (tạo lớp), T06 (import), T10 (đổi và vô hiệu mã), thêm sinh viên, điều chỉnh nhóm; mở rộng `ApiClient` gửi `FormData` cho import và gửi `Idempotency-Key`.
  - Chuyển các lời gọi lớp/nhóm từ `/api/work` sang `/api/classroom` (L8) trong adapter.
- **Nhu cầu API** (yêu cầu, chưa phải hợp đồng): danh sách lớp phụ trách và lớp đã ghi danh; chi tiết lớp; tạo và sửa lớp; mã tham gia (xem, đổi, vô hiệu); tham gia lớp bằng mã; roster sinh viên; thêm từng sinh viên và import CSV/XLSX (đối chiếu mô tả ở [Identity spec §3.5.1](../architecture/Identity_Service_API_Specification.md): `Idempotency-Key`, `summary` và `results[]` theo dòng); nhóm và thành viên; mã/lời mời nhóm; chuyển Leader; mutation membership của Teacher kèm chính sách sĩ số, Leader thay thế, quyền đọc lịch sử sau chuyển nhóm; tên tầng Course/Class (§7).
- **Hoàn tất khi**: luồng Teacher tạo lớp → Student tham gia → tạo hoặc vào nhóm chạy với backend thật; kết quả import phân biệt tạo mới, có sẵn, trùng, cần kiểm tra, lỗi theo dòng.

### E. Project workspace: backlog, Kanban, Sprint, task, comment (Project Service)

- **User story**: US-2.4, 3.1, 3.2, 3.3, 4.1 (P0); US-3.4 (P1).
- **Backend**: **Chưa triển khai**.
- **Hiện trạng frontend**: Backlog, Board, Code, IssuePanel đọc được trên MSW; Board và Backlog đã kéo thả và đổi trạng thái trên Demo MSW ([kanban-board.md](kanban-board.md)); IssuePanel chỉ hiển thị comment; checkbox subtask chỉ đổi state cục bộ (R12 trong teacher-flow).
- **Việc frontend**:
  - Cấu hình project (tên, mô tả, mục tiêu, tech stack, thời gian).
  - Leader tạo, sửa, sắp xếp, gán, lưu trữ task; Member cập nhật task được giao, đánh dấu blocked kèm lý do.
  - Kanban kéo thả bằng `@atlaskit/pragmatic-drag-and-drop`, cập nhật lạc quan và hoàn tác khi lỗi, có menu thay thế cho bàn phím: **Demo MSW**, xem [kanban-board.md](kanban-board.md).
  - Tìm kiếm, lọc theo trạng thái, assignee, priority, deadline; hiển thị rõ task quá hạn và blocked (cần `dueAt`, trạng thái blocked trong `Issue`).
  - Subtask lưu thật, bỏ state cục bộ.
  - Comment có mention; Teacher gửi phản hồi cấp task; lịch sử thay đổi.
  - Sprint (P1): tạo, bắt đầu, kết thúc, chuyển task chưa xong, ghi lý do khi đổi phạm vi.
  - Giữ chế độ chỉ xem cho giảng viên theo `ProjectViewer`.
- **Nhu cầu API**: workspace kèm viewer context (`courseId`, `teamId`); danh sách issue có phân trang và lọc; tạo, sửa, đổi trạng thái, sắp xếp, gán, lưu trữ; subtask; comment và mention; lịch sử; Sprint (chỉ một Sprint active trong MVP); `dueAt`, blocked, archived.
- **Hoàn tất khi**: nhóm dùng được backlog và Kanban end-to-end; quyền Leader/Member/Teacher bị backend enforce, UI chỉ phản ánh.

### F. GitHub (Integration Service)

- **User story**: US-5.1, 5.2, 5.3.
- **Backend**: **Chưa triển khai**. Chỉ Integration được gọi GitHub API. Identity có liên kết GitHub username ở mức tài khoản (khi bật OAuth), chưa đủ cho repository.
- **Hiện trạng frontend**: tab Code đọc trên MSW; kết nối và đồng bộ bị vô hiệu hóa.
- **Việc frontend**:
  - Leader kết nối, đổi, ngắt repository chính (cảnh báo khi đổi repo vì liên kết cũ có thể không còn cập nhật).
  - Member xác nhận GitHub username.
  - Liên kết, hủy liên kết PR/commit/branch với task; xác nhận liên kết được đề xuất.
  - Hiển thị repository đang cấp dữ liệu và `lastSyncedAt`; phân biệt riêng: chưa ánh xạ tài khoản, mất kết nối, dữ liệu cũ, không có dữ liệu. Không suy ra mức đóng góp từ số commit.
- **Nhu cầu API**: kết nối repo, danh sách repo được phép, trạng thái webhook và đồng bộ, liên kết task–GitHub, ánh xạ tài khoản GitHub–thành viên.

### G. Thông báo (Notification)

- **User story**: US-4.2.
- **Backend**: **Chưa triển khai**.
- **Hiện trạng frontend**: trang `/notifications` chạy trên MSW.
- **Việc frontend**: chuông trên thanh trên cùng kèm số chưa đọc; điều hướng tới tài nguyên liên quan; chọn kênh nhận; cơ chế cập nhật (polling hay đẩy) **Chưa xác minh**, cần quyết định; thông báo cấp project cho giảng viên chờ quy tắc (§7).
- **Nhu cầu API**: danh sách có phân trang, đánh dấu đã đọc từng cái và tất cả, số chưa đọc, tùy chọn kênh.

### H. Tiến độ và rủi ro (Progress)

- **User story**: US-4.3, 4.4, 5.7 (P1).
- **Backend**: **Chưa triển khai**. Progress tính bằng quy tắc xác định, không phụ thuộc AI.
- **Hiện trạng frontend**: tín hiệu rủi ro Teacher chạy theo quy tắc cố định ở `signalsFor`, nhãn Demo MSW.
- **Việc frontend**: dashboard nhóm cho Leader (phân bổ task và story point, không xếp hạng); thay `signalsFor` bằng dữ liệu Progress; luôn hiển thị nguồn dữ liệu và thời điểm tính; không chấm điểm.
- **Nhu cầu API**: chỉ số theo lớp, nhóm, Sprint; tín hiệu rủi ro có nguyên nhân, dữ liệu nguồn và thời điểm; ngưỡng chính thức thay giá trị demo 7 ngày.

### I. Trợ lý AI (AI Service)

- **User story**: US-5.4, 5.5 (P0); US-5.6 (P1).
- **Backend**: **Một phần**, ở nhánh chưa merge. API: `POST /api/ai/v1/requests` (cần `Idempotency-Key`, trả 200 hoặc 202 kèm `status_url`), `GET /api/ai/v1/requests/{id}`; ba `intent`: `backlog_generation`, `task_decomposition`, `risk_analysis`.
- **Việc frontend**:
  - Màn nhập ngữ cảnh để sinh backlog; bảng bản nháp cho sửa, chọn, loại từng mục; chỉ khi Leader xác nhận mới gọi API Project để tạo task; chống xác nhận lặp.
  - Phân rã task thành subtask.
  - Xử lý trạng thái `queued`/`running`/`succeeded`/`failed`; polling `status_url`; hiển thị lỗi có thể thử lại.
  - Lỗi hoặc chậm của AI không chặn các chức năng khác; đánh dấu task có nguồn từ AI.
  - Quyết định về BYOK (khóa AI của nhóm) hiện có ở Settings dự án: giữ hay bỏ khi AI Service chốt hợp đồng.
- **Nhu cầu và điều kiện**: merge nhánh AI; sửa rewrite gateway; thống nhất envelope lỗi; đồng bộ issuer/audience JWT với Identity; ngữ cảnh đi qua Kafka nên phụ thuộc Project và Kafka chạy thật.

### J. Trải nghiệm chung

- Kiểm tra truy cập thật bằng bàn phím và trình đọc màn hình (chưa làm ở các phase trước).
- Tìm kiếm toàn cục và command palette (`cmdk` đã có trong dependency).
- Trạng thái loading, empty, error, forbidden thống nhất; hiệu năng với lớp lớn (đã có fixture 100 sinh viên).
- Quyết định: **không làm i18n** trong lộ trình này; toàn bộ giao diện giữ tiếng Việt.
- Chưa có chủ đề tối (dark mode); có khai báo biến thể `dark` nhưng không có nút chuyển. Ngoài phạm vi lộ trình này.

## 5. Lộ trình theo đợt

Thứ tự theo phụ thuộc. Đợt 2 chạy trên Demo MSW vì backend chưa có; đợt 4 mới
thay mock bằng service thật, từng service một khi hợp đồng đã chốt.

| Đợt | Nội dung | Mảng | Phụ thuộc backend |
| --- | --- | --- | --- |
| 0 | Nền tích hợp: proxy, chế độ lai, adapter và envelope, lint/format, e2e smoke, dọn nợ | A | Không |
| 1 | Identity thật end-to-end | B | Identity có sẵn; cần giải pháp CSRF cho SPA |
| 2 | Hoàn thiện giao diện P0 còn thiếu trên MSW: tham gia lớp và nhóm, cấu hình project, backlog CRUD, Kanban kéo thả, comment, kết nối và liên kết GitHub, duyệt bản nháp AI | D, E, F, I | Không; mock bám nhu cầu API |
| 3 | Khu quản trị Admin | C | Identity có sẵn |
| 4 | Nối từng service khi có hợp đồng: Classroom → Project → Integration → Notification → AI → Progress | D–I | Hợp đồng và mã từng service |
| 5 | P1: Sprint đầy đủ, dashboard nhóm, phản hồi của Teacher, điều chỉnh nhóm, rủi ro có nguồn | E, H, D | Project, Progress, Classroom |

Mảng J chạy xuyên suốt, chốt từng phần ở cuối mỗi đợt.

Mỗi đợt có:

- **Tiêu chí vào**: đợt trước đã xong; hợp đồng liên quan có trong `contracts/` (với đợt 4).
- **Tiêu chí hoàn tất**: nút thao tác ghi chỉ bật khi có hợp đồng; test cho luồng mới; tài liệu và nhãn trạng thái được cập nhật.
- **Kiểm tra bắt buộc** (theo [AGENTS.md](../../AGENTS.md)): formatter, `pnpm lint`, `pnpm typecheck`, `pnpm test`, `pnpm build`, cộng e2e smoke khi đã có; kiểm tra link trong tài liệu.
- **Commit gợi ý**: nhỏ, theo phần review được, dạng `feat(web): …`, `fix(web): …`, `docs(web): …`.

## 6. Ma trận sẵn sàng theo user story

Cột "UI" và "MSW" mô tả `apps/web` hiện tại; "Hợp đồng" và "Backend" mô tả trạng thái ở §2.1.

| Story | Mức | Mảng | UI | MSW | Hợp đồng | Backend | Đợt |
| --- | --- | --- | --- | --- | --- | --- | --- |
| US-1.1 Đăng nhập, tài khoản | P0 | B | Một phần | Có (lệch shape) | Có (Identity) | Có | 1 |
| US-1.2 Tạo lớp, mã tham gia | P0 | D | Một phần (nút gửi tắt) | Chỉ đọc | Không | Không | 2, 4 |
| US-1.3 Tham gia lớp bằng mã | P0 | D | Chưa | Chưa | Không | Không | 2, 4 |
| US-1.4 Thêm và import sinh viên | P0 | D | Một phần (xem trước CSV) | Không | Chỉ mô tả ở Identity spec | Không (Identity nội bộ có) | 2, 4 |
| US-2.1, 2.2 Tạo và tham gia nhóm | P0 | D | Một phần (tạo nhóm) | Một phần | Không | Không | 2, 4 |
| US-2.3 Quản lý thành viên nhóm | P0 | D | Chưa | Chưa | Không | Không | 2, 4 |
| US-2.4 Cấu hình project | P0 | E | Chưa | Chưa | Không | Không | 2, 4 |
| US-2.5 Teacher điều chỉnh nhóm | P1 | D | Một phần (xem trước) | Chỉ đọc | Không | Không | 5 |
| US-3.1 Quản lý backlog | P0 | E | Một phần (sắp thứ tự, đổi Sprint; chưa tạo/sửa) | Có (Demo) | Không | Không | 2, 4 |
| US-3.2 Backlog và Kanban | P0 | E | Một phần (kéo thả, lọc trên URL, hiện bị chặn/quá hạn) | Có (Demo) | Không | Không | 2, 4 |
| US-3.3 Cập nhật task | P0 | E | Một phần (đổi trạng thái, bị chặn kèm lý do; chưa sửa nội dung) | Có (Demo) | Không | Không | 2, 4 |
| US-3.4 Sprint | P1 | E | Một phần (đổi phạm vi Sprint kèm lý do; chưa tạo/kết thúc Sprint) | Có (Demo) | Không | Không | 5 |
| US-4.1 Comment, mention | P0 | E | Chỉ đọc | Chỉ đọc | Không | Không | 2, 4 |
| US-4.2 Thông báo | P0 | G | Một phần | Có | Không | Không | 4 |
| US-4.3 Dashboard nhóm | P1 | H | Một phần (Teacher) | Chỉ đọc | Không | Không | 5 |
| US-4.4 Dashboard lớp | P0 | H | Một phần (Teacher) | Chỉ đọc | Không | Không | 4 |
| US-4.5 Teacher phản hồi | P1 | E | Chỉ nháp | Không | Không | Không | 5 |
| US-5.1 Kết nối repository | P0 | F | Chưa (nút tắt) | Chưa | Không | Không | 2, 4 |
| US-5.2 Liên kết task–GitHub | P0 | F | Chưa | Chưa | Không | Không | 2, 4 |
| US-5.3 Xem hoạt động GitHub | P0 | F | Có (tab Code) | Có | Không | Không | 4 |
| US-5.4, 5.5 AI backlog, phân rã | P0 | I | Chưa | Chưa | Chưa chốt (nhánh chưa merge) | Một phần | 2, 4 |
| US-5.6 AI phân tích rủi ro | P1 | I, H | Chưa | Chưa | Chưa chốt | Một phần | 5 |
| US-5.7 Teacher xem rủi ro | P1 | H | Có (quy tắc demo) | Có | Không | Không | 5 |
| Admin quản trị tài khoản | Ngoài MVP trong phân tích | C | Chưa | Chưa | Có (Identity) | Có | 3 |

## 7. Rủi ro và vấn đề còn mở

| Vấn đề | Chặn gì | Người quyết định |
| --- | --- | --- |
| CSRF và cookie refresh cho SPA (L5), `CSRF_TRUSTED_ORIGINS`, cookie `Secure` khi chạy `http://localhost` | Đợt 1 | Identity + Frontend |
| Tên và số tầng Course/Class/Classroom; hợp đồng REST Classroom | D, đợt 4 | Backend Classroom |
| Hợp đồng Project: viewer context cho giảng viên, `dueAt`, blocked, comment; tên `work-service` hay `project-service` | E, đợt 4 | Backend Project |
| Cách web nhận cập nhật thông báo (polling hay đẩy) | G | Backend Notification + Frontend |
| Cách deploy web và chính sách MSW ở production | A | Đội phát triển |
| `docker-compose.yml` gốc không chạy được vì thiếu service | A | Hạ tầng |
| Nhánh `feat/ai-service` và `feat/classroom-service` chưa merge; rewrite gateway AI; envelope lỗi AI khác Identity | I, D | Backend |
| Mâu thuẫn trong phân tích vai trò: §2.2 cho Admin mọi quyền nhưng §1.3 nói Admin không mặc định đọc project; §2.1 không cho Member yêu cầu AI phân rã nhưng US-5.5 cho Member | C, I | Nghiệp vụ |
| Quyền thấy thông báo cấp project của giảng viên; chính sách sĩ số, Leader thay thế, quyền đọc lịch sử sau chuyển nhóm | G, D | Nghiệp vụ |
| Mock lệch hợp đồng thật khi hợp đồng ra đời | Đợt 4 | Frontend: đối chiếu và sửa adapter khi hợp đồng chốt |
| Ánh xạ tài khoản Identity thật vào graph mock trong chế độ lai | Đợt 0–1 | Frontend |
| Kafka chưa có producer/consumer nên chưa có luồng sự kiện nào để UI dựa vào | G, H, I | Hạ tầng + Backend |

## 8. Cách cập nhật tài liệu này

- Khi hoàn tất một đợt: cập nhật nhãn ở §2 và bảng §6.
- Chi tiết từng màn ghi vào [student-flow.md](student-flow.md),
  [teacher-flow.md](teacher-flow.md) hoặc một tài liệu luồng mới (ví dụ
  `admin-flow.md`), không để roadmap phình ra.
- Khi một service có hợp đồng, chuyển phần "nhu cầu API" tương ứng thành tham
  chiếu tới `contracts/` và xóa phần yêu cầu đã thỏa.
- Kiểm tra lại hiện trạng ở §2 theo mã nguồn mỗi lần cập nhật; không suy ra từ thiết kế.
