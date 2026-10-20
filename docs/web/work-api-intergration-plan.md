# Phase 9 — Tích hợp Work Projects vào frontend

## Context

`apps/web` đã nối API thật cho Identity (Phase 1–4) và Classroom (Phase 5–8) sau cờ `VITE_REAL_SERVICES`; phần Work vẫn chạy MSW. Phase 9 nối **Project của Work**: danh sách dự án của tôi, vỏ dự án với trang Thông tin & thành viên, tạo dự án từ nhóm (Leader), sửa/lưu trữ dự án, và lấp các chỗ `projectId`/`project`/`teamsWithoutProject` đang để `null` từ Phase 5 và Phase 8. Board, Backlog, Sprint, Task, Comment, Dashboard, GitHub, AI **không** thuộc Phase 9: ở chế độ thật các tab đó hiển thị thông báo chưa tích hợp, không dựng số liệu giả.

Nhánh làm việc: `feat/web-real-api-integration` (HEAD `5687e6a`). Không tạo nhánh mới, không commit cho tới khi người dùng xác nhận.

## Môi trường và lệnh

`pnpm` hỏng trong WSL này; `node` là node.exe của Windows. Mọi lệnh chạy từ `apps/web`:

- Typecheck: `node node_modules/typescript/bin/tsc --noEmit` rồi `echo tsc=$?` (phải là 0).
- Test: `node node_modules/vitest/vitest.mjs run [đường dẫn]`.
- Build: `node node_modules/typescript/bin/tsc -b && node node_modules/vite/bin/vite.js build`.

Cảnh báo: WSL interop thỉnh thoảng lỗi `UtilAcceptVsock:273: accept4 failed 110`; khi đó `node` không in gì và thoát 1. Dòng lỗi đó **không** phải kết quả pass; kiểm tra exit code.

Git: working tree có ~1100 file chỉ khác CRLF/LF. Chỉ `git add` theo đường dẫn tường minh, chạy `sed -i 's/\r$//' <file>` trước khi add. Không bao giờ `git add -A`, không chạy `git status --short` không lọc.

## Hợp đồng API đã xác minh (Work OpenAPI 1.4 + mã nguồn + probe staging 19/10/2026)

Base path qua proxy Vite: `/api/work`. Mọi path Work kết thúc bằng `/`. Envelope `{success,message,data,meta,error:{code,details:[{field?,issue}]}}`.

| Endpoint | Ghi chú đã xác minh |
|---|---|
| `GET /api/work/projects/?status=&classroom_group_id=&cursor=&page_size=` | `status` ∈ `active`(mặc định)\|`archived`\|`all`; giá trị khác → 400 `VALIDATION_ERROR`. `page_size` mặc định 20, tối đa 100. `meta.pagination` như Classroom (`total_count,page_size,next_cursor,prev_cursor,has_next`); thêm `meta.scope = {partial:true, source:"WORK_MEMBERSHIP", teacher_scope:"UNAVAILABLE"}` khi Work không hỏi được Classroom. **STUDENT truyền `classroom_group_id` → 403 `PERMISSION_DENIED`** (chỉ giảng viên lọc được). Khi Classroom chết **và** có `classroom_group_id` → **503 `CLASSROOM_UNAVAILABLE`**, không phải `partial` (`apps/work-service/apps/projects/queries/projects.py:26-28`) |
| `POST /api/work/projects/` | Header `Idempotency-Key` bắt buộc (thiếu → 400 `IDEMPOTENCY_KEY_REQUIRED`; dài hơn 100 ký tự → 400 `VALIDATION_ERROR`; cùng khóa khác body → **422 `IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD`**; hai request cùng khóa chạy song song → **409 `CONCURRENT_MUTATION_IN_PROGRESS`**). Body `{classroom_group_id, identifier, name, description?, target_goals?, tech_stack?, start_date?, end_date?}`. Chỉ **LEADER ACTIVE** của nhóm → sai thì 403 `LEADER_PERMISSION_REQUIRED`. Snapshot nhóm lệch/Classroom chết → 503 `CLASSROOM_UNAVAILABLE`. 201 trả `Project` |
| `GET /api/work/projects/{id}/` | Thành viên ACTIVE hoặc giảng viên của nhóm; người khác → 404 `RESOURCE_NOT_FOUND` |
| `PATCH /api/work/projects/{id}/` | Body các trường sửa + `expected_version` (bắt buộc). Chỉ Leader. Lệch version → 409 `VERSION_CONFLICT`. Dự án đã lưu trữ → 400 `INVALID_OPERATION`. Giảng viên ghi → 403 `TEACHER_MUTATION_RESTRICTED` |
| `POST /api/work/projects/{id}/archive/` và `/unarchive/` | Body `{expected_version}`. Chỉ Leader. **Không yêu cầu `Idempotency-Key`** (`views/projects.py:70-93` không gọi `require_key`). Gọi khi trạng thái đã đúng → 200 nhưng `version` **không tăng** (`services/projects.py:160-186`) |
| `GET /api/work/projects/{id}/members/?status=&cursor=&page_size=` | `status` ∈ `ACTIVE`(mặc định)\|`LEFT`\|`REMOVED`\|`all`. Có thêm `PATCH .../members/{user_id}/capacity/` và `/github/` (chỉ Leader) — **ngoài phạm vi Phase 9** |

Ràng buộc nghiệp vụ đọc từ `apps/work-service`:

- `identifier` khớp `^[A-Z0-9]{2,10}$`, **duy nhất toàn hệ thống** → trùng trả 409 `DUPLICATE_IDENTIFIER` (`apps/work-service/common/errors.py:16`).
- Một nhóm Classroom được phép có **nhiều** project (migration `0002_multiple_group_projects` bỏ ràng buộc một project/nhóm).
- Tạo project sao chép thành viên nhóm sang `ProjectMember` và dựng 5 state mặc định. Danh sách thành viên (thêm/bớt) đồng bộ từ Classroom, Work **không** có API sửa roster; nhưng `weekly_capacity` và liên kết GitHub của thành viên **sửa được** qua hai endpoint PATCH ở trên (Leader) — Phase 9 không dùng.
- Không có API xóa project.
- `Project` **không** chứa tên môn/lớp/nhóm, không chứa tiến độ sprint.

