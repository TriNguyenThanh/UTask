# Tích hợp đầy đủ Work Service vào apps/web (Phase 10–15, không gồm AI)

Tài liệu viết bằng tiếng Việt theo quy ước repo. Tên kỹ thuật giữ nguyên tiếng Anh.

## Context

Phase 9 (đã commit `d4ce718`) đã nối **Project** của Work Service vào `apps/web` sau cờ `isRealService("work")`. Phần còn lại của Work vẫn chạy MSW demo: Board, Backlog, Code, Settings hiện `WorkModuleNotIntegrated`; My Work, Notifications, Settings tài khoản luôn MSW. Yêu cầu: lập kế hoạch tích hợp **toàn bộ** Work Service, chia phase, theo đúng quy ước đã dùng ở Phase 5–9. Kết thúc: ở chế độ `VITE_REAL_SERVICES` có `work`, mọi màn hình Work (trừ AI) chạy API thật.

**Phần AI làm cuối cùng, trong một plan riêng, cùng lúc với API của AI Service.** Trong plan này, mọi điểm chạm AI giữ nguyên trạng thái hiện tại (nút tắt hoặc `WorkModuleNotIntegrated`), không nối nửa chừng: `POST /projects/{id}/tasks/bulk-apply-ai/`, `POST /tasks/{id}/subtasks/bulk-apply-ai/`, `POST /projects/{id}/ai-actions/apply/`, `GET /projects/{id}/ai-operations/{opId}/`, tab `/projects/:id/settings` (AI key/BYOK), `AiSubtaskAction`, `useProjectAiSettings`, nút "AI ước lượng".

Bản sao tài liệu này cũng nằm ở `docs/web/work-full-integration-plan.md` (đã tạo trước khi vào plan mode) và được link từ `docs/web/api-integration.md:275`. Khi thực thi, **tài liệu trong `docs/` là bản chuẩn**; cập nhật nó nếu phát hiện lệch.

## Môi trường và lệnh

`pnpm` hỏng trong WSL này; `node` là node.exe của Windows. Mọi lệnh chạy từ `apps/web`:

- Typecheck: `node node_modules/typescript/bin/tsc --noEmit` rồi `echo tsc=$?` (phải là 0).
- Test: `node node_modules/vitest/vitest.mjs run [đường dẫn]`.
- Build: `node node_modules/typescript/bin/tsc -b && node node_modules/vite/bin/vite.js build`.
- ESLint **không chạy được** (`node_modules/eslint/bin/eslint.js` không tồn tại); bỏ qua, ghi rõ khi báo cáo.

Cảnh báo: WSL interop thỉnh thoảng lỗi `UtilAcceptVsock:273: accept4 failed 110`; khi đó `node` không in gì và thoát 1. Dòng đó **không** phải pass; kiểm exit code.

Mỗi phase phải pass: `tsc=0`, toàn bộ vitest **cả khi có và khi không có `apps/web/.env.local`** (kiểm bằng `mv .env.local /tmp/el; <chạy test>; mv /tmp/el .env.local`), build. Không sửa `.env.local` của máy. Git: ~1100 file chỉ khác CRLF/LF → chỉ `git add` đường dẫn tường minh, **không bao giờ** `git add -A`. Không commit khi người dùng chưa xác nhận.

Tài khoản smoke staging (đã dùng ở Phase 9, **không commit vào repo**): TEACHER `vinhxuanan28@gmail.com`, STUDENT `aunhathuy28@gmail.com`, mật khẩu `Utask@123123`.

## Quy ước chung (áp dụng mọi phase)

