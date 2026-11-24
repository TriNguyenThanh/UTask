# Biên bản bàn giao & Hướng dẫn tích hợp Backend cho Team Web

> **Mục đích tài liệu:** Kênh bàn giao chính thức giữa **Team Backend** và **Team Web (`apps/web`)** trong quá trình xử lý khoảng trống API, hợp đồng và tích hợp theo [Kế hoạch triển khai Backend](../system/backend-web-gap-implementation-plan.md).  
> **Trạng thái tổng thể:** `Tài liệu sống` — **Mục 1** áp dụng được **ngay trên Backend hiện có** (`Đã triển khai` trong source); **Đợt 1 và Đợt 2** đã `Đã triển khai (local)` và qua toàn bộ kiểm thử unit/integration PostgreSQL/contract (xem **Biên bản Đợt 1 & Đợt 2** ở Mục 4; deploy staging `Chưa xác minh`); **Đợt 3–Đợt 7** đang ở trạng thái `Chờ Backend triển khai` (`Thiết kế mục tiêu`).

---

## Bảng theo dõi trạng thái bàn giao theo đợt

| Đợt | Nội dung chính | Trạng thái Backend | Team Web có thể làm lúc này? | Nguồn hợp đồng chuẩn |
| --- | --- | --- | --- | --- |
| **Đợt 0 (Sẵn có)** | API Backend đã có sẵn + các lỗi/đường vòng thuần Web (xem Mục 1) | `Đã triển khai` (source; cờ ngoài tắt mặc định) | **Có — triển khai ngay** | `contracts/api/{classroom,work,integration,ai}-service*.yaml`, `/api/auth/openapi/` |
| **Đợt 1** | Vá lệch hợp đồng P1 (`PATCH /users/me` đủ trường, chặn Admin tự đình chỉ, `GET/PATCH partial/unarchive` Course, guard lớp `OPEN`, quyền Member Work & Admin Classroom `NH07/10/11`, `/docs/`, Nginx `OPTIONS` & chặn `/api/ai/v1/internal`) | `Đã triển khai (local)` — đạt toàn bộ unit/integration PostgreSQL/contract/Docker Nginx (deploy staging `Chưa xác minh`) | **Có — sẵn sàng ghép trên local theo Biên bản Đợt 1** (chờ deploy staging để smoke staging) | `contracts/api/classroom-service.yaml`, `contracts/api/work-service.yaml`, `/api/auth/openapi/` |
| **Đợt 2** | `GET /classes/<id>/my-group/`, thống kê gắn trên Class/Group (`course_summary`, `enrolled_count`, `active_group_count`, `primary_teacher_id`, `my_group_id`/`my_group_name`, `member_count`, `leader_id`), 4 góc chết vòng đời Classroom + sync consumer Work, bộ lọc `django_filters` + index Postgres, `GET /users/search` | `Đã triển khai (local)` — đạt toàn bộ unit/integration PostgreSQL/contract (deploy staging `Chưa xác minh`) | **Có — sẵn sàng ghép trên local theo Biên bản Đợt 2** (chú ý breaking guard `lock-grouping` & `reason` khi lưu trữ nhóm) | `contracts/api/classroom-service.yaml`, `contracts/events/classroom.group.membership.changed.v1.json`, `/api/auth/openapi/` |
| **Đợt 3** | Tổng hợp `/my-work` (`GET /me/tasks/`, `GET /me/overview/`), Giám sát Giảng viên (`GET /teacher/classes/summary/`, `GET /teacher/oversight/projects/`), `/kanban/` đủ trường, `GET /projects/<id>/activities/`, lọc `is_teacher_feedback` | `Chưa triển khai` | Chờ Backend chốt & bàn giao | Cập nhật sau Đợt 3 |
| **Đợt 4** | Ghép nhóm mở (`open-groups`, `unassigned-students`), Yêu cầu gia nhập nhóm, Kỹ năng thành viên, Đề xuất & Duyệt đề tài nhóm | `Chưa triển khai` | Chờ Backend chốt & bàn giao | Cập nhật sau Đợt 4 |
| **Đợt 5** | AI `bulk-apply-ai` nguyên tử (`B31`, `B32`), đồng bộ `is_github_verified`, API GitHub Activity cấp Project (`GET /projects/<id>/github/activity/`) & ứng viên PR/commit | `Chưa triển khai` | Chờ Backend chốt & bàn giao | Cập nhật sau Đợt 5 |
| **Đợt 6** | Bộ API Quản trị `SYSTEM_ADMIN`, `DELETE /users/me/avatar`, `linked_providers`/`has_usable_password`, `POST /password-set` (Google-only), chính sách kích hoạt email | `Chưa triển khai` | Chờ Backend chốt & bàn giao | Cập nhật sau Đợt 6 |
| **Đợt 7** | Work nâng cao (`reparent`, bulk task, vòng đời/velocity/snapshot Sprint, xóa Project, sửa Epic, ordering/search/export/checklist/watchers/worklogs) & Classroom P2 | `Chưa triển khai` | Chờ Backend chốt & bàn giao | Cập nhật sau Đợt 7 |

---

## 1. Việc Team Web có thể triển khai NGAY trên Backend hiện có (Đợt 0)

Toàn bộ các mục dưới đây **đã có API ở Backend** hoặc là **lỗi/đường vòng thuần phía Web** — team Web không cần chờ Backend viết thêm API mới.

### 1.1. Sửa các đường vòng & lỗi kỹ thuật thuần phía Web