`ProjectDto` (đầy đủ, dùng nguyên tên trường): `id, identifier, name, description, target_goals, tech_stack, start_date, end_date, classroom_group_id, class_id, group_source_version, version, board_revision, github_repo_name, github_repo_id, github_connection_status, github_synced_at, created_at, updated_at, archived_at`.

`ProjectMemberDto`: `id, user_id, display_name, avatar_url, role ("LEADER"|"MEMBER"), status ("ACTIVE"|"LEFT"|"REMOVED"), weekly_capacity, github_username, github_user_id, is_github_verified, joined_at, left_at, updated_at`.

Nullability đã đối chiếu serializer (dùng đúng cho `dto.ts`): `string | null` cho `class_id, start_date, end_date, archived_at, github_repo_name, github_repo_id, github_connection_status, github_synced_at`; `description, target_goals` luôn là chuỗi (có thể rỗng), không `null`; `tech_stack: Record<string, unknown>`. `ProjectMemberDto`: `avatar_url, github_username, github_user_id, left_at` có thể `null`; `display_name` luôn là chuỗi.

Mã lỗi phải xử lý ở mọi lệnh ghi: `VERSION_CONFLICT` (409) ≠ `CONCURRENT_MUTATION_IN_PROGRESS` (409) ≠ `IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD` (422). Chỉ `VERSION_CONFLICT` mới hiện câu "đã được cập nhật bởi thao tác khác"; hai mã còn lại hiện "Yêu cầu trước đó đang được xử lý, hãy chờ rồi thử lại." Mọi lệnh đọc có thể trả 503 `CLASSROOM_UNAVAILABLE` → hiện `ErrorState` với `error.message`, không coi là lỗi frontend.

Trạng thái staging lúc lập kế hoạch: `GET /api/work/projects/` trả rỗng cho cả STUDENT, TEACHER, SYSTEM_ADMIN. Chưa có project nào.

## Approach

Thứ tự dưới đây giữ cây build được và test cũ pass sau mỗi bước. Bước 1–3 độc lập với UI; bước 4–8 phụ thuộc bước 1–3; bước 9 phụ thuộc bước 1–2.

Nguyên tắc chung áp dụng cho mọi bước, theo đúng cách Phase 5–8 đã làm: **không sửa kiểu và component của chế độ demo**; chế độ thật dùng component `Real*` riêng, chọn bằng `isRealService("work")` ngay trong `Component()` của route (mẫu có sẵn: `apps/web/src/features/courses/routes/CourseTeamRoute.tsx:1022-1025`, `apps/web/src/features/teacher/components/RealTeamDetail.tsx`). Không cập nhật lạc quan. `Idempotency-Key` sinh **một lần cho mỗi ý định của người dùng** (lúc mở dialog / lúc form chuyển sang trạng thái gửi), gửi lại **cùng** khóa khi bấm "Thử lại", sinh khóa mới khi nội dung form đổi.

### 1. Tầng API Work

Tạo `src/lib/api/work/dto.ts`: `ProjectDto`, `ProjectMemberDto`, `ProjectMemberRole = "LEADER" | "MEMBER"`, `ProjectMemberStatus = "ACTIVE" | "LEFT" | "REMOVED"`, `ProjectStatusFilter = "active" | "archived" | "all"` — đúng tên trường trong bảng hợp đồng trên. Ghi chú đầu file: nguồn Work OpenAPI 1.4, đối chiếu 19/10/2026.

Tạo `src/lib/api/work/endpoints.ts` với `const ROOT = "/api/work"`. Sao chép đúng mẫu `src/lib/api/classroom/endpoints.ts:29-45` (`PageQuery`, `listUrl`, `fetchPage` dùng `client.requestEnvelope` + `collectAllPages` + `MAX_PAGE_SIZE` từ `src/lib/api/pagination.ts`) — giữ bản cục bộ trong file Work, **không** tách helper dùng chung, vì query của Work có thêm `classroom_group_id` và `meta` khác kiểu (`WorkListMeta`). Chữ ký:

```ts
export interface WorkListMeta extends ListMeta {
  scope?: { partial: boolean; source: "WORK_MEMBERSHIP"; teacher_scope: "UNAVAILABLE" };
}
export interface ProjectListResult { projects: ProjectDto[]; partial: boolean }

export async function listProjects(client: ApiClient, status: ProjectStatusFilter): Promise<ProjectListResult>
export async function getProject(client: ApiClient, projectId: string): Promise<ProjectDto>
export function listProjectMembers(client: ApiClient, projectId: string, status?: ProjectMemberStatus): Promise<ProjectMemberDto[]>
export async function createProject(client: ApiClient, input: CreateProjectInput & { idempotencyKey: string }): Promise<ProjectDto>
export async function patchProject(client: ApiClient, projectId: string, input: PatchProjectInput & { expectedVersion: number }): Promise<ProjectDto>
export async function setProjectArchived(client: ApiClient, projectId: string, input: { archived: boolean; expectedVersion: number }): Promise<ProjectDto>

export interface CreateProjectInput {
  classroomGroupId: string; identifier: string; name: string;
  description: string; targetGoals: string; startDate: string | null; endDate: string | null;
}
export interface PatchProjectInput {
  name?: string; description?: string; targetGoals?: string; startDate?: string | null; endDate?: string | null;
}
```

Chi tiết bắt buộc:

- `listProjects` tự phân trang hết bằng `collectAllPages` với `page_size=100`, đồng thời đọc `meta.scope?.partial === true` ở **trang đầu**; vì `collectAllPages` chỉ trả mảng, viết vòng lặp cursor riêng trong `listProjects` (giống `collectAllPages` nhưng giữ `meta`), trả `{ projects, partial }`. Trang không có `scope` → `partial: false`.
- `listProjects` **không** nhận `classroom_group_id`: sinh viên truyền vào sẽ bị 403, còn giảng viên tự lọc phía client sau khi tải tất cả. Ghi comment nêu lý do (B16).
- `createProject` gửi body snake_case `{classroom_group_id, identifier, name, description, target_goals, start_date, end_date, tech_stack: {}}`. `tech_stack` luôn `{}`: OpenAPI chỉ khai báo `object` tự do, chưa có cấu trúc (B17).
- `patchProject` chỉ đưa vào body các khóa `!== undefined`, cộng `expected_version`. Không gửi `tech_stack`.
- `setProjectArchived` gọi `/archive/` khi `archived === true`, `/unarchive/` khi `false`; body `{expected_version}`. **Không gửi `Idempotency-Key`**: backend không đăng ký receipt cho hai path này (`views/projects.py:70-93`), gửi header chỉ gây hiểu nhầm là có dedupe. Bấm lại sau khi mất phản hồi sẽ ra 409 `VERSION_CONFLICT` — xử lý bằng invalidate + thông báo, không tự gửi lại. Sau khi thành công phải đọc `version` từ phản hồi (no-op không tăng `version`), không tự cộng 1.
- Mọi hàm dùng `encodeURIComponent` cho id, giống `classroom/endpoints.ts`.

### 2. Adapter Work → kiểu hiển thị

Tạo `src/lib/api/work/adapters.ts`. Không tái dùng `ProjectSummary`/`ProjectWorkspace` của `src/features/projects/types.ts`: hai kiểu đó đòi `sprint`, `epics`, `issues` mà Work chưa cấp, và chúng đang phục vụ chế độ demo. Kiểu mới:

```ts
export interface WorkProjectCard {
  projectId: string; identifier: string; name: string; archived: boolean;
  classId: string | null; classCode: string; className: string; courseCode: string;
  groupId: string; groupName: string;
  myRole: "LEADER" | "MEMBER" | null;   // null = không phải thành viên (giảng viên xem)
  repository: string | null;            // github_repo_name
  createdAt: string;
}
export interface WorkProjectShell {
  project: ProjectDto;
  classCode: string; className: string; courseCode: string; groupName: string;
  members: ProjectMemberDto[];
  myRole: "LEADER" | "MEMBER" | null;
  canEdit: boolean;                      // myRole === "LEADER" && project.archived_at === null
}
```

Hàm thuần (không gọi mạng, dễ unit test):

- `toProjectCards(projects, context)` với `context = { classes: Map<string, ClassDto>, courses: Map<string, CourseDto>, groupNames: Map<string, string>, roleByProject: Map<string, "LEADER"|"MEMBER"|null> }`. Thiếu lớp → `classCode`/`className` = `""`, `courseCode` = `""`; thiếu tên nhóm → `""`. Không bịa chữ thay thế ở adapter; component quyết định hiển thị.
- `myRoleOf(members, userId)` → `"LEADER" | "MEMBER" | null`, chỉ xét `status === "ACTIVE"`.
- `pickPrimaryProject(projects)` → project **chưa lưu trữ** có `created_at` nhỏ nhất; hòa thì so `id` tăng dần; không có cái nào chưa lưu trữ → `null`. Dùng cho liên kết "project của nhóm" ở trang môn và trang giảng viên khi nhóm có nhiều project.
- `projectsByGroup(projects)` → `Map<string, ProjectDto[]>` theo `classroom_group_id`, mỗi mảng sắp theo `created_at` tăng dần.

### 3. Hook React Query cho Work

Tạo `src/lib/query/workHooks.ts`, theo đúng mẫu `src/lib/query/classroomHooks.ts` (khóa gắn `userId` lấy từ `useAuth()`; ném lỗi khi chưa đăng nhập) và `src/lib/query/teacherClassHooks.ts:39-57` (helper lệnh, invalidate khi thành công **và** khi `isConflict(error)`).

```ts
export const workKeys = {
  all: ["work"] as const,
  projects: (userId: string) => ["work", userId, "projects"] as const,
  project: (userId: string, projectId: string) => ["work", userId, "project", projectId] as const,
  groupProjects: (userId: string) => ["work", userId, "group-projects"] as const,
};
export function useWorkProjects(): UseQueryResult<{ cards: WorkProjectCard[]; partial: boolean }>
export function useWorkProject(projectId: string): UseQueryResult<WorkProjectShell>
export function useGroupProjects(): UseQueryResult<{ byGroup: Map<string, ProjectDto[]>; partial: boolean }>
export function useCreateProject(): UseMutationResult<ProjectDto, unknown, CreateProjectInput & { idempotencyKey: string }>
export function usePatchProject(projectId: string): UseMutationResult<ProjectDto, unknown, PatchProjectInput & { expectedVersion: number }>
export function useSetProjectArchived(projectId: string): UseMutationResult<ProjectDto, unknown, { archived: boolean; expectedVersion: number }>
```

Loader đi kèm, đặt trong `src/lib/api/work/loaders.ts` (giữ hook mỏng như `classroomHooks` → `loaders.ts`):

- `loadProjectCards(client, userId)`: `listProjects(client, "all")`; nếu rỗng → trả `{cards: [], partial}` ngay, không gọi thêm. Ngược lại: `listCourses(client)` một lần; với mỗi `class_id` khác nhau (bỏ `null`) gọi song song `getClass` và `listClassGroups(classId, "ACTIVE")`; với mỗi project gọi `listProjectMembers(projectId, "ACTIVE")`. Mỗi lời gọi phụ bọc `try/catch`: lỗi → bỏ trường tương ứng (`classCode: ""`, `groupName: ""`, `myRole: null`), **không** làm hỏng cả danh sách. Giới hạn song song 5 request một đợt, sao chép mẫu `loadMembers` tại `src/lib/api/classroom/teacherLoaders.ts:79-89`.
- `loadProjectShell(client, userId, projectId)`: `getProject` + `listProjectMembers(..., "ACTIVE")` song song; rồi `getClass(project.class_id)`, `listCourses`, `listClassGroups(project.class_id, "ACTIVE")` để lấy tên lớp/môn/nhóm, mỗi cái bọc `try/catch` → `""` khi lỗi. `getProject` lỗi thì ném tiếp (route cần 403/404).
- `loadGroupProjects(client)`: `listProjects(client, "all")` → `{ byGroup: projectsByGroup(projects), partial }` (trả cả `partial`, khớp chữ ký `useGroupProjects`). Dùng cho trang nhóm của sinh viên và trang giảng viên.