1. **Tầng API** theo mẫu Phase 9: `src/lib/api/work/*` + test cạnh file; hook trong `src/lib/query/workHooks.ts` (khóa `workKeys.*`); handler MSW cho test trong `src/test/workHandlers.ts`. Đường dẫn thật là `/api/work/...` (`ROOT` trong `src/lib/api/work/endpoints.ts`), **không** `/api/work/api/v1` (đó là MSW demo).
2. **Chống xung đột file khi chạy song song**: ngay ở bước đầu Phase 10, tách `src/lib/api/work/endpoints.ts` thành `endpoints.projects.ts` (nội dung hiện tại), `endpoints.tasks.ts`, `endpoints.sprints.ts`, `endpoints.collab.ts`, và `endpoints.ts` chỉ `export *` cả bốn. Tương tự `workHandlers.ts` → `workHandlers.projects.ts` + `workHandlers.tasks.ts` + `workHandlers.sprints.ts` + `workHandlers.collab.ts`, `workHandlers.ts` gom lại. Mỗi phase sau chỉ sửa file của mình.
3. **Khóa lạc quan**: mọi lệnh ghi task/sprint gửi `expected_version` trong body. 409 `VERSION_CONFLICT` → invalidate `workKeys.all` và hiện "Dữ liệu đã được cập nhật bởi thao tác khác. Dữ liệu đã được tải lại, hãy thử lại."; form đang mở phải **nạp lại theo bản mới** khi `version` đổi (mẫu đã làm: `ProjectEditForm` trong `src/features/projects/routes/ProjectInfoRoute.tsx`, hàm `formValuesOf` + so `project.version !== base.version`). Không nạp lại → ô người dùng không đụng tới sẽ ghi đè thay đổi của người khác.
4. **`Idempotency-Key`** chỉ gửi ở các lệnh backend gọi `require_key`: `POST /projects/{id}/tasks/`, `POST /tasks/{id}/subtasks/`, `POST /projects/{pid}/sprints/{id}/start/`, `POST /sprints/{id}/tasks/`, `POST /sprints/{id}/close/`, `POST .../attachments/` (confirm), `POST /tasks/{id}/github-links/{linkId}/confirm/`. Tùy chọn (gửi luôn cho nhất quán): `POST /projects/{id}/github/repository/`, `POST /tasks/{id}/github-links/`, `POST .../github/request-verification/`. **Không** gửi ở PATCH, DELETE, transition, block/unblock, labels, relations. Vòng đời key theo `src/features/projects/components/CreateProjectDialog.tsx`: sinh khi mở dialog, giữ nguyên khi thử lại cùng body, sinh mới khi người dùng sửa ô sau một lần lỗi, khóa toàn bộ ô bằng `<fieldset disabled>` khi đang gửi.
5. **Dự án lưu trữ là chỉ đọc**: mọi lệnh ghi trả 400 `INVALID_OPERATION`. UI ẩn hoặc tắt nút ghi khi `project.archived_at !== null`, đồng thời vẫn ánh xạ mã lỗi đó thành "Dự án đang ở chế độ chỉ đọc."
6. **Quyền** (đọc từ `apps/work-service`): tạo/xóa/lưu trữ task, tạo epic/label/state, mọi thao tác sprint, sửa capacity = **Leader**. Sửa task, transition, block, relation, gán nhãn, tạo subtask = **Leader hoặc người được giao task đó**. Teacher **chỉ đọc**, ghi trả 403 `TEACHER_MUTATION_RESTRICTED`, riêng comment được phép (server tự gắn `is_teacher_feedback`). UI lấy vai từ `shell.myRole` (`loadProjectShell`), không tự suy từ dữ liệu khác.
7. **Phân trang** cursor một chiều, `page_size` 1–100 (`common/pagination.py`); dùng `collectAllPages` và `MAX_PAGE_SIZE` ở `src/lib/api/pagination.ts`. `GET /projects/{id}/states/` trả hết, `next_cursor` luôn `null`; không hiện nút "tải thêm" cho states.
8. **`VALIDATION_ERROR` thường có `details` rỗng** → `fieldErrors` rỗng. Luôn kiểm phía client trước khi gửi, và khi lỗi server không gắn được vào ô nào thì hiện `error.message` ở đầu form. Không để lỗi của một ô không có chỗ hiển thị bị nuốt (mẫu `mapError` + `FIELD_ERROR_KEYS` trong `CreateProjectDialog.tsx`).
9. **Tên hiển thị đến từ `UserProjection` đồng bộ qua Kafka**, có thể rỗng. Khi `display_name` rỗng thì tra lại qua `users/batch` như Phase 9 (`useUserNames`), fallback "Chưa rõ tên".
10. **Mock test phải khớp thứ tự kiểm của backend.** Backend kiểm quyền ghi (dự án/task lưu trữ → `INVALID_OPERATION`) **trước** khi so version. Viết `workHandlers.*` theo đúng thứ tự đó.
11. **Mỗi hàm mới có unit test trong cùng thay đổi** (AGENTS.md): endpoint (đường dẫn, body, header), adapter (nhánh null/rỗng), loader (lời gọi phụ lỗi không làm hỏng lời gọi chính), component (hành vi quan sát được, không test wiring). Không xóa test demo; chế độ demo vẫn phải chạy.
12. **Không render `description_html`.** Repo `apps/web` **không có** thư viện sanitize (đã kiểm `package.json` và toàn bộ `src`: không có `dompurify`, không có hàm `sanitize`). Hiển thị mô tả bằng `description_stripped` (text thuần, server tự sinh). Khi gửi lên, đặt `description_html` bằng đúng text người dùng nhập (textarea, không rich text). Nếu sau này cần rich text thì mở plan riêng.

## Quyết định thiết kế bắt buộc

Ba quyết định này chạm kiểu dùng chung, phải làm xong trong Phase 10 bước 1–2 trước khi nối API.

**D1. Cột Board dựng từ `State` của dự án, bỏ 4 cột cố định.**
Backend cho dự án tùy biến state, 6 nhóm `BACKLOG|UNSTARTED|STARTED|REVIEW|COMPLETED|CANCELLED`; 5 state mặc định khi tạo dự án là Backlog, To Do, In Progress, Code Review, Done (`apps/work-service/apps/projects/services/projects.py:22`). UI demo cố định 4 cột (`COLUMNS` trong `src/features/projects/issueMeta.ts:4`).
Thực hiện: thêm `states: ProjectState[]` vào `ProjectWorkspace`; `ProjectState = { id: string; name: string; color: string; sequence: number; group: StateGroup; isDefault: boolean }`. `Issue` thêm `statusId: string` và `stateGroup: StateGroup`, **giữ** `status: IssueStatus` để component demo không phải viết lại (adapter thật suy `status` từ `group`: `BACKLOG|UNSTARTED→"todo"`, `STARTED→"in-progress"`, `REVIEW→"review"`, `COMPLETED→"done"`, `CANCELLED→"done"`). Board render cột từ `workspace.states` sắp tăng dần theo `sequence`; **ẩn** cột có `group === "CANCELLED"` và không cho kéo thả vào đó. Fixture demo (`src/mocks/data/studentFlow.ts`) sinh 4 state giả có `id` ổn định để test demo vẫn xanh.