| # | Vấn đề hiện tại trong `apps/web` | Thay đổi khuyến nghị cho Team Web | API Backend đã sẵn sàng |
| --- | --- | --- | --- |
| **W1** | `apps/web/src/lib/api/csrf.ts:2-3,17` đang gọi `GET /api/auth/docs/` (tải Swagger HTML) để lấy `csrftoken`. | Đổi `WARMUP_PATH` sang `GET /api/auth/csrf` (gửi kèm `credentials: "include"`). Endpoint trả `{success: true, data: {csrf_token}}` kèm cookie `csrftoken` và `Cache-Control: no-store`. *(Chú ý phối hợp hạ tầng `IDENTITY_CSRF_TRUSTED_ORIGINS` theo `B2`.)* | `GET /api/auth/csrf` (`authentication/views/auth.py:43-54`) |
| **W2** | `apps/web/src/features/auth/AuthProvider.tsx:210-228` đang gọi 2 request `GET /sessions` + `DELETE /sessions/{id}` để đăng xuất. | Thêm wrapper `logout()` gọi thẳng 1 request `POST /api/auth/logout` (kèm `Authorization: Bearer`, `X-CSRFToken` và cookie). Nếu trả lỗi phiên đã mất vẫn xóa state cục bộ như hiện tại. | `POST /api/auth/logout` (`authentication/views/devices.py:35-61`) |
| **W3** | `apps/web/src/features/notifications/components/SettingsIntegrationsPage.tsx:29,146-147` luôn gọi endpoint MSW giả `/api/work/api/v1/me/settings` và `/api/work/api/v1/me/github/disconnect` → vỡ `404` khi tắt mock. | **Tuân thủ [ADR-004](../system/adr/004-integration-github-account-ownership.md):** liên kết GitHub cá nhân thuộc **Integration Service**, **KHÔNG** gọi Identity legacy `/oauth/github*` và không gọi Work. Thêm `"integrations"` vào `RealService` (`apps/web/src/lib/config/services.ts:1-3`), cập nhật `apps/web/.env.example`, tạo client `/api/integrations/api/v1/github/...` và route OAuth callback (ví dụ `/settings/integrations/github/callback`) gọi `GET/DELETE /account`, `POST /authorizations/start` và `POST /authorizations/complete` (chú ý giữ cookie `utask_github_consent` cùng origin). | `GET/DELETE /api/integrations/api/v1/github/account`, `POST .../authorizations/{start,complete}` (khi `INTEGRATION_GITHUB_APP_ENABLED=true`) |
| **W4** | `apps/web/src/features/auth/components/LoginForm.tsx:75-95` có nút `<DisabledAction>` "Đăng nhập bằng GitHub". | Theo **DG1 / ADR-004** (sau khi xác nhận): **gỡ nút "Đăng nhập bằng GitHub"** trên màn hình đăng nhập; chỉ giữ Google SSO (khi bật `IDENTITY_GOOGLE_ENABLED=true`) và hướng dẫn người dùng liên kết GitHub sau đăng nhập tại `/settings/integrations`. | Identity không có GitHub SSO login (chỉ có Google login tại `POST /api/auth/oauth/google/start` & `POST /api/auth/oauth/google`) |
| **W5** | Chip lọc `"Có Pull Request"` vẫn hiển thị trên Board/Backlog thật (`ProjectBoardRoute.tsx:51`, `ProjectBacklogRoute.tsx:417`) dù `hasPullRequest` luôn là `false` → bấm vào ra 0 task. | Ẩn hoặc vô hiệu chip lọc `"Có Pull Request"` khi chưa tích hợp dữ liệu GitHub thật (bật lại sau khi nhận bàn giao Đợt 5). | — |
| **W6** | Sinh viên chưa có màn hình xem/trả lời phản hồi cấp dự án của giảng viên (`listProjectComments` chỉ gắn ở `RealTeamDetail.tsx` của giảng viên). | Hiển thị khối **"Phản hồi dự án / Nhận xét giảng viên"** cho sinh viên trên `/projects/:id/info` gọi `GET /api/work/projects/{id}/comments/` và `POST /api/work/comments/` (`project_id`). | `GET /api/work/projects/{id}/comments/`, `POST /api/work/comments/` (đã có sẵn) |
| **W7** | Nút AI (`ProjectBacklogRoute.tsx:708-713`, `IssuePanelHost.tsx:105-114`) chỉ kiểm `isRealService("work")`, bỏ qua `isRealService("ai")`. | Kiểm tra thêm `isRealService("ai") || mocksEnabled` để tránh bấm nút bắn request thật sang `/api/ai/v1/requests` khi môi trường tắt cả mock lẫn `ai`. | — |
| **W8** | `RequireProjectManagePermission.tsx:15-17` đang bỏ qua kiểm tra vai trò Leader ở chế độ Work thật. | Khi mở trang `/projects/:id/settings` thật, bắt buộc bật lại kiểm tra `shell.myRole === "LEADER"`. | — |
| **W9** | 3 câu thông báo demo lỗi thời vẫn hiện ở chế độ thật (`TeacherCourseTeamsRoute.tsx:287-290`, `TeacherCourseOverviewRoute.tsx:131-133`, `WorkModuleNotIntegrated.tsx:21`) và JSDoc cũ ở `IssueEditForm.tsx:23`. | Cập nhật lại copy/chú thích cho đúng năng lực hiện đã nối (điều chỉnh nhóm thật, Board/Backlog thật). | — |

### 1.2. Các API Backend ĐÃ CÓ SẴN nhưng Team Web chưa nối UI

| Service | API đã tồn tại (qua Gateway) | Gợi ý màn hình / hành vi cần nối | Lưu ý quyền & điều kiện bật |
| --- | --- | --- | --- |
| **Work** | `POST /api/work/projects/{id}/states/`<br>`PATCH /api/work/projects/{id}/states/{sid}/`<br>`DELETE /api/work/projects/{id}/states/{sid}/?target_state_id=...` | Quản lý cột trạng thái Kanban (tạo, đổi tên/màu/thứ tự, xóa cột kèm di chuyển task sang cột đích). | Chỉ Leader, dự án chưa lưu trữ. |
| **Work** | `GET/POST /api/work/projects/{id}/attachments/`<br>`POST .../presigned-url/`, `GET .../{aid}/download/`, `DELETE .../{aid}/` | Khối tài liệu đính kèm cấp Project tại `/projects/:id/info` (tái dùng flow upload R2 đã làm cho Task). | **Chờ xác nhận CORS R2 (`B30`)** trước khi bật trên trình duyệt production. |
| **Work** | `GET/POST/DELETE /api/work/projects/{id}/github/repository/`<br>`GET/POST/DELETE /api/work/tasks/{id}/github-links/` + `POST .../confirm/`<br>`PATCH /api/work/projects/{id}/members/{uid}/github/` + `POST .../request-verification/` | Kết nối/ngắt repo (lấy danh sách repo từ Integration `GET /api/integrations/api/v1/github/installations/{id}/repositories` để khỏi nhập tay `github_repo_id`), gắn/gỡ/xác nhận PR/commit/branch trên `IssuePanel`, hiển thị và khai báo `github_username` trong bảng thành viên. | Yêu cầu bật cờ `WORK_GITHUB_CONNECTION_ENABLED=true`, `RemoteIntegration`, và Integration flags; `PENDING` ứng viên tự động & tab Code activity có đầy đủ sau **Đợt 5**. |
| **AI** | `POST /api/ai/v1/requests` (`intent: "risk_analysis"`, `target: project\|sprint`) + `GET /api/ai/v1/requests/{id}` | Nút **"AI phân tích rủi ro"** (chỉ đọc, hiển thị mức rủi ro, bằng chứng và `limitations`). DTO đã có sẵn ở `lib/api/ai/dto.ts:62-78`. | Cổng hóa theo `isRealService("ai")`; phụ thuộc xử lý JWT staging `B32`. |
| **Classroom** | `PATCH /api/classroom/courses/{id}/`<br>`POST /api/classroom/courses/{id}/archive/` | Sửa và lưu trữ môn học. *(Lưu ý: `PATCH` hiện bắt gửi đủ `code` và `name` cho tới khi Đợt 1 sửa `partial=True`.)* | Teacher chỉ sửa/lưu trữ môn mình tạo; Admin mọi môn. |
| **Classroom** | `PATCH /api/classroom/groups/{id}/` | Đổi tên nhóm (wrapper `patchGroup` đã viết sẵn ở `apps/web/src/lib/api/classroom/endpoints.ts:126`). *(Lưu ý: tính năng lưu trữ nhóm nên đợi **Đợt 2** để tự động giải phóng thành viên.)* | Leader, Giảng viên phụ trách hoặc Admin; cần `version`. |
| **Classroom** | `POST /api/classroom/classes/{id}/teachers/assign/` | Thêm nút **Gỡ đồng giảng viên** (`status: "LEFT"`) và **Chuyển Giảng viên chính** (`role: "PRIMARY"`) trong `ClassTeachersCard.tsx` (`assignTeacher` & `useAssignTeacher` đã nhận đủ tham số). | Giảng viên phụ trách hoặc Admin; không gỡ giảng viên cuối cùng. |
| **Classroom** | `GET /api/classroom/groups/{id}/projects/` | Dùng làm nguồn ánh xạ nhanh nhóm → dự án (wrapper `listGroupProjects` đã có sẵn ở `endpoints.ts:85`). | Thành viên nhóm hoặc Giảng viên lớp (Admin sau Đợt 1/DG2). |
| **Identity** | `POST /api/auth/users/me/avatar/presigned-url`, `POST .../confirm`<br>`POST /api/auth/oauth/google/start`, `POST/DELETE /api/auth/oauth/google` | Upload avatar (và render `<img src={avatar_url}>` trên hồ sơ/header), đăng nhập bằng Google + route callback `/auth/oauth/google/callback`. | Chỉ khả dụng khi môi trường bật `IDENTITY_AVATAR_ENABLED=true` / `IDENTITY_GOOGLE_ENABLED=true` và CORS R2 (`B30`) đã mở; xóa avatar & đặt mật khẩu Google-only có sau **Đợt 6**. |