Mutation: cả ba chỉ invalidate `workKeys.all` (không còn `classroomKeys.all`: bước 8 không nạp project vào loader Classroom nữa). Cả ba cũng invalidate khi `isConflict(error)` (409), dùng `isConflict` sẵn có ở `src/features/courses/lib/groupErrors.ts`. `usePatchProject` gửi `Idempotency-Key`; `useSetProjectArchived` không gửi (backend không dedupe, xem bước 1).

### 4. Trang danh sách `/projects` ở chế độ thật

Thêm `src/features/projects/components/RealProjectList.tsx` (component mới, không sửa `ProjectsRoute` demo ngoài một nhánh chọn):

- `src/features/projects/routes/ProjectsRoute.tsx` — `export function Component()` (hiện ở dòng 401-403) đổi thành: `isRealService("work") ? <RealProjectList /> : <ProjectsRoute />`. Không đụng gì khác trong file.
- `RealProjectList` dùng `useWorkProjects()`. Trạng thái: đang tải → `PageSkeleton`; lỗi → `ErrorState` (`src/components/feedback/ErrorState.tsx`) có `onRetry`; rỗng → `EmptyState` tiêu đề "Chưa có dự án", mô tả "Bạn chưa thuộc dự án nào. Trưởng nhóm tạo dự án từ trang nhóm của môn học.", action `Link` tới `/courses`.
- Hai tab "Đang hoạt động" / "Đã lưu trữ" lọc theo `archived`, dùng `segmentedTabsListClass`/`segmentedTabClass` từ `src/components/navigation/segmentedTabs.ts` như `ProjectsRoute` hiện tại. Ô tìm kiếm lọc theo `identifier`, `name`, `classCode`, `courseCode`, `groupName` (không phân biệt hoa thường). Không có bộ lọc vai trò: `myRole` có thể `null`.
- Thẻ dự án hiển thị: badge `identifier`, tên dự án (link `/projects/{id}`), `courseCode`/`classCode` + `className` khi có (chuỗi rỗng thì bỏ qua dòng đó, không in dấu `—`), tên nhóm, badge vai trò ("Trưởng nhóm" khi `LEADER`, "Thành viên" khi `MEMBER`, không hiện badge khi `null`), repository khi `repository !== null`, nút "Vào dự án" → `/projects/{id}`. **Không** hiển thị panel Sprint hay phần trăm tiến độ: Work chưa cấp dữ liệu đó (B15).
- `partial === true` → banner cảnh báo phía trên danh sách: "Danh sách có thể thiếu dự án của lớp bạn phụ trách vì hệ thống chưa xác minh được quyền giảng viên."

### 5. Vỏ dự án ở chế độ thật

Thêm `src/features/projects/components/RealProjectLayout.tsx`:

- `src/features/projects/routes/ProjectWorkspaceLayout.tsx` — `export function Component()` (dòng 227-229) đổi thành `isRealService("work") ? <RealProjectLayout /> : <ProjectWorkspaceLayout />`. Giữ nguyên `ProjectWorkspaceLayout`, `useProjectWorkspaceContext`, `projectModuleTitles`: demo vẫn dùng.
- `RealProjectLayout` đọc `projectId` từ `useParams()`, gọi `useWorkProject(projectId)`. Người ngoài dự án nhận **404 `RESOURCE_NOT_FOUND`** (không phải 403) → `EmptyState` "Không tìm thấy dự án" + link `/projects`; 403 → `ForbiddenPage` (chỉ xảy ra với lệnh ghi, giữ nhánh cho chắc); 503 `CLASSROOM_UNAVAILABLE` và lỗi khác → `ErrorState` với `error.message` + `onRetry`; đang tải → `PageSkeleton` (giống `ProjectWorkspaceLayout.tsx:113-151`).
- Cung cấp context riêng, export từ chính file này:
  ```ts
  export interface RealProjectContextValue { projectId: string; shell: WorkProjectShell }
  export function useRealProjectContext(): RealProjectContextValue  // ném Error khi dùng ngoài RealProjectLayout
  ```
- Header: tên dự án, badge `identifier`, dòng phụ `classCode`/`className`/`groupName` (bỏ phần rỗng), badge "Đã lưu trữ" khi `archived_at !== null`, badge "Chế độ chỉ xem" khi `myRole === null`. Breadcrumb: `Dự án` (`/projects`) → tên dự án.
- Thanh tab chỉ một mục "Thông tin" trỏ `/projects/{id}/info`. Không render `ProjectNavigation` (component đó gắn với 4 tab demo).

Route table `src/app/router/router.tsx:65-94`: giữ nguyên các child hiện có, thêm child `{ path: "info", lazy: () => import("@/features/projects/routes/ProjectInfoRoute") }`. Đổi `{ index: true, element: <Navigate to="backlog" replace /> }` (dòng 70) thành `{ index: true, element: <ProjectIndexRedirect /> }`, thêm `import { ProjectIndexRedirect } from "@/features/projects/routes/ProjectIndexRedirect";` ở đầu `router.tsx` (import tĩnh, không `lazy`, vì element là JSX ở cấp module). Component mới `src/features/projects/routes/ProjectIndexRedirect.tsx`:

```tsx
export function ProjectIndexRedirect() {
  return <Navigate to={isRealService("work") ? "info" : "backlog"} replace />;
}
```

Không tính cờ ở cấp module khi dựng bảng route: test dùng `vi.stubEnv` sau khi import `appRoutes`, nên mọi nhánh phải xảy ra lúc render.