**D2. Thứ hạng là số thực `sort_order`, không phải chuỗi.**
`Issue.rank` đổi `string` → `number`. `compareByRank` trong `src/features/projects/lib/rank.ts` so sánh số; `rankBetween` trả trung điểm `(a+b)/2`, dùng **chỉ** cho cập nhật lạc quan trước khi server trả giá trị thật. Di chuyển thẻ gọi `PATCH /tasks/{id}/transition/` với `previous_task_id`/`next_task_id` là hàng xóm hiện tại trong cột đích; server tự tính trung điểm và tự tái cân bằng cột. Cột đích **không rỗng** mà gửi cả hai neighbor `null` → 409; luôn gửi ít nhất một neighbor. Cột rỗng thì gửi cả hai `null`.

**D3. Board và Backlog đọc từ `GET /projects/{id}/tasks/`, không dùng `GET /projects/{id}/kanban/`.**
Thẻ kanban chỉ trả `id, code, title, sort_order, version`, thiếu assignee/ưu tiên/điểm/epic nên không dựng được `IssueCard`. Dùng `GET /projects/{id}/tasks/?expand=state,epic,labels,assignees` và `collectAllPages` (tối đa `DEFAULT_MAX_PAGES` 50 × 100 = 5000 task; vượt thì `collectAllPages` ném "Danh sách quá dài để tải hết." — hiện nguyên văn lỗi đó). `board_revision` chỉ xuất hiện trong phản hồi transition và **không dùng** để điều khiển UI.

**D4. Task không mang `sprint_id`.** `TaskSerializer` không có trường sprint. Dựng quan hệ task↔sprint bằng cách gọi `GET tasks?sprint_id=<id>` cho mỗi sprint `DRAFT` và `ACTIVE`, cộng `sprint_id=none` cho backlog; sprint `COMPLETED` chỉ tải khi người dùng mở. Trả về map `sprintIdByTaskId`. Chi phí 1 + S lời gọi mỗi lần tải workspace.

**D5. Đổi sprint và đổi cột là hai lời gọi, không nguyên tử.** Demo gộp vào một `move`. Thật: `PATCH /tasks/{id}/transition/` cho cột/thứ hạng, và `POST /sprints/{id}/tasks/` (`action: ADD|REMOVE`, có `Idempotency-Key`, `scope_change_reason` bắt buộc khi sprint `ACTIVE`) cho sprint. Thứ tự: đổi sprint trước, đổi cột sau. Nếu bước hai lỗi → invalidate `workKeys.all` và hiện "Đã đổi sprint nhưng chưa đổi cột, hãy thử lại."; nếu bước một lỗi thì dừng, không gọi bước hai.

**D6. Epic không có màu và không có số task.** `EpicSerializer` chỉ có `id, project_id, name, description, lead_user_id, status, start_date, target_date, created_at, updated_at, deleted_at`. Màu suy từ `id` bằng hàm thuần `epicColor(id)`: tổng mã ký tự modulo một bảng 8 màu Tailwind cố định. `issueCount` đếm phía client từ task đã tải.

## Approach

### Phase 10 — Workspace chỉ đọc (Board + Backlog)

Phụ thuộc: không. Là nền của mọi phase sau.