---

## 2. Hướng dẫn thay đổi phía Web theo từng Đợt Backend (`Chờ Backend bàn giao`)

> **Lưu ý:** Các endpoint và payload dưới đây mô tả **hợp đồng dự kiến** từ kế hoạch Backend. Team Web chỉ bắt đầu ghép từng đợt sau khi Backend đánh dấu `Đã bàn giao` tại **Mục 4** và đối chiếu lại với file OpenAPI YAML thực tế trong `contracts/api/`.

### Đợt 1 — Vá lệch hợp đồng P1 & Gateway *(Đã triển khai local & kiểm thử đầy đủ — xem chi tiết tại Biên bản Đợt 1 ở Mục 4)*
- **Identity `PATCH /api/auth/users/me`:** Trả đầy đủ hồ sơ `CurrentUserSerializer` (giống `GET /api/auth/users/me`, không còn schema thu gọn `ProfilePatchData`).
  - *Việc của Web:* Bỏ lời gọi thừa `getMe(client)` trong `usePatchMe()` (`apps/web/src/lib/query/identityHooks.ts:21-35`), cập nhật cache thẳng từ response `PATCH`.
- **Identity `PATCH /api/auth/admin/users/{id}/status`:** Chặn `SYSTEM_ADMIN` tự đình chỉ chính mình bằng `400 CANNOT_SUSPEND_SELF`.
- **Classroom `GET /api/classroom/courses/{id}/`, `PATCH /api/classroom/courses/{id}/`, `POST /api/classroom/courses/{id}/unarchive/`:**
  - *Việc của Web:* `PATCH` chấp nhận cập nhật từng phần (`code` hoặc `name`), từ chối body rỗng `{}` với `400 VALIDATION_ERROR`; có thể dùng `GET /courses/{id}/` (Student chỉ xem môn thuộc lớp ghi danh `ACTIVE`, ngoài phạm vi trả `404`) và thêm nút **"Mở lại môn học"** (`POST .../unarchive/` + `Idempotency-Key`).
- **Classroom guard `require_open` trên lớp `CLOSED`/`ARCHIVED`:**
  - *Việc của Web:* 4 lệnh `PATCH /classes/{id}/`, `POST /classes/{id}/lock-grouping/`, `POST /classes/{id}/teachers/assign/`, `POST /classes/{id}/join-code/` nay trả `409 CLASS_NOT_OPEN` nếu lớp không ở trạng thái `OPEN` (`POST /classes/{id}/state/` vẫn cho phép mở lại lớp `CLOSED → OPEN`). Khóa/ẩn form sửa lớp tương ứng khi `class.status !== "OPEN"`.
- **Classroom quyền `SYSTEM_ADMIN` (`NH07`, `NH10`, `NH11`):**
  - *Việc của Web:* `SYSTEM_ADMIN` nay đọc được `GET /groups/{id}/members/`, `GET /groups/{id}/projects/` (chỉ metadata liên kết) và thực hiện `POST /groups/{id}/transfer-leader/`. `POST /groups/{id}/invite-code/` vẫn chỉ dành cho Trưởng nhóm.
- **Work `PATCH /api/work/tasks/{id}/` (chốt DG7 Phương án A):**
  - *Việc của Web:* Thành viên đang được giao task nay được sửa 3 trường `title`, `description_html`, `acceptance_criteria` (các trường điều phối khác vẫn trả `403 LEADER_PERMISSION_REQUIRED`). Cập nhật `apps/web/src/features/projects/lib/issueForm.ts:92-119`, `IssueFormFields.tsx:57,80` để mở lại 2 ô `title` và `acceptance_criteria` cho thành viên được giao, và đồng bộ JSDoc ở `IssueEditForm.tsx:23`.
- **Swagger `/docs/` (Work & Classroom) & Nginx Gateway:**
  - `GET /docs/` ở Work và Classroom bỏ ép xác thực nên gửi kèm Bearer hết hạn vẫn trả `200`.
  - Nginx xử lý `OPTIONS -> 204` cho `/api/integrations/` và `/api/ai/`, đồng thời chặn `/api/ai/v1/internal` (`404`).

### Đợt 2 — Khử N+1 Classroom, 4 góc chết vòng đời, bộ lọc & tra cứu User *(Đã triển khai local & kiểm thử đầy đủ — xem chi tiết tại Biên bản Đợt 2 ở Mục 4)*
- **Classroom `GET /api/classroom/classes/{id}/my-group/` + trường tóm tắt trên `Class` & `Group` (`B5`):**
  - *Việc của Web:* **Xóa hoàn toàn** logic dò 50 nhóm (`loadMyGroup` ở `apps/web/src/lib/api/classroom/loaders.ts:18-50`), gọi 1 request `GET /classes/{id}/my-group/` (xử lý `data: null` là chưa có nhóm, không bắt `404`). Tận dụng `course_summary: {id, code, name}` (giữ nguyên `course` dạng UUID string để không phá client cũ), `my_group_id`, `my_group_name`, `enrolled_count`, `active_group_count`, `primary_teacher_id` từ `GET /classes/` và `member_count`, `leader_id` từ `GET /groups/` để bỏ các request đếm thừa trong `teacherLoaders.ts`.
- **Classroom 4 góc chết vòng đời (`B11`, `B12`):**
  - *Khôi phục sinh viên:* Thêm nút **"Khôi phục vào lớp"** gọi `POST /api/classroom/classes/{id}/enrollments/{eid}/reactivate/` (kèm `Idempotency-Key` + `reason`), hoặc tùy chọn `reactivate_inactive: true` khi import danh sách.
  - *Trưởng nhóm duy nhất:* Khi gặp mã lỗi `409 SOLE_LEADER_DISSOLVE_REQUIRED` (hoặc biết trước nhóm chỉ còn 1 thành viên), hiện hộp thoại xác nhận giải thể/lưu trữ nhóm rồi gửi lại kèm `dissolve_if_sole_member: true` trên `leave`, `remove-member`, `adjust-member`, `exit`.
  - *Lưu trữ nhóm:* Khi gọi `PATCH /api/classroom/groups/{id}/` với `status: "ARCHIVED"`, bắt buộc thu nhập `reason` và cảnh báo toàn bộ thành viên sẽ được giải phóng khỏi nhóm; sau thành công invalidate cache nhóm & lớp.
  - *Mở khóa & chốt chia nhóm:* Trên `POST /classes/{id}/lock-grouping/`, bắt mã `409 GROUPING_PRECONDITIONS_UNMET` để hiển thị số sinh viên chưa có nhóm / danh sách nhóm chưa đủ `group_min_size`, cho phép giảng viên chọn **"Vẫn chốt lập nhóm"** (`force: true`). Bổ sung nút **"Mở khóa chia nhóm"** gọi `POST /classes/{id}/unlock-grouping/`.