Bốn route con còn lại phải sống được ở chế độ thật (hiện chúng gọi `useProjectWorkspaceContext()` và sẽ ném lỗi):

- `ProjectBacklogRoute.tsx`, `ProjectBoardRoute.tsx`, `ProjectCodeRoute.tsx`, `ProjectSettingsRoute.tsx`: trong `Component()` (và `export default` ở những file có), trả sớm `<WorkModuleNotIntegrated module="…" />` khi `isRealService("work")`, trước mọi hook đọc context demo. Vì quy tắc hook không cho gọi có điều kiện, bọc phần thân cũ vào component con (`DemoBacklog`, `DemoBoard`, `DemoCode`, `DemoSettings`) và để `Component()` chỉ chọn nhánh — giống cách `CourseTeamRoute.tsx:1014-1025` tách `MockCourseTeam`/`RealCourseTeam`. Lưu ý `ProjectBoardRoute.tsx` **không có `export default`** và đặt hook ngay trong `Component()` (dòng 179-180), nên phải tách `DemoBoard` trước khi phân nhánh.
- `src/features/projects/components/WorkModuleNotIntegrated.tsx` (mới): `EmptyState` với tiêu đề theo `module` và mô tả "Phần này chưa nối API Work. Hiện chỉ xem được thông tin dự án và thành viên." + nút quay lại `/projects/{projectId}/info`. Nhãn: `backlog` → "Backlog chưa khả dụng", `board` → "Bảng công việc chưa khả dụng", `code` → "Mã nguồn chưa khả dụng", `settings` → "Cài đặt AI chưa khả dụng".
- `src/features/projects/routes/RequireProjectManagePermission.tsx` gọi `useProjectWorkspaceContext()` ở dòng 12 nên sẽ ném trước khi `ProjectSettingsRoute` kịp chạy. Thêm ở đầu hàm: `if (isRealService("work")) return <Outlet />;` kèm comment rằng chế độ thật không có quyền AI để kiểm, màn hình con tự báo chưa tích hợp.

### 6. Trang Thông tin & thành viên

Tạo `src/features/projects/routes/ProjectInfoRoute.tsx` (`export function Component`, `export default`), dùng `useRealProjectContext()`.

- Thẻ thông tin chỉ đọc: `identifier`, tên, mô tả (rỗng → "Chưa có mô tả"), mục tiêu, ngày bắt đầu/kết thúc (`null` → "Chưa đặt"), ngày tạo, repository GitHub (`github_repo_name`, `null` → "Chưa kết nối"), trạng thái lưu trữ.
- Khi `shell.canEdit`: nút "Sửa thông tin" mở form inline với `name`, `description`, `target_goals`, `start_date`, `end_date`. Gửi `usePatchProject` chỉ với các trường đổi so với giá trị ban đầu, kèm `expectedVersion: project.version`.
  - Kiểm phía client trước khi gửi: `name` 1–200 ký tự; `end_date` không sớm hơn `start_date` (lỗi gắn vào ô `end_date`, chữ "Ngày kết thúc không được trước ngày bắt đầu."). Kiểm này **bắt buộc** vì backend chặn cùng điều kiện nhưng trả `VALIDATION_ERROR` với `details` rỗng (`services/projects.py:144-147`) → `fieldErrors` không có khóa nào, UI chỉ còn `error.message` chung.
  - Lỗi `VALIDATION_ERROR` có `details[].field` → hiện theo `error.fieldErrors` từng ô; `details` rỗng → hiện `error.message` ở đầu form. 409 `VERSION_CONFLICT` → "Dự án đã được cập nhật bởi thao tác khác. Dữ liệu đã được tải lại, hãy thử lại." (hook đã invalidate). 409 `CONCURRENT_MUTATION_IN_PROGRESS` / 422 `IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD` → "Yêu cầu trước đó đang được xử lý, hãy chờ rồi thử lại." 400 `INVALID_OPERATION` → "Dự án đang ở chế độ chỉ đọc." 503 → `error.message`. Lỗi khác → `error.message`.
- Khi `myRole === "LEADER"` (kể cả dự án đã lưu trữ): nút "Lưu trữ dự án" / "Mở lại dự án" mở `ConfirmDialog` (`src/components/feedback/ConfirmDialog.tsx`, props `open,title,description,confirmLabel,destructive,pending,onConfirm,onCancel`), gọi `useSetProjectArchived` với `expectedVersion: project.version`. Không gửi `Idempotency-Key`; sau khi thành công lấy `version` mới từ phản hồi.
- Bảng thành viên: lấy `shell.members` (chỉ `ACTIVE`), cột tên, vai trò ("Trưởng nhóm"/"Thành viên"), giờ/tuần (`weekly_capacity`). Tên trống → tra qua `useUserNames(userIds)` (`src/lib/query/teacherClassHooks.ts:190`), vẫn trống → "Chưa rõ tên" (hằng `UNKNOWN_NAME` đã có ở `src/lib/api/classroom/teacherLoaders.ts:182`). Không có nút thêm/bớt thành viên: Work không có API đó, ghi một dòng chú thích "Thành viên đồng bộ từ nhóm lớp học."

### 7. Tạo dự án từ trang nhóm (Leader)

Tạo `src/features/projects/components/CreateProjectDialog.tsx` và `src/features/courses/components/TeamProjectSection.tsx`.

- `TeamProjectSection({ groupId, isLeader })` render trong `TeamHubView` của `src/features/courses/routes/CourseTeamRoute.tsx` (chèn ngay trước khối `team.repository` ở dòng 997-1005, sau nhánh `if (!team) return <EmptyState/>` dòng 912-919 — sinh viên chưa có nhóm sẽ không thấy mục này, đúng ý đồ), chỉ khi `isRealService("work")`. Dữ liệu từ `useGroupProjects()`, lấy mảng theo `groupId`; `TeamHubView` đã có `team.teamId` và `team.isLeader` trong phạm vi.
  - Có project → danh sách: `identifier` + tên + nút "Vào dự án" (`/projects/{id}/info`); project đã lưu trữ kèm badge "Đã lưu trữ".
  - Chưa có project và `isLeader` → nút "Tạo dự án" mở dialog.
  - Chưa có project và không phải Leader → chữ "Nhóm chưa có dự án. Trưởng nhóm là người tạo dự án."
  - Query lỗi → chỉ hiện dòng "Chưa tải được dự án của nhóm."; **không** làm hỏng trang nhóm.