1. Tách file theo quy ước 2 (chỉ di chuyển code, không đổi hành vi). Chạy `tsc` + vitest để chắc không vỡ.
2. Áp D1, D2, D6 vào kiểu và component demo: `src/features/projects/types.ts`, `issueMeta.ts`, `lib/rank.ts`, `lib/optimistic.ts`, `lib/moveIntent.ts`, `dnd/boardDnd.ts`, `dnd/backlogDnd.ts`, `components/IssueCard.tsx`, fixture `src/mocks/data/studentFlow.ts`, handler `src/mocks/handlers/studentFlow.ts`. Chạy lại toàn bộ vitest; khoảng 10 file test demo (`KanbanBoard`, `BacklogDnd`, `ProjectWorkspaceLayout`, `StudentFlow`, `StudentFlowRegression`, `MultiMembershipAccess`, `MyWork`, `projectIssues`, `TeacherWorkspace`, `TaskRow`) phải xanh. Commit riêng bước này trước khi nối API.
3. `src/lib/api/work/dto.ts`: thêm `StateDto` (`id, project_id, name, slug, color, sequence, group, is_default, created_at`), `EpicDto`, `LabelDto` (`id, project_id, name, color, description`), `SprintDto` (`id, project_id, name, goal, status, start_date, end_date, sort_order, version, started_at, closed_at, created_at, updated_at, archived_at`), `TaskDto` (đủ các trường của `TaskSerializer`: `id, project_id, sequence_id, code, epic_id, state_id, parent_id, type, source, acceptance_criteria, version, title, description_html, description_stripped, priority, story_points, due_date, is_blocked, blocked_reason, sort_order, created_by_user_id, completed_at, created_at, updated_at, archived_at, deleted_at, assignee_ids, label_ids, subtasks_count, comments_count, attachments_count`), `TaskDetailDto` (thêm `state, epic, labels, assignees, relations, subtasks, attachments`), `RelationDto` (`id, related_task_id, related_task_code, relation_type`).
4. `endpoints.tasks.ts`: `listStates(client, projectId)`, `listEpics`, `listLabels`, `listTasks(client, projectId, filters, cursor)`, `getTask(client, taskId)`. `filters` chỉ gửi khóa có giá trị (tham số lạ → 422). Khóa hợp lệ: `state_id, epic_id, parent_id, type, priority, is_blocked, due_date_from, due_date_to, assignee_id, label_id, search, sprint_id, status, fields, expand, cursor, page_size`. `sprint_id` nhận UUID hoặc đúng chuỗi `"none"`. `expand` trên **danh sách** chỉ được `state,epic,labels,assignees`; `relations,subtasks,attachments,github_links` chỉ dùng ở `getTask` (danh sách sẽ 422). `getTask` ở phase này **không** gửi `github_links` (503 nếu app integrations vắng).
5. `endpoints.sprints.ts`: `listSprints(client, projectId, status?)`.
6. `adapters.ts`: `stateToColumn`, `taskToIssue` (áp D1 map `group`→`status`, D2 `sort_order`→`rank`), `sprintToView` (`DRAFT→"upcoming"`, `ACTIVE→"active"`, `COMPLETED→"completed"`), `epicToView` (D6), `taskToIssueDetail` (mô tả lấy `description_stripped`, theo quy ước 12).
7. `loaders.ts`: `loadWorkspace(client, projectId)` trả `ProjectWorkspace`. Gọi song song tối đa 5 (mẫu `loadMembers` trong `src/lib/api/classroom/teacherLoaders.ts`). `states`, `tasks`, `sprints` lỗi → ném (không có thì không dựng được màn hình). `epics`, `labels`, `members` lỗi → bỏ phần đó và đặt `partial: true`. Áp D4 để gắn `sprintId` cho từng issue.
8. `workHooks.ts`: `useWorkspaceReal(projectId)` khóa `workKeys.workspace(projectId)`, `useIssueDetailReal(taskId)` khóa `workKeys.task(taskId)`. Khóa phải khác hook demo.
9. `ProjectBoardRoute.tsx` và `ProjectBacklogRoute.tsx`: thay nhánh `WorkModuleNotIntegrated` bằng component thật (`RealBoard`, `RealBacklog`) dùng lại `IssueCard`, `IssueFilterBar`, `IssuePanel` với prop `readOnly` (phase này luôn `readOnly`). Nhánh demo giữ nguyên. Kiểm tra `isRealService("work")` **không được** nằm sau bất kỳ hook nào (lỗi đã gặp ở `RequireProjectManagePermission`): tách component con cho nhánh demo.
10. `RealProjectLayout.tsx`: thêm tab Board và Backlog vào thanh điều hướng; Code và Settings vẫn `WorkModuleNotIntegrated`.
11. `useIssueMover` hiện tắt ghi theo `demoWritesEnabled()` (`VITE_ENABLE_MOCKS === "true"`); đổi thành prop `canWrite` do route truyền vào, demo truyền `demoWritesEnabled()`, thật truyền `false` ở phase này.
12. Bộ lọc `IssueFilterBar` vẫn lọc phía client trên danh sách đã tải (giữ hành vi demo), `search` không gọi server.
13. Test mới: `endpoints.tasks.test.ts`, `endpoints.sprints.test.ts`, `adapters` bổ sung, `loaders` bổ sung (nhánh `partial`, lỗi `tasks` ném), `src/features/projects/RealBoard.test.tsx` (cột dựng từ state, ẩn cột `CANCELLED`, thẻ xếp theo `sort_order`, lọc, mở panel, dự án lưu trữ không có nút ghi), `src/features/projects/RealBacklog.test.tsx` (nhóm theo sprint D4, backlog lấy `sprint_id=none`).

### Phase 11 — Ghi task cốt lõi

Phụ thuộc: Phase 10.