- **Classroom bộ lọc `django_filters` (`B13`):**
  - *Việc của Web:* Nối thanh tìm kiếm & bộ lọc server-side cho danh sách môn, lớp, ghi danh (`has_group`), nhóm, và lịch sử hoạt động (`verb`, `actor_user_id`, phân trang cursor thay vì lấy cố định 50 dòng).
- **Identity `GET /api/auth/users/search?q=...&role=TEACHER` (`B9`):**
  - *Việc của Web:* Thay ô nhập UUID thủ công trong `ClassTeachersCard.tsx:20-55` bằng ô tìm kiếm autocomplete (debounce 300ms) chọn giảng viên theo tên/email.

### Đợt 3 — My Work, Giám sát Giảng viên, Kanban & Project Activities
- **Classroom `GET /api/classroom/teacher/classes/summary/` & `GET /api/classroom/classes/{id}/summary/`:**
  - *Việc của Web:* Điền số liệu thật cho `studentsWithoutTeam`, `teamsWithoutProject` trong `apps/web/src/lib/api/classroom/teacherLoaders.ts` mà không phải tải toàn bộ thành viên mọi nhóm.
- **Work `GET /api/work/me/overview/` & `GET /api/work/me/tasks/` (`B15`, `B20`):**
  - *Việc của Web:* Sửa `apps/web/src/features/my-work/queries.ts:19` — bỏ điều kiện ép bật đồng thời cả `work` và `classroom` (chỉ cần `isRealService("work")` là chạy dữ liệu thật từ `/me/overview/` & `/me/tasks/`, bỏ fan-out N+1 từng dự án; ghép thêm tên lớp khi `classroom` bật).
- **Work `GET /api/work/teacher/oversight/projects/?class_id=...` (`B6`):**
  - *Việc của Web:*
    - Mở lại `<AttentionPanel />` ở `TeacherHomeRoute.tsx:137` dùng dữ liệu thật.
    - Thay `<WorkDataUnavailable />` ở `TeacherCourseOversightRoute.tsx:304` bằng bảng giám sát thật hiển thị `progress`, `overdue_count`, `blocked_count`, `last_activity_at`, `signals`.
    - Lấp đầy `teamsWithSignals`, `overdue`, `lastActivity`, `progress` trong `teacherLoaders.ts`.
- **Work `/projects/{id}/kanban/`, `GET /projects/{id}/activities/`, lọc `is_teacher_feedback`:**
  - *Việc của Web:* Chuyển Board sang dùng `/projects/{id}/kanban/` (đã có đủ trường cho `IssueCard`, bỏ tải toàn bộ `/tasks/`); bổ sung feed hoạt động dự án từ `GET /projects/{id}/activities/`; thêm bộ lọc `?is_teacher_feedback=true` trên bình luận Task & Project.

### Đợt 4 — Ghép nhóm mở, Yêu cầu gia nhập, Kỹ năng & Đề tài nhóm
- **Ghép nhóm mở & Bạn học chưa có nhóm:**
  - *Việc của Web:* Nối `GET /api/classroom/classes/{id}/open-groups/` và `GET /api/classroom/classes/{id}/unassigned-students/` vào `course.formation` (`adapters.ts:113`) để bật `OpenTeamsSection` và `UnassignedClassmatesSection` trên `CourseTeamRoute.tsx`. Thêm công tắc *"Đang tuyển thành viên"*, mô tả & kỹ năng cần tuyển vào form tạo/sửa nhóm; thêm hạn đăng ký nhóm (`formation_deadline`) vào cài đặt lớp.
- **Yêu cầu gia nhập nhóm:**
  - *Việc của Web:* Nối nút **"Xin gia nhập"** (`POST /groups/{id}/join-requests/`), màn `PendingJoinRequestView` + **"Hủy yêu cầu"** (`GET /classes/{id}/my-join-requests/`, `POST .../cancel/`), danh sách duyệt cho Leader/Giảng viên (`GET .../join-requests/`, `approve`, `reject`), và điền `pendingTeam` ở `teacherLoaders.ts:137`.
- **Kỹ năng & Vai trò chuyên môn:**
  - *Việc của Web:* Nối `skills` & `responsibility` vào `adapters.ts:63-64` (tự bật 2 cột ở `MembersSection`) và thêm form sửa qua `PATCH /groups/{id}/members/me/`.
- **Đề tài nhóm (`TopicSection`, theo DG3):**
  - *Việc của Web:* Nối `GET/PUT /groups/{id}/topic/`, `POST .../submit/`, `POST .../review/` để bỏ ẩn `TopicSection` (`CourseTeamRoute.tsx:669-670`) và thêm màn duyệt đề tài cho giảng viên.

### Đợt 5 — AI `bulk-apply-ai` & Tab Code (GitHub Activity)
- **AI Proposal `bulk-apply-ai` (`B31`, `B32`):**
  - *Việc của Web:* Thay `applySequentially()` trong `apps/web/src/lib/api/ai/applyProposal.ts` bằng lệnh nguyên tử `POST /api/work/projects/{id}/tasks/bulk-apply-ai/` (backlog) và `POST /api/work/tasks/{id}/subtasks/bulk-apply-ai/` (subtasks), gửi kèm `proposal_id`, `local_id`, `ai_revision` và quan hệ `BLOCKS` giữa các `local_id`. Bật `ai` trong `VITE_REAL_SERVICES` khi `B32` trên staging xong.
- **Tab `/projects/:id/code` & Liên kết GitHub:**
  - *Việc của Web:*
    - Bật tab `code` trong `RealProjectLayout.tsx:72-76`, thay `<WorkModuleNotIntegrated module="code" />` trong `ProjectCodeRoute.tsx:902-905` bằng màn thật gọi `GET /api/work/projects/{id}/github/activity/`.
    - Chọn repo trực tiếp từ Integration `GET /api/integrations/api/v1/github/installations` + `/repositories` rồi gửi `github_repo_id` cho Work `POST /projects/{id}/github/repository/` (kèm polling 202 `PENDING`).
    - Bật `expand=github_links` trong `getTask()` khi `repository.status === "CONNECTED"`, thêm thao tác xác nhận ứng viên `PENDING` (`POST .../confirm/`), cập nhật `hasPullRequest` & `openPullRequests` thật và bật lại chip lọc `"Có Pull Request"`.

### Đợt 6 — Giao diện Quản trị `SYSTEM_ADMIN`, Avatar & Google OAuth
- **Khu vực Admin (`/admin/*`):**
  - *Việc của Web:* Xây dựng nhóm route mới có guard `SYSTEM_ADMIN` và cập nhật redirect ở `apps/web/src/features/auth/utils.ts:31-34` (từ `/settings/profile` sang `/admin/users`), nối các API mới: `POST /admin/users`, `GET/PATCH/DELETE /admin/users/{id}`, `?deleted=active|deleted|all`, `PATCH .../status {restore_deleted}`, `POST .../unlock-login`, `GET /admin/audit-logs`, `GET/DELETE /admin/users/{id}/sessions`.
- **Avatar & Google OAuth & Bẫy mật khẩu:**
  - *Việc của Web:* Thêm nút **"Xóa ảnh đại diện"** (`DELETE /api/auth/users/me/avatar`); đọc `linked_providers` và `has_usable_password` từ `GET /api/auth/users/me`; nếu `!has_usable_password`, hiển thị form **"Đặt mật khẩu lần đầu"** (`POST /api/auth/password-set`) trước khi cho phép hủy liên kết Google.
- **Kích hoạt tài khoản:** Kiểm tra lại màn `/register` và `/auth/activate` với luồng email thật sau khi Backend bật `IDENTITY_REQUIRE_EMAIL_ACTIVATION=true` và xác nhận Notification/SMTP (`B3`).