- `CreateProjectDialog({ groupId, open, onOpenChange })`: ô `identifier` (tự `toUpperCase()` khi nhập, kiểm `^[A-Z0-9]{2,10}$`, nhãn phụ "2–10 chữ in hoa hoặc số, duy nhất toàn hệ thống"), `name` (bắt buộc, ≤200), `description`, `target_goals`, `start_date`, `end_date`. Gọi `useCreateProject`, `idempotencyKey` sinh khi mở dialog, sinh lại khi bất kỳ ô nào đổi sau một lần gửi lỗi.
  - Thành công → đóng dialog, toast `sonner` "Đã tạo dự án.", `navigate(\`/projects/${project.id}/info\`)`.
  - Lỗi theo `error.code`: `DUPLICATE_IDENTIFIER` → gắn ô `identifier`, "Mã dự án đã được dùng. Hãy chọn mã khác." (backend trả message chung "Dữ liệu xung đột với thay đổi hiện hành." và **không** có `details.field`, nên câu chữ do frontend đặt); `LEADER_PERMISSION_REQUIRED` → "Chỉ trưởng nhóm mới tạo được dự án."; `CLASSROOM_UNAVAILABLE` (503) → "Chưa xác minh được nhóm lớp học. Hãy thử lại sau ít phút."; `CONCURRENT_MUTATION_IN_PROGRESS` (409) / `IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD` (422) → "Yêu cầu trước đó đang được xử lý, hãy chờ rồi thử lại."; `CLASSROOM_SCOPE_DENIED` → `error.message`; `VALIDATION_ERROR` → theo `error.fieldErrors`; còn lại → `error.message`.

### 8. Lấp chỗ trống của Phase 5 và Phase 8

- Sinh viên — **bỏ phần sửa `src/lib/api/classroom/adapters.ts` và `loaders.ts`**. Lý do đã kiểm: `CourseEnrollment.projectId` chỉ có hai nơi đọc, cả hai đều không chạy ở chế độ thật — sidebar lấy dữ liệu từ `useMyWorkOverview` (`src/features/my-work/queries.ts:11-16` → MSW `/api/work/api/v1/my-work/overview`), không từ `loadCourseEnrollments`; `team.projectId` chỉ dùng trong `ApprovedTopicAction` (`src/features/courses/routes/CourseTeamRoute.tsx:692-704`) với điều kiện `topic.status === "approved"`, mà adapter thật đặt `topic: null` (`adapters.ts:104`). Điền `projectId` ở đây là mã chết và khiến trang môn phân trang `GET /projects/?status=all` thêm một lần. Lối vào dự án của sinh viên ở chế độ thật là `TeamProjectSection` (bước 7) và trang `/projects`. Ghi khoảng trống B20 cho sidebar/My Work.
- Giảng viên — `src/lib/api/classroom/teacherLoaders.ts`:
  - `toTeacherTeams` (dòng 138) nhận thêm `projectsByGroup?: Map<string, ProjectDto[]>`; `TeacherTeam.project` = `pickPrimaryProject(...)` → `{ projectId: p.id, key: p.identifier, name: p.name }`, không có → `null`.
  - **Chỗ gọi `toTeacherTeams` không nằm trong `loadTeacherCourse`** mà ở `useTeacherTeams` (`src/lib/query/teacherFlowHooks.ts:93-109`, qua `fetchRoster`). Phải sửa chính `queryFn` đó: khi `isRealService("work")` gọi thêm `loadGroupProjects`, bọc `try/catch` → lỗi hoặc `partial === true` thì truyền `undefined`. Nếu chỉ sửa `loadTeacherCourse` thì `team.project` vẫn `null` ở `TeacherCourseTeamsRoute.tsx` và `RealTeamDetail`.
  - `toTeacherCourseDetail` (dòng 184) nhận thêm `projectsByGroup?`; `teamsWithoutProject` = số nhóm có mảng project rỗng, **chỉ khi** `projectsByGroup !== undefined`, ngược lại giữ `null`. Giá trị `null` hiện đến từ `summaryBase` (`teacherLoaders.ts:38-50`, trường ở dòng 46) được spread ở dòng 188 và dùng chung với `loadTeacherCourses`; phải ghi đè **sau** spread, không sửa `summaryBase`, nếu không trang danh sách lớp sẽ sai.
  - `loadTeacherCourse` (dòng 209) gọi thêm `loadGroupProjects` song song khi `isRealService("work")`, bọc `try/catch`; `partial === true` → truyền `undefined`. `loadTeacherCourses` (dòng 58) **không** đổi.
  - `src/features/teacher/components/RealTeamDetail.tsx` hiện **hard-code** "Project và tiến độ chưa có dữ liệu (cần Work Service)" (dòng 19, 51-53) và không đọc `team.project`; chỗ đọc `detail.project` ở `TeacherTeamDetailRoute.tsx:349-351` thuộc `DemoTeamDetail`. Phải sửa `RealTeamDetail` để hiện `identifier` + tên dự án và `Link` tới `/projects/{projectId}/info`, giữ câu cũ cho phần tiến độ (Work chưa cấp).

### 9. Hạ tầng test cho Work

Tạo `src/test/workHandlers.ts` theo mẫu `src/test/classroomHandlers.ts`: `buildProject(overrides)`, `buildProjectMember(overrides)`, `workHandlers(fixture)` phủ 6 endpoint ở mục hợp đồng; tái dùng `envelope` và `envelopeError` đang export sẵn từ `src/test/classroomHandlers.ts:127,151`. `workHandlers` hỗ trợ `status` filter, `meta.scope` khi fixture bật cờ `partial`, và trả 409/422/403/404/503 khi fixture yêu cầu. Không đăng ký handler này ở runtime MSW: đường dẫn thật `/api/work/projects/` khác đường dẫn mock hiện có `/api/work/api/v1/...`, nên chế độ demo không bị ảnh hưởng. Lưu ý: `src/test/setup.ts:8` dùng khóa `onUnhandledFrame` (MSW thật là `onUnhandledRequest`) nên request thiếu handler **không** làm test đỏ ngay mà thành lỗi mạng khó đọc — mỗi test phải assert nội dung hiển thị, không dựa vào cơ chế này.

