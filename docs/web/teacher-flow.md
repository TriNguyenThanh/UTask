# Luồng giảng viên (Teacher Flow) — hiện trạng, phạm vi và kế hoạch

**Trạng thái tài liệu: Phase 0 (rà soát, chốt nền) hoàn tất; Phase 1 (nền quyền, graph mock dùng chung, giao diện đọc lớp) đã triển khai trên dữ liệu Demo MSW. Kết quả và bằng chứng ở [§13](#13-kết-quả-phase-1); giao diện được dựng lại theo thiết kế Stitch và thêm màn Giám sát ở [§14](#14-cập-nhật-theo-thiết-kế-stitch); Phase 2 (dashboard nhóm T08, workspace chỉ xem cho giảng viên) ở [§15](#15-kết-quả-phase-2--từ-nhóm-đến-workspace-chỉ-xem). Chưa có backend, hợp đồng API hay thao tác ghi nào của Teacher.**

Căn cứ: nhánh `fix/frontend-student-flow`, HEAD `c9df96b` (08/10/2026); phần
Phase 1 nằm trong working tree, chưa commit. Mọi kết
luận "hiện trạng" dưới đây dựa trên mã nguồn ở HEAD. Bằng chứng lấy từ nhánh
khác được ghi rõ dạng `nhánh:đường-dẫn`; các nhánh đó **chưa merge** vào nhánh
hiện tại nên không được coi là tính năng đã chạy ở đây.

Nguồn nghiệp vụ: [phân tích vai trò](utask-role-analysis.md) (US-1.2, US-1.4,
US-2.5, US-4.4, US-4.5, US-5.7 và ma trận quyền §2.2). Luồng sinh viên hiện có:
[student-flow.md](student-flow.md). Ranh giới service:
[kiến trúc](../system/architecture.md), [quyền sở hữu dữ liệu](../system/data-ownership.md).

Nhãn trạng thái theo [quy ước](../system/README.md#quy-ước-trạng-thái).
Thuật ngữ: *capability* = khả năng dùng một không gian giao diện (ví dụ không
gian giảng viên); *assignment* = quan hệ giảng viên phụ trách một lớp cụ thể;
*viewer context* = tư cách của người xem đối với một project (thành viên nhóm
hay giảng viên của lớp).

## 1. Nguồn đã rà soát

| Nguồn | Kết quả |
| --- | --- |
| `utask-role-analysis.md` | Có tại [docs/web/utask-role-analysis.md](utask-role-analysis.md) (chưa track trong git) |
| `UTask_Teacher_Flow_Plan.md` | **Không tồn tại** trong repo. Nội dung plan đã chốt nằm trong bản nháp trước của chính file này; tài liệu này thay thế bản nháp đó, giữ các quyết định và bổ sung bằng chứng |
| HTML/asset thiết kế Teacher | **Không có.** Repo chỉ có [apps/web/index.html](../../apps/web/index.html); `.stitch-assets` nhắc trong README web không có trong repo. Bố cục ở §5 là **đề xuất** bám UI hiện có |
| Backend trong HEAD | **Không có.** `apps/` chỉ có `web`; [docker-compose.yml](../../docker-compose.yml) và [nginx.conf](../../infra/nginx/nginx.conf) tham chiếu `identity-service`, `work-service`, `classroom-service`… nhưng thư mục không tồn tại |
| `contracts/` | Chỉ có [api/README.md](../../contracts/api/README.md) và [events/README.md](../../contracts/events/README.md); không có hợp đồng máy đọc được |
| Identity Service | Có ở `origin/main` (`apps/identity-service`, `docs/architecture/Identity_Service_API_Specification.md` v1.8, trạng thái tự ghi "Một phần") |
| Classroom Service | Ở `origin/feat/classroom-service` chỉ có khung Django + `/healthz` (`config/urls.py`); tài liệu `docs/classroom-service/{data-model,objects,chuc-nang}.md` ghi "Thiết kế mục tiêu, cần review" |
| Project/Work, Progress Service | Không có mã ở bất kỳ nhánh nào đã kiểm tra |
| AI Service | `origin/feat/ai-service:contracts/api/ai-service-v1.yaml` ghi `x-utask-status: designed-not-implemented` |

## 2. Hiện trạng frontend trước Phase 1 (bằng chứng ở HEAD `c9df96b`)

Các mục 2 và 3 mô tả HEAD **trước** Phase 1 để giữ lý do của từng quyết định.
Trạng thái hiện tại của từng điểm nằm ở [§13](#13-kết-quả-phase-1).

### 2.1 Auth và biểu diễn Teacher — Chưa triển khai

- `AuthUser` chỉ có `global_role: "USER"` và `capabilities: string[]`
  ([types.ts:1-7](../../apps/web/src/features/auth/types.ts) (HEAD `c9df96b`, dòng 1–7)). Không có
  giá trị nào biểu diễn Teacher. `capabilities` chỉ xuất hiện trong mock/test
  ([database.ts:10-32](../../apps/web/src/mocks/data/database.ts) (HEAD `c9df96b`, dòng 10–32),
  `test/render.tsx`), không có mã nào đọc nó.
- Ba tài khoản demo đều là sinh viên; không có tài khoản Teacher.
- Identity (`origin/main`, ngoài HEAD) dùng mảng `roles` gồm `SYSTEM_ADMIN`,
  `TEACHER`, `STUDENT` (`accounts/roles.py`, `accounts/serializers/profiles.py`
  trả `roles` đã sắp xếp). Đặc tả ghi rõ: role toàn cục **không** cấp quyền
  Project/Classroom; "quyền trên lớp do Classroom quản lý"; JWT không chứa roles.
- Lệch hợp đồng auth (ngoài phạm vi Teacher nhưng là điều kiện tích hợp thật):
  frontend đọc `access_token`/`refresh_token`/`expires_in`/`user` ở gốc
  ([auth.ts](../../apps/web/src/features/auth/api/auth.ts)); Identity trả
  envelope `{success, message, data, meta, error}` với `data.access`,
  refresh qua cookie. `ApiClient` không bóc envelope
  ([client.ts](../../apps/web/src/lib/api/client.ts)).
- Sau đăng nhập luôn về `/my-work`
  ([LoginForm.tsx:33](../../apps/web/src/features/auth/components/LoginForm.tsx) (HEAD `c9df96b`, dòng 33),
  [router.tsx:32](../../apps/web/src/app/router/router.tsx) (HEAD `c9df96b`, dòng 32)).

### 2.2 Guard và permission — Một phần (chỉ Leader/Member)

| Thành phần | Tái sử dụng cho Teacher? | Ghi chú |
| --- | --- | --- |
| [RequireAuth](../../apps/web/src/app/router/RequireAuth.tsx) | Có | Chỉ kiểm tra đăng nhập, giữ `returnTo` |
| [ForbiddenPage](../../apps/web/src/components/feedback/ForbiddenPage.tsx), [EmptyState](../../apps/web/src/components/feedback/EmptyState.tsx), [ErrorState](../../apps/web/src/components/feedback/ErrorState.tsx), [PageSkeleton](../../apps/web/src/components/feedback/PageSkeleton.tsx) | Có | Dùng cho loading/empty/error/forbidden |
| Xử lý 403/404 trong [ProjectWorkspaceLayout](../../apps/web/src/features/projects/routes/ProjectWorkspaceLayout.tsx) | Có | Quyết định theo phản hồi server, an toàn với deep link |
| [RequireProjectManagePermission](../../apps/web/src/features/projects/routes/RequireProjectManagePermission.tsx#L13) | Có, giữ nguyên | Chỉ Leader; Teacher bị chặn Settings đúng ý |
| [lib/permissions.ts](../../apps/web/src/lib/permissions.ts#L19) | Phải mở rộng | `ProjectPermissionContext.role: TeamRole \| null`; `canViewProject` = `role !== null` nên Teacher luôn bị từ chối |
| [my-work/permissions.ts](../../apps/web/src/features/my-work/permissions.ts#L30) | Không dùng cho Teacher | `ROLE_PERMISSIONS` chỉ có `member`/`leader`; `task:comment` gắn với Member |
| `ProjectWorkspace.myRole: TeamRole` | Phải mở rộng | Bắt buộc, không thể biểu diễn người xem không thuộc nhóm ([types.ts:80](../../apps/web/src/features/projects/types.ts#L80)) |
| [AppSidebar](../../apps/web/src/components/navigation/AppSidebar.tsx) (HEAD `c9df96b`, dòng 99), [TopNavigation](../../apps/web/src/components/navigation/TopNavigation.tsx#L25) | Không dùng nguyên | Cả hai gọi `useMyWorkOverview()` (endpoint sinh viên); sidebar có "Môn học", "Dự án", "Điểm danh QR"; top bar có "Tạo task mới" |

### 2.3 Workspace dùng chung — Một phần

- Board chỉ hiển thị issue của Sprint `active`; không có Sprint thì hiện "Chưa
  có Sprint đang chạy… liên hệ Trưởng nhóm"
  ([ProjectBoardRoute.tsx:365](../../apps/web/src/features/projects/routes/ProjectBoardRoute.tsx#L365),
  [:390](../../apps/web/src/features/projects/routes/ProjectBoardRoute.tsx#L390)).
  Nhóm chỉ dùng Kanban chưa xem được trên Board.
- Board không có kéo-thả; select trạng thái trong IssuePanel bị vô hiệu hóa.
- IssuePanel chỉ **hiển thị** comment
  ([IssuePanel.tsx:435](../../apps/web/src/features/projects/components/IssuePanel.tsx#L435));
  không có composer, API wrapper hay mutation comment.
- Checkbox subtask bật cho mọi người xem và chỉ đổi state cục bộ
  ([IssuePanel.tsx:130](../../apps/web/src/features/projects/components/IssuePanel.tsx#L130)):
  trông như thao tác ghi nhưng không lưu.
- Breadcrumb workspace luôn trỏ `/projects`
  ([ProjectWorkspaceLayout.tsx:119](../../apps/web/src/features/projects/routes/ProjectWorkspaceLayout.tsx#L119));
  `ProjectWorkspace` không có `courseId`/`teamId`, nên không dựng được đường
  quay về lớp/nhóm từ dữ liệu khi mở deep link.
- `Issue` không có hạn chót, trạng thái blocked hay cờ archived
  ([types.ts:43](../../apps/web/src/features/projects/types.ts#L43)); `MyTask`
  có `dueAt` nhưng chỉ cho việc của chính sinh viên. `ProjectCode` không có thời
  điểm đồng bộ gần nhất ([types.ts:171](../../apps/web/src/features/projects/types.ts#L171)).

### 2.4 API client, query key và cache — Một phần

- Mọi wrapper đi qua `/api/work/api/v1/...`, kể cả course
  ([studentFlow.ts](../../apps/web/src/lib/api/studentFlow.ts)). Theo kiến trúc,
  lớp/nhóm thuộc Classroom Service (gateway `/api/classroom/`); đường hiện tại
  chỉ là đường demo, chưa có hợp đồng.
- Client luôn `JSON.stringify` body và đặt `Content-Type: application/json`
  ([client.ts:88](../../apps/web/src/lib/api/client.ts#L88)): chưa gửi được
  `multipart/form-data` cho import file.
- Query key không gắn danh tính: `["courses", id]`, `["projects"]`,
  `["my-work","overview"]`
  ([studentFlowHooks.ts:23](../../apps/web/src/lib/query/studentFlowHooks.ts#L23),
  [queries.ts:8](../../apps/web/src/features/my-work/queries.ts#L8)). Cache
  được xóa khi logout/401/khôi phục thất bại
  ([AuthProvider.tsx:74-78](../../apps/web/src/features/auth/AuthProvider.tsx) (HEAD `c9df96b`, dòng 74–78));
  `login()` không xóa cache
  ([AuthProvider.tsx:120](../../apps/web/src/features/auth/AuthProvider.tsx) (HEAD `c9df96b`, dòng 120)).

### 2.5 Mock — Demo MSW, chỉ có quan hệ sinh viên

- Graph quan hệ [relationships.ts](../../apps/web/src/mocks/data/relationships.ts)
  có enrollment theo user (dòng 28), team assignment (35), pending (45),
  team → project (50). **Không có**: giảng viên phụ trách lớp, team → lớp,
  danh sách sinh viên của lớp.
- `GET /courses` luôn trả `courses: []`
  ([handlers/studentFlow.ts:82](../../apps/web/src/mocks/handlers/studentFlow.ts) (HEAD `c9df96b`, dòng 82)).
- Guard mock chỉ theo enrollment/membership
  ([:96](../../apps/web/src/mocks/handlers/studentFlow.ts) (HEAD `c9df96b`, dòng 96),
  [:279](../../apps/web/src/mocks/handlers/studentFlow.ts) (HEAD `c9df96b`, dòng 279)).

## 3. Rủi ro lộ dữ liệu và lệch fixture đã phát hiện

| # | Vấn đề | Bằng chứng | Hệ quả khi thêm Teacher |
| --- | --- | --- | --- |
| R1 | Workspace mock fallback `myRole … ?? "member"` | [studentFlow.ts:645](../../apps/web/src/mocks/data/studentFlow.ts) (HEAD `c9df96b`, dòng 645), [:671](../../apps/web/src/mocks/data/studentFlow.ts) (HEAD `c9df96b`, dòng 671) | Nếu chỉ nới guard handler, Teacher nhận quyền Member (cập nhật task được giao, link git) |
| R2 | Handler trả 404 trước khi kiểm tra quyền | [handlers/studentFlow.ts:91-99](../../apps/web/src/mocks/handlers/studentFlow.ts) (HEAD `c9df96b`, dòng 91–99), [:275-282](../../apps/web/src/mocks/handlers/studentFlow.ts) (HEAD `c9df96b`, dòng 275–282) | Người ngoài quyền phân biệt được lớp/project có tồn tại hay không |
| R3 | Thông báo cấp lớp (`team-hub`, `team-formation`, `join-request`, `course-deadline`) trả cho **mọi** user | [handlers/studentFlow.ts:335](../../apps/web/src/mocks/handlers/studentFlow.ts) (HEAD `c9df96b`, dòng 335) | Teacher và sinh viên lớp khác thấy thông báo SE330 |
| R4 | Hoạt động GitHub Home giống nhau cho mọi user | [handlers/myWork.ts:84](../../apps/web/src/mocks/handlers/myWork.ts#L84) | Không dùng làm nguồn "hoạt động gần nhất" cho Teacher |
| R5 | `isMine`, `isMe` tĩnh | [studentFlow.ts:625](../../apps/web/src/mocks/data/studentFlow.ts) (HEAD `c9df96b`, dòng 625), [:678](../../apps/web/src/mocks/data/studentFlow.ts) (HEAD `c9df96b`, dòng 678), [:804](../../apps/web/src/mocks/data/studentFlow.ts) (HEAD `c9df96b`, dòng 804) | Teacher thấy task "của tôi" và contributor "Bạn" sai |
| R6 | Ba danh sách NEXUS khác nhau: roster lớp 5 người gồm SV01 là Leader thứ hai ([:42](../../apps/web/src/mocks/data/studentFlow.ts) (HEAD `c9df96b`, dòng 42)); assignee 4 người không có SV01 ([:552](../../apps/web/src/mocks/data/studentFlow.ts) (HEAD `c9df96b`, dòng 552)); contributor 4 người không có SV01 | — | Dashboard nhóm và workspace lệch nhau về thành viên |
| R7 | Graph cho `leader@utask.test` là Member DELI ([relationships.ts:37](../../apps/web/src/mocks/data/relationships.ts) (HEAD `c9df96b`, dòng 37)) nhưng không có trong roster DELI ([studentFlow.ts:90](../../apps/web/src/mocks/data/studentFlow.ts) (HEAD `c9df96b`, dòng 90)) | — | Danh sách sinh viên/nhóm của Teacher sẽ mâu thuẫn với Student |
| R8 | `classSize` hardcode (45/40/42) | [studentFlow.ts:147](../../apps/web/src/mocks/data/studentFlow.ts) (HEAD `c9df96b`, dòng 147) | Không khớp số sinh viên Teacher đếm được từ graph |
| R9 | Tên team hardcode theo id | [myWork.ts:374](../../apps/web/src/mocks/data/myWork.ts) (HEAD `c9df96b`, dòng 374) | Thêm team mới sẽ hiển thị sai tên |
| R10 | Code chỉ có cho NEXUS; DELI trả 404 "Không tìm thấy dự án" | [studentFlow.ts:780](../../apps/web/src/mocks/data/studentFlow.ts) (HEAD `c9df96b`, dòng 780) | Không phân biệt "chưa có repository" với "không tồn tại" |
| R11 | Thời gian workspace/code tính từ `new Date()` | [studentFlow.ts:689](../../apps/web/src/mocks/data/studentFlow.ts) (HEAD `c9df96b`, dòng 689), [:705](../../apps/web/src/mocks/data/studentFlow.ts) (HEAD `c9df96b`, dòng 705) | "Hoạt động gần nhất" luôn trông mới; quá hạn khó kiểm thử ổn định |
| R12 | Checkbox subtask đổi state cục bộ | [IssuePanel.tsx:130](../../apps/web/src/features/projects/components/IssuePanel.tsx#L130) | Teacher thấy có thể "hoàn thành" subtask dù không có quyền |

Khác biệt code ↔ analysis (ghi nhận, **không** sửa trong Teacher Flow): luồng
duyệt đề tài (`TopicStatus`), mock "phân nhóm ngẫu nhiên"
([studentFlow.ts:882](../../apps/web/src/mocks/data/studentFlow.ts) (HEAD `c9df96b`, dòng 882)), và
câu "để giảng viên chấm điểm công bằng"
([SettingsIntegrationsPage.tsx:54](../../apps/web/src/features/notifications/components/SettingsIntegrationsPage.tsx#L54))
trái với US-5.3/§8.5 (không đánh giá đóng góp từ số commit).

## 4. Phạm vi

| Đợt | Phạm vi | Ghi chú |
| --- | --- | --- |
| P0 | Home giảng viên, danh sách lớp phụ trách, tổng quan lớp, sinh viên, nhóm, dashboard nhóm, xem workspace (Backlog/Board/Code/issue) | Luồng đọc hoàn chỉnh, đúng quyền, chạy trên mock |
| P0 | Form tạo lớp, xem/sao chép mã tham gia, thêm từng sinh viên, import (preview) | UI và validation đầy đủ; bước ghi bị vô hiệu hóa kèm lý do đến khi có contract |
| P0 dùng chung | Xem comment task | Gửi comment chờ contract (§8) |
| P1 | Tạo/điều chỉnh nhóm, chuyển thành viên, chỉ định Leader (US-2.5) | Chờ policy và contract |
| P1 | Phản hồi cấp project, tổng hợp rủi ro có nguồn (US-4.5, US-5.7) | Chờ contract Project/Progress |
| Ngoài phạm vi | Duyệt đề tài, chấm điểm, điểm danh, tự phân nhóm ngẫu nhiên, LMS, template lớp, xóa lớp, khóa tài khoản toàn hệ thống, Admin | Không có trong analysis hoặc thuộc vai trò khác |

Teacher **không** được: tạo/sửa/gán task, đổi trạng thái/priority/deadline,
quản lý Sprint, cấu hình repository/BYOK, yêu cầu AI phân rã, phê duyệt backlog
AI, đổi trạng thái subtask. "Quản trị tài khoản và tích hợp — Có với lớp phụ
trách" (analysis §2.2) chưa có đặc tả hành động: mặc định chỉ gồm các thao tác
đã liệt kê ở bảng trên.

## 5. Sitemap, luồng và bố cục

### 5.1 Route đề xuất (frontend, không phải endpoint)

| Route | Màn | Đợt |
| --- | --- | --- |
| `/teacher` | T01 Home giảng viên | P0 |
| `/teacher/courses` | T02 Danh sách lớp phụ trách | P0 |
| `/teacher/courses/new` | T03 Tạo lớp | P0 (ghi chờ contract) |
| `/teacher/courses/:courseId` | T04 Tổng quan lớp | P0 |
| `/teacher/courses/:courseId/students` | T05 Sinh viên | P0 |
| `/teacher/courses/:courseId/students/import` | T06 Nhập danh sách | P0 (ghi chờ contract) |
| `/teacher/courses/:courseId/teams` | T07 Nhóm + sinh viên chưa có nhóm | P0 xem, P1 điều chỉnh |
| `/teacher/courses/:courseId/oversight` | Giám sát tiến độ nhóm (xem §14; thêm sau Phase 1) | Đã triển khai (Demo MSW, chỉ đọc) |
| `/teacher/courses/:courseId/teams/:teamId` | T08 Dashboard nhóm | Đã triển khai (Demo MSW, chỉ đọc; §15) |
| `/teacher/courses/:courseId/settings` | T10 Cài đặt lớp | P0 xem |
| `/projects/:projectId/{backlog,board,code}` | T09 Workspace dùng chung | Đã triển khai chế độ chỉ xem cho giảng viên (Demo MSW; §15) |
| `/notifications`, `/settings/*` | Màn dùng chung | Sau khi sửa R3 |

Dùng `courseId` thay vì `classId` (lý do ở §7). Filter (học kỳ, tìm kiếm, có/chưa
có nhóm) lưu trên query string để back/refresh giữ trạng thái. Breadcrumb và
liên kết quay lại dựng từ dữ liệu phản hồi, không từ navigation state.

Điểm vào: sau đăng nhập, `returnTo` hợp lệ luôn được ưu tiên. Nếu không có,
tài khoản có capability Teacher và không có enrollment sinh viên về `/teacher`;
còn lại giữ `/my-work`. Tài khoản vừa là sinh viên vừa là Teacher: sidebar có
mục "Không gian giảng viên"; không có bộ chuyển vai trò tự cấp quyền.

### 5.2 Luồng chính

```text
Đăng nhập → /teacher → lớp phụ trách → Sinh viên | Nhóm → dashboard nhóm
  → /projects/:id/board?issue=KEY → xem task, PR/commit → comment (khi có contract)
```

Mỗi bước có thể mở trực tiếp bằng URL; quyền được kiểm tra lại ở mỗi route theo
phản hồi server/MSW, không theo việc đã đi qua sidebar.

### 5.3 Bố cục từng màn (đề xuất, chưa có asset thiết kế)

Khung chung: tái sử dụng `AuthenticatedLayout` (sidebar desktop, drawer mobile tự
đóng khi đổi route), [PageHeader](../../apps/web/src/components/layout/PageHeader.tsx),
[Breadcrumbs](../../apps/web/src/components/navigation/Breadcrumbs.tsx),
`components/ui/*`. Sidebar Teacher là nội dung riêng trong cùng khung: Trang chủ,
Lớp phụ trách, Thông báo, Cài đặt tài khoản; dưới là danh sách lớp phụ trách. Không
có "Môn học", "Dự án", "Điểm danh QR", "Tạo task mới".

Mọi màn có query đều có: loading (`PageSkeleton`/skeleton theo section), empty
(`EmptyState`), error + thử lại (`ErrorState`), forbidden (`ForbiddenPage`), không
tìm thấy. Lớp ngoài quyền và lớp không tồn tại hiển thị cùng một trạng thái để
không lộ sự tồn tại (khớp cách xử lý R2).

| Màn | Bố cục chính | CTA | Trạng thái riêng | Responsive |
| --- | --- | --- | --- | --- |
| T01 Home | Header "Bàn làm việc giảng viên" + bộ lọc học kỳ; hàng chỉ số (lớp phụ trách, nhóm, sinh viên chưa có nhóm, nhóm cần chú ý); lưới thẻ lớp (tên, mã môn, học kỳ, số SV/nhóm, chưa có nhóm, hoạt động gần nhất có thời điểm) | Tạo lớp (disabled kèm lý do đến khi có contract) | Chưa có lớp; chỉ số thiếu dữ liệu hiển thị "Chưa có dữ liệu" | Chỉ số 4 → 2 → 1 cột |
| T02 Danh sách lớp | Tìm kiếm tên/mã + lọc học kỳ; bảng (desktop) / card (mobile) | Mở lớp; Tạo lớp | Không có kết quả lọc khác với chưa có lớp | Bảng cuộn trong vùng riêng |
| T03 Tạo lớp | Form: tên lớp, mã môn (tùy chọn), học kỳ, ngày bắt đầu/kết thúc, giới hạn thành viên nhóm min/max | Hủy; Tạo lớp | Validation min ≤ max, kết thúc ≥ bắt đầu; lỗi field cạnh field, lỗi chung đầu form; submit disabled + lý do khi chưa có contract; rời trang khi form đã sửa phải xác nhận | Một cột |
| T04 Tổng quan lớp | Header tên lớp, học kỳ, giảng viên phụ trách, mã tham gia (sao chép); tabs có route riêng: Tổng quan / Sinh viên / Nhóm / Cài đặt; bảng nhóm: tên, Leader, sĩ số, project, tiến độ, cập nhật gần nhất | Mở nhóm; mở workspace | Nhóm chưa có project hiện "Chưa có project" (không gán lý do); clipboard lỗi không báo thành công | Tabs cuộn ngang; bảng → card |
| T05 Sinh viên | Lọc tên/email/MSSV, có/chưa có nhóm; bảng MSSV, tên, email, nhóm, vai trò trong nhóm của lớp này | Thêm sinh viên (dialog), Nhập danh sách | Lớp rỗng; trạng thái kích hoạt chỉ hiện khi nguồn có | Bảng → card |
| T06 Import | 3 bước: Chọn file → Kiểm tra định dạng (client) → Kết quả; bảng preview theo `row_number` | Xác nhận nhập (disabled đến khi có contract) | File sai định dạng, thiếu cột, trùng trong file; ghi rõ đối chiếu tài khoản xảy ra ở backend; không hiện mật khẩu/link kích hoạt | Bảng cuộn ngang |
| T07 Nhóm | Hai tab: Danh sách nhóm / Sinh viên chưa có nhóm; card nhóm: tên, Leader, sĩ số/giới hạn, project | P1: tạo nhóm, phân/chuyển thành viên, chỉ định Leader | Không có nhóm; nhóm thiếu thành viên | Card một cột |
| T08 Dashboard nhóm | Header nhóm, lớp, Leader; khối project (tên, repository); khối tiến độ (đếm issue theo trạng thái, Sprint active nếu có); thành viên + vai trò; khối GitHub (repository, trạng thái đồng bộ) | Mở workspace (khi có project) | Mỗi khối có lỗi/thời điểm riêng; GitHub lỗi không làm mất khối task; không xếp hạng thành viên | Khối xếp dọc |
| T09 Workspace | Dùng `ProjectWorkspaceLayout`, Backlog, Board, Code, IssuePanel; breadcrumb Lớp → Nhóm → Project | Tìm/lọc, mở issue, (comment khi có contract) | Ẩn: tạo Epic/issue, AI, đổi assignee/trạng thái, hoàn thành Sprint, subtask checkbox, tab Settings; Board không Sprint: dẫn sang Backlog với lời giải thích dành cho Teacher | Issue panel full-width trên mobile |
| T10 Cài đặt lớp | Thông tin lớp, giới hạn nhóm, mã tham gia và trạng thái mã | Đổi/vô hiệu mã (disabled, có xác nhận khi bật) | Không có xóa lớp, GitHub, API key | Một cột |

Accessibility: nút icon có tên truy cập, focus trả về nơi mở sau khi đóng
dialog/panel, tín hiệu rủi ro luôn kèm chữ và nguyên nhân, không có thao tác chỉ
dùng hover.

## 6. Ma trận quyền theo tài nguyên

Nguyên tắc: hai lớp kiểm tra tách biệt.

1. **Capability không gian giảng viên**: tài khoản có role toàn cục `TEACHER`
   (từ Identity). Chỉ quyết định hiển thị khu `/teacher`; **không** cấp quyền
   trên bất kỳ lớp hay project nào.
2. **Quyền theo tài nguyên**: lấy từ assignment giảng viên–lớp (Classroom) và
   viewer context của project (Project Service). Frontend chỉ ẩn/vô hiệu hóa;
   backend thật là nơi quyết định cuối.

| Tài nguyên / hành động | Teacher phụ trách lớp | Teacher khác | Leader | Member | Nguồn |
| --- | --- | --- | --- | --- | --- |
| Khu `/teacher` | Có | Có (chỉ thấy lớp của mình) | Không (trừ khi có role TEACHER) | Không | US-1.1 |
| Xem lớp, sinh viên, nhóm | Có | Không | Lớp mình học | Lớp mình học | §1.3, US-4.4 |
| Tạo lớp | Có điều kiện (capability; chờ contract) | — | Không | Không | US-1.2 |
| Đổi/vô hiệu mã tham gia | Có (chờ contract) | Không | Không | Không | US-1.2 |
| Thêm/import sinh viên | Có (chờ contract) | Không | Không | Không | US-1.4 |
| Tạo nhóm, phân/chuyển thành viên, chỉ định Leader | P1, chờ contract | Không | Mời/kick trong nhóm mình | Không | US-2.5, US-2.3 |
| Xem project, Backlog, Board, Sprint, issue | Chỉ xem | Không | Có | Có | §2.2 |
| Tạo/sửa/gán task, đổi trạng thái/priority/deadline, subtask | Không | Không | Có | Task được giao | §2.2 |
| Quản lý Sprint | Chỉ xem | Không | Có | Chỉ xem | §2.2 |
| Comment task | Có (gửi chờ contract) | Không | Có | Có | §2.2, US-4.5 |
| Phản hồi cấp project | P1, chờ contract | Không | — | — | US-4.5 |
| Xem GitHub/PR/commit | Chỉ xem | Không | Có | Có | US-5.3 |
| Kết nối repository, BYOK, Settings project | Không | Không | Có | Không | US-5.1 |
| AI phân rã/đề xuất/phê duyệt backlog | Không | Không | Có | Không (xem §11) | §2.2 |
| Xem cảnh báo rủi ro | P1 | Không | Có | Trong nhóm | US-5.7 |

Mô hình frontend đề xuất (tạm, chờ contract):

```ts
// Không thêm "teacher" vào TeamRole; không tạo role toàn cục Leader/Member.
type ProjectViewer =
  | { kind: "team-member"; role: TeamRole }
  | { kind: "course-instructor"; courseId: string };
```

- `lib/permissions.ts` nhận `ProjectViewer`; mỗi helper liệt kê rõ kind được
  phép. Thêm `canCommentOnTask(viewer)` tách khỏi `ROLE_PERMISSIONS`.
- `ProjectWorkspace` thêm `viewer: ProjectViewer`, `courseId`, `teamId`. Giữ
  `myRole` trong giai đoạn chuyển tiếp để không phá Student Flow; Teacher nhận
  `myRole` vắng mặt, không nhận giá trị mặc định.
- `AuthUser` thêm `roles: ("STUDENT" | "TEACHER" | "SYSTEM_ADMIN")[]` theo
  serializer Identity đã thấy; helper `canUseTeacherSpace(user)`. Không đọc
  `capabilities` cho quyền lớp.

## 7. Mapping môn/lớp và tương thích Student Flow

Bằng chứng:

| Nguồn | `courseId`/Course mang nghĩa | Trạng thái |
| --- | --- | --- |
| Frontend `CourseEnrollment`, `CourseDetail` ([my-work/types.ts:27](../../apps/web/src/features/my-work/types.ts#L27), [courses/types.ts:59](../../apps/web/src/features/courses/types.ts#L59)) | Có học kỳ, giảng viên, cấu hình thành lập nhóm, sĩ số lớp, giới hạn nhóm → **lớp mở trong học kỳ**; `courseCode` (SE330) là mã môn | Đã triển khai (UI + mock) |
| Fixture | Mỗi mã môn chỉ có một `course-*`, cùng học kỳ HK1 2026–2027 | Không có ca hai lớp cùng môn để phân biệt |
| `docs/classroom-service/README.md` (HEAD) | Liệt kê riêng "môn học, lớp" | Thiết kế mục tiêu |
| `origin/feat/classroom-service:docs/classroom-service/data-model.md` | Chỉ một tầng `Course` có `term`, `join_code`, `max_group_members`, `starts_on/ends_on`, `course_instructors.is_owner` → Course = lớp mở | Thiết kế mục tiêu, cần review, chưa merge |
| `origin/main` Identity spec §3.5.1 | Endpoint import dùng `classrooms/{classroom_id}` | Mô tả hợp đồng phía Identity; Classroom chưa triển khai |

Kết luận: ở frontend, `courseId` **đại diện lớp mở trong học kỳ** (đơn vị Teacher
quản lý). Tên phía backend (Course / Class / Classroom) **Chưa xác minh**.

Quyết định tạm (ít ảnh hưởng nhất):

- Không thêm `classId`. Teacher dùng chung `courseId` với Student, route
  `/teacher/courses/:courseId`. Nhãn giao diện: "Lớp"; mã môn hiển thị từ
  `courseCode`.
- Thêm fixture lớp thứ hai cùng mã môn (ví dụ `course-se330-n2`) để kiểm thử
  rằng mọi thứ khóa theo `courseId`, không theo `courseCode`.
- Khi backend chốt tên, chỉ adapter API đổi trường (`classroom_id` → `courseId`);
  không đổi route Student. Nếu backend tách Môn và Lớp, `courseId` frontend
  ánh xạ sang ID lớp; mã/tên môn là thuộc tính hiển thị.

## 8. Ma trận API readiness

Cột: **Contract** = hợp đồng đã chốt; **Backend** = mã service; **FE** = wrapper
trong `apps/web`; **MSW** = handler demo. Kết luận: *Dùng ngay* / *Mở rộng FE* /
*Chỉ UI hoặc mock đọc* / *Chờ contract*.

| Thao tác | Contract | Backend | FE | MSW | Kết luận |
| --- | --- | --- | --- | --- | --- |
| Đăng nhập + nhận diện TEACHER | Identity spec (`origin/main`): `roles` trong user | Một phần (`origin/main`), ngoài HEAD | `loginRequest` có nhưng lệch shape (§2.1) | Không có tài khoản Teacher | Mở rộng FE (mock `roles`); tích hợp thật chờ adapter auth |
| Danh sách lớp phụ trách | Không | Không | Không | `GET /courses` trả rỗng | Chỉ mock đọc |
| Tổng quan/dashboard lớp (US-4.4) | Không | Không (Classroom/Progress) | Không | Không | Chỉ mock đọc, nhãn demo |
| Danh sách sinh viên/nhóm của lớp | Không | Không | Không | Không | Chỉ mock đọc |
| Tạo lớp (US-1.2) | Không (chỉ "hàm nghiệp vụ mục tiêu" ở nhánh feature) | Không | Không | Không | Chờ contract; UI + validation |
| Xem mã tham gia | Không | Không | Không | Không | Chỉ mock đọc |
| Đổi/vô hiệu mã | Không | Không | Không | Không | Chờ contract |
| Sửa thông tin lớp | Không (không suy ra từ tạo lớp) | Không | Không | Không | Chờ contract |
| Thêm từng sinh viên | Không | Không | Không | Không | Chờ contract |
| Import CSV/XLSX (US-1.4) | Mô tả trong Identity spec §3.5.1: `POST …/classrooms/{id}/students/import`, multipart, `Idempotency-Key`, `summary` + `results[]`; Classroom là chủ sở hữu nhưng chưa có hợp đồng của chính Classroom | Identity provisioning nội bộ có (`origin/main`, không gọi được từ trình duyệt); Classroom không | Không; client chưa gửi được multipart | Không | Chỉ UI preview; ghi chờ Classroom xác nhận contract |
| Gửi lại email kích hoạt | Chỉ API nội bộ Identity; endpoint Classroom công khai chưa có | Identity nội bộ có | Không | Không | Chờ contract |
| Điều chỉnh nhóm (US-2.5, P1) | Không | Không | Không | Không | Chờ contract + policy |
| Xem workspace/Backlog/Board | Không (Project Service) | Không | Có (`projectWorkspaceRequest`) | Có, chỉ cho member | Mở rộng FE + MSW (viewer context) |
| Xem issue, history, comment | Không | Không | Có (`issueDetailRequest`) | Có, chỉ cho member | Mở rộng FE + MSW |
| Xem Code/GitHub | Không (Integration Service sở hữu GitHub) | Không | Có (`projectCodeRequest`, đi qua `/api/work`) | Chỉ NEXUS | Mở rộng MSW; đường gọi chờ contract |
| Gửi comment task | Không | Không | Không | Không | Chờ contract; P0 chỉ hiển thị |
| Phản hồi cấp project (P1) | Không | Không | Không | Không | Chờ contract |
| Tổng hợp rủi ro (US-5.7, P1) | Không (Progress); AI contract `designed-not-implemented` ở nhánh feature | Không | Không | Không | Chỉ mock đọc ở P1; Teacher không kích hoạt AI |
| Thông báo | Không | Không | Có | Có, nhưng lộ phạm vi (R3) | Sửa scope mock trước khi Teacher dùng |

Hiện **không có thao tác Teacher nào "Dùng ngay"**. Không đưa schema demo vào
`contracts/`. Shape MSW Teacher được mô tả ở §9 và chỉ là demo.

## 9. Kế hoạch mock dùng chung

> Đây là kế hoạch của Phase 0. Phần đã làm và các điểm khác kế hoạch: [§13](#13-kết-quả-phase-1).

### 9.1 Mở rộng graph quan hệ

Mở rộng [relationships.ts](../../apps/web/src/mocks/data/relationships.ts), không
tạo bộ fixture Teacher riêng:

| Bảng mới | Ý nghĩa | Nguồn dẫn xuất |
| --- | --- | --- |
| `MOCK_COURSE_INSTRUCTORS: courseId → { userId, isOwner }[]` | Teacher phụ trách lớp | Dùng cho guard Teacher và hiển thị giảng viên |
| `MOCK_TEAM_COURSES: teamId → courseId` | Nhóm thuộc lớp nào | Hiện chỉ ngầm qua key assignment |
| `MOCK_COURSE_STUDENTS: courseId → userId[]` | Danh sách sinh viên của lớp (gồm cả người không đăng nhập demo) | `enrolledCoursesFor` dẫn xuất từ bảng này để Student và Teacher dùng chung |
| `MOCK_TEAM_MEMBERS: teamId → { userId, role }[]` | Một nguồn roster | Roster lớp, assignee, contributor đều tra từ đây |

Helper mới: `coursesTaughtBy(userId)`, `isInstructorOf(userId, courseId)`,
`projectViewerFor(userId, projectId)` (trả `team-member` hoặc
`course-instructor` qua team → course → instructor, hoặc `null`). Handler
workspace/issue/code dùng `projectViewerFor`; bỏ fallback `?? "member"` (R1).
Settings vẫn chỉ Leader. **Phase 1 chưa làm `projectViewerFor`** (Teacher chưa mở
project), xem §13.5.

### 9.2 Fixture

| Case | Fixture đề xuất |
| --- | --- |
| Teacher phụ trách nhiều lớp | `teacher@utask.test` (TS. Trần Minh Đức, khớp `instructorName` SE330): owner SE330, đồng phụ trách IT3090 |
| Lớp ngoài quyền | CS402, SE331 (giảng viên khác) → 404, cùng phản hồi với lớp không tồn tại, cho `teacher@utask.test` |
| Hai Teacher tách biệt | `teacher2@utask.test` (ThS. Lê Thị Mai) owner CS402 |
| Lớp rỗng | `course-se330-n2`: cùng mã SE330, 0 sinh viên, 0 nhóm |
| Sinh viên chưa có nhóm | SV01 ở IT3090 (đã có) |
| Nhóm chưa có project | Nhóm IT3090 (`team-iot-vision`, `team-iot-sense`) đưa vào graph với một Leader, không có project |
| Một Student nhiều lớp | SV01 xuất hiện ở SE330 (Leader), IT3090 (chưa có nhóm) dưới góc nhìn Teacher, khớp Home của SV01 |
| GitHub lỗi/cũ/chưa ánh xạ | NEXUS dùng scenario sẵn có (`webhook-error`, `token-expired`, `disconnected`); thêm contributor `githubUsername: null`; DELI "chưa có repository" thay vì 404 (R10) |
| Leader duy nhất (cho P1) | Một nhóm IT3090 có đúng một Leader. NEXUS giữ hai Leader như giản lược đã ghi ở [student-flow.md](student-flow.md), không dùng để kiểm thử chuyển Leader |

Nhất quán cần sửa khi mở rộng (không refactor ngoài mục tiêu): `isMine`/`isMe`
tính theo người xem (R5; Teacher luôn `false`), roster NEXUS/DELI thống nhất
(R6, R7), `classSize` và tên team dẫn xuất từ graph (R8, R9), thông báo cấp lớp
lọc theo enrollment hoặc assignment (R3), kiểm tra quyền trước khi tra tồn tại
(R2), thời gian fixture Teacher theo `ANCHOR_DATE` và hàm tính quá hạn nhận `now`
(R11). Sửa R6–R8 làm thay đổi dữ liệu Student; mỗi sửa phải chạy lại
`MultiMembershipAccess` và `StudentFlowRegression`.

Mock chỉ đọc cho Teacher (handler mới, đường demo chưa có hợp đồng):
`GET …/teacher/courses`, `GET …/teacher/courses/:courseId` (kèm students, teams,
chỉ số). Không có handler ghi Teacher cho đến khi contract tương ứng có; khi có,
handler phải cập nhật graph dùng chung và gắn nhãn demo.

### 9.3 Quy tắc số liệu

| Chỉ số | Công thức | Thiếu dữ liệu |
| --- | --- | --- |
| Tiến độ nhóm | Có Sprint `active` và `totalPoints > 0`: `completedPoints / totalPoints` (cùng công thức [CourseSprintCard](../../apps/web/src/features/my-work/components/CourseSprintCard.tsx#L23-L26); card này hiện hiển thị 0% khi `totalPoints = 0`, Teacher thì không). Không có Sprint: số issue `done` / tổng issue của project, ghi rõ "theo số issue". Không tính subtask (subtask không nằm trong danh sách issue) | Mẫu số 0 → "Chưa có task", không phải 0% |
| Task quá hạn | Có `dueAt`, `dueAt < now`, trạng thái ≠ `done` (như `taskFilters` hiện tại) | `Issue` chưa có `dueAt` → "Chưa có dữ liệu hạn chót". Đề xuất thêm `dueAt?: string \| null` vào `Issue` (tùy chọn, không phá Student) |
| Blocked | Chưa có trong `IssueStatus` | Không hiển thị cho đến khi contract có |
| Hoạt động gần nhất | Giá trị lớn nhất của `issue.updatedAt`, `comment.createdAt`, `commit.committedAt`; luôn kèm loại hoạt động và thời điểm | "Chưa ghi nhận hoạt động"; không dùng R4 |
| Đồng bộ GitHub | `syncState` hiện có | Không có `lastSyncedAt` → "Chưa rõ thời điểm đồng bộ"; không quy thành "không đóng góp" |

Archived và timezone: `Issue` chưa có cờ archived; so sánh thời gian bằng
timestamp ISO UTC, hiển thị theo giờ trình duyệt. Cần chốt lại khi có contract
Project/Progress.

### 9.4 Case kiểm thử

- `teacher@utask.test` xem SE330, IT3090; mở CS402 bằng URL → "Không tìm thấy lớp
  học", cùng trạng thái với lớp không tồn tại. (Việc mở project NEXUS/DELI bằng
  tư cách Teacher thuộc Phase 2; Phase 1 chặn hoàn toàn.)
- Teacher mở workspace: không thấy tạo Epic/issue, AI, Settings, checkbox subtask;
  gọi trực tiếp `GET …/settings` → 403; `myRole` không bị gán `member`.
- Student account mở `/teacher/...` → forbidden, không vòng lặp redirect.
- SV01 thấy cùng nhóm/vai trò ở Home Student và ở danh sách của Teacher.
- Lớp rỗng và lớp cùng mã môn khác `courseId` không trộn dữ liệu.
- Deep link `/projects/project-nexus/board?issue=NEXUS-104` dưới Teacher: breadcrumb
  về đúng lớp/nhóm; refresh giữ filter.
- Thiếu dữ liệu: zero task không chia 0; task done không quá hạn; GitHub lỗi không
  ẩn khối task; contributor chưa ánh xạ hiện "chưa xác định".
- Logout Teacher → đăng nhập Student: không còn dữ liệu Teacher trong cache.
- Thông báo cấp lớp không hiển thị cho người ngoài lớp (R3).
- Toàn bộ test Student hiện có vẫn qua.

## 10. Các phase tiếp theo

Mỗi phase dừng lại để review; không tự sang phase sau. Commit nhỏ theo phần có
thể review, trên checkout hiện tại.

### Phase 1 — Nền quyền, graph dùng chung, shell đọc lớp (Đã triển khai, Demo MSW)

Phạm vi: §9.1 (instructors, team → course, course students, team members), tài
khoản Teacher, `roles` trong `AuthUser` mock, `canUseTeacherSpace`, sửa R2/R3,
layout Teacher (sidebar/top bar riêng trong cùng khung), T01, T02, T04, T05, T07
(chỉ xem), forbidden/empty/error.

Hoàn tất khi: Teacher vào lớp phụ trách bằng sidebar và URL; lớp ngoài quyền bị
chặn ở UI và MSW; Student Flow không đổi hành vi (test hiện có qua); lint, test,
build đạt. **Kết quả, cách thử và giới hạn: [§13](#13-kết-quả-phase-1).**

Commit đề xuất (theo thứ tự phụ thuộc):

1. `feat(web): derive student and teacher mock data from one relationship graph`
2. `feat(web): scope mock access and notifications by enrollment or assignment`
3. `feat(web): add teacher role helper, route guard and sign-in landing`
4. `feat(web): add teacher space layout and read-only class views`

Danh sách file của từng commit nằm trong báo cáo cuối của Phase 1.

### Phase 2 — Nhóm đến workspace (Đã triển khai, Demo MSW; kết quả ở [§15](#15-kết-quả-phase-2--từ-nhóm-đến-workspace-chỉ-xem))

Phạm vi: `ProjectViewer`, `courseId`/`teamId` trong workspace, bỏ fallback R1,
`isMine`/`isMe` theo người xem (R5), roster thống nhất (R6, R7), T08, breadcrumb
Teacher, ẩn thao tác ghi trong workspace (gồm R12), Board không Sprint dẫn về
Backlog, `dueAt` tùy chọn, trạng thái GitHub "chưa có repository" (R10).

Hoàn tất khi: Home → lớp → nhóm → board → issue/PR đi được và refresh được;
không có thao tác Leader/Member nào gọi được bằng UI hoặc MSW.

Việc chuyển tiếp từ Phase 1 ([§13.6](#136-tình-trạng-r1r12-sau-phase-1)): R1, R5, R6
phần workspace/Code (assignee và contributor chưa gồm Lê Minh Khoa), R10, R11, R12.
Điều kiện trước khi bắt đầu: hợp đồng Project Service cho tư cách người xem là
giảng viên (§12); nếu chưa có, chỉ dựng bằng Demo MSW và ghi rõ.

Commit dự kiến: `feat(web): add project viewer context for course instructors`,
`feat(web): add teacher team dashboard and workspace breadcrumbs`,
`test(web): cover teacher read-only workspace access`.

### Phase 3 — UI tổ chức lớp

Điều kiện bắt đầu ghi: contract tạo lớp, mã tham gia, thêm sinh viên, import
được chốt và có trong `contracts/`. Không cần chờ để làm UI: T03, T06 (preview),
T10, dialog thêm sinh viên với submit disabled kèm lý do; client hỗ trợ `FormData`.

Hoàn tất khi: mỗi nút đúng mức readiness; không fake success; kết quả import
phân biệt tạo mới/có sẵn/trùng/cần kiểm tra/lỗi theo dòng khi contract có.

Commit dự kiến: `feat(web): add teacher course setup and student import forms`.

### Phase 4 — Phản hồi và điều chỉnh nhóm (P1)

Điều kiện: contract comment task/project và mutation membership; policy sĩ số,
Leader thay thế, quyền đọc lịch sử sau chuyển nhóm.

Hoàn tất khi: Teacher comment mà task không đổi; nháp giữ khi gửi lỗi; chuyển
nhóm giữ lịch sử và nhóm luôn có Leader.

### Phase 5 — Rủi ro (P1) và hoàn thiện

Điều kiện: contract Progress cho tín hiệu rule-based có nguồn và thời điểm.

Hoàn tất khi: cảnh báo truy vết được tới dữ liệu nguồn; không có/cũ/mất kết
nối/chưa ánh xạ là trạng thái riêng; không chấm điểm; smoke test desktop/mobile.

## 11. Nhật ký phản biện (devil's advocate)

Tự rà soát, không phải đánh giá độc lập. Mỗi vòng xét lại tài liệu sau khi sửa ở
vòng trước.

| Vòng | Vấn đề | Thay đổi | Lý do giữ quyết định cuối |
| --- | --- | --- | --- |
| 1 Nghiệp vụ | Nhánh Classroom đề xuất template lớp, xóa lớp, "xóa nhóm thì xóa project" | Đưa vào ngoài phạm vi; ghi là vấn đề mở | Không có trong analysis; xóa project mâu thuẫn US-2.5 "không xóa lịch sử" |
| 1 Nghiệp vụ | Analysis cho Teacher "Tạo nhóm: Có" nhưng US-2.5 là Should | Giữ tạo/điều chỉnh nhóm ở P1 | §8.2 xếp US-2.5 vào P1 |
| 1 Nghiệp vụ | "Quản trị tài khoản và tích hợp: Có với lớp phụ trách" có thể bị hiểu rộng | Chỉ giữ thao tác đã liệt kê; gửi lại kích hoạt chờ contract | Chưa có đặc tả hành động; tránh tự thêm quyền |
| 1 Nghiệp vụ | Code Student có duyệt đề tài, phân nhóm ngẫu nhiên, chấm điểm từ commit | Ghi nhận ở §3, không sửa | Ngoài phạm vi Teacher Flow; sửa là việc riêng |
| 2 Quyền/dữ liệu | Nới guard handler sẽ khiến Teacher nhận `myRole: "member"` (R1) | Thêm `ProjectViewer`, bỏ fallback trong Phase 2 | Đây là đường dễ vượt quyền nhất |
| 2 Quyền/dữ liệu | Thêm `"teacher"` vào `TeamRole` cho nhanh | Không làm; dùng union viewer | `TeamRole` là membership nhóm; trộn vào sẽ biến Teacher thành thành viên giả |
| 2 Quyền/dữ liệu | Thông báo cấp lớp và 404/403 làm lộ dữ liệu (R2, R3) | Sửa trong Phase 1, trước khi có tài khoản Teacher | Tài khoản mới sẽ phơi bày lỗi ngay |
| 2 Quyền/dữ liệu | Roster Teacher đọc từ fixture lớp sẽ lệch workspace (R6–R8) | Một nguồn `MOCK_TEAM_MEMBERS`/`MOCK_COURSE_STUDENTS` | Yêu cầu Teacher–Student dùng chung dữ liệu |
| 2 Quyền/dữ liệu | Chuẩn hóa NEXUS về một Leader sẽ phá test Student | Giữ hai Leader (đã ghi là giản lược); test chuyển Leader dùng nhóm IT3090 | Không sửa code Student ngoài mục tiêu |
| 3 Khả thi | Plan cũ dùng `/teacher/classes/:classId` | Đổi sang `/teacher/courses/:courseId` | Cùng ID với Student; tên backend chưa chốt |
| 3 Khả thi | Plan cũ cho bật comment "nếu contract sẵn sàng" | Ghi rõ: không có wrapper/mutation; P0 chỉ hiển thị | Không có bằng chứng contract |
| 3 Khả thi | Import tưởng như có contract (Identity §3.5.1) | Ghi là mô tả phía Identity; Classroom chưa xác nhận; client chưa gửi multipart | Không suy ra endpoint Classroom đã có từ tài liệu service khác |
| 3 Khả thi | Sidebar/top bar gọi endpoint sinh viên | Layout Teacher dùng nội dung sidebar riêng trong cùng khung | Tránh gọi `/my-work` cho Teacher và tránh boolean prop rẽ nhánh |
| 3 Khả thi | Dashboard cần quá hạn, blocked, thời điểm sync nhưng type không có | Thêm `dueAt` tùy chọn; blocked và `lastSyncedAt` hiển thị "chưa có dữ liệu" | Không bịa trường; thay đổi tùy chọn không phá Student |
| 4 Trải nghiệm | Deep link vào workspace không quay về được lớp | `courseId`/`teamId` trong phản hồi workspace | Navigation state mất khi refresh/mở URL |
| 4 Trải nghiệm | Nhóm chỉ dùng Kanban thấy Board trống với lời nhắn cho sinh viên | Teacher được dẫn sang Backlog; dashboard đếm theo trạng thái không phụ thuộc Sprint | Không refactor Board dùng chung |
| 4 Trải nghiệm | Lỗi một phần (Code 500) làm hỏng dashboard | Mỗi khối có trạng thái lỗi/thời điểm riêng | Đã có tiền lệ `student-partial-error` |
| 4 Trải nghiệm | Sau logout đổi tài khoản còn cache | Giữ `queryClient.clear()`; key Teacher bắt đầu bằng `["teacher", …]`; 403 xóa query của lớp đó | Key hiện tại không gắn danh tính |
| 5 Kiểm tra ổn định | Rà lại 4 góc nhìn sau các thay đổi trên | Không còn thay đổi cấu trúc | Dừng phản biện |

## 12. Quyết định tạm và vấn đề còn mở

Quyết định tạm (đủ cơ sở cho Phase 1, xem lại khi có contract):

- Teacher = role toàn cục `TEACHER` (capability) + assignment theo lớp (quyền).
- `courseId` frontend = lớp mở trong học kỳ; route `/teacher/courses/:courseId`.
- Mở rộng graph mock dùng chung; không fixture Teacher riêng; không membership giả.
- Teacher chỉ đọc workspace; comment chờ contract.

Còn mở — điều kiện trước khi triển khai phần liên quan:

| Vấn đề | Chặn | Chủ quyết định |
| --- | --- | --- |
| Tên và tầng Course/Class/Classroom; hợp đồng REST Classroom (lớp, sinh viên, nhóm, mã) | Phase 3, tích hợp thật | Backend Classroom |
| Classroom xác nhận endpoint import và shape báo cáo | Ghi import | Backend Classroom |
| Hợp đồng Project Service: viewer context cho giảng viên, `courseId`/`teamId`, `dueAt`, blocked, comment | Phase 2 tích hợp thật, comment | Backend Project |
| Adapter auth: envelope, `access`/refresh cookie, `roles` | Tích hợp backend thật | Frontend + Identity |
| Quyền ghi của giảng viên được thêm (không phải owner) | Phase 3–4 | Nghiệp vụ |
| Policy sĩ số, Leader thay thế, quyền đọc lịch sử sau chuyển nhóm | Phase 4 | Nghiệp vụ |
| Analysis mâu thuẫn: §2.1 Member "Không" yêu cầu AI phân rã, US-5.5 cho Member phân rã | Không chặn Teacher (Teacher luôn không có) | Nghiệp vụ |
| Analysis §2.2 cho Admin mọi quyền nhưng §1.3 nói Admin không mặc định đọc project | Không chặn (Admin ngoài phạm vi) | Nghiệp vụ |
| Contract Progress cho tiến độ/rủi ro | Phase 5 | Backend Progress |

## 13. Kết quả Phase 1

Phạm vi: nền quyền, graph mock dùng chung và giao diện **đọc** lớp của Teacher.
Mọi dữ liệu Teacher hiện là **Demo MSW**: không có backend, không có hợp đồng
API, và không có thao tác ghi nào. Các đường `/api/work/api/v1/teacher/…` chỉ
tồn tại trong mock, **không** phải hợp đồng đã chốt và không được đưa vào
`contracts/`.

### 13.1 Đã làm gì

| Hạng mục | Nhãn | Bằng chứng |
| --- | --- | --- |
| Graph quan hệ dùng chung (giảng viên của lớp, nhóm → lớp, sinh viên của lớp, thành viên và vai trò nhóm) | Demo MSW | [relationships.ts](../../apps/web/src/mocks/data/relationships.ts) |
| Danh bạ người, lớp, nhóm (tên, MSSV, email, mã tham gia, sĩ số tối đa) | Demo MSW | [directory.ts](../../apps/web/src/mocks/data/directory.ts) |
| Roster, `classSize`, tên nhóm, giảng viên của Student dẫn xuất từ graph | Demo MSW | [studentFlow.ts](../../apps/web/src/mocks/data/studentFlow.ts), [myWork.ts](../../apps/web/src/mocks/data/myWork.ts) |
| Read model Teacher dẫn xuất từ graph (không có số liệu viết tay) | Demo MSW | [mocks/data/teacherFlow.ts](../../apps/web/src/mocks/data/teacherFlow.ts) |
| 4 endpoint đọc Teacher | Demo MSW | [mocks/handlers/teacherFlow.ts](../../apps/web/src/mocks/handlers/teacherFlow.ts) |
| `roles` trong `AuthUser`; `canUseTeacherSpace`, `defaultLandingPath`, `resolveLoginTarget` | Đã triển khai (frontend); nguồn `roles` là mock, auth thật **Chưa xác minh** | [auth/utils.ts](../../apps/web/src/features/auth/utils.ts) |
| Guard `/teacher/*` và chuyển `/` theo tài khoản | Đã triển khai | [RequireTeacherSpace.tsx](../../apps/web/src/app/router/RequireTeacherSpace.tsx) |
| Sidebar, top bar, layout Teacher; liên kết "Không gian giảng viên/sinh viên" cho tài khoản kép | Đã triển khai | [TeacherSidebar.tsx](../../apps/web/src/components/navigation/TeacherSidebar.tsx), [TeacherTopNavigation.tsx](../../apps/web/src/components/navigation/TeacherTopNavigation.tsx), [AuthenticatedLayout.tsx](../../apps/web/src/app/layouts/AuthenticatedLayout.tsx) |
| T01 Home, T02 danh sách lớp, T04 tổng quan lớp, T05 sinh viên, T07 nhóm (chỉ đọc) | Đã triển khai trên dữ liệu Demo MSW | [features/teacher/](../../apps/web/src/features/teacher/) |
| Query key theo user và lớp; xóa cache khi đăng nhập/đăng xuất; bỏ cache con của lớp mất quyền | Đã triển khai | [teacherFlowHooks.ts](../../apps/web/src/lib/query/teacherFlowHooks.ts), [AuthProvider.tsx](../../apps/web/src/features/auth/AuthProvider.tsx), [TeacherCourseLayout.tsx](../../apps/web/src/features/teacher/routes/TeacherCourseLayout.tsx) |
| Sửa R2 (không lộ sự tồn tại) và R3 (phạm vi thông báo) | Demo MSW | [handlers/studentFlow.ts](../../apps/web/src/mocks/handlers/studentFlow.ts) |
| T03 tạo lớp, T06 import, T08 chi tiết nhóm, T09 workspace Teacher, T10 cài đặt lớp | **Chưa triển khai** (đúng phạm vi: Phase 2/3) | — |

### 13.2 Cách thử

Mật khẩu mọi tài khoản demo: `demo1234`. Chạy `VITE_ENABLE_MOCKS=true` (xem
[apps/web/README.md](../../apps/web/README.md)).

| Tài khoản | Role | Phụ trách |
| --- | --- | --- |
| `teacher@utask.test` (TS. Trần Minh Đức) | TEACHER | SE330 Lớp 1 (chủ lớp), SE330 Lớp 2 (chủ lớp, lớp rỗng), IT3090 (đồng phụ trách, chủ lớp là TS. Đặng Văn Cường) |
| `teacher2@utask.test` (ThS. Lê Thị Mai) | TEACHER | CS402 (chủ lớp) |
| `student@utask.test`, `leader@utask.test`, `member@utask.test` | STUDENT | Không phụ trách lớp nào |

SE331 (TS. Vũ Thu Hương) và chủ lớp IT3090 (TS. Đặng Văn Cường) là giảng viên
không có đăng nhập, nên SE331 là lớp ngoài quyền của cả hai tài khoản giảng
viên; CS402 ngoài quyền của `teacher@utask.test`, còn SE330 và IT3090 ngoài
quyền của `teacher2@utask.test`. Sinh viên và giảng viên không có đăng nhập chỉ
có hồ sơ hiển thị; không có tài khoản nào được tạo thêm (đủ 5 tài khoản đăng
nhập).

Route: `/teacher`, `/teacher/courses`, `/teacher/courses/:courseId`,
`/teacher/courses/:courseId/students`, `/teacher/courses/:courseId/teams`.
Bộ lọc nằm trên URL: `?term=`, `?q=`, `?team=has-team|no-team`,
`?view=unassigned`.

Scenario (`VITE_MOCK_SCENARIO`): `teacher-empty` (giảng viên chưa có lớp nào),
`teacher-partial-error` (danh sách lớp tải được, sinh viên và nhóm trả 500),
`server-error` và `slow-network` có sẵn. Tổng 29 scenario.

Điểm vào sau đăng nhập: `returnTo` nội bộ hợp lệ được ưu tiên; nếu không,
tài khoản chỉ có role TEACHER vào `/teacher`, các tài khoản khác vào `/my-work`.
`returnTo` không nới quyền: trang đích vẫn tự kiểm tra. Dữ liệu để chọn điểm vào
lấy từ `user.roles` của phiên (mock đăng nhập/làm mới), không tra email hay đọc
graph trong component.

### 13.3 Chính sách lỗi của mock (R2)

| Tình huống | Mã | Ghi chú |
| --- | --- | --- |
| Không có phiên | 401 | |
| Tài khoản không có role TEACHER gọi `/teacher/*` | 403 | Cổng theo role, không tiết lộ lớp nào |
| Lớp **không phân công cho người gọi** hoặc không tồn tại | 404, cùng nội dung | Test so sánh từng byte |
| Student mở môn, project, issue, code, settings, tạo nhóm, đánh dấu thông báo ngoài quyền | 404, cùng nội dung với "không tồn tại" | Trước đây là 403 ở một số đường |
| Người đã vào được project nhưng thiếu quyền hành động (Member mở settings) | 403 | Giữ nguyên |

Role TEACHER **không** mở endpoint Student (môn, tạo nhóm, project): có test.

Thông báo: một hàm `visibleNotifications` quyết định phạm vi cho cả danh sách,
đánh dấu đã đọc và đánh dấu tất cả. Thông báo cấp lớp cần ghi danh hoặc phân
công cho lớp đó; thông báo cấp project cần là thành viên project (Teacher chưa
có). ID ngoài phạm vi trả 404, không còn báo thành công giả.

### 13.4 Quy tắc số liệu đã dùng

- Tiến độ nhóm: điểm Sprint đang chạy (`completed/total`, nhãn "theo điểm Sprint
  đang chạy"); không có Sprint nhưng có issue: tỷ lệ issue `done` (nhãn "theo số
  issue"); không có gì để đo, hoặc nhóm chưa có project: "Chưa có dữ liệu tiến độ"
  — không bao giờ 0% giả.
- Hoạt động gần nhất: `updatedAt` lớn nhất của issue, luôn kèm loại ("Cập nhật
  issue") và đồng hồ cố định của fixture; không có thì "Chưa ghi nhận hoạt động".
- "Task quá hạn" trên Home: **"Chưa có dữ liệu"**, vì `Issue` chưa có hạn chót
  (xem §9.3). Không hiển thị số 0.
- Không dùng dữ liệu GitHub Home của Student cho nhóm nào.
- "Chưa có nhóm" tính theo từng lớp: một sinh viên chưa có nhóm ở hai lớp được
  đếm hai lần (ghi trong chú thích của chỉ số).

### 13.5 Khác với kế hoạch Phase 0 và lý do

| Thay đổi | Lý do |
| --- | --- |
| Thêm [directory.ts](../../apps/web/src/mocks/data/directory.ts) (người, lớp, nhóm) | Người không có đăng nhập cần hồ sơ hiển thị; metadata lớp/nhóm trước đây nằm rải ở 3 file |
| Thêm `section` ("Lớp 1/Lớp 2") | Hai lớp cùng mã SE330 cần phân biệt trên UI; `courseId` vẫn là khóa duy nhất |
| ID Teacher đổi sang `…00f1`/`…00f2` | `…0004`/`…0005` trùng Bùi Quang Thắng/Trần Bảo Long ở NEXUS |
| `teacher2` chỉ phụ trách CS402; SE331 và chủ lớp IT3090 là giảng viên không có đăng nhập | Khớp yêu cầu và `instructorName` mà Student đã hiển thị |
| Không làm `ProjectViewer`/`projectViewerFor` | Teacher chưa truy cập project: thuộc Phase 2. Tránh mã chết mang ngữ nghĩa quyền chưa dùng |
| Cache con bị xóa khi lớp mất quyền, nhưng bản ghi chi tiết lớp (đang ở trạng thái lỗi) vẫn nằm trong cache và không được render | Xóa chính query đang được quan sát sẽ gây vòng lặp tải lại. Cache xóa sạch khi đăng nhập/đăng xuất |
| Tab "Cài đặt" lớp là chữ vô hiệu, không phải liên kết | Trang chưa có |
| Thông báo cấp lớp của tài khoản chỉ-giảng-viên dẫn tới `/teacher/courses/:id` | Đường cũ `/courses/:id/team` là trang Student và trả "không tìm thấy" |
| Sửa `LoginRoute` | Nó luôn chuyển về `/my-work` ngay khi đăng nhập xong, có thể đè lên điều hướng đúng của form (giảng viên bị đẩy sang trang Student, `returnTo` bị mất) |
| Sidebar Teacher không có huy hiệu thông báo chưa đọc | Tránh gọi hook Student; Teacher chưa có nội dung thông báo riêng |

Các thay đổi này làm **dữ liệu Student đổi**, đã chạy lại toàn bộ test Student:

- Sĩ số lớp (tổng/đã có nhóm, viết tay → từ graph): SE330 45/38 → 6/5, CS402 40/37 → 6/5,
  SE331 42/39 → 3/1, IT3090 38/30 → 9/4.
- Roster DELI: có thêm Nguyễn Hoàng Nam (graph xếp `leader@` là Member DELI,
  roster cũ không có); Lý Bảo Châu rời DELI vì 6/5 vượt giới hạn, trở thành sinh
  viên chưa có nhóm của CS402.
- Màn thành lập nhóm IT3090: Team VISION/SENSE còn 2 thành viên (trước: 3 và 4) và
  danh sách "chưa có nhóm" gồm cả Nguyễn Hoàng Nam và Đặng Thảo Linh (trước chỉ 3
  người), vì nay lấy từ graph.
- Tên giảng viên trên thẻ Sprint ở Home khớp chủ lớp (trước: tên khác với trang môn).
- Tên nhóm ở Home lấy từ danh bạ (trước: gán "Team DELI" cho mọi nhóm không phải NEXUS).

### 13.6 Tình trạng R1–R12 sau Phase 1

| Mục | Tình trạng |
| --- | --- |
| R1 `myRole ?? "member"` | **Còn** trong mock workspace, nhưng Teacher không tới được (project chặn 404). Xử lý ở Phase 2 cùng `ProjectViewer`. **Đã sửa ở Phase 2 (§15)** |
| R2 404 trước 403 | Đã sửa cho môn, project, issue, code, settings, ai-key, tạo nhóm, đánh dấu thông báo |
| R3 thông báo cấp lớp | Đã sửa (§13.3) |
| R4 GitHub Home dùng chung | Không dùng cho Teacher |
| R5 `isMine`/`isMe` tĩnh | **Còn** — Phase 2. **Đã sửa ở Phase 2 (§15)** |
| R6 roster lệch | Đã sửa cho roster lớp/nhóm; **còn** danh sách assignee (4 người) và contributor (4 người) trong workspace/Code, không có Lê Minh Khoa — Phase 2. **Đã sửa ở Phase 2: đóng góp NEXUS có đủ 5 người (§15.5)**; danh sách assignee của issue vẫn 4 người vì chưa issue nào giao cho Khoa |
| R7 roster DELI thiếu `leader@` | Đã sửa |
| R8 `classSize` | Đã sửa |
| R9 tên nhóm | Đã sửa |
| R10 DELI Code trả 404 | **Còn** — Phase 2. **Đã sửa ở Phase 2 (§15)** |
| R11 thời gian `new Date()` | Read model Teacher dùng đồng hồ cố định; workspace Student vẫn `new Date()` — Phase 2. **Phase 2: giảng viên đọc workspace theo đồng hồ cố định, sinh viên giữ đồng hồ thật (§15.2)** |
| R12 checkbox subtask | **Còn** — Phase 2. **Đã sửa ở Phase 2: disabled với giảng viên (§15)** |

### 13.7 Kết quả kiểm tra

Chạy trong `apps/web`:

- `pnpm lint` (`tsc --noEmit`): đạt.
- `pnpm test`: 189 test, 10 file đạt; chạy lặp liên tiếp nhiều lần đều đạt (trước
  Phase 1: 81 test). Gồm 25 test nhất quán graph, 21 test chính sách API, 67 test
  giao diện Teacher qua bảng route thật (guard, layout, route lazy).
- `pnpm build`: đạt.
- Kiểm tra đột biến: tạm bỏ guard `/teacher`, bỏ kiểm tra phân công lớp, đặt lại
  ID trùng sinh viên, và để read-all bỏ qua phạm vi lớp — mỗi lần có test đỏ
  (4, 10, 6 và 1 test), rồi đã khôi phục.
- Smoke trên trình duyệt thật (Edge headless qua CDP, dev server mock): 19 lượt mở
  trang ở desktop 1280×800 và mobile 390×844. Không tràn ngang; điều hướng, lớp
  rỗng, lớp ngoài quyền, Student bị chặn và chuyển `/` đều đúng; bảng sinh viên
  chuyển thành thẻ trên mobile. Chỉ có 1 dòng lỗi console, là log 404 của chính
  yêu cầu tới lớp ngoài quyền. Smoke còn bắt được một lỗi hiển thị (thiếu dấu
  cách sau "Trưởng nhóm:") mà test jsdom không thấy; đã sửa và siết test.

Không có formatter hay ESLint trong repo (script `lint` chỉ chạy `tsc`) nên không
chạy formatter.

### 13.8 Giới hạn và điểm chưa xác minh

- Chưa kiểm tra bằng bàn phím và trình đọc màn hình thật, Safari/Firefox, thiết
  bị di động thật, và ngăn kéo điều hướng mobile trên trình duyệt thật (chỉ có
  test jsdom). Chưa chạy bản build production với mock tắt.
- Danh bạ là tĩnh: sửa hồ sơ ở trang cài đặt không đổi roster/danh sách lớp.
- Một lớp có hai tên trong giao diện Student (Home/sidebar dùng "Đồ án Chuyên
  ngành SE330", trang môn dùng tên đầy đủ); Teacher dùng tên đầy đủ. Có sẵn từ
  trước, chưa gộp.
- Thông báo cho Teacher dùng lại nội dung viết cho sinh viên ("Mở Project
  Workspace", "Xem môn học") vì chưa có nội dung riêng; nút dẫn tới trang lớp
  của Teacher. Tài khoản vừa Teacher vừa Student vẫn được dẫn tới trang Student.
- Kịch bản `student-no-team` / `student-join-pending` của SE330 vẫn là fixture
  riêng (4 nhóm giả, 7 bạn cùng lớp) và mâu thuẫn với graph, nơi SV01 là Leader
  NEXUS; đó là kịch bản chủ ý, không đại diện dữ liệu Teacher.
- Chưa kiểm thử từng commit đề xuất riêng lẻ; chỉ chạy trên cây làm việc cuối.
- Vấn đề mở ở §12 (contract Classroom/Project/Progress, quyền ghi của giảng viên
  đồng phụ trách, policy chuyển nhóm) **chưa được giải quyết** bởi phase này.

### 13.9 Tự phản biện sau triển khai

| Câu hỏi | Kết luận có bằng chứng | Đã sửa |
| --- | --- | --- |
| Có cấp quyền chỉ từ role TEACHER không? | Không. Role chỉ mở khu `/teacher`; mỗi lớp cần phân công. Test: tài khoản Student được gán thêm TEACHER vẫn 404 ở SE330 | Bản trước cho Teacher đi qua endpoint Student (`accessibleCoursesFor` gộp cả lớp phụ trách, gồm tạo nhóm); đã loại |
| Dữ liệu Teacher có lệch Student không? | Test so từng sinh viên: nhóm, vai trò, chờ duyệt khớp Home của chính họ; sĩ số/roster/giảng viên khớp trang môn | ID trùng, `classSize` và tên nhóm hardcode, roster lệch; đã sửa |
| Có CTA/link chết hoặc thành công giả không? | Test quét mọi `a[href]` trên 5 trang Teacher; CTA tương lai là nút vô hiệu có mô tả; sao chép mã báo lỗi khi clipboard hỏng | Thông báo dẫn sang trang Student; breadcrumb không có liên kết (đưa `href` thay vì `to`); sao chép nuốt lỗi; đã sửa |
| Có lấn sang Phase 2/3 không? | Không có mutation, form tạo lớp/import, chi tiết nhóm, workspace; nút tương ứng bị vô hiệu | Đã bỏ `projectViewerFor` |
| Có ảnh hưởng Student chưa được test? | Toàn bộ test Student cũ vẫn qua; thêm test cho 404 thống nhất, thông báo, IT3090 | Danh sách ảnh hưởng ở §13.5 |
| Chỉ số có hardcode không? | Mọi số trên Home/lớp dẫn xuất từ graph; test so với hàm dựng | Trước đó `progress: 0.35` và mã tham gia giống nhau cho mọi lớp |

## 14. Cập nhật theo thiết kế Stitch

Sau Phase 1, giao diện Teacher được dựng lại theo 5 màn Stitch của project "UTask -
Project Management Platform" (`.stitch/`, kèm `.stitch/vivid_focus/DESIGN.md`) và
thêm màn **Giám sát** (Oversight). Mọi dữ liệu vẫn là Demo MSW, chỉ đọc. Đây không
phải Phase 2: workspace, dashboard nhóm (T08), form tạo lớp và thao tác ghi chưa làm.

Lưu ý: `.stitch/` đang nằm trong `.gitignore`, nên các ảnh và HTML thiết kế không
được commit; phần đối chiếu dưới đây là bản ghi duy nhất trong repo.

### 14.1 Ánh xạ từng màn Stitch

| Màn Stitch | Trong code | Đã lấy từ thiết kế | Cố ý không làm (lý do) |
| --- | --- | --- | --- |
| Danh mục lớp (`/teacher/classes`) | `/teacher/courses` và `/teacher` (Home) | Thẻ lớp có mã môn, học kỳ, số sinh viên/nhóm, huy hiệu tín hiệu, lối tắt Sinh viên / Nhóm / Giám sát; ô tìm kiếm và lọc học kỳ | Tab "Học kỳ trước/Lưu trữ" (chưa có dữ liệu nhiều học kỳ); Import danh sách lớp, Nhật ký hoạt động, Xuất báo cáo (không có nguồn dữ liệu hay contract); "Sprint % hoàn thành" và "On-track/Cần lưu ý/Nguy cơ cao" (chưa có định nghĩa nghiệp vụ, thay bằng tín hiệu có nguyên nhân, mục 14.3); "Đồng bộ Webhook GitHub" (chưa có Integration); "Tạo lớp" vẫn disabled kèm lý do |
| TCH-01-FLAT: Lớp và Sinh viên | `/teacher/courses/:courseId` (Tổng quan) và `/students` | Thẻ "Quy định nhóm và tham gia lớp" (sĩ số, mã tham gia, giảng viên, hoạt động gần nhất); tab có số đếm; ô tìm kiếm, chip lọc "Tất cả / Chưa có nhóm / Đã có nhóm" có số đếm; bảng có avatar chữ cái, vai trò trong nhóm, dòng chưa có nhóm tô nhẹ | Cột "Ngày tham gia" và hạn lập nhóm/hạn nộp đề tài (graph không có dữ liệu, không bịa); Sửa/Xóa/Gán nhóm từng dòng (thao tác ghi, P1); chọn nhiều dòng; "Thêm sinh viên" và "Nhập danh sách" giữ disabled kèm lý do |
| TCH-01-TEAMS: Cơ cấu nhóm | `/teacher/courses/:courseId/teams` | Hàng thống kê (tổng, đã có nhóm, chưa có nhóm, quy định sĩ số); khối "Sinh viên chưa có nhóm"; thẻ nhóm liệt kê đủ thành viên (Leader, MSSV), "còn n chỗ", tiến độ, hoạt động gần nhất; tìm kiếm và chip lọc (còn chỗ trống, chưa có project) | Duyệt/yêu cầu sửa đề tài (ngoài phạm vi, §4); phân nhóm ngẫu nhiên và kéo thả (ngoài phạm vi / P1); nhắc nộp đề tài; mở Jira; phân trang (dữ liệu ít); "Tạo nhóm thủ công" và "Xem chi tiết nhóm" giữ disabled |
| TCH-03-OVERSIGHT: Giám sát | `/teacher/courses/:courseId/oversight` (**mới**) | Tóm tắt trên đầu; tìm kiếm, lọc theo tín hiệu, sắp xếp; bảng nhóm và project, tiến độ, hoạt động gần nhất, tín hiệu cần chú ý; thẻ ở màn hẹp | Cột "Cảnh báo AI Gemini" và nút "AI quét sức khỏe" (Teacher không kích hoạt AI, §4); commit/PR/CI theo tuần (Integration chưa có); mức "Critical/At-risk" và "độ lệch so với mốc" (ngưỡng chưa chốt); xuất xlsx; nhãn "LIVE" (dữ liệu là fixture) |
| TCH-04-GRADING: Chấm điểm | **Không dựng** | Không | Analysis §8.5 loại trừ chấm điểm tự động từ commit/task và quản lý điểm số; §7.3 yêu cầu cảnh báo không tự chuyển thành điểm; analysis cũng loại trừ "kết luận năng lực sinh viên". Màn này chỉ dùng làm tham khảo bố cục (thẻ thống kê, bảng theo nhóm). Sidebar và tab không có "Chấm điểm" |

Khác với thiết kế ở các điểm chung: sidebar hiện danh sách lớp phụ trách và, với
lớp đang mở, các mục Tổng quan / Sinh viên / Nhóm / Giám sát (không có Archive,
Settings của lớp); không có breadcrumb "Classes"; dùng phông Inter của ứng dụng,
chưa nạp Public Sans mà `DESIGN.md` dùng cho nhãn; palette và bo góc dùng token đã có
(trùng với Vivid Focus: primary `#5645d4`, nền `#faf9f8`).

### 14.2 Tên route

Giữ `/teacher/courses/:courseId` (lý do ở §7: dùng chung `courseId` với Student
Flow). Thiết kế dùng `/teacher/classes/...`; chưa có alias, vì thêm alias là một
quyết định đặt tên chưa được chốt. Nếu muốn đổi sang `classes`, cần đổi `router.tsx`,
sidebar, liên kết và test cùng lúc.

### 14.3 Tín hiệu cần chú ý (quy tắc cố định, không AI, không điểm)

Tính trong `signalsFor` (`apps/web/src/mocks/data/teacherFlow.ts`) trên dữ liệu
fixture và đồng hồ cố định `2026-10-20T08:30:00Z`. Mỗi tín hiệu luôn có nguyên nhân
bằng chữ; "chưa có tín hiệu" không có nghĩa là nhóm đang tốt (màn hình nói rõ).

| Mã | Điều kiện | Nhãn hiển thị |
| --- | --- | --- |
| `no-project` | Nhóm chưa gắn project | "Chưa có project" |
| `no-progress-data` | Có project nhưng không có điểm Sprint đang chạy lẫn issue | "Chưa có dữ liệu để đo tiến độ" |
| `no-activity` | Có project nhưng không issue nào có thời điểm cập nhật | "Chưa ghi nhận cập nhật issue nào" |
| `stale-activity` | Cập nhật issue gần nhất cách mốc ≥ `STALE_AFTER_DAYS` (7) ngày | "Không có cập nhật issue trong N ngày" |
| `below-min-size` | Số thành viên < sĩ số tối thiểu của lớp | "Chưa đủ thành viên tối thiểu (n/min)" |

Ngưỡng 7 ngày là giá trị demo do mock chọn, **chưa phải quy tắc nghiệp vụ**; server
mock trả `staleAfterDays` để màn hình in đúng con số đang dùng. Nếu nghiệp vụ chốt
ngưỡng khác hoặc có tín hiệu từ Progress Service, thay thế `signalsFor`, không sửa UI.

### 14.4 Thay đổi API demo (MSW, không phải contract)

- Mới: `GET /api/work/api/v1/teacher/courses/:courseId/oversight` →
  `{ teams: TeacherOversightRow[], staleAfterDays }`. Cùng thứ tự kiểm tra với các
  endpoint Teacher khác (401, 500 theo scenario, 403 thiếu role, 404 lớp không được
  phân công hoặc không tồn tại). Scenario `teacher-partial-error` làm endpoint này
  trả 500 như students/teams.
- `teams[]` thêm `members` (`userId`, `name`, `studentCode`, `role`) lấy từ graph.
- Danh sách/chi tiết lớp thêm `teamsWithSignals`, tính từ chính các hàng oversight để
  con số ở thẻ lớp và ở màn Giám sát không thể lệch nhau.
- Query key mới `["teacher", userId, "courses", courseId, "oversight"]`, nằm dưới
  khóa lớp nên bị gỡ cùng lớp khi mất quyền.

### 14.5 Kết quả kiểm tra

- `pnpm lint` (`tsc --noEmit`): đạt. `pnpm build`: đạt.
- `pnpm test`: 212 test / 10 file đạt (trước đợt này: 189). Thêm: quy tắc tín hiệu
  (cả hai phía ngưỡng 7 ngày), `teamsWithSignals` khớp số hàng oversight, danh sách
  thành viên khớp roster, endpoint oversight (401/403/404 giống lớp không tồn tại, 500
  theo scenario, lớp rỗng), màn Giám sát (tiến độ và căn cứ, không vẽ 0% khi thiếu dữ
  liệu, lọc/tìm/sắp xếp lưu trên URL, lỗi + thử lại, lớp ngoài quyền, sinh viên bị
  chặn, không có nút AI/chấm điểm), màn Nhóm (thống kê, chip lọc, thành viên và chỗ
  trống), sidebar theo lớp đang mở, không liên kết chết (có thêm `/oversight`).
- Duyệt thử trên Edge headless (desktop 1280×800 và mobile 390×844) các màn Home,
  danh sách lớp, Tổng quan, Sinh viên, Nhóm, Giám sát, lớp rỗng, lớp ngoài quyền: không
  tràn ngang trang, không có lỗi console ngoài log 404 đã biết của lớp ngoài quyền.
- Chưa kiểm tra: bàn phím và trình đọc màn hình thật, Safari/Firefox, thiết bị thật,
  chế độ tối (ứng dụng chưa có), so sánh điểm ảnh với Stitch (chỉ so bằng mắt).

### 14.6 Giới hạn và rủi ro còn lại

- `StatCard` hiện in nhãn chữ hoa nhỏ; ở màn hẹp tiêu đề dài ("Nhóm có tín hiệu cần
  chú ý") xuống dòng, chấp nhận được nhưng chưa tinh chỉnh.
- Dữ liệu fixture ít (SE330 chỉ có 1 nhóm, IT3090 có 2 nhóm chưa có project) nên
  chưa có ca `stale-activity` trong giao diện; quy tắc này chỉ được kiểm bằng test
  đơn vị. Muốn xem trên giao diện cần thêm fixture (đổi graph dùng chung, không
  fixture riêng cho Teacher).
- Số liệu "Tiến độ" và "issue đã hoàn thành" có thể khác nhau (NEXUS: 65% theo điểm
  Sprint nhưng 1/10 issue xong); hai con số có nhãn căn cứ riêng, nhưng người dùng
  vẫn có thể thắc mắc. Cần nghiệp vụ chốt đâu là số chính.
- Phase 2 (T08 dashboard nhóm, workspace chỉ đọc, R1/R5/R6/R10/R12) đã làm sau đó;
  xem [§15](#15-kết-quả-phase-2--từ-nhóm-đến-workspace-chỉ-xem).

## 15. Kết quả Phase 2 — từ nhóm đến workspace (chỉ xem)

Dữ liệu vẫn là Demo MSW; không có backend, hợp đồng hay thao tác ghi của Teacher.
Trên nhánh `feat/frontend-teacher-flow`, chưa commit phần Phase 2.

### 15.1 Đã làm gì

| Yêu cầu | Trạng thái | Cách làm / bằng chứng |
| --- | --- | --- |
| T08 dashboard nhóm | Đã triển khai (Demo MSW) | `/teacher/courses/:courseId/teams/:teamId` ([TeacherTeamDetailRoute.tsx](../../apps/web/src/features/teacher/routes/TeacherTeamDetailRoute.tsx)); mở từ thẻ nhóm và từ bảng Giám sát; thành viên, project, tiến độ + căn cứ, issue theo trạng thái, quá hạn, GitHub, tín hiệu, lối vào workspace |
| `ProjectViewer` | Đã triển khai | `ProjectViewer = team-member{role} \| course-instructor{courseId}` trong `features/projects/types.ts`; `viewerRole`, `projectPermissionContext`, `canViewProject`, `isReadOnlyViewer` trong `lib/permissions.ts`; mọi helper ghi vẫn khóa theo `role === "leader"` nên giảng viên (role `null`) không qua được |
| `courseId`/`teamId` trong workspace | Đã triển khai | `ProjectWorkspace` thêm `courseId`, `teamId`, `viewer`; breadcrumb Teacher dựng từ chính payload nên đúng khi mở thẳng URL hoặc refresh |
| Bỏ fallback Teacher → Member (R1) | Đã sửa | `projectWorkspaceFor` trả `null` khi không có quan hệ viewer; `myRole` chỉ có với thành viên, vắng mặt với giảng viên |
| Mở đọc workspace/issue/code qua assignment | Đã triển khai (mock) | `projectViewerFor` trong graph: thành viên nhóm, hoặc giảng viên của lớp chứa nhóm đó **và** tài khoản có role `TEACHER`; thiếu một trong hai → 404 |
| Settings và thao tác Leader vẫn chặn | Đã triển khai | Settings và `PUT ai-key`: giảng viên nhận 403 (mở được project nhưng không có quyền), người ngoài nhận 404; route settings trên UI vào Forbidden; tab Cài đặt ẩn |
| Dùng lại Backlog, Board, Code, IssuePanel | Đã triển khai | Không có bản sao Teacher; hành vi đổi theo `viewer` qua `readOnly` trong context của `ProjectWorkspaceLayout` |
| Ẩn/vô hiệu đúng quyền | Đã triển khai | Ẩn Tạo Epic, Tạo Issue, thanh AI, AI sinh sub-task, Hoàn thành Sprint, tab Cài đặt, bộ lọc "Chỉ việc của tôi"; checkbox subtask disabled (R12); trạng thái đã disabled sẵn |
| Không có composer comment | Đã triển khai | Không có ô nhập; ghi chú "Gửi bình luận sẽ khả dụng khi có hợp đồng API"; bình luận hiện có vẫn đọc được |
| `isMine`/`isMe` theo người xem (R5) | Đã sửa | `isMine = assignee.userId === userId` mỗi request; `isMe` tương tự; không giá trị cứng |
| Board không có Sprint | Đã triển khai | Giảng viên thấy "Nhóm chưa có Sprint đang chạy" kèm liên kết sang Backlog; sinh viên giữ thông điệp cũ |
| GitHub chưa kết nối ≠ project không tồn tại (R10) | Đã sửa | Project không có repository trả `syncState: "no-repository"`; project không tồn tại hoặc ngoài quyền vẫn 404 |
| Quá hạn, tiến độ, sync có nguồn và công thức | Đã triển khai | Xem 15.3; thiếu dữ liệu hiển thị "Chưa có dữ liệu", không phải 0 |
| Mỗi section lỗi độc lập | Đã triển khai | T08 gồm một truy vấn nhóm và một truy vấn GitHub riêng; GitHub lỗi chỉ hiện lỗi + "Thử lại" trong khối đó |

Việc kèm theo, cần biết:

- Giao diện Teacher được giữ khi giảng viên mở `/projects/*`: tài khoản chỉ có role
  Teacher dùng ngay thanh bên Teacher; tài khoản vừa là sinh viên đổi sang thanh bên
  Teacher khi workspace báo viewer là giảng viên (`TeacherChromeContext`).
- Trang 404 của workspace dẫn tài khoản chỉ-Teacher về "Về danh sách lớp phụ trách"
  thay vì danh sách dự án của sinh viên.
- Cột "Trạng thái" (Key Contributor / Active / Watch) trong bảng đóng góp bị ẩn với
  giảng viên: nhãn đó đánh giá sinh viên từ số commit, trái US-5.3 và §8.5. Các số
  liệu thô (commit, dòng code, PR) vẫn hiển thị. Sinh viên vẫn thấy cột này như trước.

### 15.2 Khác biệt với kế hoạch Phase 0 và lý do

| Phase 0 | Thực tế | Lý do |
| --- | --- | --- |
| `ProjectWorkspace` giữ `myRole` trong giai đoạn chuyển tiếp | `myRole` đã thành tùy chọn và chỉ có với thành viên | Teacher không được nhận giá trị mặc định (R1); các chỗ dùng `myRole` được chuyển sang `viewer` |
| `canCommentOnTask(viewer)` | Không thêm | Chưa có contract và không có composer; một hàm không ai gọi chỉ là mã chết mang ngữ nghĩa quyền |
| Dùng `ProjectWorkspace` cho read model Teacher | Thêm `projectDataFor` (dữ liệu không gắn viewer) | Read model lớp/nhóm không có "người xem"; tránh truyền `userId` rỗng |
| Thời gian workspace dùng chung `new Date()` | Giảng viên đọc theo đồng hồ cố định `2026-10-20T08:30:00Z`, sinh viên giữ đồng hồ thật | Giữ con số của T08, danh sách lớp và workspace khớp nhau và test ổn định (R11 chỉ đóng với Teacher) |
| `dueAt` tùy chọn | Thêm `Issue.dueAt?` và 4 issue NEXUS có hạn chót | Cần nguồn thật cho "quá hạn"; các issue còn lại không có hạn chót |
| Roster thống nhất (R6) | Bảng đóng góp NEXUS thêm Lê Minh Khoa và cân lại số liệu | Tổng commit/dòng code/PR vẫn khớp `stats` (có test); là thay đổi nhìn thấy được với sinh viên |
| Project settings kiểm tra bằng `projectRoleForUser` | Kiểm tra bằng viewer | Phân biệt "mở được nhưng thiếu quyền" (403) với "không mở được" (404) cho giảng viên |

### 15.3 Công thức và nguồn số liệu

| Số liệu | Công thức / nguồn | Khi thiếu |
| --- | --- | --- |
| Tiến độ nhóm | Điểm đã xong / tổng điểm của Sprint đang chạy; nếu không có Sprint hoặc tổng điểm 0 thì issue `done` / tổng issue | "Chưa có dữ liệu tiến độ" |
| Issue theo trạng thái | Đếm `status` của issue project | "Project chưa có issue nào" |
| Quá hạn | Issue có `dueAt`, chưa `done`, `dueAt` trước mốc tính; mẫu số là số issue có `dueAt`; mốc tính hiển thị cạnh số | "Chưa có dữ liệu (không issue nào có hạn chót)" |
| GitHub | Trạng thái đồng bộ, repository, commit gần nhất, số commit/PR mở/đã merge từ `/projects/:id/code` | Thời điểm đồng bộ gần nhất luôn là "Chưa có dữ liệu" (API không trả) |
| Hoạt động gần nhất, tín hiệu | Như §14.3 | Như §14.3 |

Hai ghi chú: số "Tiến độ" (65%) và "issue hoàn thành" (1/10) của NEXUS lệch nhau và cả
hai được giữ kèm căn cứ; bộ đếm "Còn N ngày" trên Board dùng ngày thật của trình
duyệt nên khác với mốc cố định của giảng viên (Còn 17 ngày theo ngày thật, trong khi Sprint kết thúc 25/10 theo mốc cố định).

### 15.4 Chính sách quyền của mock (bổ sung §13.3)

| Tình huống | Phản hồi |
| --- | --- |
| Không có phiên | 401 |
| Giảng viên của lớp chứa nhóm, tài khoản có role `TEACHER` | 200 cho workspace, issue, code |
| Giảng viên của lớp chứa nhóm nhưng tài khoản mất role `TEACHER` | 404 |
| Giảng viên lớp khác, hoặc role `TEACHER` không có assignment | 404, cùng thân phản hồi với project không tồn tại |
| Giảng viên mở settings hoặc `PUT ai-key` của project mình xem được | 403 |
| Nhóm không thuộc lớp trong `GET /teacher/courses/:id/teams/:teamId` | 404 "Không tìm thấy nhóm.", cùng với nhóm không tồn tại |
| Danh sách `/projects` của giảng viên | Rỗng (chỉ là danh sách dự án của sinh viên) |
| Thông báo cấp project | Vẫn chỉ cho thành viên project; giảng viên chỉ thấy thông báo cấp lớp |

### 15.5 Thay đổi mà sinh viên nhìn thấy

- "Chỉ việc của tôi" và huy hiệu "Bạn" trong bảng đóng góp giờ theo tài khoản đang
  đăng nhập (trước đây luôn là Nguyễn Hoàng Nam). Lê Minh Khoa (SV01) nay xuất hiện
  trong bảng đóng góp NEXUS và là người được đánh dấu "Bạn" khi SV01 đăng nhập.
- Project DELI không còn repository (`null`) ở danh sách và workspace; trang Code của
  DELI hiện "Dự án chưa có repository" thay vì "Không tìm thấy dự án".
- Thành viên không phải Leader không còn gọi `GET …/settings` khi mở Backlog/Board
  (trước đây nhận 403 rồi bỏ qua).
- Số liệu đóng góp NEXUS được chia lại cho 5 người, tổng không đổi (142 commit,
  14.250 dòng thêm, 3.120 dòng xóa, 28 PR).

### 15.6 Kết quả kiểm tra

Chạy trong `apps/web`:

- `pnpm lint` (`tsc --noEmit`): đạt. `pnpm build`: đạt.
- `pnpm test`: 253 test / 11 file đạt, chạy lặp 3 lần liên tiếp (trước Phase 2: 212).
  Mới: 14 test handler cho đọc project qua assignment (viewer, 403 so với 404, đồng hồ
  cố định, `no-repository`, role `TEACHER` đơn lẻ, mất role, đóng góp khớp roster và
  tổng) và endpoint nhóm; 26 test UI mới (`TeacherWorkspace.test.tsx`) cho T08 (kể cả GitHub lỗi độc lập, nhóm không project),
  workspace chỉ xem (breadcrumb khi mở thẳng URL, không có yêu cầu ghi hay settings,
  subtask không tick được, không có ô comment, Forbidden cho settings, Board không Sprint),
  quyền (giảng viên ngoài lớp, teacher2), và hồi quy Student (Leader, "mine" theo tài
  khoản, "Bạn" theo tài khoản).
- Kiểm tra đột biến, mỗi lần có test đỏ rồi khôi phục: bỏ kiểm tra role `TEACHER` (1),
  cho giảng viên đọc settings (3), mở lại checkbox subtask (1), tắt `readOnly` (10),
  gán cứng `isMine` (3).
- Duyệt thử trên Edge headless (1280×800 và 390×844): T08 (có và không có project), Backlog,
  Board, issue mở thẳng bằng URL, Code, Settings, project ngoài lớp; không tràn ngang trang,
  chỉ có log 404 đã biết ở project ngoài quyền.
- Chưa kiểm tra: bàn phím và trình đọc màn hình thật, Safari/Firefox, thiết bị thật, kéo
  thả/focus trap của IssuePanel với giảng viên, tài khoản vừa là sinh viên vừa là giảng
  viên của cùng một lớp (fixture không có), từng commit riêng lẻ.

### 15.7 Giới hạn và rủi ro còn lại

- Hợp đồng Project Service cho tư cách giảng viên (viewer context) chưa có (§12); toàn
  bộ ở trên chỉ là Demo MSW.
- Thông báo cấp project không đến giảng viên: có thể cần đổi khi có nghiệp vụ.
- Workspace của giảng viên và sinh viên dùng hai đồng hồ khác nhau trong mock; trên backend
  thật chỉ có một đồng hồ.
- Cùng một URL `/projects/:id/*` phục vụ hai loại người xem nên giao diện chỉ biết viewer
  sau khi tải xong workspace; tài khoản vừa là sinh viên có thể thấy thanh bên Student
  trong thoáng chốc trước khi đổi.
- Ngưỡng "7 ngày" và các quy tắc tín hiệu vẫn là giá trị demo (§14.3).
- Chưa có dashboard tiến độ theo thời gian, cảnh báo AI, comment, chấm điểm; nằm ngoài
  phạm vi (§4).

### 15.8 Lớp 100 sinh viên để thử quy mô

Đăng nhập `teacher3@utask.test` (mật khẩu demo như các tài khoản khác) để thấy lớp
`course-se360-large` (SE360, "Lập trình Web Nâng cao"): 100 sinh viên, 19 nhóm (17 nhóm
5 người, 2 nhóm 4 người), 7 sinh viên chưa có nhóm, trong đó 2 người đang chờ duyệt vào
nhóm. Dữ liệu sinh tự động và cố định trong `apps/web/src/mocks/data/largeClass.ts`, nhập
vào graph dùng chung; sinh viên chỉ là danh sách, không có tài khoản đăng nhập. Không
nhóm nào có project (chưa có fixture project cho chúng), nên màn Giám sát hiện cả 19 nhóm
với tín hiệu "Chưa có project". `teacher3@` chỉ dạy lớp này; các tài khoản khác không
thấy lớp.