1. `endpoints.tasks.ts`: `createTask` (Idempotency-Key), `patchTask` (chỉ gửi khóa đổi + `expected_version`), `transitionTask`, `blockTask`, `unblockTask`, `createSubtask` (Idempotency-Key). `PatchTaskSerializer` **không nhận** `state_id`, `type`, `parent_id`, `source`; đổi cột phải qua `transition`.
2. `CreateIssueDialog` theo mẫu `CreateProjectDialog`: `title` bắt buộc ≤300; `type` ∈ `TASK|BUG|STORY` (không có `SUBTASK`); `priority` ∈ `LOW|MEDIUM|HIGH|URGENT` mặc định `MEDIUM`; `story_points` số nguyên ≥0 hoặc rỗng; `due_date`; `state_id` để trống thì server dùng state mặc định; `epic_id`; `assignee_ids` ≤100 chọn từ thành viên `ACTIVE`; `label_ids` ≤100; `description_html`; `acceptance_criteria` ≤100000. Chỉ Leader thấy nút. Bật nút "Tạo Issue" ở `ProjectBoardRoute.tsx:168` (đang `disabled title="Chưa có API tạo issue"`).
3. Kéo thả Board: `useIssueMover` gọi `transitionTask` với neighbors theo D2; cập nhật lạc quan bằng `applyIssuePatch` rồi ghi `version` từ phản hồi bằng `applyServerVersion`; lỗi thì hoàn tác và invalidate.
4. `IssuePanel` ở chế độ thật: sửa `title`, `description_html`, `acceptance_criteria`, `priority`, `story_points`, `due_date`, `epic_id`, `assignee_ids`, `label_ids` qua `patchTask`. Thành viên không phải Leader chỉ sửa được task mình được giao; UI tắt phần còn lại nhưng vẫn ánh xạ 403.
5. Chặn/bỏ chặn: `blockTask` cần `blocked_reason` ≤10000, không áp dụng cho task thuộc nhóm `COMPLETED`/`CANCELLED` (UI ẩn nút, server trả lỗi thì hiện message).
6. Subtask: tạo từ `IssuePanel`. Thành viên không phải Leader chỉ đặt được `title`, `description_html`, `acceptance_criteria`; server tự ép `assignee` là chính họ, `due_date` kế thừa từ cha, `story_points` thành `null` — UI ẩn các ô đó cho vai thành viên. Toggle "xong" của subtask gọi `transitionTask` sang state có `group === "COMPLETED"` có `sequence` nhỏ nhất.
7. `src/features/projects/lib/moveErrors.ts`: bổ sung ánh xạ mã lỗi Work sang tiếng Việt: `VERSION_CONFLICT`, `INVALID_OPERATION` ("Dự án đang ở chế độ chỉ đọc."), `TEACHER_MUTATION_RESTRICTED` ("Giảng viên chỉ xem, không sửa được."), `VALIDATION_ERROR`, 403 chung, 404 chung.
8. `canWrite` ở `RealBoard`/`RealBacklog` đổi thành `myRole === "LEADER" || issue.isMine` theo từng thao tác (quy ước 6).
9. Test: endpoint (body chỉ chứa khóa đổi; header key đúng chỗ và vắng ở PATCH), dialog (vòng đời key, kiểm client, lỗi server không gắn ô), mover (neighbors đúng, hoàn tác khi 409, ba bậc quyền), panel (form nạp lại sau `VERSION_CONFLICT`), `workHandlers.tasks.ts` mô phỏng transition (neighbor cũ → 409; cột không rỗng mà thiếu neighbor → 409).

### Phase 12 — Epic, Label, Relation, lưu trữ/xóa/khôi phục task

Phụ thuộc: Phase 11. Độc lập với Phase 13 và 14.

1. `endpoints.tasks.ts`: `createEpic`, `patchEpic`, `deleteEpic`, `createLabel`, `patchLabel`, `deleteLabel`, `setTaskLabels` (`action: ADD|REMOVE`, `label_ids` 1–100, `expected_version`), `createRelation`, `deleteRelation`, `archiveTask`, `unarchiveTask`, `deleteTask`, `restoreTask`.
2. `CreateEpicDialog`: `name` ≤200, `description` ≤100000, `lead_user_id`, `status` ∈ `PLANNED|IN_PROGRESS|COMPLETED|CANCELLED`, `start_date`, `target_date`. Client chặn `start_date > target_date` trước khi gửi (backend ràng buộc ở cả DB lẫn service, trả `VALIDATION_ERROR` `details` rỗng). Bật nút "Tạo Epic" ở `ProjectBacklogRoute.tsx:548` (đang `disabled title="Chưa có API tạo Epic"`).
3. Sửa/xóa epic: Leader làm mọi thứ; `lead_user` chỉ sửa `name`, `description`, `status` — UI tắt ba ô ngày và ô lead cho vai đó.
4. Nhãn: tạo/sửa/xóa (Leader) trong một dialog quản lý nhãn mở từ Backlog; gán/bỏ nhãn trong `IssuePanel`. Xóa nhãn gỡ khỏi mọi task → invalidate `workKeys.all`.
5. Relation trong `IssuePanel`: chọn `BLOCKS|BLOCKED_BY|DUPLICATE|RELATES_TO` + task đích. Backend chuẩn hóa lưu trữ và trả về theo góc nhìn của task đang xem, nên UI hiển thị thẳng `relations` từ `getTask`. Vòng chặn trả 409 `DAG_CYCLE` → "Liên kết này tạo vòng chặn."
6. Lưu trữ/mở lại/xóa/khôi phục task (Leader): nút trong `IssuePanel` + `ConfirmDialog` (`src/components/feedback/ConfirmDialog.tsx`, có props `open,title,description,confirmLabel,destructive,pending,onConfirm,onCancel`; render `role="dialog"`, không phải `alertdialog`). Thêm bộ chọn phạm vi ở Backlog: `active` (mặc định) | `archived` | `deleted`, truyền vào `status` của `listTasks`. Xóa là xóa mềm và cascade cả cây con; khôi phục lỗi nếu cha còn bị xóa hoặc state đã bị xóa → hiện `error.message` của server.
7. **Không làm UI đổi cha task**: service `reparent_task` (`apps/work-service/apps/tasks/services/hierarchy.py:23`) không có URL. `type` cũng không sửa được sau khi tạo.
8. Test: dialog epic (ràng buộc ngày, quyền của `lead_user`), 409 vòng chặn, luồng xóa→khôi phục, xóa nhãn làm mới workspace.