Test chế độ thật dùng đúng mẫu Phase 8: `vi.stubEnv("VITE_REAL_SERVICES", "auth,classroom,work")`, `createAuthHandlers("default", createMemoryRepository("default"))`, `renderAppRoutes(route, session)` (`src/test/render.tsx:79`). Handler đăng ký trước thắng trong `server.use(...)`, nên override phải đặt trước.

## Critical files & anchors

| File | Vùng | Lý do |
|---|---|---|
| `apps/web/src/lib/api/classroom/endpoints.ts` | dòng 32-48 `PageQuery`/`listUrl`/`fetchPage` | Mẫu phân trang cursor phải sao đúng sang Work, kể cả `MAX_PAGE_SIZE`; `fetchPage` cố định `ListMeta` nên bản Work phải tự khai `WorkListMeta`. Cùng file dòng 87 có `listGroupProjects` (`/api/classroom/groups/{id}/projects/`) — Phase 9 **không** dùng (liên kết này cập nhật bất đồng bộ qua Kafka, xem B19) |
| `apps/web/src/lib/query/teacherClassHooks.ts` | dòng 39-57 `useTeacherCommand` | Mẫu mutation: invalidate khi thành công và khi 409, không cập nhật lạc quan |
| `apps/web/src/lib/query/teacherFlowHooks.ts` | dòng 93-109 `useTeacherTeams` | Chỗ duy nhất gọi `toTeacherTeams`; phải nạp `groupProjects` tại đây |
| `apps/web/src/features/courses/routes/CourseTeamRoute.tsx` | dòng 914-1005 `TeamHubView` (khối `team.repository` 997-1005), 1014-1025 chọn nhánh | Nơi chèn mục dự án của nhóm và mẫu tách Mock/Real |
| `apps/web/src/features/projects/routes/ProjectWorkspaceLayout.tsx` | dòng 66-165 và 227-229 | Vỏ demo giữ nguyên; chỉ `Component()` phân nhánh, context demo không được dùng lại |
| `apps/web/src/features/projects/routes/ProjectBoardRoute.tsx` | dòng 179-180 | Khác ba route con còn lại: **không có `export default`**, hook nằm ngay trong `Component()` → vẫn phải tách `DemoBoard` |
| `apps/web/src/lib/api/classroom/teacherLoaders.ts` | dòng 38-50 `summaryBase`, 138-160, 184-207, 209-220 | Ba chỗ nhận `projectsByGroup`; `teamsWithoutProject` mặc định `null` sinh ra ở `summaryBase` |

## Verification

Chạy từ `apps/web`. Đạt cả ba cổng, báo số file/test (nền trước Phase 9: 52 file / 764 test pass):

1. `node node_modules/typescript/bin/tsc --noEmit` → `echo tsc=$?` phải in `tsc=0`.
2. `node node_modules/vitest/vitest.mjs run` → tất cả pass, số test **tăng** so với 764.
3. `node node_modules/typescript/bin/tsc -b && node node_modules/vite/bin/vite.js build` → build thành công.

Unit test bắt buộc viết trong cùng phase (mỗi hàm mới có ít nhất một nhánh thành công và một nhánh lỗi/biên):

- `src/lib/api/work/endpoints.test.ts`: `listProjects` ghép `status=all&page_size=100`, gộp 2 trang khi `has_next`, đọc `partial` từ `meta.scope`; `createProject` gửi header `Idempotency-Key` đúng giá trị truyền vào và body có `tech_stack: {}`; `patchProject` chỉ gửi khóa đã đổi cộng `expected_version`; `setProjectArchived` chọn `/archive/` và `/unarchive/`; `status` sai trả lỗi từ server được ném nguyên `ApiError` với `code === "VALIDATION_ERROR"`.
- `src/lib/api/work/adapters.test.ts`: `myRoleOf` (Leader, Member, chỉ có bản ghi `LEFT` → `null`); `pickPrimaryProject` (bỏ bản đã lưu trữ, chọn `created_at` sớm nhất, tất cả đã lưu trữ → `null`); `toProjectCards` khi thiếu lớp/nhóm → chuỗi rỗng chứ không ném.
- `src/features/projects/RealProjects.test.tsx`: `/projects` rỗng → chữ "Chưa có dự án"; có 2 dự án, 1 đã lưu trữ → tab "Đang hoạt động" hiện 1, tab "Đã lưu trữ" hiện 1; `meta.scope.partial` → banner cảnh báo xuất hiện; server 503 → `ErrorState` hiện message của server.
- `src/features/projects/RealProjectDetail.test.tsx`: Leader thấy nút "Sửa thông tin", Member không thấy; sửa tên thành công → gọi `PATCH` với `expected_version` đúng và hiện tên mới; server trả 409 `VERSION_CONFLICT` → hiện câu "Dự án đã được cập nhật bởi thao tác khác…"; dự án `archived_at !== null` → không có nút sửa, có nút "Mở lại dự án"; truy cập `/projects/x/board` ở chế độ thật → hiện "Bảng công việc chưa khả dụng" (không ném lỗi context); `/projects/x` → chuyển hướng tới `/projects/x/info`.
- `src/features/projects/CreateProject.test.tsx`: Leader ở trang nhóm bấm "Tạo dự án", nhập `identifier` `ZP9T` và tên → gọi `POST /api/work/projects/` một lần rồi điều hướng `/projects/<id>/info`; server trả 409 `DUPLICATE_IDENTIFIER` → lỗi hiện ngay ô mã; bấm "Thử lại" không đổi nội dung → gửi **cùng** `Idempotency-Key`; thành viên thường không thấy nút tạo.
- `src/lib/api/classroom/teacherLoaders.test.ts` (bổ sung): có `projectsByGroup` → `teamsWithoutProject` bằng số nhóm rỗng và `team.project` đúng; không truyền → cả hai giữ `null`; `loadTeacherCourses` (danh sách lớp) vẫn `null`.