### Đợt 7 — UX quản lý nâng cao Work & Học vụ Classroom P2
- **Work nâng cao:** Nối UI đổi task cha (`PATCH /tasks/{id}/parent/`), thanh bulk actions (`POST /projects/{id}/tasks/bulk/`), xóa/lưu trữ/mở lại Sprint & biểu đồ Velocity/Snapshot (`GET /projects/{id}/velocity/`, `GET /sprints/{id}/snapshot/`), xóa mềm Project (`DELETE /projects/{id}/`), lọc/sắp xếp `GET /projects/` & `GET /projects/{id}/tasks/`, bộ lọc Dashboard, tiến độ chi tiết Epic (`GET /projects/{id}/epics/{id}/`), Global Search (`GET /search/`), Export báo cáo, Checklist, Watchers, Comment replies/reactions, Worklogs, và trang `/projects/:id/settings` (bật lại guard `RequireProjectManagePermission` cho Leader).
- **Classroom P2:** Chỉ xây dựng giao diện Điểm danh, Điểm số/Rubric, Thông báo lớp, Tài liệu môn/lớp sau khi chốt spec và Backend hoàn tất Đợt 7.2.

---

## 3. Quy ước kỹ thuật dùng chung giữa Backend và Web

1. **Envelope phản hồi theo từng service (khác nhau, Web cần giữ nguyên phân nhánh trong `client.ts`):**
   - Identity (`/api/auth/*`), Classroom (`/api/classroom/*`), Work (`/api/work/*`): `{success, message, data, meta, error}`.
   - Integration (`/api/integrations/*`): `{success, data}` hoặc `{success: false, error: {code, message}}`.
   - AI (`/api/ai/v1/*`): trả JSON trực tiếp không bọc `success/data`; lỗi có dạng `{error: {code, message, details, request_id, retryable}}`.
2. **Không dùng `message` làm mã lỗi lập trình:** Backend viết `message` và `error.details[].issue` bằng tiếng Việt tự nhiên và có thể tinh chỉnh câu chữ; Web **chỉ nhánh logic theo HTTP status và `error.code`**.
3. **Chống lặp (`Idempotency-Key`) và Khóa lạc quan (`version` / `expected_version`):**
   - Chỉ gửi header `Idempotency-Key` (UUID v4) ở các lệnh `POST` có khai báo trong OpenAPI; giữ nguyên key khi retry cùng payload và sinh key mới khi người dùng sửa form.
   - Khi nhận `409 VERSION_CONFLICT`: refetch dữ liệu mới nhất và nạp lại form đang mở theo bản mới (không ghi đè thầm lặng thay đổi của người khác).
4. **Cờ dịch vụ thật & Không rơi ngầm về Mock:**
   - Khi một service nằm trong `VITE_REAL_SERVICES` (`auth`, `classroom`, `work`, `ai`, `notifications`, `integrations`), lỗi từ API thật phải hiển thị trạng thái lỗi rõ ràng, không tự rơi về dữ liệu MSW.