### Phase 13 — Sprint, progress, burndown, dashboard, capacity

Phụ thuộc: Phase 11. Độc lập với Phase 12 và 14.

1. `endpoints.sprints.ts`: `createSprint` (Leader), `patchSprint`, `startSprint` (key), `setSprintScope` (key), `closeSprint` (key), `getSprintProgress`, `getSprintBurndown`. `endpoints.projects.ts`: `getProjectDashboard`, `patchMemberCapacity`.
2. Quản lý sprint ở Backlog: tạo (`name` ≤200, `goal`, `start_date`, `end_date`), sửa (`expected_version`; sprint `COMPLETED` bất biến → ẩn nút sửa), **Bắt đầu** (cần cả hai ngày; 409 `ACTIVE_SPRINT_EXISTS` → "Đã có sprint đang chạy."), **Kết thúc** (`target_sprint_id` là sprint `DRAFT` cùng dự án hoặc `null` = trả về backlog; hiện `summary` trong phản hồi).
3. Thêm/bớt task khỏi sprint (D5): kéo thả ở Backlog hoặc menu trong `IssueActionsMenu`. Sprint `ACTIVE` bắt buộc `scope_change_reason` (422 `SCOPE_CHANGE_REASON_REQUIRED`) — ô lý do đã có trong luồng demo `BacklogDnd`. Phản hồi có `is_scope_creep` → hiện cảnh báo, không chặn. Task đang nằm trong sprint mở khác → 422 `INVALID_OPERATION` → "Task đang thuộc sprint khác."
4. Progress và burndown hiển thị ở đầu Backlog cho sprint `ACTIVE`. Đường lý tưởng của burndown **tự tính phía client** từ `start_date`/`end_date` và `scope_work_item_count` của ngày đầu (backend không trả). Sprint `DRAFT` trả `days: []` → hiện "Sprint chưa bắt đầu." `window_truncated === true` → ghi chú "Chỉ hiện 731 ngày gần nhất." Mọi số tiến độ lấy từ server, UI **không** tự tính lại.
5. Dashboard dự án: thêm khối "Tổng quan" vào `ProjectInfoRoute` (chế độ thật). `GET /projects/{id}/dashboard/` **không nhận bất kỳ query param nào** (có param → 422). Hiện `totals`, `state_distribution`, `assignee_distribution` (kèm `weekly_capacity`), `unassigned_estimate_points`. Phần trăm dùng capacity tự tính phía client từ `allocated_estimate_points / weekly_capacity`, ghi rõ là ước lượng.
6. Capacity: Leader sửa `weekly_capacity` (số nguyên 0..2147483647) ngay trong `MembersTable` của `ProjectInfoRoute`. 422 `MEMBER_NOT_ACTIVE` → "Thành viên không còn hoạt động."
7. Test: ACTIVE_SPRINT_EXISTS, thiếu lý do khi sprint ACTIVE, `expected_version` sai, close có và không có `target_sprint_id`, burndown rỗng và `window_truncated`, dashboard gọi không kèm param, capacity chỉ Leader.

### Phase 14 — Comment, activity, attachment, GitHub

Phụ thuộc: Phase 11. Độc lập với Phase 12 và 13.

1. `endpoints.collab.ts`: `listTaskComments`, `listProjectComments`, `createComment`, `patchComment`, `deleteComment`, `listTaskActivities`, `presignAttachment`, `confirmAttachment` (key), `listAttachments`, `getAttachmentDownloadUrl`, `deleteAttachment`, `getRepository`, `selectRepository`, `listTaskGithubLinks`, `createGithubLink`, `confirmGithubLink` (key), `deleteGithubLink`, `patchMemberGithubUsername`, `requestGithubVerification`.
2. **Comment**: `IssuePanel` hiện comment thật và ô soạn thật. `POST /comments/` nhận **đúng một** trong `task_id` hoặc `project_id`. `content_html` ≤100000 (gửi text thuần theo quy ước 12), `mentioned_user_ids` ≤100 và phải là thành viên `ACTIVE` hoặc giảng viên đã xác minh (ngược lại 422). Sửa/xóa comment của mình; Leader xóa được mọi comment. `is_teacher_feedback` chỉ để hiển thị huy hiệu, không gửi lên. `FeedbackComposer` của giảng viên (hiện chỉ lưu nháp cục bộ) chuyển sang gọi `createComment`.
3. **Activity**: thay `IssueDetail.history[]` demo bằng `GET /tasks/{id}/activities/`. `old_value`/`new_value` là text thô (JSON đã tuần tự hóa) → `parseActivityValue` thử `JSON.parse`, lỗi thì trả nguyên văn chuỗi. Không có activity cấp dự án.
4. **Attachment** (màn mới trong `IssuePanel`): presign → `PUT` thẳng lên Cloudflare R2 với đúng `headers` server trả → `POST` confirm (key). Kiểm phía client trước: `content_type` ∈ `image/jpeg, image/png, image/webp, application/pdf, application/zip, text/plain, application/json`; `file_size` 1..26214400. Bản ghi presign hết hạn sau 900 giây; confirm muộn → 422 → cho chọn lại file. Tải xuống: gọi lấy `download_url` (hạn 300 giây) rồi mở, không cache. 503 → "Kho lưu trữ chưa sẵn sàng, hãy thử lại." và **không** tự retry.
   - **CORS của R2 cho origin web chưa xác minh.** Bước đầu của phase: smoke tay một lần (presign + `PUT` từ trình duyệt). Nếu `PUT` bị CORS chặn → dừng phần attachment, ghi B30 vào `docs/web/api-integration.md`, giữ `IssuePanel` không có khối đính kèm, và làm tiếp mục 5–7 của phase.