Smoke trên staging (`https://utask-api.u-code.dev` qua proxy Vite), bắt buộc trước khi báo xong:

- Chuẩn bị `apps/web/.env.local` (không commit): `VITE_ENABLE_MOCKS=true`, `VITE_REAL_SERVICES=auth,classroom,work`, `VITE_API_BASE_URL=` (để trống). Xóa file sau khi smoke.
- Chạy Vite như service đặt tên: `node node_modules/vite/bin/vite.js --host 127.0.0.1 --port 5188 --strictPort`, `ready` theo log `Local:`, `pty: true`. Dừng bằng `write proc://<tên>/kill`.
- Tài khoản staging (không ghi vào repo/tài liệu): TEACHER `vinhxuanan28@gmail.com` / `Utask@123123`; STUDENT `aunhathuy28@gmail.com` / `Utask@123123`. Access token 15 phút, lấy ở `data.access`. Gọi API bằng Python urllib phải đặt header `User-Agent: curl/8.5.0`, nếu không staging trả phản hồi không phải JSON.
- Kịch bản: TEACHER tạo lớp tạm → thêm STUDENT → tạo nhóm đặt STUDENT làm Leader → đăng nhập STUDENT, mở `/courses/<classId>/team`, bấm "Tạo dự án" với `identifier` bắt đầu bằng `ZP9` → kiểm `/projects` hiện dự án → mở `/projects/<id>/info`, sửa tên, lưu trữ rồi mở lại → đăng nhập TEACHER mở cùng URL, xác nhận không có nút sửa và trang nhóm hiện tên dự án. Kiểm thêm: tạo dự án thứ hai trùng `identifier` → phải thấy lỗi ở ô mã.
- Dọn dẹp: Work **không có API xóa dự án** và `identifier` duy nhất toàn hệ thống, nên dự án smoke chỉ lưu trữ được. Dùng tiền tố `ZP9` để phân biệt. Lớp tạm chuyển `ARCHIVED` như các phase trước. Xóa mọi script `*.tmp.mjs` và `.env.local` sau khi xong.
- Điểm chưa biết, phải ghi lại kết quả quan sát được: tạo dự án cho nhóm thuộc lớp đã `ARCHIVED` hoặc đã chốt nhóm có bị chặn không; `Member.display_name` có rỗng khi `UserProjection` chưa đồng bộ không.

## Assumptions & contingencies

Các quyết định dưới đây người dùng có thể đổi; nếu không đổi thì làm đúng như ghi.

- **Nhóm có nhiều dự án**: liên kết "dự án của nhóm" ở sidebar, trang môn và trang giảng viên dùng dự án chưa lưu trữ tạo sớm nhất; `/projects` vẫn liệt kê tất cả. Nếu người dùng muốn một dự án duy nhất mỗi nhóm thì đó là yêu cầu backend, không xử lý ở frontend.
- **Chỉ Leader tạo dự án**: nút chỉ hiện với Leader, khớp với kiểm tra của backend. Giảng viên không tạo hộ.
- **Thẻ dự án không hiển thị tiến độ, sprint, giảng viên hướng dẫn**: Work chưa cấp các trường này và việc tra thêm sẽ tốn N+1 request. Nếu người dùng muốn tên giảng viên trên thẻ, thêm `listClassTeachers` + `usersBatch` theo từng lớp trong `loadProjectCards`, bọc `try/catch` như các lời gọi phụ khác.
- **`tech_stack` luôn gửi `{}`**: OpenAPI chỉ khai báo `object` tự do nên không dựng UI đoán cấu trúc.
- Nếu `GET /api/work/projects/` trả 503 `CLASSROOM_UNAVAILABLE` trong lúc smoke: đó là Work không gọi được Classroom, không phải lỗi frontend — ghi vào báo cáo khoảng trống backend, giữ nguyên mã đã viết, và kiểm phần còn lại bằng MSW handler trong test.
- Nếu staging chặn tạo dự án trên lớp đã `ARCHIVED`: tạo lớp tạm mới ở trạng thái `OPEN` để smoke, không nới điều kiện ở frontend.

## Khoảng trống backend phát sinh (ghi vào `docs/web/api-integration.md` khi làm)

- B14: Work không có API cấu hình AI key (BYOK) → tab Cài đặt ở chế độ thật không nối được.
- B15: `Project` thiếu tên môn/lớp/nhóm và tóm tắt sprint/tiến độ; đề nghị nhúng `class {code,name}`, `group {name}`, `active_sprint {name,end_date,done_points,total_points}` để bỏ N+1.
- B16: STUDENT gọi `GET /projects/?classroom_group_id=` bị 403; đề nghị cho thành viên lọc nhóm của chính mình.
- B17: `tech_stack` là object tự do, chưa có cấu trúc hay tài liệu.
- B18: Một nhóm có nhiều dự án nhưng không có khái niệm "dự án chính"; `identifier` duy nhất toàn hệ thống dễ trùng giữa các lớp; chưa có API xóa dự án.
- B19: Liên kết Classroom↔Work (`GET /api/classroom/groups/{id}/projects/`, đã có sẵn ở `apps/web/src/lib/api/classroom/endpoints.ts:87`) cập nhật bất đồng bộ qua Kafka; cần xác nhận consumer chạy trên staging và độ trễ tối đa. Phase 9 không dùng đường này mà hỏi thẳng Work.
- B20: Sidebar và trang My Work vẫn chạy MSW (`/api/work/api/v1/my-work/overview`); Work chưa có API tổng quan công việc của tôi, nên ở chế độ thật sidebar không trỏ được vào dự án và `CourseEnrollment.projectId` không có người tiêu thụ.