5. **Đối chiếu blocker hạ tầng (`B1–B32`):** Theo dõi tiến độ xử lý các mã `B2` (CSRF origin), `B3` (SMTP/email link), `B30` (CORS R2), `B32` (JWT AI staging) trong [docs/web/api-integration.md](api-integration.md#L423-L452).

---

## 4. Nhật ký & Biên bản bàn giao thực tế theo từng đợt (Bắt buộc cập nhật sau mỗi đợt)

> **Quy tắc bắt buộc (`[WEB-HANDOFF-GATE]`):** Vì trong quá trình sửa Backend có thể phát sinh điều chỉnh so với kế hoạch ban đầu, **ngay khi hoàn tất mỗi đợt (hoặc phase con) có liên quan đến Web**, kỹ sư Backend **bắt buộc** cập nhật bảng tổng hợp bên dưới, chỉnh lại Mục 2 nếu có sai khác và điền thêm một khối **Biên bản chi tiết Đợt X** theo mẫu trước khi chốt commit hoặc chuyển sang đợt tiếp theo.

### 4.1. Bảng tổng hợp bàn giao

| Đợt | Ngày bàn giao | Nhánh / Commit Backend | Môi trường đã kiểm (Local / Staging) | Contract đã cập nhật | Tóm tắt điều chỉnh phát sinh / Breaking notes | Xác nhận tiếp nhận (Team Web) |
| --- | --- | --- | --- | --- | --- | --- |
| **Đợt 1** | 2026-11-24 | `feat/backend-api-gap-waves` (`1d02eb1`, `a1b3460`, `21f90a9`, `3fb2eb2`) | Local đầy đủ (PostgreSQL 16 + Redis 7 cô lập & Docker Nginx); Staging `Chưa xác minh` | `contracts/api/classroom-service.yaml`, `contracts/api/work-service.yaml`, Identity OpenAPI live | Không breaking cho client đang chạy; `PATCH /courses/{id}/` từ chối `{}` (`400`); 4 lệnh lớp trên lớp `CLOSED`/`ARCHIVED` trả `409 CLASS_NOT_OPEN`; `PATCH /tasks/{id}/` mở thêm `title` & `acceptance_criteria` cho thành viên được giao; `POST /groups/{id}/invite-code/` giữ quyền Trưởng nhóm (`SYSTEM_ADMIN` nhận `404`) | `[ ]` |
| **Đợt 2** | 2026-11-24 | `feat/backend-api-gap-waves` (`a1b3460`, `21f90a9`, `3fb2eb2`) | Local đầy đủ (PostgreSQL 16 + Redis 7 cô lập); Staging `Chưa xác minh` | `contracts/api/classroom-service.yaml`, `contracts/events/classroom.group.membership.changed.v1.json`, Identity OpenAPI live | **Breaking cần xử lý:** `lock-grouping` mặc định trả `409 GROUPING_PRECONDITIONS_UNMET` khi còn SV chưa có nhóm hoặc nhóm thiếu người (cần dialog xác nhận gửi `force: true`); `PATCH /groups/{id}/` với `status=ARCHIVED` bắt buộc `reason`; trưởng nhóm duy nhất trả `409 SOLE_LEADER_DISSOLVE_REQUIRED` cho tới khi gửi `dissolve_if_sole_member: true`. **Giữ tương thích:** `Class.course` vẫn là UUID string, bổ sung `course_summary: {id, code, name}`. | `[ ]` |
| **Đợt 3** | _Chưa bàn giao_ | — | — | — | — | `[ ]` |
| **Đợt 4** | _Chưa bàn giao_ | — | — | — | — | `[ ]` |
| **Đợt 5** | _Chưa bàn giao_ | — | — | — | — | `[ ]` |
| **Đợt 6** | _Chưa bàn giao_ | — | — | — | — | `[ ]` |
| **Đợt 7** | _Chưa bàn giao_ | — | — | — | — | `[ ]` |

### 4.2. Mẫu biên bản chi tiết cho từng đợt đã hoàn thành (sao chép khi bàn giao)

```markdown
#### Biên bản Đợt <X> — <Tên đợt / phạm vi>
- **Ngày bàn giao:** YYYY-MM-DD | **Nhánh / Commit:** `<branch>` (`<sha>`)
- **Trạng thái kiểm chứng Backend:** `Đã triển khai (local)` / `Đã triển khai (staging)` (nêu rõ test đã chạy & phần chưa xác minh)
- **Contract đã cập nhật:** `contracts/api/<service>.yaml` (và `contracts/events/...` nếu có)
- **Điều chỉnh phát sinh trong quá trình triển khai (khác so với kế hoạch ban đầu):**
  - <Ghi rõ từng điểm đã chỉnh sửa về tên trường, query param, trạng thái, quyền, mã lỗi; hoặc ghi "Khớp thiết kế ban đầu".>
- **API công khai thay đổi / bổ sung (qua Gateway `/api/...`):**
  - `<METHOD> /api/<prefix>/...` — Quyền, header (`Idempotency-Key`, `X-CSRFToken`), khóa lạc quan (`version`/`expected_version`), request/response mẫu rút gọn, danh sách `HTTP status + error.code`.
- **Yêu cầu thay đổi phía Team Web:**
  - **Bắt buộc (Breaking / Fix bug):** <liệt kê cụ thể file/luồng cần đổi nếu có>
  - **Nâng cấp khuyến nghị (Bỏ hack/N+1 hoặc mở tính năng mới):** <liệt kê cụ thể>
  - **Biến môi trường / Cờ cần bật (`VITE_REAL_SERVICES`, cờ backend):** <ghi rõ nếu có>
```

*(Các mục `#### Biên bản Đợt 1..7` thực tế được nối thêm ngay bên dưới sau khi từng đợt Backend hoàn tất và qua kiểm thử.)*

#### Biên bản Đợt 1 — Vá lệch hợp đồng P1 & Nginx Gateway
- **Ngày bàn giao:** 2026-11-24 | **Nhánh / Commit:** `feat/backend-api-gap-waves` (`1d02eb1`, `a1b3460`, `21f90a9`, `3fb2eb2`)
- **Trạng thái kiểm chứng Backend:** `Đã triển khai (local)` — toàn bộ kiểm thử cục bộ đã đạt trên PostgreSQL 16 + Redis 7 cô lập và container `nginx:1.27-alpine`:
  - **Lint / Format / Django checks:** `ruff check` & `ruff format --check`, `manage.py check`, `manage.py makemigrations --check --dry-run` đều `0` lỗi trên cả 3 service (`identity-service`, `classroom-service`, `work-service`).
  - **Identity Service:** `pytest` toàn bộ **400/400 đạt** (gồm `tests/test_account_api.py` và `tests/test_openapi.py` kiểm tra live envelope `PATCH /users/me` khớp `#/components/schemas/CurrentUser`).
  - **Classroom Service:** `pytest` toàn bộ **479/479 đạt** (gồm `test_courses.py`, `test_class_sections.py`, `test_group_role_commands.py`, `test_openapi_contracts.py`, `test_auth_contract.py`; `spectacular --validate --fail-on-warn` 0 cảnh báo).
  - **Work Service:** `pytest` toàn bộ **957/957 đạt** (6 bài tách theo cấu hình pytest mặc định; gồm `test_tasks.py`, `test_auth_contract.py`), cộng thêm `integration-service` `test_work_receipt_contract.py` **79/79 đạt** xác nhận `contracts/api/work-service.yaml`.
  - **Nginx Gateway & Compose:** `test_integration_compose.py` (**9/9 đạt**, gồm container `nginx:1.27-alpine` chạy `nginx -t` + kiểm chứng `OPTIONS -> 204` trên public route và `404` trên mọi biến thể `/api/integrations/api/v1/internal`), `test_ai_compose.py` (**8/8 đạt** + kiểm chứng trực tiếp trên container `nginx:1.27-alpine`: `OPTIONS /api/ai/v1/requests -> 204` kèm `Access-Control-Allow-Origin`, `GET /api/ai/v1/requests -> 503`, `/api/ai/v1/internal* -> 404` cho cả `GET`/`OPTIONS`), `test_classroom_compose.py` (4/4), `test_client_ip_ingress.py` (5/5), `test_work_integration_configuration.py` (5/5), `docker compose config --quiet` (dev & staging đều `0`).
  - **Chưa xác minh:** Build image mới & triển khai thực tế lên môi trường **staging** (và các test shell bash chỉ chạy trên POSIX của `scripts/tests/test_staging_deployment.py`).
- **Contract đã cập nhật:**
  - `contracts/api/classroom-service.yaml` (`operationId: courses_list`, thêm `GET /courses/{course_id}/`, `PatchedCoursePatch` partial, `POST /courses/{course_id}/unarchive/`, cập nhật mô tả quyền Admin ở `NH07/10/11`)
  - `contracts/api/work-service.yaml` (cập nhật mô tả quyền thành viên được giao trên `PATCH /tasks/{task_id}/`, giữ nguyên `$ref` tới `work-ai-context-v1.yaml`)
  - Identity OpenAPI live (`/api/auth/openapi/`): `PATCH /users/me` trả cùng schema `#/components/schemas/CurrentUser` như `GET /users/me` (xóa schema thu gọn `ProfilePatchData`)
- **Điều chỉnh phát sinh trong quá trình triển khai (khác/bổ sung so với kế hoạch ban đầu):**
  - `GET /courses/` ở Classroom được gắn rõ `operationId: courses_list` (khớp `classes_list`/`groups_list`) để tránh xung đột `operationId` với `GET /courses/{course_id}/` (`courses_retrieve`).
  - `PATCH /courses/{course_id}/` dùng `CoursePatchSerializer` (kế thừa `CourseInputSerializer`) đánh dấu `code`/`name` tùy chọn và **từ chối body rỗng `{}`** với `400 VALIDATION_ERROR` (*"Cần cung cấp ít nhất một trường để cập nhật."*).
  - `POST /classes/{id}/teachers/assign/` kiểm `require_open(section)` ngay cả trước khi gọi Identity lookup, nên trên lớp `CLOSED`/`ARCHIVED` trả nhanh `409 CLASS_NOT_OPEN` mà không gọi sang Identity.
  - `infra/nginx/nginx.conf` đồng thời thêm block chặn `404` cho `/api/ai/v1/internal` và `/api/ai/v1/internal/` sớm ngay từ Đợt 1.
- **API công khai thay đổi / bổ sung (qua Gateway `/api/...`):**
  - `PATCH /api/auth/users/me` — Trả đầy đủ `CurrentUser` (`id, email, username, student_id, display_name, avatar_url, roles, first_name, last_name, phone_number, bio, github_username, academic_year, faculty, timezone, preferences, created_at`).
  - `PATCH /api/auth/admin/users/{user_id}/status` — Thêm mã lỗi `400 CANNOT_SUSPEND_SELF` (*"Bạn không thể tự tạm đình chỉ tài khoản quản trị của mình."*) khi Admin tự đình chỉ mình.
  - `GET /api/classroom/courses/{course_id}/` — Quyền giống `GET /courses/` (Student chỉ xem môn thuộc lớp ghi danh `ACTIVE`, không thuộc phạm vi trả `404`; Teacher/Admin xem mọi môn).
  - `PATCH /api/classroom/courses/{course_id}/` — Nhận partial `code` và/hoặc `name`, yêu cầu `Idempotency-Key`; `{}` trả `400 VALIDATION_ERROR`.
  - `POST /api/classroom/courses/{course_id}/unarchive/` — Yêu cầu `Idempotency-Key`, body `{}`; quyền chủ môn/Admin theo CS01; trả `200` với `archived_at: null` và thông báo `"Đã mở lại môn học."`.
  - `PATCH /api/classroom/classes/{id}/`, `POST .../lock-grouping/`, `POST .../teachers/assign/`, `POST .../join-code/` — Trả `409 CLASS_NOT_OPEN` khi lớp ở trạng thái `CLOSED` hoặc `ARCHIVED`.
  - `GET /api/classroom/groups/{id}/members/`, `GET .../projects/`, `POST .../transfer-leader/` — Mở thêm quyền `SYSTEM_ADMIN` (riêng `projects/` chỉ trả metadata liên kết). Lưu ý: `POST /api/classroom/groups/{id}/invite-code/` (`NH05`) giữ nguyên quyền Trưởng nhóm (`SYSTEM_ADMIN` nhận `404 RESOURCE_NOT_FOUND` theo cơ chế ẩn tài nguyên ngoài phạm vi nhóm).
  - `PATCH /api/work/tasks/{task_id}/` — Thành viên đang được giao task được sửa `title`, `description_html`, `acceptance_criteria`; các trường khác (`priority`, `story_points`, `due_date`, `epic_id`, `assignee_ids`, `label_ids`) vẫn trả `403 LEADER_PERMISSION_REQUIRED`.
  - `GET /api/work/docs/` & `GET /api/classroom/docs/` — Không chạy JWT auth nên không còn lỗi `401`/`503` khi kèm Bearer hết hạn.
- **Yêu cầu thay đổi phía Team Web:**
  - **Nâng cấp khuyến nghị:**
    1. `apps/web/src/lib/query/identityHooks.ts:21-35`: bỏ lời gọi thừa `getMe(client)` sau `patchMe(client, body)`, cập nhật cache trực tiếp từ kết quả `PATCH /api/auth/users/me`.
    2. `apps/web/src/features/projects/lib/issueForm.ts:92-119`, `IssueFormFields.tsx:57,80`, `IssueEditForm.tsx:23`: cho phép thành viên được giao sửa `title` và `acceptance_criteria` cùng `description_html` (đồng bộ với backend).
    3. Trên màn cài đặt lớp giảng viên: vô hiệu/ẩn form sửa lớp, phân công giảng viên, cấp mã lớp và chốt chia nhóm khi `class.status !== "OPEN"` và xử lý mã `409 CLASS_NOT_OPEN`.
    4. Khi nối màn quản lý môn học: có thể dùng `GET /courses/{id}/`, `PATCH` từng phần và `POST /courses/{id}/unarchive/`.
  - **Biến môi trường / Cờ cần bật:** Không thêm biến môi trường mới ở Đợt 1; cần reload/recreate Nginx khi triển khai `infra/nginx/nginx.conf`.

#### Biên bản Đợt 2 — API `my-group`, 4 góc chết vòng đời Classroom, bộ lọc `django_filters` & tra cứu User Identity
- **Ngày bàn giao:** 2026-11-24 | **Nhánh / Commit:** `feat/backend-api-gap-waves` (`a1b3460`, `21f90a9`, `3fb2eb2`)
- **Trạng thái kiểm chứng Backend:** `Đã triển khai (local)` — toàn bộ kiểm thử cục bộ đã đạt trên PostgreSQL 16 + Redis 7 cô lập:
  - **Lint / Format / Migrations / OpenAPI:** `ruff check` & `ruff format --check` sạch trên cả 3 service; `manage.py check` và `makemigrations --check --dry-run` `0` lỗi; đã tạo 3 migration thêm index PostgreSQL tương thích ngược (`courses/0003`, `groups/0004`, `messaging/0002`); `spectacular --validate --fail-on-warn` `0` cảnh báo; `export_event_contract` khớp schema sự kiện.
  - **Classroom Service:** `pytest` toàn bộ **495/495 đạt** (23 bài e2e tách theo cấu hình mặc định; gồm `test_my_group_and_summaries.py` chứng minh không N+1 bằng `django_assert_num_queries`, `test_lifecycle_edge_cases.py`, `test_list_filters.py`, `test_events.py`, `test_openapi_contracts.py`, `test_student_lists.py`).
  - **Work Service:** `pytest` toàn bộ **961/961 đạt** (6 bài tách mặc định; gồm `test_classroom_facts.py` và `test_membership_consumer.py` xác minh consumer xử lý an toàn sự kiện nhóm `ARCHIVED` có 0 thành viên `ACTIVE`, đóng toàn bộ `ProjectMember` và bảo toàn lịch sử dự án/task).
  - **Identity Service:** `pytest` toàn bộ **404/404 đạt** (gồm `test_account_api.py` kiểm tra quyền, bộ lọc, chỉ trả trường công khai, loại tài khoản `SUSPENDED`/đã xóa mềm, rate limit `30/min` và `test_openapi.py` live envelope conformance cho `GET /users/search`).
  - **Chưa xác minh:** Build lại container local đang chạy, chạy migration trên DB runtime/staging và kiểm thử E2E trên môi trường **staging**.
- **Contract đã cập nhật:**
  - `contracts/api/classroom-service.yaml` (thêm `GET /classes/{class_id}/my-group/`, `POST /classes/{class_id}/unlock-grouping/`, `POST /classes/{class_id}/enrollments/{enrollment_id}/reactivate/`; làm giàu `Class` & `Group`; bổ sung toàn bộ tham số lọc `django_filters`, `ActivityChanges`, `dissolve_if_sole_member`, `force`, `reactivate_inactive`, `summary.reactivated`; chuẩn hóa tên enum `ClassStatusEnum`, `GroupStatusEnum`, `TeacherStatusEnum`, `TeacherRoleEnum`, `MemberFactRoleEnum`, `MemberFactStatusEnum`).
  - `contracts/events/classroom.group.membership.changed.v1.json` (bổ sung trường `data.group_status`: `"ACTIVE" | "ARCHIVED"`, mặc định `"ACTIVE"` tương thích ngược).
  - Identity OpenAPI live (`/api/auth/openapi/`): thêm `GET /users/search` (`UserSearchResults`).
- **Điều chỉnh phát sinh trong quá trình triển khai (khác/bổ sung so với kế hoạch ban đầu):**
  - **Bảo toàn tương thích cho `Class.course`:** Thay vì đổi trường `course` từ UUID string sang object (sẽ làm vỡ `courseById.get(cls.course)` ở `apps/web/src/lib/api/classroom/{loaders,teacherLoaders}.ts`), Backend **giữ nguyên `course` dạng UUID string** và **thêm trường mới `course_summary: {id, code, name}`**.
  - **Tách mã lỗi rõ ràng cho Trưởng nhóm:** Khi nhóm còn `>= 2` thành viên `ACTIVE`, 4 lệnh (`leave`, `remove-member`, `adjust-member`, `exit`) vẫn trả `409 LEADER_SUCCESSOR_REQUIRED` (kể cả khi gửi `dissolve_if_sole_member: true`); chỉ khi Trưởng nhóm là thành viên `ACTIVE` duy nhất mới trả `409 SOLE_LEADER_DISSOLVE_REQUIRED` kèm `error.details[0].field = "dissolve_if_sole_member"` nếu chưa xác nhận giải thể.
  - **Không thêm `dissolve_if_sole_member` vào `transfer-leader`:** Tách riêng `MemberLeaveSerializer` và `MemberRemoveSerializer` để `StrictInputSerializer` vẫn chặn trường lạ trên `POST /groups/{id}/transfer-leader/`.
  - **Thống kê khôi phục hàng loạt:** `POST /classes/{id}/students/` bổ sung trường `summary.reactivated` (số nguyên) cùng cờ tùy chọn `reactivate_inactive` ở root payload; bỏ giá trị mặc định trong `validated_data` để không làm đổi `payload_hash` idempotency của request cũ không gửi cờ.
  - **Nhánh `recovery-snapshot` nội bộ:** `/internal/groups/{id}/recovery-snapshot/` nay hỗ trợ cả nhóm `ARCHIVED` (0 thành viên `ACTIVE`) để đồng bộ Work khi phục hồi, còn `/internal/groups/{id}/snapshot/` (tạo dự án mới) vẫn bắt buộc nhóm `ACTIVE`.
- **API công khai thay đổi / bổ sung (qua Gateway `/api/...`):**
  - `GET /api/classroom/classes/{class_id}/my-group/` — Sinh viên ghi danh `ACTIVE` lấy nhóm hiện tại kèm `my_role`, `member_count`, `leader_id`, `members` (`ACTIVE` kèm `profile`); trả `200` với `data: null` nếu chưa có nhóm (`403 ENROLLMENT_REQUIRED` nếu gọi bằng tài khoản GV/Admin không ghi danh SV; `404` nếu ngoài lớp).
  - `GET /api/classroom/classes/` & `GET /api/classroom/classes/{class_id}/` — Bổ sung `course_summary: {id, code, name}`, `enrolled_count`, `active_group_count`, `primary_teacher_id`, `my_group_id`, `my_group_name`. Hỗ trợ lọc `?search=&course_id=&term=&status=&grouping_phase=`.
  - `GET /api/classroom/groups/`, `GET /api/classroom/classes/{class_id}/groups/`, `GET /api/classroom/groups/{group_id}/` — Bổ sung `member_count`, `leader_id`. Hỗ trợ lọc `?search=&status=`.
  - `GET /api/classroom/courses/` — Hỗ trợ lọc `?search=&archived=true|false|all`.
  - `GET /api/classroom/classes/{class_id}/enrollments/` — Hỗ trợ lọc `?status=&has_group=true|false&user_id=`.
  - `GET /api/classroom/classes/{class_id}/activities/` & `GET /api/classroom/groups/{group_id}/activities/` — Hỗ trợ lọc `?verb=&actor_user_id=&created_from=&created_to=` (ISO-8601), gắn chặt vào cursor fingerprint; đổi bộ lọc mà tái dùng cursor cũ trả `400 VALIDATION_ERROR`.
  - `POST /api/classroom/classes/{class_id}/enrollments/{enrollment_id}/reactivate/` — GV phụ trách / Admin, lớp `OPEN`, header `Idempotency-Key`, body `{reason}` (1–500 ký tự); trả `200` `Enrollment` (`409 ENROLLMENT_ALREADY_ACTIVE` nếu đang `ACTIVE`, `409 CLASS_NOT_OPEN` nếu lớp không mở).
  - `POST /api/classroom/classes/{class_id}/students/` — Bổ sung `reactivate_inactive?: boolean`, `summary.reactivated`, và giá trị `enrollment_result: "REACTIVATED"`.
  - `POST /api/classroom/groups/{group_id}/leave/`, `.../remove-member/`, `POST /api/classroom/classes/{class_id}/adjust-member/`, `POST /api/classroom/classes/{class_id}/enrollments/{enrollment_id}/exit/` — Bổ sung `dissolve_if_sole_member?: boolean`; trả `409 SOLE_LEADER_DISSOLVE_REQUIRED` nếu Trưởng nhóm là thành viên duy nhất và chưa xác nhận giải thể.
  - `PATCH /api/classroom/groups/{group_id}/` — Khi `status: "ARCHIVED"` bắt buộc kèm `reason` (1–500 ký tự); tự động chuyển mọi thành viên `ACTIVE` sang `REMOVED`, tắt mã mời, phát sự kiện Kafka và giải phóng ràng buộc để sinh viên vào/tạo nhóm mới ngay.
  - `POST /api/classroom/classes/{class_id}/lock-grouping/` — Nhận `{version, force?: boolean}`; mặc định kiểm tra SV chưa có nhóm và nhóm `< group_min_size` → `409 GROUPING_PRECONDITIONS_UNMET` (chi tiết từng mục trong `error.details[]`); nếu lớp đã `LOCKED` và gửi đúng `version`, trả `200` idempotent không tăng `version`.
  - `POST /api/classroom/classes/{class_id}/unlock-grouping/` — GV phụ trách / Admin, lớp `OPEN`, `Idempotency-Key`, body `{version, reason}`; đặt lại `grouping_phase: "FORMING"`, `grouping_locked_at: null` (idempotent nếu đang `FORMING`).
  - `GET /api/auth/users/search?q=<min 2>&role=<TEACHER|STUDENT|SYSTEM_ADMIN>&limit=<1..20>` — Chỉ `TEACHER` hoặc `SYSTEM_ADMIN` (`403 FORBIDDEN_TEACHER_OR_ADMIN` với Student), chỉ trả tài khoản `ACTIVE` chưa xóa mềm với 6 trường công khai `{id, display_name, email, student_id, avatar_url, roles}`, giới hạn tần suất `30/min` mỗi người dùng (`429`).
- **Yêu cầu thay đổi phía Team Web:**
  - **Bắt buộc (Breaking / Hành vi mới cần xử lý ngay khi nâng cấp Backend Đợt 2):**
    1. Nút **"Chốt lập nhóm"** (`POST /api/classroom/classes/{id}/lock-grouping/`): bắt mã `409 GROUPING_PRECONDITIONS_UNMET`, hiển thị danh sách cảnh báo từ `error.details[].issue` và cung cấp lựa chọn **"Vẫn chốt lập nhóm"** gửi lại với `force: true` (kèm `Idempotency-Key` mới).
    2. Thao tác lưu trữ nhóm (`PATCH /api/classroom/groups/{id}/` với `status: "ARCHIVED"`): bắt buộc thu nhập trường `reason` và cảnh báo toàn bộ thành viên sẽ được giải phóng.
    3. Các nút rời nhóm / loại thành viên / điều chỉnh nhóm / rời lớp: bắt thêm `409 SOLE_LEADER_DISSOLVE_REQUIRED`, mở hộp thoại xác nhận giải thể nhóm rồi gửi lại kèm `dissolve_if_sole_member: true`.
  - **Nâng cấp khuyến nghị (Bỏ hack/N+1 và mở tính năng mới):**
    1. `apps/web/src/lib/api/classroom/loaders.ts:18-50`: xóa toàn bộ vòng lặp dò 50 nhóm `loadMyGroup`, thay bằng 1 request `GET /api/classroom/classes/{id}/my-group/` (xử lý `data: null`).
    2. `apps/web/src/lib/api/classroom/teacherLoaders.ts`: đọc `course_summary`, `enrolled_count`, `active_group_count`, `primary_teacher_id`, `member_count`, `leader_id` trực tiếp từ `/classes/` và `/groups/` để cắt request thừa.
    3. Thêm nút **"Khôi phục vào lớp"** (`POST .../enrollments/{eid}/reactivate/`), tùy chọn `reactivate_inactive` khi import Excel và nút **"Mở khóa chia nhóm"** (`POST .../unlock-grouping/`).
    4. Nối thanh tìm kiếm & bộ lọc server-side (`search`, `archived`, `course_id`, `term`, `grouping_phase`, `has_group`, `verb`, `actor_user_id`, `created_from`/`created_to`) và thay ô nhập UUID thủ công trong `ClassTeachersCard.tsx:20-55` bằng autocomplete gọi `GET /api/auth/users/search?q=...&role=TEACHER` (debounce >= 300ms).
  - **Biến môi trường / Cờ cần bật:** Không thêm biến môi trường mới ở Đợt 2; cần chạy `manage.py migrate` cho `classroom-service` khi triển khai 3 migration index mới.