5. **GitHub repository** (Leader): `POST /projects/{id}/github/repository/` cần `github_repo_id` (bắt buộc **kể cả khi ngắt kết nối** — gửi id hiện tại), `operation_id`, `expected_connection_generation`. Gửi `Idempotency-Key` (header thắng `operation_id`). 202 → trạng thái `PENDING` → poll `GET` mỗi 2 giây, tối đa 30 giây, rồi hiện "Đang xử lý, hãy tải lại sau." 409 → generation đã đổi, tải lại rồi thử lại.
   - Work **không** gọi GitHub API trực tiếp, nên **không có API liệt kê repo để chọn**. UI dùng ô nhập `github_repo_id` thủ công và ghi rõ nguồn id. Không tự gọi Integration Service.
6. **GitHub link của task**: tạo (`link_type` ∈ `BRANCH|COMMIT|PULL_REQUEST`; `github_ref_id` ≤300, riêng PR phải là số nguyên dương, tự bỏ `#` đầu), confirm (server từ chối nếu `is_verified === false`), xóa. Chỉ thêm `github_links` vào `expand` của `getTask` khi `repository.status === "CONNECTED"`; app integrations vắng → 503.
7. **Username GitHub**: chỉ chính chủ sửa (`actor.id === user_id`); đã `is_github_verified` mà đổi → 422 "Phải xác minh lại qua GitHub." Leader gọi `request-verification`.
8. **Tab Code** (`ProjectCodeRoute`) ở chế độ thật: hiện trạng thái repo (`status`, `github_repo_owner`, `github_repo_name`, `github_default_branch`, `synced_at`) và nút kết nối/ngắt cho Leader. Work **không có** commit, branch, contributor, PR, thống kê → các khối đó hiện "Chưa khả dụng", **không** dựng số liệu. Nhánh demo giữ nguyên `ProjectCode`.
9. Test: comment (mention 422, huy hiệu giảng viên, quyền xóa của Leader), attachment (kiểm client, presign hết hạn, confirm lỗi), repository (202 rồi poll, 409 generation), link (PR không hợp lệ, chưa `is_verified`), `parseActivityValue` với chuỗi không phải JSON.

### Phase 15 — My Work, sidebar, giảng viên

Phụ thuộc: Phase 13 và 14 (và 12 nếu Backlog đã đổi).

1. **My Work** (`/my-work`): Work **không có** API tổng quan và không có truy vấn task xuyên dự án. Làm bằng fan-out: `GET /projects/?scope=all` rồi với mỗi dự án gọi `GET tasks?assignee_id=<me>&status=active`, song song tối đa 5; sprint `ACTIVE` của mỗi dự án lấy `progress` cho khối `CourseSprint`. Một dự án lỗi → bỏ dự án đó, đặt `partial: true`, hiện chú thích "Một phần dữ liệu chưa tải được."; không làm hỏng cả trang. Khối `GitHubActivity` và `semester/enrollments` không có nguồn thật trong Work → ẩn ở chế độ thật. Ghi B20 vào `docs/web/api-integration.md`.
2. **Sidebar**: thay `ProjectSummary` demo bằng `useProjectCards` thật (đã có từ Phase 9) khi `isRealService("work")`.
3. **Giảng viên**: trang theo dõi nhóm/dự án đọc `getProjectDashboard` + progress của sprint `ACTIVE` thay cho chữ "chưa khả dụng": số task quá hạn (`overdue_task_count`), tiến độ, sprint hiện tại. Workspace giảng viên dùng chính `RealBoard`/`RealBacklog` với `canWrite={false}`, cộng quyền comment (Phase 14).
4. Gỡ `WorkModuleNotIntegrated` cho `board`, `backlog`, `code`; **giữ** cho `settings` (chờ plan AI).
5. Test: aggregator My Work (một dự án lỗi không làm hỏng tổng, `partial` bật), màn giảng viên (không có nút ghi, comment vẫn gửi được).

## Critical files & anchors

| File | Vùng | Lý do |
|---|---|---|
| `apps/web/src/features/projects/types.ts` | `Issue`, `ProjectWorkspace`, `Epic`, `Sprint` | D1/D2/D6 sửa ở đây trước, mọi thứ khác theo sau |
| `apps/web/src/features/projects/components/CreateProjectDialog.tsx` | `mapError`, `FIELD_ERROR_KEYS`, `markFieldChange`, `<fieldset disabled>` | Mẫu chuẩn cho vòng đời `Idempotency-Key` và ánh xạ lỗi |
| `apps/web/src/features/projects/routes/ProjectInfoRoute.tsx` | `formValuesOf`, so `project.version !== base.version` | Mẫu chuẩn nạp lại form sau `VERSION_CONFLICT` |
| `apps/web/src/test/workHandlers.ts` | thứ tự kiểm archived trước version | Mock sai thứ tự sẽ khiến test xanh nhưng staging đỏ |
| `apps/work-service/apps/tasks/urls.py`, `apps/sprints/urls.py`, `apps/projects/urls.py` | toàn bộ `urlpatterns` | Nguồn chuẩn của đường dẫn; đọc lại trước mỗi phase |

## Verification

Chạy từ `apps/web`. Sau **mỗi** phase:

1. `node node_modules/typescript/bin/tsc --noEmit; echo tsc=$?` → `tsc=0`.
2. `node node_modules/vitest/vitest.mjs run` → tất cả xanh. Rồi `mv .env.local /tmp/el && node node_modules/vitest/vitest.mjs run; mv /tmp/el .env.local` → cũng tất cả xanh, cùng số test. (Mốc hiện tại: 59 file / 836 test.)
3. `node node_modules/typescript/bin/tsc -b && node node_modules/vite/bin/vite.js build` → `✓ built`.

Chứng minh hành vi mới (smoke staging thật, đăng nhập bằng tài khoản ở mục Môi trường, bật `VITE_REAL_SERVICES=auth,classroom,work` trong một `.env.test.local` tạm rồi xóa):

- Phase 10: mở `/projects/<id>/board` → thấy đúng số cột bằng số state không phải `CANCELLED`, thẻ xếp theo `sort_order` tăng dần; `/backlog` → nhóm sprint đúng và mục "Backlog" chứa task không thuộc sprint nào. Không có nút ghi nào bật.
- Phase 11: Leader tạo issue → thẻ xuất hiện ở cột mặc định với `code` dạng `<identifier>-<n>`; kéo sang cột khác rồi tải lại trang → vẫn ở cột mới; chặn rồi bỏ chặn; tạo subtask. Đăng nhập thành viên không phải Leader → không có nút tạo issue, vẫn kéo được task của mình. Teacher → không có nút ghi.
- Phase 12: tạo epic, gán vào issue; tạo nhãn và gán; tạo liên kết `BLOCKS` rồi tạo liên kết ngược → thấy thông báo vòng chặn; xóa task rồi khôi phục.
- Phase 13: tạo sprint → thêm 2 task → bắt đầu → thêm 1 task nữa (bắt buộc nhập lý do) → xem progress và burndown có dữ liệu → kết thúc sprint chuyển sang sprint DRAFT mới → task chưa xong nằm ở sprint mới; đặt `weekly_capacity` cho một thành viên và thấy nó trong khối Tổng quan.
- Phase 14: gửi comment có mention một thành viên → hiện ngay; giảng viên gửi comment → có huy hiệu feedback; tải lên một file PNG nhỏ rồi tải xuống được (hoặc ghi nhận CORS chặn theo nhánh dự phòng); nhập `github_repo_id` và kết nối → trạng thái chuyển `CONNECTED` hoặc `PENDING`.
- Phase 15: `/my-work` hiện task thật của chính mình; sidebar hiện dự án thật; trang giảng viên hiện số task quá hạn thật.

Dọn sau smoke: dự án smoke chuyển sang lưu trữ (Work không có API xóa dự án); task/epic/nhãn smoke xóa mềm; xóa `.env.test.local`; khôi phục `.env.local`.

## Assumptions & contingencies

- **D1 (cột theo state) có thể tốn hơn dự kiến.** Nếu sau bước 2 của Phase 10 mà số test demo phải sửa vượt quá sức, chuyển sang phương án gộp: giữ 4 cột cố định, map mỗi cột sang state có `sequence` nhỏ nhất trong nhóm tương ứng, và ghi hạn chế "dự án có state tùy biến sẽ hiển thị gộp" vào `docs/web/api-integration.md`. Không âm thầm đổi: ghi vào tài liệu.
- **Số task mỗi dự án chưa đo.** Giả định ≤5000 nên tải hết được (D3). Nếu `collectAllPages` ném "Danh sách quá dài để tải hết." trên staging → chuyển Board sang tải theo từng cột bằng `listTasks({state_id})` và hiện "đã tải N/Tổng".
- **Số dự án mỗi sinh viên chưa đo** (ảnh hưởng fan-out My Work ở Phase 15). Nếu vượt 20 dự án làm trang chậm quá 5 giây → chỉ fan-out cho dự án chưa lưu trữ và thêm nút "Tải thêm".
- **CORS R2 chưa xác minh**: nhánh dự phòng đã ghi ở Phase 14 mục 4.
- **Integration Service có thể có API liệt kê repo**, chưa kiểm. Nếu người dùng xác nhận có, thay ô nhập `github_repo_id` thủ công bằng danh sách chọn; mặc định giữ ô nhập tay.
