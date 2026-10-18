# UTask – Work Service API Technical Specification
## Đặc tả Kỹ thuật Giao diện Lập trình Ứng dụng Chuẩn hóa (RESTful API & Event-Driven Contracts)

**Phiên bản:** 1.4 (quyết định Work từ baseline/PRD/Plane ngày 08/10/2026)  
**Trạng thái:** Đặc tả mục tiêu; backend Work đã có source và kiểm thử nội bộ. Hiện trạng và giới hạn nghiệm thu tại [Work backend](../work-service/work-backend.md).  
**Dịch vụ sở hữu:** `apps/work-service` (Core Domain)  
**Cơ sở dữ liệu:** `work_db` (PostgreSQL 16)  
**Công nghệ:** Python 3.12, Django 5.x, Django REST Framework (DRF), Celery 5.x, Apache Kafka  
**Tài liệu tham chiếu:**
- [Kiến trúc hiện hành](../system/architecture.md), [ownership](../system/data-ownership.md) (nguồn chuẩn sau pull; các số mục baseline cũ là tham chiếu lịch sử)
- [UTask - Phân tích thiết kế yêu cầu.md](UTask%20-%20Phân%20tích%20thiết%20kế%20yêu%20cầu.md) (Source of Truth nghiệp vụ PRD)
- [docs/diagram/work-service/erd.md](../diagram/work-service/erd.md) (Mô hình dữ liệu và ràng buộc mục tiêu)
- [docs/diagram/work-service/usecase.md](../diagram/work-service/usecase.md) (Hệ thống Sơ đồ Use Case & Ma trận phân quyền)
- [docs/diagram/work-service/sequence.md](../diagram/work-service/sequence.md) (Hệ thống 12 Sơ đồ Tuần tự & Concurrency Control)
- [docs/diagram/work-service/bfd.md](../diagram/work-service/bfd.md) (Cây phân rã chức năng nghiệp vụ BFD)
- Dự án tham khảo kỹ thuật: [Plane](https://github.com/makeplane/plane) (`apps/api/plane/api/views/`)

---

## 1. NGUYÊN TẮC THIẾT KẾ & QUY CHUẨN KỸ THUẬT NỀN TẢNG

### 1.1. Ranh giới Work / Project Service
Nguồn kiến trúc chuẩn: [architecture](../system/architecture.md), [data ownership](../system/data-ownership.md), [communication](../system/communication.md). Work tương ứng Project Service; giữ tên thư mục `apps/work-service` và cấu hình `work_db`, không đổi database bằng sửa tài liệu.

- Work sở hữu Project, ProjectMember, State, Task, Assignment, Relation, Epic, Label, Sprint, SprintTask, Comment, Attachment, Activity, Outbox và receipt xử lý lặp.
- Classroom sở hữu Class, Group, GroupMember, quyền Teacher và giới hạn nhóm. ProjectMember mô tả quyền dự án; trong MVP kế thừa membership/role nhóm đã xác minh, còn capacity thuộc Work. Work không tạo/kick/chuyển Leader nhóm học tập.
- Integration sở hữu connection, repository, GitHub identity proof, webhook và mọi GitHub API. Work giữ projection kết nối và liên kết/candidate theo repo identity.
- Work query/job nội bộ tính chỉ số công việc/burndown và tín hiệu cơ bản theo luật trong domain hiện có, snapshot cuối Sprint ở Work. Không thêm service/database để tính tiến độ. Báo cáo Risk Analysis và draft thuộc nhóm AI, không Work DB.
- User gọi AI business API/xem kết quả bên nhóm AI; agent/context/job/AIDB nội bộ do nhóm khác phụ trách. Work chỉ cấp facts/snapshot Kafka và apply đã duyệt; agent không gọi Work REST/database lấy context. Contract provenance/permission/result cần hai nhóm thống nhất.
- Notification sở hữu thông báo/kênh gửi. Work phát dữ kiện assign/mention/deadline; không gửi email/push trong transaction.
- Dashboard lớp ghép phạm vi Classroom, dữ kiện/chỉ số Work. AI lỗi không làm dashboard hoặc thông báo cơ bản ngừng hoạt động.

Work dùng URL nội bộ không gắn phiên bản, theo cùng quy ước với Identity: service đăng ký `/projects/`, `/tasks/`, `/openapi/` và `/docs/`; gateway công khai API nghiệp vụ tại `/api/work/...`. Không còn alias public `/api/v1/...` cho Work. Các đường dẫn `/api/v1/internal/...` thuộc hợp đồng nội bộ của service phụ thuộc vẫn giữ nguyên nếu được nhắc tới.

Các yêu cầu API và event dưới đây là **hợp đồng mục tiêu**. OpenAPI được sinh từ URL/view/serializer của Work và phục vụ tại `/openapi/` (gateway: `/api/work/openapi/`; xem [URLconf](../../apps/work-service/config/urls.py)); hiện trạng tại [Work backend](../work-service/work-backend.md). Source/kiểm thử nội bộ không chứng minh service/provider liên quan đã chạy. Tên event liên service phải được producer/consumer thống nhất; không coi các interface Work giả lập trong test là contract upstream.

---

### 1.2. Quy chuẩn Cấu trúc Response năm trường cho API nghiệp vụ Work (Single Unified Envelope)
Mọi endpoint nghiệp vụ thuộc Work (truy vấn, hành động và lỗi; ngoại lệ protocol tại 9.1) **bắt buộc tuân thủ một cấu trúc JSON 5 trường duy nhất**:

```typescript
interface ApiResponse<T> {
  success: boolean;       // true cho HTTP 2xx, false cho HTTP 4xx/5xx
  message: string;        // Thông điệp ngữ cảnh rõ ràng, thân thiện cho UI
  data: T | null;         // Payload dữ liệu (Object thực thể, Mảng danh sách, hoặc Kết quả thao tác)
  meta: ApiMeta | null;   // Metadata phụ trợ (phân trang cursor/total), null nếu không phải danh sách
  error: ApiError | null; // Cấu trúc lỗi chuẩn hóa khi success = false, null khi thành công
}

interface ApiMeta {
  scope?: { // Chỉ list Project khi Classroom không khả dụng
    partial: boolean;
    source: 'WORK_MEMBERSHIP';
    teacher_scope: 'UNAVAILABLE';
  };
  pagination?: {
    total_count: number;        // Tổng số bản ghi thỏa mãn bộ lọc
    page_size: number;          // Số lượng bản ghi trên mỗi trang
    next_cursor: string | null; // Con trỏ trang kế tiếp (Opaque base64 e.g. "eyJjcmVhdGVkX2F0Ijoi...")
    prev_cursor: string | null; // Con trỏ trang trước đó
    has_next: boolean;          // Cờ báo hiệu còn trang tiếp theo hay không
  };
}

interface ApiError {
  code: string;           // Mã lỗi định danh viết hoa chuẩn hóa (e.g. "PERMISSION_DENIED")
  details: Array<{
    field?: string;       // Tên trường dữ liệu bị lỗi (nếu là lỗi validation form)
    issue: string;        // Diễn giải chi tiết nguyên nhân vi phạm
  }>;
}
```

#### Quy ước phân trang
1. API danh sách Work dùng `page_size` và cursor danh sách theo `(created_at DESC, id DESC)`; State cấu hình nhỏ trả toàn bộ theo `sequence ASC`. Không áp dụng một thứ tự cho mọi loại view.
2. Cursor được ký bằng thư viện Django, chứa version và fingerprint scope/filter/order. Client coi là opaque; Base64 đơn thuần không chống sửa token. Nếu dùng DRF CursorPagination, không tự nhận nó là tuple keyset hai cột khi chưa kiểm implementation.
3. `has_next=false` bắt buộc `next_cursor=null`. Counts là số liệu theo filter và thời điểm đọc, không được hứa index-only scan cho mọi truy vấn.
4. Board có cursor riêng theo `(board_revision, state_id, filter_hash, sort_order, task_id)`, xem 5.2.1. Rank mutable chỉ dùng cùng revision; revision đổi trả `409 BOARD_REVISION_CHANGED` để client tải lại cột. Không dùng cursor list để tải tiếp board.

---

### 1.3. Bối cảnh Xác thực, Nhận diện Người dùng & Phân quyền DRF

**Quyền hiện hành:** Không cấp admin bypass project. Teacher phải được Classroom xác nhận phụ trách đúng lớp/nhóm; projection quyền có source version và policy cập nhật, command nhạy cảm xác minh nguồn khi cần. Tác giả comment/uploader vẫn phải có scope hiện hành. Project archived/deleted chặn các mutation, kể cả AI apply/upload; unarchive là ngoại lệ có kiểm uniqueness. Quyền role/assignee được kiểm lại trong transaction theo protocol khóa chung, không chỉ trước khi mở transaction.

1. **Xác thực tại Work:** Dùng verifier JWT của thư viện, RS256/JWKS, `iss=https://identity.utask.internal`, `aud=utask-platform`, hạn token và `token_type=access`; `sub` là user ID. Theo [Identity README](../identity-service/README.md), JWKS hiện có một khóa và token SimpleJWT không có `kid`. Work chuyển Bearer access tới Identity session-status bằng `X-Service-Key` riêng caller `work`; chỉ tiếp tục khi active. Timeout/lỗi Identity trả `503 IDENTITY_UNAVAILABLE`, không cache kết quả cho phép ở giai đoạn đầu. Work không đọc Identity DB hoặc giữ refresh token.
2. **Nguyên tắc an toàn:** Tuyệt đối không tin cậy `user_id` hay `created_by` từ Request Body của client. Mọi hành động ghi nhận quyền lực hoặc tác giả đều lấy từ `request.user.id`.
3. **Khóa Phạm vi Truy cập theo Dự án (Project-scoped Access Control):**
   * Mọi truy vấn tài nguyên con (Task, Sprint, State, Label, Epic, Comment) phải được lọc theo phạm vi dự án mà người dùng được phép xem trước khi resolve đối tượng.
   * Với các endpoint trực tiếp như `GET/PATCH /tasks/{task_id}/`: Lớp truy vấn `get_queryset()` bắt buộc join và filter theo quyền trên dự án cha (`project__members__user_id = request.user.id` và `project__members__status = 'ACTIVE'` hoặc lớp học của Giảng viên). Nếu người dùng không có quyền trên dự án chứa task đó, hệ thống trả về `404 RESOURCE_NOT_FOUND` (nhằm bảo vệ an toàn chống enumeration attack, không để lộ tài nguyên của nhóm khác).
4. **Bộ lớp Phân quyền (DRF Permission Classes) & Quy tắc Toán tử OR:**
   * Trong Django REST Framework, khai báo danh sách `permission_classes = [A, B]` sẽ được thực thi theo phép **AND** (bắt buộc thỏa mãn cả A và B).
   * Do đó, đối với các endpoint cho phép Thành viên nhóm **HOẶC** Giảng viên phụ trách xem, hệ thống **bắt buộc sử dụng toán tử bitwise OR**: `permission_classes = [IsProjectMember | IsClassTeacher]` hoặc lớp tổng hợp `IsProjectMemberOrClassTeacher`.
   * **Chi tiết từng lớp phân quyền:**
     * **`IsAuthenticated`:** Yêu cầu người dùng đã đăng nhập hợp lệ.
     * **`IsProjectMember`:** Kiểm tra người dùng thuộc dự án và có `status = 'ACTIVE'` trong bảng `project_members`.
     * **`IsProjectLeader`:** Yêu cầu người dùng là Trưởng nhóm đồ án (`role = 'LEADER'` và `status = 'ACTIVE'`). Bắt buộc cho các hành động: Tạo task backlog (US-3.1), Lập/Kích hoạt/Đóng Sprint (US-3.4), Chỉ định repo GitHub (US-5.1), Phê duyệt Backlog AI (US-5.4).
     * **`IsTaskAssignee`:** Kiểm tra người dùng đang được phân công trực tiếp trong `task_assignments` của task.
     * **`IsTaskAssigneeOrLeader`:** Cú pháp `[IsTaskAssignee | IsProjectLeader]`; cả hai đều yêu cầu membership ACTIVE.
     * **`IsClassTeacher`:** Kiểm tra Giảng viên có phụ trách nhóm lớp học `classroom_group_id` tương ứng của đồ án. Giảng viên có quyền **Read-only** trên Sprint/Kanban và quyền **Gửi phản hồi Feedback** (US-4.5); tuyệt đối không có quyền đóng sprint hay can thiệp đổi trạng thái task của sinh viên.
     * **`IsProjectMemberOrClassTeacher`:** Cú pháp `[IsProjectMember | IsClassTeacher]`.

---

### 1.4. Transactional Outbox và thứ tự sự kiện
Mutation, Activity, OutboxEvent và durable idempotency receipt được ghi trong cùng `transaction.atomic()`. Cột `outbox_events.data` lưu toàn envelope; dữ kiện nghiệp vụ nằm tại `event.data`. Envelope mục tiêu có event_id/type/version, aggregate_id, occurred_at, trace_id, producer, data; Work bổ sung project_id, entity_version và project_sequence theo contract được thống nhất. Retry giữ nguyên event_id/time/sequence.

Topic mục tiêu `utask.work.events`, key `project_id`. Key chỉ giữ thứ tự **broker nhận** trong partition, không tự sắp lại thứ tự transaction hoặc loại trừ mọi race.

MVP dùng một publisher process, chọn pending events theo sequence và chỉ đánh dấu published sau Kafka ACK. Không dùng nhiều poller SKIP LOCKED để hứa FIFO theo project. Khi cần nhiều publisher phải có ownership/lease theo project/shard và protocol không phát n+1 trước ACK của n. Crash sau ACK trước DB update có thể resend: consumer vẫn phải dedup. Retry lỗi có backoff/next_attempt_at, không bỏ event đang lỗi rồi gọi đó là thứ tự nghiêm ngặt.

Không giữ DB transaction nghiệp vụ khi chờ Kafka, R2 hoặc REST service khác. `on_commit` có thể đánh thức publisher, không thay durable outbox. Consumer kiểm sequence/version và xử lý gap; outbox không phải event store lưu vô hạn.

---

### 1.5. Xử lý lặp an toàn bằng durable receipt

Operation lookup/replay sau auth/scope hiện hành nhưng **trước** kiểm expected_version cho mutation mới. Body hash là semantic command + target + revision + edited payload, không chứa Idempotency-Key/actor (actor đã là HTTP scope). Một row authoritative có operation_id NOT NULL UNIQUE. AI action single-item có ai_proposal_id/ai_item_id đủ cặp và UNIQUE cặp trên mọi actor/key; cùng payload trả operation cũ có quyền, payload khác conflict, không tạo row thứ hai cho retry. Bulk Task items vẫn có unique Task provenance, không nhét mảng item IDs vào cột single-item receipt.
`Idempotency-Key` bắt buộc với tạo Project/Task/Subtask, AI bulk apply, thay scope Sprint, start/close Sprint và confirm GitHub link/upload. Không có key trả `400 IDEMPOTENCY_KEY_REQUIRED`.

Scope unique là `(user_id, http_method, endpoint_path, idempotency_key)`, route chuẩn hóa gồm resource ID. Hash từ body chuẩn hóa; cùng scope/key nhưng body khác trả `422 IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD`.

Sau auth/scope, command claim receipt bằng unique constraint trong **cùng transaction** với mutation. Winner ghi entity, Activity, Outbox và response envelope/status/header cần replay trước commit. Contender chờ hữu hạn hoặc trả `409 CONCURRENT_MUTATION_IN_PROGRESS`; sau rollback/savepoint đúng cách đọc receipt đã commit và trả replay. Không ghi receipt ở middleware sau response. Luôn kiểm DB kể cả Redis miss/restart; Redis chỉ tối ưu, correctness không phụ thuộc TTL lock.

Replay vẫn kiểm auth/quyền hiện hành trước trả dữ liệu. Retention tối thiểu 24 giờ là cửa sổ mục tiêu; hết hạn không hứa replay. Redis lease nếu dùng phải có owner token và compare-delete. Validation failure trước mutation không để receipt thành công. Mọi đường crash/replay cần test PostgreSQL thực.

Consumer validate producer/schema/version, claim `(event_id,consumer_group)` cùng transaction với effect; unique constraint xử lý race, SELECT trước INSERT không đủ. Hash khác với cùng event_id là lỗi hợp đồng. Commit Kafka offset chỉ sau DB commit hoặc sau DLQ đã lưu/phát bền có ACK; unsupported schema không được ghi PROCESSED.

---

## 2. BẢNG MÃ LỖI CHUẨN HÓA & ÁNH XẠ NGOẠI LỆ

### 2.1. Danh mục Mã lỗi Toàn cục (Error Codes Registry)

| HTTP Status | Mã lỗi (`error.code`) | Ý nghĩa Nghiệp vụ & Điều kiện Phát sinh |
| :---: | :--- | :--- |
| **`400`** | `VALIDATION_ERROR` | Dữ liệu đầu vào sai định dạng, thiếu trường bắt buộc (vd: thiếu lý do khi task blocked). |
| **`400`** | `INVALID_OPERATION` | Thao tác không hợp lệ với trạng thái hiện tại (vd: xóa cột Kanban mặc định). |
| **`400`** | `STATE_HAS_EXISTING_TASKS` | Cột trạng thái đang chứa task, bắt buộc truyền `target_state_id` để di chuyển task trước khi xóa. |
| **`400`** | `IDEMPOTENCY_KEY_REQUIRED` | Thao tác ghi quan trọng bắt buộc phải gửi kèm header `Idempotency-Key`. |
| **`401`** | `AUTHENTICATION_REQUIRED` | Token JWT không hợp lệ, thiếu header Authorization hoặc token đã hết hạn. |
| **`403`** | `PERMISSION_DENIED` | Không có quyền thực hiện thao tác trên tài nguyên. |
| **`403`** | `LEADER_PERMISSION_REQUIRED` | Chỉ Team Leader mới có quyền thực hiện (US-3.1 Tạo backlog, US-3.4 Đóng sprint, US-5.1 Liên kết repo, sửa trường kế hoạch task). |
| **`403`** | `ASSIGNEE_PERMISSION_REQUIRED`| Thành viên chỉ được đổi trạng thái task được phân công cho mình (US-3.3). |
| **`403`** | `TEACHER_MUTATION_RESTRICTED` | Giảng viên chỉ có quyền xem và feedback, không được can thiệp đổi trạng thái/sprint (US-4.5). |
| **`404`** | `RESOURCE_NOT_FOUND` | Không tìm thấy thực thể hoặc thực thể thuộc dự án khác mà người dùng không có quyền truy cập. |
| **`409`** | `ACTIVE_SPRINT_EXISTS` | Dự án đã có một Sprint đang `ACTIVE`. Quy định chỉ duy nhất 1 Sprint active (US-3.4). |
| **`409`** | `STATE_NAME_EXISTS` | Tên cột trạng thái đã tồn tại trong quy trình Kanban của dự án. |
| **`409`** | `DUPLICATE_IDENTIFIER` | Mã tiền tố dự án (Identifier e.g. `UT`) đã được sử dụng. |
| **`409`** | `GROUP_PROJECT_ALREADY_EXISTS` | Nhóm đồ án thuộc lớp học phần đã có 1 đồ án chính được khởi tạo (US-2.4). |
| **`409`** | `DUPLICATE_GITHUB_USERNAME_IN_PROJECT` | Tài khoản GitHub này đã được liên kết với một thành viên khác trong cùng đồ án (Mục 7.4). |
| **`409`** | `DAG_CYCLE_DETECTED` | Phát hiện quan hệ phụ thuộc vòng lặp khép kín giữa các task (Vi phạm tính chu trình DAG). |
| **`409`** | `ONE_LEADER_PER_PROJECT` | Dự án đã có một Trưởng nhóm đang hoạt động. Phải bàn giao quyền thay vì gán thêm Leader. |
| **`409`** | `CONCURRENT_MUTATION_IN_PROGRESS`| Request với cùng Idempotency-Key đang được xử lý đồng thời. |
| **`422`** | `MEMBER_NOT_ACTIVE` | Thành viên được phân công không thuộc dự án hoặc đã rời khỏi nhóm đồ án (`status != 'ACTIVE'`). |
| **`422`** | `STUDENT_NOT_IN_CLASSROOM_GROUP`| Sinh viên không thuộc danh sách lớp học hoặc nhóm lớp học tương ứng (US-2.3). |
| **`422`** | `GROUP_MEMBER_LIMIT_EXCEEDED`| Số lượng thành viên vượt quá giới hạn tối đa cho phép của một nhóm đồ án (US-2.5). |
| **`422`** | `SCOPE_CHANGE_REASON_REQUIRED`| Bổ sung/rút task khi Sprint đang active bắt buộc phải nhập lý do giải trình Scope Creep (US-3.4). |
| **`422`** | `IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD`| Gửi lại Idempotency-Key cũ nhưng nội dung payload bị thay đổi. |
| **`500`** | `INTERNAL_SERVER_ERROR` | Lỗi máy chủ không xác định, ghi structured log đã làm sạch kèm trace_id. |
| **`409`** | `VERSION_CONFLICT` | Task/Project/Sprint đã đổi so với expected_version. |
| **`409`** | `BOARD_REVISION_CHANGED` | Board đổi, cursor cần refresh đúng bộ lọc. |
| **`409`** | `ASSIGNMENT_DUPLICATE` | Assignment đã có; mutation set phải xử lý no-op rõ. |
| **`405`** | `METHOD_NOT_ALLOWED` | Method không được API hỗ trợ. |
| **`409`** | `TASK_SEQUENCE_COLLISION` | Vi phạm uniqueness sequence, cần kiểm allocator. |
| **`503`** | `IDENTITY_UNAVAILABLE` | Không thể kiểm phiên, không cấp quyền. |
| **`503`** | `AI_UNAVAILABLE` | Không thể kiểm provenance theo contract AI; không chặn thao tác Work thủ công/dashboard. |
| **`503`** | `CLASSROOM_UNAVAILABLE` | Không thể xác minh scope lớp/nhóm cần cho quyết định hiện tại. |

### 2.2. Bảng Ánh xạ từ Ngoại lệ Nghiệp vụ / IntegrityError sang Mã lỗi HTTP
Khi database ném ngoại lệ hoặc trigger thiết kế được triển khai, tầng Exception Handler phải ánh xạ theo SQLSTATE/constraint tại 9.2 và bảng dưới; chưa có mapper Work runtime:

| Ngoại lệ / Trigger Cơ sở dữ liệu | HTTP Code | Mã lỗi Envelope (`error.code`) | Thông điệp Trả về Client (`message`) |
| :--- | :---: | :--- | :--- |
| `IntegrityError: uq_projects_identifier` | `409` | `DUPLICATE_IDENTIFIER` | Mã tiền tố Identifier của dự án đã tồn tại trong hệ thống. |
| `IntegrityError: uq_one_primary_project_per_group`| `409` | `GROUP_PROJECT_ALREADY_EXISTS` | Nhóm đồ án này đã có một dự án chính đang hoạt động. |
| `IntegrityError: uq_one_active_sprint_per_project`| `409` | `ACTIVE_SPRINT_EXISTS` | Mỗi dự án chỉ được phép có duy nhất 1 Sprint ở trạng thái ACTIVE. |
| `IntegrityError: uq_one_leader_per_project` | `409` | `ONE_LEADER_PER_PROJECT` | Dự án đã có Trưởng nhóm đang hoạt động. |
| `IntegrityError: uq_state_name_per_project` | `409` | `STATE_NAME_EXISTS` | Tên cột trạng thái đã tồn tại trong dự án. |
| `IntegrityError: uq_project_member_github_username`| `409` | `DUPLICATE_GITHUB_USERNAME_IN_PROJECT` | Tài khoản GitHub này đã được gắn cho thành viên khác trong nhóm. |
| `CheckViolation (23514): chk_task_relation_dag` | `409` | `DAG_CYCLE_DETECTED` | Phát hiện chu trình phụ thuộc vòng lặp (DAG Cycle) giữa các task. |
| `CheckViolation (23514): chk_task_assignment_membership` | `422` | `MEMBER_NOT_ACTIVE` | Thành viên được phân công phải đang hoạt động (ACTIVE) trong dự án. |
| `rest_framework.exceptions.PermissionDenied` | `403` | `PERMISSION_DENIED` hoặc mã cụ thể | Bạn không có quyền thực hiện thao tác trên tài nguyên này. |
| `rest_framework.exceptions.NotAuthenticated` | `401` | `AUTHENTICATION_REQUIRED` | Yêu cầu xác thực tài khoản đăng nhập hợp lệ. |
| `rest_framework.exceptions.ValidationError` | `400` | `VALIDATION_ERROR` | Dữ liệu gửi lên không vượt qua kiểm tra tính hợp lệ. |
| `django.http.Http404` / `NotFound` | `404` | `RESOURCE_NOT_FOUND` | Tài nguyên không tồn tại hoặc bạn không có quyền truy cập. |

---

## 3. NHÓM 1: QUẢN LÝ DỰ ÁN & THÀNH VIÊN ĐỒ ÁN (EPIC 2)

### 3.1. Lấy Danh sách Đề tài Đồ án của Người dùng Hiện tại (Khóa Phạm vi Truy cập)
* **Phương thức & Đường dẫn:** `GET /projects/`
* **Mô tả & Căn cứ:** Lấy toàn bộ danh sách các dự án đề tài mà người dùng có quyền xem theo đúng vai trò, **tuyệt đối không trả về dự án của nhóm khác** (US-2.1, US-2.3, BFD 1.1).
* **Phân quyền DRF:** `IsAuthenticated`.
* **Logic Lọc QuerySet theo Phạm vi:**
  * **Nếu là Sinh viên:** `Project.objects.filter(members__user_id=request.user.id, members__status='ACTIVE')`.
  * **Nếu là Giảng viên:** `Project.objects.filter(classroom_group_id__in=teacher_class_group_ids)`.
  * Người dùng không thuộc nhóm nào hoặc không phụ trách lớp nào sẽ nhận mảng rỗng `[]`.
  * Identity JWT không có role toàn cục: Work lấy membership ACTIVE tại Work và scope Teacher từ Classroom. Khi Classroom không khả dụng, list không lọc nhóm chỉ trả Project có membership ACTIVE, kèm `meta.scope = {partial: true, source: 'WORK_MEMBERSHIP', teacher_scope: 'UNAVAILABLE'}`. Không cấp quyền Teacher khi chưa xác minh; lọc `classroom_group_id` vẫn trả `503 CLASSROOM_UNAVAILABLE`. Cursor gắn với phạm vi hiện tại; khi scope thay đổi, lấy lại trang đầu.
* **Query Parameters:**
  * `status`: `active` (mặc định), `archived`, `all`.
  * `classroom_group_id`: Lọc theo nhóm lớp học cụ thể (chỉ áp dụng cho Giảng viên).
  * `page_size`: Số bản ghi trên mỗi trang (Mặc định `20`).
  * `cursor`: Con trỏ Base64 phân trang.
* **Success Response (`HTTP 200 OK`):**
  ```json
  {
    "success": true,
    "message": "Lấy danh sách đề tài thành công",
    "data": [
      {
        "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
        "identifier": "UT",
        "name": "Hệ thống Quản lý Đồ án UTask",
        "description": "Nền tảng hỗ trợ sinh viên CNTT làm đồ án theo mô hình Agile",
        "classroom_group_id": "grp_class_k16_01",
        "my_role": "LEADER",
        "total_members": 4,
        "active_sprint_id": "sprint_uuid_01",
        "archived_at": null,
        "created_at": "2026-09-28T08:00:00Z"
      }
    ],
    "meta": {
      "pagination": {
        "total_count": 1,
        "page_size": 20,
        "next_cursor": null,
        "prev_cursor": null,
        "has_next": false
      }
    },
    "error": null
  }
  ```

---

### 3.2. Khởi tạo Đề tài Đồ án & Không gian Làm việc

**Ghi chú cập nhật 15/10/2026:** Nhóm tự chọn và nhập đề tài; không cần đề bài
chung của giảng viên hoặc `class_work_item_id`. Giới hạn một dự án đang hoạt
động mỗi nhóm dưới đây vẫn phản ánh mã Work hiện tại. Xem
[ghi chú liên kết Classroom–Work](../work-service/classroom-project-linking.md)
cho đề xuất phát sự kiện qua Kafka và các việc triển khai sau của Work.
**Đã chốt cho phép nhiều dự án hoạt động đồng thời trên một nhóm.** Giới hạn
một dự án trong mô tả/kết quả lỗi cũ bên dưới là hiện trạng mã nguồn cần sửa,
không còn là yêu cầu mục tiêu. Thiết kế bảng nhận liên kết nằm trong [ERD Classroom](../diagram/classroom-service/erd.md); các quyết định và sơ đồ được mô tả tại [README sơ đồ Classroom](../diagram/classroom-service/README.md).

**Nguồn membership:** Chỉ Group Leader được Classroom xác nhận mới tạo project cho nhóm. Xác minh group đang hợp lệ, user là Leader, danh sách membership/role và source version qua API Classroom đã công bố; kiểm user thuộc group đơn thuần chưa đủ. Không tự nâng một Member thành Leader. Xác minh REST ngoài transaction; tạo Project, toàn bộ ProjectMember được kế thừa, State, current_task_sequence=0, Activity, Outbox và receipt trong một transaction. Unique identifier, khóa chống lặp và khóa giao dịch theo group xử lý race mà vẫn cho phép nhiều Project; source version + reconcile xử lý thay đổi nhóm giữa verify và commit.

* **Phương thức & Đường dẫn:** `POST /projects/`
* **Mô tả & Căn cứ:** Group Leader đã được Classroom xác nhận khởi tạo đề tài, cấp Identifier, kế thừa membership/role nguồn và sinh 5 cột Kanban mặc định (US-2.4, BFD 1.1); không tự nâng Member tạo request thành Leader.
* **Quy chuẩn Định dạng Tiền tố Identifier:** Trường `identifier` bắt buộc tuân thủ regex `^[A-Z0-9]{2,10}$` (từ 2 đến 10 ký tự, chỉ gồm chữ in hoa và chữ số, không khoảng trắng hay ký tự đặc biệt). Tiền tố này dùng để tạo mã hiển thị định danh duy nhất (ví dụ: `UT-1`, `K16DATN-25`) và làm mốc bóc tách regex trong tích hợp GitHub.
* **Ranh giới Xác minh với Classroom Service (US-2.4):**
  1. **Quyền sở hữu Nhóm Lớp học:** Người gọi phải được Classroom xác minh là Group Leader trong đúng nhóm; route xác minh Classroom là hợp đồng liên service cần triển khai, không giả định đã có từ JWT claim. Không có quyền tạo project trả `403 LEADER_PERMISSION_REQUIRED`.
  2. **Quy tắc Duy nhất 1 Dự án Chính mỗi Nhóm (US-2.4):** Hệ thống kiểm tra ràng buộc `uq_one_primary_project_per_group` trên `projects(classroom_group_id) WHERE archived_at IS NULL AND deleted_at IS NULL`. Nếu nhóm đồ án đã có 1 đề tài chính đang hoạt động, hệ thống từ chối và trả về `409 Conflict` (`GROUP_PROJECT_ALREADY_EXISTS`).
* **Phân quyền DRF:** `IsAuthenticated`.
* **Request Body:**
  ```json
  {
    "identifier": "UT",
    "name": "Hệ thống Quản lý Đồ án UTask",
    "description": "Nền tảng hỗ trợ sinh viên CNTT làm đồ án theo mô hình Agile",
    "target_goals": "Xây dựng microservices hoàn chỉnh, tích hợp AI phân tích tiến độ",
    "tech_stack": {
      "backend": "Django",
      "frontend": "Next.js",
      "database": "PostgreSQL 16",
      "broker": "Kafka"
    },
    "start_date": "2026-09-01",
    "end_date": "2026-12-30",
    "classroom_group_id": "grp_class_k16_01"
  }
  ```
* **Success Response (`HTTP 201 Created`):**
  ```json
  {
    "success": true,
    "message": "Khởi tạo đề tài đồ án thành công",
    "data": {
      "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
      "identifier": "UT",
      "name": "Hệ thống Quản lý Đồ án UTask",
      "description": "Nền tảng hỗ trợ sinh viên CNTT làm đồ án theo mô hình Agile",
      "target_goals": "Xây dựng microservices hoàn chỉnh, tích hợp AI phân tích tiến độ",
      "tech_stack": {
        "backend": "Django",
        "frontend": "Next.js",
        "database": "PostgreSQL 16",
        "broker": "Kafka"
      },
      "start_date": "2026-09-01",
      "end_date": "2026-12-30",
      "classroom_group_id": "grp_class_k16_01",
      "github_repo_name": null,
      "github_repo_id": null,
      "created_at": "2026-09-28T08:00:00Z",
      "updated_at": "2026-09-28T08:00:00Z"
    },
    "meta": null,
    "error": null
  }
  ```
* **Error Response (`HTTP 409 Conflict` - Khi nhóm đã có dự án hoặc trùng Identifier):**
  ```json
  {
    "success": false,
    "message": "Nhóm đồ án thuộc lớp học phần này đã có 1 đề tài chính đang hoạt động (US-2.4)",
    "data": null,
    "meta": null,
    "error": {
      "code": "GROUP_PROJECT_ALREADY_EXISTS",
      "details": [
        {
          "field": "classroom_group_id",
          "issue": "Nhóm 'grp_class_k16_01' đã khởi tạo dự án 'UT' trước đó. Mỗi nhóm chỉ được phép có 1 dự án chính."
        }
      ]
    }
  }
  ```
* **Side-effects & Events:**
  - Tạo ProjectMember cho danh sách nhóm đã được Classroom xác minh; role kế thừa nguồn, người tạo phải là Group Leader.
  - Sinh 5 bản ghi `State` mặc định: Backlog, To Do, In Progress, Code Review, Done.
  - Sinh bản ghi `outbox_events` (`event_type='project.created'`, `aggregate_type='project'`).

---

### 3.3. Lấy Thông tin Chi tiết Đề tài Đồ án
* **Phương thức & Đường dẫn:** `GET /projects/{project_id}/`
* **Mô tả & Căn cứ:** Xem thông tin đề tài, mục tiêu, tech stack và trạng thái liên kết GitHub (US-2.1, US-2.3).
* **Phân quyền DRF:** `IsProjectMember` hoặc `IsClassTeacher`.
* **Path Parameters:** `project_id` (UUID).
* **Success Response (`HTTP 200 OK`):**
  ```json
  {
    "success": true,
    "message": "Lấy thông tin đề tài thành công",
    "data": {
      "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
      "identifier": "UT",
      "name": "Hệ thống Quản lý Đồ án UTask",
      "description": "Nền tảng hỗ trợ sinh viên CNTT làm đồ án theo mô hình Agile",
      "target_goals": "Xây dựng microservices hoàn chỉnh, tích hợp AI phân tích tiến độ",
      "tech_stack": {"backend": "Django", "frontend": "Next.js"},
      "start_date": "2026-09-01",
      "end_date": "2026-12-30",
      "classroom_group_id": "grp_class_k16_01",
      "github_repo_name": "utask-team/utask-platform",
      "github_repo_id": "83749210",
      "created_at": "2026-09-28T08:00:00Z",
      "updated_at": "2026-09-28T08:30:00Z"
    },
    "meta": null,
    "error": null
  }
  ```

---

### 3.4. Cập nhật Thông tin Đề tài, Mục tiêu & Tech Stack
* **Phương thức & Đường dẫn:** `PATCH /projects/{project_id}/`
* **Mô tả & Căn cứ:** Cập nhật phạm vi, mục tiêu, công nghệ hoặc ngày bảo vệ đồ án (US-2.3, BFD 1.1).
* **Phân quyền DRF:** `IsProjectLeader` ONLY (Thành viên hoặc Giảng viên gọi bị trả `403 Forbidden`).
* **Request Body:**
  ```json
  {
    "name": "Hệ thống Quản lý Đồ án UTask (Cập nhật)",
    "target_goals": "Hoàn thiện 7 module cốt lõi, đạt kiểm thử độ phủ 85%",
    "tech_stack": {"backend": "Django", "frontend": "Next.js", "cache": "Redis"}
  }
  ```
* **Success Response (`HTTP 200 OK`):**
  ```json
  {
    "success": true,
    "message": "Cập nhật thông tin đề tài thành công",
    "data": {
      "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
      "identifier": "UT",
      "name": "Hệ thống Quản lý Đồ án UTask (Cập nhật)",
      "description": "Nền tảng hỗ trợ sinh viên CNTT làm đồ án theo mô hình Agile",
      "target_goals": "Hoàn thiện 7 module cốt lõi, đạt kiểm thử độ phủ 85%",
      "tech_stack": {
        "backend": "Django",
        "frontend": "Next.js",
        "cache": "Redis"
      },
      "updated_at": "2026-09-28T08:45:00Z"
    },
    "meta": null,
    "error": null
  }
  ```
* **Side-effects & Events:** Ghi `outbox_events` (`event_type='project.updated'`).

---

### 3.5. Xem Danh sách Thành viên Dự án & Đóng góp
* **Phương thức & Đường dẫn:** `GET /projects/{project_id}/members/`
* **Mô tả & Căn cứ:** Liệt kê các thành viên nhóm đồ án, vai trò, năng lực giờ làm và trạng thái liên kết GitHub (US-2.4, BFD 1.2).
* **Phân quyền DRF:** `IsProjectMember` hoặc `IsClassTeacher`.
* **Query Parameters:** `status` (Optional, mặc định `'ACTIVE'`).
* **Success Response (`HTTP 200 OK`):**
  ```json
  {
    "success": true,
    "message": "Lấy danh sách thành viên dự án thành công",
    "data": [
      {
        "id": "pm_uuid_01",
        "user_id": "usr_student_01",
        "display_name": "Nguyễn Văn Trưởng Nhóm",
        "avatar_url": "https://r2.utask.edu.vn/avatars/user_01.png",
        "role": "LEADER",
        "status": "ACTIVE",
        "weekly_capacity": 30,
        "github_username": "truongnhom_it",
        "is_github_verified": true,
        "joined_at": "2026-09-01T08:00:00Z"
      },
      {
        "id": "pm_uuid_02",
        "user_id": "usr_student_02",
        "display_name": "Trần Thị Thành Viên",
        "avatar_url": "https://r2.utask.edu.vn/avatars/user_02.png",
        "role": "MEMBER",
        "status": "ACTIVE",
        "weekly_capacity": 20,
        "github_username": "thanhvien_dev",
        "is_github_verified": true,
        "joined_at": "2026-09-01T08:15:00Z"
      }
    ],
    "meta": {
      "pagination": {
        "total_count": 2,
        "page_size": 20,
        "next_cursor": null,
        "prev_cursor": null,
        "has_next": false
      }
    },
    "error": null
  }
  ```

---

### 3.6. Đồng bộ ProjectMember từ Classroom

Một row bền cho (project_id,user_id), UNIQUE toàn vòng đời. Rejoin/restore cập nhật slot hiện hành dưới lock và ghi Activity trước/sau; không tạo nhiều LEFT rows. joined_at/left_at phản ánh phiên hiện hành, lịch sử qua Activity. Unique ACTIVE Leader chỉ bảo vệ tối đa một; command phải giữ ít nhất một Leader cho project active.
Không mở Work endpoint để thêm người vào Group. UI quản lý GroupMember qua Classroom; Classroom sở hữu enrollment, giới hạn nhóm, một nhóm active/student/class và ngoại lệ sau chốt nhóm.

Work nhận ảnh chụp membership có group_id, danh sách user/role/status và source_version,
validate/dedup rồi tìm mọi Project đang hoạt động của group. Mỗi Project được
khóa và áp dụng phiên bản mới trong giao dịch cùng Activity/Outbox; dự án đã
lưu trữ/xóa không được đồng bộ và không tự mở lại. Event schema/name cụ thể là
đầu ra của bước triển khai producer/consumer, được kiểm thử và khóa phiên bản,
không chỉ suy từ wildcard hoặc tạo hợp đồng giả trước mã nguồn.

Trong MVP role dự án kế thừa role nhóm. Work sở hữu capacity, assignment và quyền tài nguyên dự án. Khi khởi tạo, snapshot đầy đủ từ Classroom; khi source version thiếu/gap phải reconcile, không tự đoán membership từ profile Identity.

---

### 3.7. Cấu hình Weekly Capacity của Thành viên
* **Phương thức & Đường dẫn:** `PATCH /projects/{project_id}/members/{user_id}/capacity/`
* **Mô tả & Căn cứ:** Thiết lập số giờ cam kết làm việc/tuần của từng thành viên làm căn cứ cho AI phân tích nguy cơ quá tải workload (US-2.4, BFD 1.3).
* **Phân quyền DRF:** `IsProjectLeader` ONLY.
* **Request Body:**
  ```json
  {
    "weekly_capacity": 25
  }
  ```
* **Success Response (`HTTP 200 OK`):**
  ```json
  {
    "success": true,
    "message": "Cập nhật năng lực làm việc thành viên thành công",
    "data": {
      "user_id": "usr_student_02",
      "weekly_capacity": 25,
      "updated_at": "2026-09-28T09:00:00Z"
    },
    "meta": null,
    "error": null
  }
  ```

---

### 3.8. Đồng bộ bàn giao Leader đã được Classroom xác nhận
Chuyển Leader nhóm học tập được Leader hiện tại hoặc Teacher đúng lớp thực hiện tại Classroom theo chính sách nhóm. Work không cung cấp public `transfer-leader` thay Group ownership.

Consumer Work khóa project, kiểm source version, hạ role cũ/nâng role mới trong một transaction; partial unique bảo vệ tối đa một ACTIVE Leader, command bảo vệ ít nhất một Leader cho project active. Giữ activity trước/sau và lịch sử assignment; dedup và commit offset sau DB commit. Nếu sản phẩm cần Project Leader độc lập Group Leader, phải có quyết định riêng trước khi thêm endpoint.

---

### 3.9. Thành viên rời nhóm hoặc bị Classroom loại bỏ
Classroom quyết định thay đổi GroupMember. Work nhận source version mới rồi đánh dấu ProjectMember LEFT/REMOVED, ghi left_at/activity/outbox và chặn quyền ghi/giao việc mới. Giữ assignment và đóng góp lịch sử; không xóa user/commit/comment cũ.

Permission task luôn kết hợp membership ACTIVE, kể cả user còn trong TaskAssignment. Consumer removal và command assignment dùng cùng protocol khóa membership/project để không giao việc mới cho người vừa bị loại. Projection có độ trễ; thao tác nhạy cảm cần xác minh Classroom hoặc policy scope proof có expiry/version. Không hứa thu hồi tức thì chỉ bằng Kafka.

---

### 3.10. Đóng băng / Lưu trữ Đề tài Đồ án (Project Archiving)
* **Phương thức & Đường dẫn:** `POST /projects/{project_id}/archive/`
* **Mô tả & Căn cứ:** Đóng băng dự án sau khi bảo vệ hoàn tất hoặc kết thúc học kỳ, chuyển sang chế độ chỉ đọc (Read-only) bảo toàn số liệu (BFD 1.1.4).
* **Phân quyền DRF:** `IsProjectLeader` ONLY.
* **Success Response (`HTTP 200 OK`):**
  ```json
  {
    "success": true,
    "message": "Dự án đồ án đã được đóng băng lưu trữ thành công",
    "data": {
      "project_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
      "archived_at": "2026-09-28T09:20:00Z"
    },
    "meta": null,
    "error": null
  }
  ```

---

### 3.11. Mở khóa / Phục hồi Đề tài Đồ án (Project Unarchiving)

Kiểm active project/group uniqueness dưới barrier trước phục hồi; nếu nhóm đã có project active khác trả GROUP_PROJECT_ALREADY_EXISTS.
* **Phương thức & Đường dẫn:** `POST /projects/{project_id}/unarchive/`
* **Mô tả & Căn cứ:** Phục hồi dự án từ kho lưu trữ về trạng thái hoạt động bình thường (BFD 1.1.4).
* **Phân quyền DRF:** `IsProjectLeader` ONLY.
* **Success Response (`HTTP 200 OK`):**
  ```json
  {
    "success": true,
    "message": "Dự án đồ án đã được phục hồi thành công",
    "data": {
      "project_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
      "archived_at": null,
      "updated_at": "2026-09-28T09:25:00Z"
    },
    "meta": null,
    "error": null
  }
  ```

---

## 4. NHÓM 2: CỘT KANBAN & WORKFLOW STATE ENGINE (EPIC 3)

### 4.1. Lấy danh sách Cột Trạng thái Workflow của Dự án
* **Phương thức & Đường dẫn:** `GET /projects/{project_id}/states/`
* **Mô tả & Căn cứ:** Lấy toàn bộ các cột Kanban theo thứ tự `sequence` tăng dần (US-3.2, BFD 3.1).
* **Phân quyền DRF:** `IsProjectMember` hoặc `IsClassTeacher`.
* **Success Response (`HTTP 200 OK`):**
  ```json
  {
    "success": true,
    "message": "Lấy danh sách cột trạng thái thành công",
    "data": [
      {
        "id": "state_uuid_01",
        "name": "Backlog",
        "slug": "backlog",
        "color": "#94A3B8",
        "sequence": 1000.0,
        "group": "BACKLOG",
        "is_default": true
      },
      {
        "id": "state_uuid_02",
        "name": "To Do",
        "slug": "todo",
        "color": "#3B82F6",
        "sequence": 2000.0,
        "group": "UNSTARTED",
        "is_default": false
      },
      {
        "id": "state_uuid_03",
        "name": "In Progress",
        "slug": "in-progress",
        "color": "#F59E0B",
        "sequence": 3000.0,
        "group": "STARTED",
        "is_default": false
      },
      {
        "id": "state_uuid_04",
        "name": "Code Review",
        "slug": "code-review",
        "color": "#8B5CF6",
        "sequence": 4000.0,
        "group": "REVIEW",
        "is_default": false
      },
      {
        "id": "state_uuid_05",
        "name": "Done",
        "slug": "done",
        "color": "#10B981",
        "sequence": 5000.0,
        "group": "COMPLETED",
        "is_default": false
      }
    ],
    "meta": {
      "pagination": {
        "total_count": 5,
        "page_size": 50,
        "next_cursor": null,
        "prev_cursor": null,
        "has_next": false
      }
    },
    "error": null
  }
  ```

---

### 4.2. Tạo Cột Trạng thái Mới
* **Phương thức & Đường dẫn:** `POST /projects/{project_id}/states/`
* **Mô tả & Căn cứ:** Leader bổ sung cột quy trình làm việc theo đặc thù đề tài (US-3.2, BFD 3.5, UC08.4).
* **Phân quyền DRF:** `IsProjectLeader` ONLY.
* **Request Body:**
  ```json
  {
    "name": "Testing & QA",
    "color": "#EC4899",
    "sequence": 4500.0,
    "group": "REVIEW"
  }
  ```
* **Success Response (`HTTP 201 Created`):**
  ```json
  {
    "success": true,
    "message": "Tạo cột trạng thái mới thành công",
    "data": {
      "id": "state_uuid_testing",
      "project_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
      "name": "Testing & QA",
      "slug": "testing-qa",
      "color": "#EC4899",
      "sequence": 4500.0,
      "group": "REVIEW",
      "is_default": false,
      "created_at": "2026-09-28T09:20:00Z"
    },
    "meta": null,
    "error": null
  }
  ```
* **Error Response (`HTTP 409 Conflict`):**
  ```json
  {
    "success": false,
    "message": "Tên cột trạng thái đã tồn tại trong dự án",
    "data": null,
    "meta": null,
    "error": {
      "code": "STATE_NAME_EXISTS",
      "details": [
        {
          "field": "name",
          "issue": "Tên cột 'Testing & QA' đã được sử dụng"
        }
      ]
    }
  }
  ```

---

### 4.3. Cập nhật Thuộc tính & Vị trí Cột Kanban

Project ownership bất biến; không đổi group của State đang chứa Task bằng PATCH vì làm lệch completion/history. Nếu cần đổi group phải có command migration riêng kiểm completion/audit/closure. Thay default bảo vệ một default/project trong transaction.
* **Phương thức & Đường dẫn:** `PATCH /projects/{project_id}/states/{state_id}/`
* **Phân quyền DRF:** `IsProjectLeader` ONLY.
* **Request Body:**
  ```json
  {
    "name": "QA Validation",
    "color": "#DB2777",
    "sequence": 4600.0
  }
  ```
* **Success Response (`HTTP 200 OK`):**
  ```json
  {
    "success": true,
    "message": "Cập nhật cột trạng thái thành công",
    "data": {
      "id": "state_uuid_testing",
      "project_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
      "name": "QA Validation",
      "slug": "qa-validation",
      "color": "#DB2777",
      "sequence": 4600.0,
      "group": "REVIEW",
      "is_default": false
    },
    "meta": null,
    "error": null
  }
  ```

---

### 4.4. Xóa Cột Trạng thái Workflow (Mở rộng Di chuyển Task Hàng loạt của UTask)

Target cùng project và khác source, còn hợp lệ. Dùng bulk transition command cùng transaction project barrier để cập nhật completion, Activity/Outbox/version/board revision rồi mới tombstone State; không queryset.update bỏ side effect. Đổi terminal group giữ các facts Sprint cũ bất biến.
* **Phương thức & Đường dẫn:** `DELETE /projects/{project_id}/states/{state_id}/`
* **Phân quyền DRF:** `IsProjectLeader` ONLY.
* **Query Parameters:**
  * `target_state_id`: (UUID Optional) Cột trạng thái đích để tự động di chuyển toàn bộ task đang thuộc cột bị xóa sang.
* **Quy tắc An toàn Nghiệp vụ:**
  1. Cấm tuyệt đối xóa nếu cột đang được đánh dấu `is_default = true` $\rightarrow$ Trả về `400 Bad Request` (`INVALID_OPERATION`).
  2. Nếu cột đang chứa task: Khác với Plane từ chối xóa hoàn toàn cột có task (`400 Bad Request`), UTask cung cấp cơ chế mở rộng linh hoạt:
     * Nếu Leader **có truyền `?target_state_id=<uuid>`**: Backend bọc trong transaction để chuyển toàn bộ các task sang `target_state_id` trước khi tombstone cột.
     * Nếu Leader **không truyền `target_state_id`**: Chặn xóa và trả về `400 Bad Request` (`STATE_HAS_EXISTING_TASKS`) kèm thông báo yêu cầu chỉ định trạng thái thay thế.
* **Success Response (`HTTP 200 OK`):**
  ```json
  {
    "success": true,
    "message": "Xóa cột trạng thái thành công và đã di chuyển công việc liên quan",
    "data": {
      "deleted_state_id": "state_uuid_testing",
      "migrated_tasks_count": 4,
      "target_state_id": "state_uuid_02"
    },
    "meta": null,
    "error": null
  }
  ```

---

### 4.5. Quản lý Nhãn Dán Phân loại (Labels)

Label nằm trong baseline mục 4.2, dùng phân loại nhiều chiều; không thay nhóm tính năng Epic. DELETE là tombstone deleted_at, không hard-delete FK Activity; active name unique có điều kiện. TaskLabel xử lý dưới command với audit, không cascade mất lịch sử.

**Giới hạn action:** Member ACTIVE được tạo/sửa metadata nhãn; gán/bỏ label trên Task chỉ Assignee hoặc Leader. PATCH Task của Member không mở label_ids; action mục tiêu `POST /tasks/{task_id}/labels/` nhận ADD/REMOVE và label_ids, cùng transaction Activity/Outbox. Chỉ Leader xóa nhãn. Teacher chỉ xem.
* **`GET /projects/{project_id}/labels/`**
  * **Phân quyền:** `IsProjectMember` hoặc `IsClassTeacher`.
  * **Success Response (`HTTP 200 OK`):**
    ```json
    {
      "success": true,
      "message": "Lấy danh sách nhãn dán thành công",
      "data": [
        {
          "id": "lbl_uuid_01",
          "name": "Backend",
          "color": "#3B82F6",
          "description": "Các tác vụ liên quan đến API và Database"
        },
        {
          "id": "lbl_uuid_02",
          "name": "Bug",
          "color": "#EF4444",
          "description": "Lỗi phần mềm cần khắc phục"
        }
      ],
      "meta": {
        "pagination": {
          "total_count": 2,
          "page_size": 100,
          "next_cursor": null,
          "prev_cursor": null,
          "has_next": false
        }
      },
      "error": null
    }
    ```

* **`POST /projects/{project_id}/labels/`**
  * **Phân quyền:** `IsProjectMember` (Thành viên hoặc Leader tạo nhãn theo BFD 2.3).
  * **Request Body:** `{"name": "Frontend", "color": "#10B981", "description": "Giao diện React/Next.js"}`
  * **Success Response (`HTTP 201 Created`):**
    ```json
    {
      "success": true,
      "message": "Tạo nhãn dán thành công",
      "data": {
        "id": "lbl_uuid_03",
        "project_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
        "name": "Frontend",
        "color": "#10B981",
        "description": "Giao diện React/Next.js",
        "created_at": "2026-09-28T09:25:00Z"
      },
      "meta": null,
      "error": null
    }
    ```

* **`PATCH /projects/{project_id}/labels/{label_id}/`**
  * **Phân quyền:** `IsProjectMember`.
  * **Request Body:** `{"name": "Frontend Web", "color": "#059669"}`
  * **Success Response (`HTTP 200 OK`):**
    ```json
    {
      "success": true,
      "message": "Cập nhật nhãn dán thành công",
      "data": {
        "id": "lbl_uuid_03",
        "name": "Frontend Web",
        "color": "#059669",
        "description": "Giao diện React/Next.js"
      },
      "meta": null,
      "error": null
    }
    ```

* **`DELETE /projects/{project_id}/labels/{label_id}/`**
  * **Phân quyền:** `IsProjectLeader`.
  * **Success Response (`HTTP 200 OK`):**
    ```json
    {
      "success": true,
      "message": "Xóa nhãn dán thành công",
      "data": {
        "deleted_label_id": "lbl_uuid_03"
      },
      "meta": null,
      "error": null
    }
    ```

---

### 4.6. Quản lý Tính năng Lớn / Module (Epics)

**Quyết định Work:** Giữ Epic vì baseline mục 4.2 đã nêu Epic riêng với User Story/Task. Epic nhóm nhiều Work Item theo tính năng, có mô tả/lead/ngày/status riêng; Story vẫn là Task.type=STORY và dùng Task.parent_id khi cần phân rã. Các tiêu đề “Epic 1–5” trong PRD là nhóm yêu cầu, không dùng làm bằng chứng có bảng Epic.

Tham khảo Plane Module/ModuleIssue, nhưng UTask chọn mỗi Task thuộc tối đa một Epic: Task.epic_id nullable, không thêm EpicTask/EpicMember như mô hình nhiều–nhiều của Plane. Epic lead không tự thành Task assignee. Leader gán/bỏ epic_id qua Task command; Epic lead ACTIVE chỉ sửa nội dung/status Epic được giao. Quyết định này áp dụng cùng cho UI/API/context, không suy từ permission monolith Plane.

DELETE là tombstone deleted_at, không hard-delete FK Activity; active name unique có điều kiện. Giữ Task.epic_id để xem lịch sử, loại Epic đã xóa khỏi lựa chọn mới; gán/bỏ Epic dưới command có Activity, không cascade xóa Task.
* **`GET /projects/{project_id}/epics/`**
  * **Phân quyền:** `IsProjectMember` hoặc `IsClassTeacher`.
  * **Success Response (`HTTP 200 OK`):**
    ```json
    {
      "success": true,
      "message": "Lấy danh sách Epic thành công",
      "data": [
        {
          "id": "epic_uuid_01",
          "name": "Module Xác thực & Phân quyền",
          "description": "Toàn bộ chức năng đăng nhập, đăng ký, JWT và RBAC",
          "lead_user_id": "usr_student_01",
          "status": "IN_PROGRESS",
          "start_date": "2026-09-01",
          "target_date": "2026-10-15"
        }
      ],
      "meta": {
        "pagination": {
          "total_count": 1,
          "page_size": 50,
          "next_cursor": null,
          "prev_cursor": null,
          "has_next": false
        }
      },
      "error": null
    }
    ```

* **`POST /projects/{project_id}/epics/`**
  * **Phân quyền:** `IsProjectLeader`.
  * **Request Body:**
    ```json
    {
      "name": "Module Quản lý Công việc & Kanban",
      "description": "Cột Kanban, kéo thả thẻ, chuyển state và subtasks",
      "lead_user_id": "usr_student_02",
      "start_date": "2026-09-15",
      "target_date": "2026-10-30"
    }
    ```
  * **Success Response (`HTTP 201 Created`):**
    ```json
    {
      "success": true,
      "message": "Khởi tạo Module/Epic thành công",
      "data": {
        "id": "epic_uuid_02",
        "project_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
        "name": "Module Quản lý Công việc & Kanban",
        "description": "Cột Kanban, kéo thả thẻ, chuyển state và subtasks",
        "lead_user_id": "usr_student_02",
        "status": "PLANNED",
        "start_date": "2026-09-15",
        "target_date": "2026-10-30",
        "created_at": "2026-09-28T09:28:00Z"
      },
      "meta": null,
      "error": null
    }
    ```

* **`PATCH /projects/{project_id}/epics/{epic_id}/`**
  * **Phân quyền:** Leader hoặc Epic lead ACTIVE chỉ sửa nội dung/status Epic được giao; không mở quyền assign/deadline/Task ngoài whitelist.
  * **Request Body:** `{"status": "COMPLETED"}`
  * **Success Response (`HTTP 200 OK`):**
    ```json
    {
      "success": true,
      "message": "Cập nhật trạng thái Epic thành công",
      "data": {
        "id": "epic_uuid_02",
        "status": "COMPLETED",
        "updated_at": "2026-09-28T10:45:00Z"
      },
      "meta": null,
      "error": null
    }
    ```

* **`DELETE /projects/{project_id}/epics/{epic_id}/`**
  * **Phân quyền:** `IsProjectLeader`.
  * **Success Response (`HTTP 200 OK`):**
    ```json
    {
      "success": true,
      "message": "Xóa Module/Epic thành công",
      "data": {
        "deleted_epic_id": "epic_uuid_02"
      },
      "meta": null,
      "error": null
    }
    ```

---

## 5. NHÓM 3: BACKLOG, TASK LIFECYCLE & PHỤ THUỘC DAG (EPIC 3 & 5)

### 5.1. Tạo Task trong Backlog (Siết quyền Leader - Counter theo Project)

**Allocator chung:** Project.current_task_sequence khởi tạo 0 cùng Project, không có bảng counter riêng. Single và bulk writer đều dùng `UPDATE projects SET current_task_sequence=current_task_sequence+N WHERE id=project_id RETURNING`; row UPDATE tuần tự hóa cấp số, không cần khóa advisory thứ hai cho cùng counter. Mã hiển thị dùng `project.identifier`, không hard-code UT; không tái dùng code sau xóa. Sanitize HTML trước lưu, sinh plain text riêng; strip_tags không phải sanitizer. Ghi acceptance_criteria riêng và xử lý side effect bulk rõ vì bulk_create không gọi save/signals.

* **Phương thức & Đường dẫn:** `POST /projects/{project_id}/tasks/`
* **Mô tả & Căn cứ Nghiệp vụ:** Tạo hạng mục công việc trong Backlog. **Chỉ Trưởng nhóm mới có quyền tạo** theo US-3.1 (US-3.1). Cấp số nguyên tử từ counter/project để chống trùng lặp mã công việc (Sequence 1, BFD 2.1).
* **Quy chuẩn Điểm Story Points:** Trường `story_points` lưu trữ số nguyên không âm (`INTEGER`, theo thang Fibonacci chuẩn: 1, 2, 3, 5, 8...). Khi AI phân tích phân bổ khối lượng (`workload-analysis`) hoặc chia nhỏ nhiệm vụ cho nhiều người, phân bổ points dùng Decimal hoặc phân số, chỉ làm tròn khi hiển thị; không ghi ngược phân bổ vào story_points của Task. Points không phải số giờ, không chia trực tiếp cho capacity giờ/tuần để kết luận quá tải.
* **Phân quyền DRF:** `IsProjectLeader` ONLY. Member gọi vào bị chặn `403 Forbidden`.
* **Request Body:**
  ```json
  {
    "title": "Thiết kế API xác thực JWT và phân quyền RBAC",
    "description_html": "<p>Cần hỗ trợ RS256 và refresh token rotation bảo mật</p>",
    "type": "TASK",
    "priority": "HIGH",
    "story_points": 5,
    "due_date": "2026-10-15",
    "state_id": "state_uuid_02",
    "assignee_ids": ["usr_student_02"],
    "label_ids": ["lbl_uuid_backend"]
  }
  ```
* **Success Response (`HTTP 201 Created`):**
  ```json
  {
    "success": true,
    "message": "Tạo hạng mục công việc Backlog thành công",
    "data": {
      "id": "task_uuid_14",
      "project_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
      "sequence_id": 14,
      "code": "UT-14",
      "title": "Thiết kế API xác thực JWT và phân quyền RBAC",
      "description_html": "<p>Cần hỗ trợ RS256 và refresh token rotation bảo mật</p>",
      "type": "TASK",
      "source": "MANUAL",
      "priority": "HIGH",
      "story_points": 5,
      "due_date": "2026-10-15",
      "state_id": "state_uuid_02",
      "parent_id": null,
      "is_blocked": false,
      "blocked_reason": null,
      "sort_order": 65535.0,
      "assignee_ids": ["usr_student_02"],
      "created_by_user_id": "usr_student_01",
      "created_at": "2026-09-28T09:30:00Z",
      "updated_at": "2026-09-28T09:30:00Z"
    },
    "meta": null,
    "error": null
  }
  ```
* **Error Response (`HTTP 403 Forbidden` - Khi Member gọi):**
  ```json
  {
    "success": false,
    "message": "Chỉ Trưởng nhóm (Leader) mới có quyền tạo hạng mục công việc trong Backlog theo quy định US-3.1",
    "data": null,
    "meta": null,
    "error": {
      "code": "LEADER_PERMISSION_REQUIRED",
      "details": []
    }
  }
  ```
* **Side-effects & Events:**
  - Cấp phát `N=1` qua projects.current_task_sequence UPDATE RETURNING trong transaction chung với receipt/entity.
  - Tự động sinh `description_stripped = strip_tags(html)` làm context sạch cho AI.
  - Ghi bản ghi `task_assignments`, `activities`; bộ đếm nằm trên `projects` (`verb='created'`).
  - Ghi bản ghi `outbox_events` (`event_type='task.created'`).

---

### 5.2. Lấy Danh sách Task Dự án (Phân trang Con trỏ & Tùy biến Thuộc tính theo Plane)
* **Phương thức & Đường dẫn:** `GET /projects/{project_id}/tasks/`
* **Mô tả & Căn cứ:** Truy vấn danh sách công việc phục vụ hiển thị danh sách Backlog list hoặc tìm kiếm (US-3.2, BFD 3.1). Kế thừa cơ chế lọc trường động (`fields`) và mở rộng đối tượng lồng (`expand`) từ Plane để tối ưu băng thông mạng.
* **Phân quyền DRF:** `[IsProjectMember | IsClassTeacher]`.
* **Query Parameters:**
  * `search`: Từ khóa tìm kiếm theo mã công việc (code), tiêu đề (title) hoặc mô tả (US-3.2).
  * `state_id`: Lọc theo cột workflow.
  * `assignee_id`: Lọc theo người phụ trách.
  * `priority`: `LOW`, `MEDIUM`, `HIGH`, `URGENT`.
  * `is_blocked`: `true` để lấy danh sách điểm nghẽn.
  * `due_date_from`: Lọc công việc có hạn chót từ ngày (`YYYY-MM-DD`).
  * `due_date_to`: Lọc công việc có hạn chót đến ngày (`YYYY-MM-DD`).
  * `sprint_id`: Lọc SprintTask có ended_at/deleted_at null; `none` dùng NOT EXISTS membership hiện hành. Không dùng membership lịch sử hoặc state BACKLOG để suy Task chưa ở Sprint.
  * `fields`: Danh sách các trường cần lấy cách nhau bởi dấu phẩy (vd: `fields=id,code,title,priority,state_id,story_points`). Kích thước giảm thực tế phải được đo trên workload của UTask.
  * `expand`: Mở rộng đối tượng liên kết (vd: `expand=assignees,labels,state`). Tự động nhúng thông tin chi tiết thay vì chỉ trả về ID, triệt tiêu các request phụ từ client.
  * `cursor`, `page_size`: Phân trang con trỏ (Mặc định `page_size=50`, tối đa 100).
* **Success Response (`HTTP 200 OK`):**
  ```json
  {
    "success": true,
    "message": "Lấy danh sách công việc thành công",
    "data": [
      {
        "id": "task_uuid_14",
        "code": "UT-14",
        "title": "Thiết kế API xác thực JWT và phân quyền RBAC",
        "priority": "HIGH",
        "story_points": 5,
        "due_date": "2026-10-15",
        "state_id": "state_uuid_02",
        "is_blocked": false,
        "blocked_reason": null,
        "sort_order": 65535.0,
        "assignee_ids": ["usr_student_02"],
        "labels": [{"id": "lbl_uuid_01", "name": "Backend", "color": "#3B82F6"}],
        "subtasks_count": 2,
        "attachments_count": 1,
        "comments_count": 3
      },
      {
        "id": "task_uuid_15",
        "code": "UT-15",
        "title": "Cấu hình Docker Compose cho cụm Microservices",
        "priority": "MEDIUM",
        "story_points": 3,
        "due_date": "2026-10-10",
        "state_id": "state_uuid_03",
        "is_blocked": true,
        "blocked_reason": "Chưa có file .env mẫu từ nhóm trưởng",
        "sort_order": 131070.0,
        "assignee_ids": ["usr_student_01"],
        "labels": [{"id": "lbl_uuid_01", "name": "Backend", "color": "#3B82F6"}],
        "subtasks_count": 0,
        "attachments_count": 0,
        "comments_count": 1
      }
    ],
    "meta": {
      "pagination": {
        "total_count": 2,
        "page_size": 50,
        "next_cursor": null,
        "prev_cursor": null,
        "has_next": false
      }
    },
    "error": null
  }
  ```

---

### 5.2.1. Lấy Bảng Kanban Dự án Gom nhóm theo Cột Workflow (Kanban Grouped Board View - Tối ưu từ Plane)

**Phân trang board riêng:** Tải tiếp bằng `GET /projects/{project_id}/kanban/states/{state_id}/tasks/`, giữ nguyên sprint/assignee/priority/blocked filter. Signed cursor chứa board_revision, state_id, filter_hash và vị trí (sort_order,id); revision khác trả 409 BOARD_REVISION_CHANGED. Board revision tăng khi create/delete/restore/transition/reorder/rebalance hoặc field ảnh hưởng filter đổi; board read phải lấy revision và page từ snapshot đọc nhất quán. Counts bằng toàn bộ dữ liệu theo filter; khi has_more=false, mảng thẻ phải đủ theo column_total_tasks. Ví dụ dưới đây có đủ 5 cột và 1 task, không là trang bị cắt. Cursor list created_at không dùng cho board. Plane có GroupedOffsetPaginator; revision cursor này là thiết kế của UTask.

* **Phương thức & Đường dẫn:** `GET /projects/{project_id}/kanban/`
* **Mô tả & Khắc phục Lỗ hổng Phân trang Phẳng:** Khắc phục triệt để nhược điểm của phân trang phẳng (Flat Pagination làm rỗng các cột Kanban khi số lượng task lớn). Tham khảo gom nhóm `GroupedOffsetPaginator` của Plane, với cursor board riêng của UTask, API này trả về **toàn bộ các cột trạng thái (`states`) của dự án theo thứ tự `sequence ASC`**, bên trong mỗi cột chứa danh sách thẻ con được sắp xếp theo tọa độ kéo thả `sort_order ASC` kèm cờ `has_more` và `next_cursor` phân trang độc lập cho từng cột.
* **Cơ chế Phân trang Từng Cột (Per-column Pagination):** Khi một cột có `has_more = true`, client lấy các thẻ tiếp theo của cột đó bằng cách gọi: `GET /projects/{project_id}/kanban/states/{state_id}/tasks/?cursor={next_cursor}&page_size=50` kèm nguyên bộ lọc và board revision.
* **Phân quyền DRF:** `[IsProjectMember | IsClassTeacher]`.
* **Query Parameters:**
  * `sprint_id`: Lọc theo sprint cụ thể hoặc `none` (chỉ lấy Backlog).
  * `assignee_id`: Lọc theo người phụ trách (US-3.2, UC08.2).
  * `priority`: Lọc theo mức ưu tiên (`LOW`, `MEDIUM`, `HIGH`, `URGENT`).
  * `is_blocked`: `true` để lọc các điểm nghẽn viền đỏ.
  * `limit_per_column`: Số thẻ tối đa trả về ban đầu trên mỗi cột (Mặc định `50`, tối đa `100`).
* **Success Response (`HTTP 200 OK`):**
  ```json
  {
    "success": true,
    "message": "Lấy bảng Kanban thành công",
    "data": {
      "project_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
      "board_revision": 3,
      "columns": [
        {
          "state_id": "state_uuid_01",
          "state_name": "Backlog",
          "state_group": "BACKLOG",
          "sequence": 1000,
          "column_total_tasks": 1,
          "has_more": false,
          "next_cursor": null,
          "tasks": [
            {
              "id": "task_uuid_10",
              "code": "UT-10",
              "title": "Nghiên cứu kiến trúc",
              "sort_order": 10000,
              "version": 1
            }
          ]
        },
        {
          "state_id": "state_uuid_02",
          "state_name": "To Do",
          "state_group": "UNSTARTED",
          "sequence": 2000,
          "column_total_tasks": 0,
          "has_more": false,
          "next_cursor": null,
          "tasks": []
        },
        {
          "state_id": "state_uuid_03",
          "state_name": "In Progress",
          "state_group": "STARTED",
          "sequence": 3000,
          "column_total_tasks": 0,
          "has_more": false,
          "next_cursor": null,
          "tasks": []
        },
        {
          "state_id": "state_uuid_04",
          "state_name": "Code Review",
          "state_group": "REVIEW",
          "sequence": 4000,
          "column_total_tasks": 0,
          "has_more": false,
          "next_cursor": null,
          "tasks": []
        },
        {
          "state_id": "state_uuid_05",
          "state_name": "Done",
          "state_group": "COMPLETED",
          "sequence": 5000,
          "column_total_tasks": 0,
          "has_more": false,
          "next_cursor": null,
          "tasks": []
        }
      ],
      "total_columns": 5,
      "total_tasks": 1
    },
    "meta": null,
    "error": null
  }
  ```

---

### 5.3. Xem Chi tiết Hạng mục Công việc (Task Detail - Tùy biến Expand theo Plane)
* **Phương thức & Đường dẫn:** `GET /tasks/{task_id}/`
* **Mô tả & Căn cứ:** Xem đầy đủ thông tin task bao gồm nội dung rich text, liên kết GitHub, tệp đính kèm và quan hệ DAG. Kế thừa cơ chế `expand` từ Plane để tải có chọn lọc các thực thể phụ thuộc nặng.
* **Phân quyền DRF:** `[IsProjectMember | IsClassTeacher]`.
* **Path Parameters:** `task_id` (UUID).
* **Query Parameters:**
  * `fields`: Danh sách trường cần lấy (vd: `fields=id,code,title,description_html,priority,state_id`).
  * `expand`: Mở rộng các quan hệ chi tiết (vd: `expand=relations,subtasks,github_links,attachments`). Giúp chọn kế hoạch truy vấn khi chỉ cần nội dung text không cần tải tệp đính kèm lớn.
* **Success Response (`HTTP 200 OK`):**
  ```json
  {
    "success": true,
    "message": "Lấy chi tiết công việc thành công",
    "data": {
      "id": "task_uuid_14",
      "project_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
      "sequence_id": 14,
      "code": "UT-14",
      "title": "Thiết kế API xác thực JWT và phân quyền RBAC",
      "description_html": "<p>Cần hỗ trợ RS256 và refresh token rotation bảo mật</p>",
      "type": "TASK",
      "source": "MANUAL",
      "priority": "HIGH",
      "story_points": 5,
      "due_date": "2026-10-15",
      "state_id": "state_uuid_02",
      "parent_id": null,
      "is_blocked": false,
      "blocked_reason": null,
      "sort_order": 65535.0,
      "assignees": [
        {
          "user_id": "usr_student_02",
          "display_name": "Trần Thị Thành Viên",
          "avatar_url": "https://r2.utask.edu.vn/avatars/user_02.png"
        }
      ],
      "labels": [
        {
          "id": "lbl_uuid_01",
          "name": "Backend",
          "color": "#3B82F6"
        }
      ],
      "relations": [
        {
          "id": "rel_uuid_01",
          "related_task_code": "UT-10",
          "relation_type": "BLOCKED_BY"
        }
      ],
      "github_links": [
        {
          "link_type": "PULL_REQUEST",
          "github_ref_id": "#24",
          "github_title": "feat(auth): integrate JWT authentication middleware",
          "github_status": "OPEN"
        }
      ],
      "attachments_count": 1,
      "created_by_user_id": "usr_student_01",
      "created_at": "2026-09-28T09:30:00Z",
      "updated_at": "2026-09-28T09:30:00Z"
    },
    "meta": null,
    "error": null
  }
  ```

---

### 5.4. Cập nhật Thuộc tính Task (Phân tách Quyền hạn theo Từng Trường - Field-level Permissions)
* **Phương thức & Đường dẫn:** `PATCH /tasks/{task_id}/`
* **Mô tả & Căn cứ Nghiệp vụ:** Cập nhật nội dung hoặc kế hoạch công việc. **Hệ thống phân định nghiêm ngặt quyền sửa theo từng nhóm trường dữ liệu (Field-level Security)**:
  * **Trưởng nhóm (`IsProjectLeader`):** Có toàn quyền cập nhật các trường quản lý kế hoạch và điều phối: `title`, `description_html`, `priority`, `story_points`, `due_date`, `assignee_ids`, `epic_id`.
  * **Thành viên được giao việc (`IsTaskAssignee`):** **CHỈ được phép cập nhật nội dung thực hiện (`description_html`)** nhằm ghi chép kết quả hoặc tiến độ kỹ thuật. Tuyệt đối không được phép sửa `story_points`, `due_date`, `priority`, hay `assignee_ids`.
  * **Chuyển trạng thái workflow:** Bắt buộc thực hiện qua endpoint chuyên biệt `PATCH /tasks/{task_id}/transition/` (tuân thủ kiểm tra assignee hoặc leader theo US-3.3).
  * **Báo nghẽn việc (Blocked):** Bắt buộc thực hiện qua endpoint chuyên biệt `PATCH /tasks/{task_id}/block/` hoặc `PATCH /tasks/{task_id}/unblock/`.
  * **Giảng viên (`IsClassTeacher`):** Hoàn toàn không có quyền sửa task (`403 TEACHER_MUTATION_RESTRICTED`), chỉ có quyền gửi nhận xét Feedback.
* **Phân quyền DRF:** `IsTaskAssigneeOrLeader`.
* **Ví dụ 1: Request Body do Trưởng nhóm (Leader) gửi (Sửa kế hoạch, deadline, điểm số):**
  ```json
  {
    "title": "Thiết kế API xác thực JWT và phân quyền RBAC (Hoàn thiện)",
    "story_points": 8,
    "due_date": "2026-10-18",
    "priority": "URGENT",
    "assignee_ids": ["usr_student_02", "usr_student_03"]
  }
  ```
* **Ví dụ 2: Request Body do Thành viên được giao việc (Assignee) gửi (Cập nhật ghi chú/nội dung thực hiện):**
  ```json
  {
    "description_html": "<p>Đã hoàn thành cấu hình middleware RS256, đang viết unit test kiểm thử phân quyền.</p>"
  }
  ```
* **Success Response (`HTTP 200 OK`):**
  ```json
  {
    "success": true,
    "message": "Cập nhật thông tin công việc thành công",
    "data": {
      "id": "task_uuid_14",
      "code": "UT-14",
      "title": "Thiết kế API xác thực JWT và phân quyền RBAC (Hoàn thiện)",
      "story_points": 8,
      "due_date": "2026-10-18",
      "priority": "URGENT",
      "description_html": "<p>Đã hoàn thành cấu hình middleware RS256, đang viết unit test kiểm thử phân quyền.</p>",
      "updated_at": "2026-09-28T09:45:00Z"
    },
    "meta": null,
    "error": null
  }
  ```
* **Error Response (`HTTP 403 Forbidden` - Khi Thành viên được giao cố tình sửa điểm số/deadline/kế hoạch):**
  ```json
  {
    "success": false,
    "message": "Thành viên chỉ được phép cập nhật nội dung thực hiện (description_html). Chỉ Trưởng nhóm mới có quyền điều chỉnh điểm số, hạn chót, mức ưu tiên và phân công (US-3.1)",
    "data": null,
    "meta": null,
    "error": {
      "code": "LEADER_PERMISSION_REQUIRED",
      "details": [
        {
          "field": "story_points",
          "issue": "Bạn không có quyền chỉnh sửa story_points của công việc"
        },
        {
          "field": "due_date",
          "issue": "Bạn không có quyền chỉnh sửa due_date của công việc"
        }
      ]
    }
  }
  ```
* **Side-effects & Events:**
  - Nếu có cập nhật `description_html` $\rightarrow$ Tự động sinh lại `description_stripped = strip_tags(html)` làm context sạch cho AI.
  - Ghi bản ghi `Activity` cho từng thuộc tính bị thay đổi.
  - Ghi `outbox_events` (`event_type='task.updated'`).

---

### 5.5. Chuyển trạng thái và sắp xếp thẻ Kanban
- Endpoint mục tiêu: `PATCH /tasks/{task_id}/transition/`; quyền IsTaskAssigneeOrLeader và membership ACTIVE.
- Body: `target_state_id`, `previous_task_id`, `next_task_id` (nullable) và `expected_version`. Không nhận tọa độ float hoặc is_blocked để vượt action policy.
- Khóa State/cột liên quan, Sprint/membership nếu có và Task theo protocol 9.3; kiểm same-project, neighbor thuộc cột đích, version và quyền hiện hành. UI cũ trả 409 VERSION_CONFLICT; không ghi đè im lặng.
- Đọc rank hiện tại: cột rỗng dùng 10000; đầu/cuối/cặp neighbor tính rank tại server. Chỉ chấp nhận số hữu hạn và khoảng hợp lệ; hết khoảng thì rebalance cùng khóa và tăng board_revision. Thao tác thường đổi một thẻ, rebalance O(n), không có benchmark O(1) toàn request.
- Vào COMPLETED từ nhóm khác gán completed_at. Reorder hoặc chuyển giữa các cột COMPLETED giữ mốc; reopen clear completed_at, lịch sử cũ còn Activity.
- Mutation, Activity và Outbox commit cùng transaction. Block/unblock dùng endpoint riêng 5.6/5.7.

```json
{"target_state_id":"state_uuid_05","previous_task_id":"task_uuid_10","next_task_id":null,"expected_version":2}
```

Success 200 trả envelope năm trường, data chứa task_id/state_id/rank/version/completed_at và board_revision mới.

---

### 5.6. Đánh dấu Task Bị chặn (Blocked) & Nhập Lý do

Task COMPLETED/CANCELLED không được bật blocked mới (400 INVALID_OPERATION). Reason không rỗng sau trim; dùng project barrier/version và Activity/Outbox cùng transaction. Unblock không tự đổi workflow.
* **Phương thức & Đường dẫn:** `PATCH /tasks/{task_id}/block/`
* **Mô tả & Căn cứ:** Thành viên báo cáo điểm nghẽn kỹ thuật hoặc phụ thuộc bên ngoài. **Bắt buộc phải nhập lý do** (US-3.3, Sequence 3, BFD 3.4).
* **Phân quyền DRF:** `IsTaskAssigneeOrLeader`.
* **Request Body:**
  ```json
  {
    "is_blocked": true,
    "blocked_reason": "Đang đợi API login từ nhóm Backend để gắn màn hình UI"
  }
  ```
* **Success Response (`HTTP 200 OK`):**
  ```json
  {
    "success": true,
    "message": "Đã ghi nhận công việc bị nghẽn tiến độ",
    "data": {
      "id": "task_uuid_14",
      "is_blocked": true,
      "blocked_reason": "Đang đợi API login từ nhóm Backend để gắn màn hình UI",
      "updated_at": "2026-09-28T10:05:00Z"
    },
    "meta": null,
    "error": null
  }
  ```
* **Error Response (`HTTP 400 Bad Request` - Nếu thiếu lý do):**
  ```json
  {
    "success": false,
    "message": "Dữ liệu gửi lên không hợp lệ",
    "data": null,
    "meta": null,
    "error": {
      "code": "VALIDATION_ERROR",
      "details": [
        {
          "field": "blocked_reason",
          "issue": "Bắt buộc phải nhập lý do giải trình khi đánh dấu công việc bị nghẽn (is_blocked = true)"
        }
      ]
    }
  }
  ```

---

### 5.7. Gỡ bỏ Trạng thái Bị chặn (Unblock)
* **Phương thức & Đường dẫn:** `PATCH /tasks/{task_id}/unblock/`
* **Phân quyền DRF:** `IsTaskAssigneeOrLeader`.
* **Request Body:** `{}`
* **Success Response (`HTTP 200 OK`):**
  ```json
  {
    "success": true,
    "message": "Đã gỡ bỏ trạng thái bị nghẽn công việc",
    "data": {
      "id": "task_uuid_14",
      "is_blocked": false,
      "blocked_reason": null,
      "updated_at": "2026-09-28T10:10:00Z"
    },
    "meta": null,
    "error": null
  }
  ```

---

### 5.8. Phân rã Sub-task Phân cấp (Hierarchical)

**Whitelist Member:** Chỉ title, description_html, acceptance_criteria của việc con; assignee con là chính người tạo đang được giao task cha, state mặc định, due_date kế thừa cha, story_points chưa ước lượng (null). Member không nhận assignee_ids/priority/story_points/due_date/Sprint từ body; field vượt quyền trả 403. Leader mới được điều phối/ước lượng/ngày. Ví dụ body có estimate/date bên dưới chỉ dành Leader. Áp dụng giống nhau cho manual và AI bulk, không đổi state/estimate của parent. Parent cùng project, không cycle hierarchy.

* **Phương thức & Đường dẫn:** `POST /tasks/{parent_task_id}/subtasks/`
* **Mô tả & Căn cứ:** Thành viên phân nhỏ đầu việc mình phụ trách thành các việc con. **Quy tắc US-5.5: Task cha tuyệt đối không tự động đổi trạng thái khi tạo việc con** (US-5.5, BFD 2.2).
* **Phân quyền DRF:** Member phụ trách task cha HOẶC Leader.
* **Request Body:**
  ```json
  {
    "title": "Viết Unit Tests cho middleware xác thực token",
    "story_points": 2,
    "due_date": "2026-10-12"
  }
  ```
* **Success Response (`HTTP 201 Created`):**
  ```json
  {
    "success": true,
    "message": "Tạo việc con phân cấp thành công",
    "data": {
      "id": "task_uuid_sub_01",
      "code": "UT-15",
      "parent_id": "task_uuid_14",
      "title": "Viết Unit Tests cho middleware xác thực token",
      "story_points": 2,
      "state_id": "state_uuid_02",
      "created_at": "2026-09-28T10:12:00Z"
    },
    "meta": null,
    "error": null
  }
  ```

---

### 5.9. Thiết lập Quan hệ Phụ thuộc DAG (Kiểm tra Chu trình 2 Chiều & Cách ly Dự án)

Response project_id suy từ Task và read-only; DB TaskRelation không có project_id copied; scope suy qua hai Task. BLOCKS giữ hướng; DUPLICATE/RELATES_TO chuẩn hóa UUID min/max và UNIQUE active (task_id,related_task_id,relation_type). Permission trên Task URL trước normalize, không lấy scope từ client.

**Quyền sửa dependency:** Member chỉ đổi relation gắn Task trong URL mình được giao (trước chuẩn hóa chiều BLOCKED_BY); Leader được điều phối mọi task. Quan hệ display BLOCKED_BY được chuẩn hóa sau kiểm action scope; mọi task target phải cùng project. RELATES_TO/DUPLICATE cũng kiểm same-project nhưng không đi vào DAG. Update loại cạnh cũ khỏi traversal; unique canonical edge và self-check. Rule Member cho label/relation/Epic lead là thiết kế bổ sung có giới hạn, chưa là runtime.

* **Phương thức & Đường dẫn:** `POST /tasks/{task_id}/relations/`
* **Mô tả & Căn cứ:** Thiết lập quan hệ `BLOCKS`, `BLOCKED_BY`, `DUPLICATE`, `RELATES_TO`. Command chuẩn hóa BLOCKED_BY thành cạnh BLOCKS, khóa graph theo project rồi kiểm reachability sau lock trước insert/update; hai khóa task đầu cạnh không đủ bảo vệ cycle đồng thời (Sequence 5, BFD 2.4).
* **Bảo vệ Cách ly Dự án (Cross-project Isolation):** Hệ thống và validator `chk_task_relation_dag` trong protocol graph lock bắt buộc kiểm tra cả `task_id` và `related_task_id` phải cùng thuộc một `project_id`. Tuyệt đối cấm tạo quan hệ phụ thuộc giữa 2 task thuộc 2 dự án khác nhau (nếu vi phạm $\rightarrow$ từ chối `400 Bad Request` với mã `INVALID_OPERATION`).
* **Phân quyền DRF:** `IsTaskAssigneeOrLeader`.
* **Request Body:**
  ```json
  {
    "related_task_id": "task_uuid_15",
    "relation_type": "BLOCKS"
  }
  ```
* **Success Response (`HTTP 201 Created`):**
  ```json
  {
    "success": true,
    "message": "Thiết lập quan hệ phụ thuộc thành công",
    "data": {
      "id": "rel_uuid_01",
      "project_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
      "task_id": "task_uuid_14",
      "related_task_id": "task_uuid_15",
      "relation_type": "BLOCKS",
      "created_at": "2026-09-28T10:15:00Z"
    },
    "meta": null,
    "error": null
  }
  ```
* **Error Response (`HTTP 409 Conflict` - Khi tạo chu trình):**
  ```json
  {
    "success": false,
    "message": "Không thể thiết lập quan hệ phụ thuộc do phát hiện chu trình vòng lặp (DAG Cycle)",
    "data": null,
    "meta": null,
    "error": {
      "code": "DAG_CYCLE_DETECTED",
      "details": [
        {
          "issue": "Quan hệ BLOCKS giữa Task UT-14 và Task UT-15 tạo thành đồ thị khép kín"
        }
      ]
    }
  }
  ```

---

### 5.10. Xóa Quan hệ Phụ thuộc

Quyền action dùng IsTaskAssigneeOrLeader với Task trong URL; relation phải có Task URL ở một trong hai đầu; không cho member không liên quan tháo dependency của người khác.

* **Phương thức & Đường dẫn:** `DELETE /tasks/{task_id}/relations/{relation_id}/`
* **Phân quyền DRF:** `IsTaskAssigneeOrLeader`.
* **Success Response (`HTTP 200 OK`):**
  ```json
  {
    "success": true,
    "message": "Đã gỡ bỏ quan hệ phụ thuộc",
    "data": {
      "deleted_relation_id": "rel_uuid_01"
    },
    "meta": null,
    "error": null
  }
  ```

---

### 5.11. Lưu trữ / Đóng băng Task (Soft Freeze)
* **Phương thức & Đường dẫn:** `POST /tasks/{task_id}/archive/`
* **Phân quyền DRF:** `IsProjectLeader` ONLY (US-3.1).
* **Success Response (`HTTP 200 OK`):**
  ```json
  {
    "success": true,
    "message": "Lưu trữ công việc thành công",
    "data": {
      "id": "task_uuid_14",
      "archived_at": "2026-09-28T10:20:00Z"
    },
    "meta": null,
    "error": null
  }
  ```

---

### 5.12. Xóa Mềm Task vào Thùng Rác (Soft Deletion)
* **Phương thức & Đường dẫn:** `DELETE /tasks/{task_id}/`
* **Mô tả & Căn cứ:** Đưa task vào thùng rác (`deleted_at = now()`), hỗ trợ khôi phục khi cần thiết (US-3.1, BFD 2.5).
* **Quy tắc Lan truyền Xóa mềm (Cascading Soft Deletion):** Khi task cha bị chuyển vào thùng rác, hệ thống thực thi trong một `transaction.atomic()` duy nhất: đánh dấu deleted_at cho toàn bộ subtree kèm deletion_batch_id, kết thúc membership Sprint hiện hành và vô hiệu relation liên quan bằng deleted_at; không xóa vật lý lịch sử để tránh gây tắc nghẽn đồ thị DAG của các task khác.
* **Phân quyền DRF:** `IsProjectLeader` ONLY.
* **Success Response (`HTTP 200 OK`):**
  ```json
  {
    "success": true,
    "message": "Đã chuyển công việc vào thùng rác",
    "data": {
      "id": "task_uuid_14",
      "deleted_at": "2026-09-28T10:25:00Z"
    },
    "meta": null,
    "error": null
  }
  ```

---

### 5.13. Phục hồi Task từ Kho Lưu trữ (Task Unarchive)
* **Phương thức & Đường dẫn:** `POST /tasks/{task_id}/unarchive/`
* **Mô tả & Căn cứ:** Mở lại task đã đóng băng về bảng Kanban hoạt động (BFD 2.5.2).
* **Phân quyền DRF:** `IsProjectLeader` ONLY.
* **Success Response (`HTTP 200 OK`):**
  ```json
  {
    "success": true,
    "message": "Phục hồi công việc từ kho lưu trữ thành công",
    "data": {
      "id": "task_uuid_14",
      "archived_at": null,
      "updated_at": "2026-09-28T10:26:00Z"
    },
    "meta": null,
    "error": null
  }
  ```

---

### 5.14. Khôi phục Task từ Thùng Rác (Task Restore)

Restore chỉ phục hồi subtree cùng deletion_batch_id, không phục hồi task đã deleted độc lập trước đó. Kiểm lại parent/state/scope và DAG dưới graph lock; không tự bật relation tới task còn deleted hoặc tạo cycle. Không phục hồi membership hiện hành cũ; Leader dùng scope command để lên kế hoạch lại; snapshot Sprint cũ giữ nguyên.

* **Phương thức & Đường dẫn:** `POST /tasks/{task_id}/restore/`
* **Mô tả & Căn cứ:** Khôi phục task đã xóa mềm từ thùng rác về lại Backlog (BFD 2.5).
* **Phân quyền DRF:** `IsProjectLeader` ONLY.
* **Success Response (`HTTP 200 OK`):**
  ```json
  {
    "success": true,
    "message": "Khôi phục công việc từ thùng rác thành công",
    "data": {
      "id": "task_uuid_14",
      "deleted_at": null,
      "updated_at": "2026-09-28T10:27:00Z"
    },
    "meta": null,
    "error": null
  }
  ```

---

## 6. NHÓM 4: VÒNG ĐỜI SPRINT & CHU KỲ PHÁT TRIỂN (P1 PILOT - US-3.4)

### 6.1. Lấy Danh sách Chu kỳ Sprint của Dự án
* **Phương thức & Đường dẫn:** `GET /projects/{project_id}/sprints/`
* **Mô tả & Căn cứ:** Liệt kê các chu kỳ Sprint (DRAFT, ACTIVE, COMPLETED) để phục vụ màn hình lập kế hoạch Sprint Planning và Burndown tracking (US-3.4, BFD 4.1, Baseline Mục 14).
* **Phân quyền DRF:** `IsProjectMember` hoặc `IsClassTeacher`.
* **Success Response (`HTTP 200 OK`):**
  ```json
  {
    "success": true,
    "message": "Lấy danh sách Sprint thành công",
    "data": [
      {
        "id": "sprint_uuid_01",
        "name": "Sprint 1: Nền tảng Kiến trúc & Xác thực",
        "goal": "Hoàn thiện DB Schema, kết nối Kafka và màn hình Login",
        "status": "ACTIVE",
        "start_date": "2026-10-01",
        "end_date": "2026-10-14",
        "sort_order": 1000.0,
        "total_tasks_count": 15,
        "completed_tasks_count": 8
      },
      {
        "id": "sprint_uuid_02",
        "name": "Sprint 2: Kanban & Quản lý Công việc",
        "goal": "Kanban có version, Task Blocked và AI context qua Kafka",
        "status": "DRAFT",
        "start_date": "2026-10-15",
        "end_date": "2026-10-28",
        "sort_order": 2000.0,
        "total_tasks_count": 5,
        "completed_tasks_count": 0
      }
    ],
    "meta": {
      "pagination": {
        "total_count": 2,
        "page_size": 20,
        "next_cursor": null,
        "prev_cursor": null,
        "has_next": false
      }
    },
    "error": null
  }
  ```

---

### 6.2. Xem Chi tiết một Chu kỳ Sprint
* **Phương thức & Đường dẫn:** `GET /sprints/{sprint_id}/`
* **Phân quyền DRF:** `IsProjectMember` hoặc `IsClassTeacher`.
* **Success Response (`HTTP 200 OK`):**
  ```json
  {
    "success": true,
    "message": "Lấy thông tin chi tiết Sprint thành công",
    "data": {
      "id": "sprint_uuid_01",
      "project_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
      "name": "Sprint 1: Nền tảng Kiến trúc & Xác thực",
      "goal": "Hoàn thiện DB Schema, kết nối Kafka và màn hình Login",
      "status": "ACTIVE",
      "start_date": "2026-10-01",
      "end_date": "2026-10-14",
      "sort_order": 1000.0,
      "total_tasks": 15,
      "total_story_points": 45,
      "completed_story_points": 24,
      "created_at": "2026-09-28T09:00:00Z"
    },
    "meta": null,
    "error": null
  }
  ```

---

### 6.3. Tạo Sprint Mới (Trạng thái DRAFT)
* **Phương thức & Đường dẫn:** `POST /projects/{project_id}/sprints/`
* **Phân quyền DRF:** `IsProjectLeader` ONLY.
* **Request Body:**
  ```json
  {
    "name": "Sprint 1: Nền tảng Kiến trúc & Xác thực",
    "goal": "Hoàn thiện DB Schema, kết nối Kafka và màn hình Login",
    "start_date": "2026-10-01",
    "end_date": "2026-10-14"
  }
  ```
* **Success Response (`HTTP 201 Created`):**
  ```json
  {
    "success": true,
    "message": "Tạo chu kỳ Sprint thành công",
    "data": {
      "id": "sprint_uuid_01",
      "project_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
      "name": "Sprint 1: Nền tảng Kiến trúc & Xác thực",
      "goal": "Hoàn thiện DB Schema, kết nối Kafka và màn hình Login",
      "status": "DRAFT",
      "start_date": "2026-10-01",
      "end_date": "2026-10-14",
      "sort_order": 65535.0,
      "created_at": "2026-09-28T10:30:00Z"
    },
    "meta": null,
    "error": null
  }
  ```

---

### 6.4. Cập nhật Mục tiêu & Ngày Chu kỳ Sprint
* **Phương thức & Đường dẫn:** `PATCH /sprints/{sprint_id}/`
* **Mô tả & Căn cứ:** Leader cập nhật tên, mục tiêu hoặc ngày của Sprint khi đang ở trạng thái DRAFT hoặc ACTIVE (US-3.4).
* **Phân quyền DRF:** `IsProjectLeader` ONLY.
* **Request Body:**
  ```json
  {
    "goal": "Hoàn thiện DB Schema, kết nối Kafka, hoàn thành xác thực và kiểm thử tích hợp",
    "end_date": "2026-10-16"
  }
  ```
* **Success Response (`HTTP 200 OK`):**
  ```json
  {
    "success": true,
    "message": "Cập nhật thông tin Sprint thành công",
    "data": {
      "id": "sprint_uuid_01",
      "goal": "Hoàn thiện DB Schema, kết nối Kafka, hoàn thành xác thực và kiểm thử tích hợp",
      "end_date": "2026-10-16",
      "updated_at": "2026-09-28T10:32:00Z"
    },
    "meta": null,
    "error": null
  }
  ```

---

### 6.5. Kích hoạt Sprint (Active Duy nhất 1 Sprint)
* **Phương thức & Đường dẫn:** `POST /projects/{project_id}/sprints/{sprint_id}/start/`
* **Phân quyền DRF:** `IsProjectLeader` ONLY.
* **Xử lý:** Chuyển `status = 'ACTIVE'`. Ràng buộc `uq_one_active_sprint_per_project` bảo đảm tính duy nhất.
* **Success Response (`HTTP 200 OK`):**
  ```json
  {
    "success": true,
    "message": "Kích hoạt Sprint thành công",
    "data": {
      "id": "sprint_uuid_01",
      "status": "ACTIVE",
      "started_at": "2026-10-01T08:00:00Z"
    },
    "meta": null,
    "error": null
  }
  ```
* **Error Response (`HTTP 409 Conflict`):**
  ```json
  {
    "success": false,
    "message": "Không thể kích hoạt Sprint do dự án đang có một Sprint khác đang chạy",
    "data": null,
    "meta": null,
    "error": {
      "code": "ACTIVE_SPRINT_EXISTS",
      "details": [
        {
          "issue": "Mỗi dự án chỉ được phép có duy nhất 1 Sprint ở trạng thái ACTIVE (theo US-3.4)"
        }
      ]
    }
  }
  ```

---

### 6.6. Thêm / Rút Task Khỏi Sprint (Quản lý Scope Creep & Cách ly Dự án)

Request scope_change_reason map vào SprintTask.scope_change_reason cho ADD, removal_reason cho REMOVE; không ghi đè lý do ADD. is_scope_creep trong response là field **suy ra** từ thời điểm added_at và started_at, không cột DB. Closure facts/history chỉ chốt ở Sprint.closure_snapshot, không lặp state/points/assignee snapshots trên từng junction.

Chỉ sửa scope Sprint DRAFT/ACTIVE; COMPLETED trả INVALID_OPERATION. ADD chỉ Task chưa có SprintTask hiện hành, hoặc no-op nếu đã ở Sprint này; chuyển giữa Sprint mở cần REMOVE rồi ADD trong cùng transaction có lý do. REMOVE kết thúc hàng hiện hành bằng ended_at/end_reason=REMOVED, không dùng deleted_at làm mốc scope. SprintTask membership, scope history/Activity/Outbox/version/receipt ghi cùng transaction theo protocol khóa chung. Không có hai membership hiện hành/task; ADD/REMOVE lặp không tạo hàng/lịch sử giả.
* **Phương thức & Đường dẫn:** `POST /sprints/{sprint_id}/tasks/`
* **Mô tả & Căn cứ:** Đưa task vào hoặc rút task khỏi Sprint. **Nếu Sprint đang ACTIVE, bắt buộc phải giải trình lý do Scope Creep** (US-3.4, BFD 4.2).
* **Bảo vệ Cách ly Dự án (Cross-project Isolation):** Serializer/command và ràng buộc same-project mục tiêu phải xác minh các `task_ids` phải có cùng `project_id` với Sprint. Nếu phát hiện task thuộc dự án khác, yêu cầu bị từ chối ngay với `400 Bad Request` (`INVALID_OPERATION`).
* **Phân quyền DRF:** `IsProjectLeader` ONLY.
* **Request Body:**
  ```json
  {
    "action": "ADD",
    "task_ids": ["task_uuid_14", "task_uuid_15"],
    "scope_change_reason": "Bổ sung chức năng xuất PDF theo yêu cầu đột xuất của Giảng viên hướng dẫn"
  }
  ```
* **Success Response (`HTTP 200 OK`):**
  ```json
  {
    "success": true,
    "message": "Cập nhật phạm vi Sprint thành công",
    "data": {
      "sprint_id": "sprint_uuid_01",
      "modified_task_ids": ["task_uuid_14", "task_uuid_15"],
      "is_scope_creep": true
    },
    "meta": null,
    "error": null
  }
  ```

---

### 6.7. Đóng Sprint và dời việc dở dang (P1)
- Endpoint mục tiêu: POST `/sprints/{sprint_id}/close/`, IsProjectLeader, Idempotency-Key, expected_version và target_sprint_id DRAFT cùng project hoặc null về backlog. Không tự start target.
- Khóa Project rồi State/Sprint/Task theo protocol chung. Kiểm quyền/source ACTIVE/version. Work chốt facts/state/points/assignees/scope và **chỉ số theo rules Work** vào closure_snapshot versioned, có formula_version/captured_at; không có service metric bên ngoài phải chờ.
- Dựng daily_burndown từ lịch sử state/reopen/estimate/scope, không suy quá khứ từ aggregate hiện tại. Snapshot immutable sau close; lịch sử đã đóng không đổi theo task bị sửa/xóa sau này. Chi tiết công thức/timezone/cửa sổ phải quyết định trước triển khai.
- Kết thúc mọi SprintTask nguồn bằng ended_at/end_reason; giữ terminal COMPLETED/CANCELLED, chỉ đưa việc còn dở sang target/backlog. Tạo membership đích trong cùng transaction, không đổi workflow Task chỉ vì rollover.
- Sprint status, snapshot, Activity, Outbox và receipt response commit atomic; publisher phát closure fact sau commit, không DB tự gửi Kafka. Nhóm AI có thể nhận facts để phân tích, không trở thành nguồn metric chính thức Work.

Response 200 data có sprint_id/status/closed_at/snapshot_version/target và summary Work tính theo formula_version. Retry receipt không close/rollover lần nữa. Metric pipeline lớn nếu cần job hậu xử lý vẫn thuộc Work, phải có trạng thái báo cáo chưa xong và finalization watermark; không hứa snapshot hoàn chỉnh khi dữ kiện lịch sử thiếu.

---

### 6.8. Work API xem Burndown
GET mục tiêu `/sprints/{sprint_id}/burndown/`, Member ACTIVE hoặc Teacher đúng lớp. Work đọc rules/history và snapshot Work; không gọi AI để tính chart. Sprint đã đóng trả phần daily_burndown/version/captured_at đã chốt, Sprint mở có computed_at/source version và policy dữ liệu thiếu.

Quyền/check/filter theo scope chung, response năm trường. Đây là API đề xuất chưa có URLconf/source, cần tests history/close/reopen/removed scope. Không có route/database tiến độ riêng.

---

### 6.9. Work API tiến độ và workload
GET mục tiêu `/sprints/{sprint_id}/progress/` (và project dashboard tương ứng theo scope), Member/Teacher đúng lớp. Work tính completion counts/points/distribution/velocity theo formula_version, closed Sprint đọc closure_snapshot bất biến. Không gọi LLM để lấy số liệu.

**Quy tắc Work đã chọn:** timestamp UTC, ngày/chốt cuối ngày theo Asia/Ho_Chi_Minh; top-level planned Work Item là đơn vị báo cáo points, không cộng cả parent/subtask. Points null là chưa ước lượng: sum chỉ các estimate đã có, trả kèm estimated_count/unestimated_count, không gọi tổng đó là đầy đủ. COMPLETED là hoàn thành, CANCELLED báo riêng. Velocity là tổng points đã ước lượng của top-level Task COMPLETED trong closure facts, kèm coverage; không cộng points CANCELLED. Scope ADD/REMOVE dựng theo timeline và lý do, không giữ mẫu số cố định rồi gọi Scope Creep là hoàn thành.

Phân bổ multi-assignee dùng Decimal/phần dư để giữ tổng; story point khác giờ/capacity, không công bố tỷ lệ quá tải từ points/weekly_capacity. Rule overdue là due_date trước ngày nghiệp vụ hiện hành và Task chưa terminal; blocked thủ công và dependency chưa xong là hai tín hiệu riêng. Ngưỡng đánh giá mức rủi ro AI thuộc hợp đồng nhóm AI, không tự biến thành công thức hiệu suất trong Work.

Rule signal Work là dữ kiện cho nhóm AI phân tích Risk/Workload; report AI hiển thị từ AI API, không nhét vào progress_snapshot Work. Ranh giới giao tiếp theo [tài liệu hệ thống](../system/communication.md).

---

## 7. NHÓM 5: GIAO TIẾP TRỢ LÝ AI (HUMAN-IN-THE-LOOP - EPIC 5)

### 7.1. User gọi AI API; Work chỉ cấp context và áp dụng
User yêu cầu phân tích/đề xuất và xem kết quả qua **AI API**, không Work facade tạo job AI. Nội bộ request/context/results/AIDB là trách nhiệm nhóm AI. Không thêm Work route `/ai/backlog-proposals/` hay `/ai/subtask-proposals/` để tự sở hữu AI request.

Work phát facts tối thiểu/version/tombstone qua outbox/Kafka. Context thiếu có thể xin snapshot theo job bất đồng bộ với request/proposal reference, actor scope, source version/deadline; chỉ đọc Work DB, không agent REST/DB context và không Kafka sync RPC từng field. Source khác do owner khác cấp.

Work cần contract từ nhóm AI: proposal/run/item ref, approved revision/hash, project/parent/action binding, source versions và verifier provenance. Không thiết kế bảng AI trong tài liệu Work; chưa có contract/provider source thì ghi dependency Chưa xác minh, không tự tin client source=AI. Xem [ranh giới giao tiếp Work–AI](../system/communication.md).

User xem/sửa draft bên AI chưa làm đổi Work. User bấm apply gọi Work bằng actor token; Work kiểm lại permission/version/whitelist rồi commit, trả/publish bằng chứng. AI chỉ đánh APPLIED sau Work commit; lost response/event dùng receipt lookup/replay. Các API bulk apply 7.2/7.3 giữ phạm vi Work hiện có.

---

### 7.2. Phê duyệt Áp dụng Bản nháp Backlog từ AI (Bulk Apply)

Work Task lưu scalar ai_proposal_id/ai_local_id/ai_revision, không ai_metadata JSONB; namespace/semantics opaque và verifier cần nhóm AI đồng ý. Không nhận source=AI do client tự khai như bằng chứng.
Work tự tính và giữ ai_payload_hash SHA-256 bất biến cho từng item được duyệt, để replay qua batch/key khác không phải so với Task đang được sửa. Hash bao gồm semantic project/parent/action/revision/edited content/dependency refs chuẩn hóa, loại actor/key/server-generated ID/version. Unique project/proposal/local giữ identity; hash giữ bằng chứng cùng nội dung được duyệt. Trong batch mới, item cũ hash trùng dùng ID cũ, hash khác rollback toàn bộ; counter chỉ cấp cho item mới. Không tạo Task/Activity/Outbox lần nữa cho item đã tồn tại. Receipt key cũ replay response gốc theo 1.5.
* **Phương thức & Đường dẫn:** `POST /projects/{project_id}/tasks/bulk-apply-ai/`
* **Mô tả & Căn cứ:** Leader xem xét đề xuất nháp của AI trên Modal, chỉnh sửa và bấm duyệt để tạo hàng loạt task có `source = 'AI_BACKLOG'` (US-5.4, Sequence 6, BFD 5.4 - Human-in-the-loop).
* **Phân quyền DRF:** `IsProjectLeader` ONLY.
* **Request Body:**
  ```json
  {
    "proposal_id": "proposal_ai_01",
    "context_version": 42,
    "expected_project_version": 3,
    "tasks": [
      {
        "local_id": "draft_1",
        "title": "Cấu hình hạ tầng",
        "description_html": "<p>PostgreSQL, Kafka KRaft, Redis</p>",
        "acceptance_criteria": "Stack khởi động và health checks đạt",
        "priority": "HIGH",
        "story_points": 5,
        "type": "TASK",
        "dependencies": []
      },
      {
        "local_id": "draft_2",
        "title": "Viết hợp đồng API",
        "description_html": "<p>Xuất OpenAPI từ source thật</p>",
        "acceptance_criteria": "OpenAPI khớp API đã triển khai",
        "priority": "MEDIUM",
        "story_points": 3,
        "type": "TASK",
        "dependencies": [
          "draft_1"
        ]
      }
    ]
  }
  ```
* **Success Response (`HTTP 201 Created`):**
  ```json
  {
    "success": true,
    "message": "Đã phê duyệt và khởi tạo hàng loạt 2 công việc từ đề xuất AI",
    "data": {
      "created_count": 2,
      "source": "AI_BACKLOG",
      "task_codes": ["UT-15", "UT-16"]
    },
    "meta": null,
    "error": null
  }
  ```
* **Block allocation của UTask:** Trong transaction chung với durable receipt, một UPDATE projects.current_task_sequence cấp N mã, bulk-create Task/Assignment/Label/Relation/Activity/Outbox rồi lưu response receipt. Counter update đã khóa row; không trộn advisory UUID64/hashtext. Sanitize/default/completion logic được xử lý trước bulk vì bulk_create bỏ save/signals. N task vẫn cần O(N) ghi; hiệu năng phải benchmark.
* **Dữ liệu apply:** proposal_id, context_version, expected_project_version, các item có local_id, ai_revision (map revision đã duyệt) và acceptance_criteria; dependencies tham chiếu local_id được map sang UUID rồi validate cùng project/DAG dưới graph lock. Không để schema mất acceptance criteria hoặc dependency.
* **Áp dụng một lần:** Ngoài replay cùng Idempotency-Key, unique `(project_id, ai_proposal_id, ai_local_id)` trên Task (map từ proposal_id/local_id request) cho item AI đã apply ngăn tạo trùng khi user gửi lại proposal bằng key mới. Work chỉ giữ provenance/operation ref nhỏ; schema/report/prompt/runtime thuộc nhóm AI, ngoài phạm vi Work.

---

### 7.3. Phê duyệt Áp dụng Bản nháp Sub-tasks từ AI

Whitelist và giới hạn Member giống 5.8; ví dụ dưới đây dành Member, không có trường điều phối. Leader mới được bổ sung story_points/due_date/assignee_ids theo quyền. Body có proposal_id/context_version/expected_parent_version, item có local_id/acceptance_criteria/dependencies như ví dụ. Apply không thay state/estimate parent, không tự assign người khác; stale version hoặc mất quyền bị từ chối. Item replay bằng key mới vẫn có unique proposal provenance như 7.2.

* **Phương thức & Đường dẫn:** `POST /tasks/{parent_task_id}/subtasks/bulk-apply-ai/`
* **Mô tả & Căn cứ:** Member/Leader phê duyệt danh sách việc con do AI chia nhỏ (US-5.5, Sequence 7, BFD 5.4). Gán `source = 'AI_DECOMPOSED'` và `parent_id = parent_task_id`. Áp dụng cơ chế Block Allocation tương tự để bảo đảm hiệu năng.
* **Phân quyền DRF:** `IsTaskAssigneeOrLeader`.
* **Request Body:**
  ```json
  {
    "proposal_id": "proposal_ai_02",
    "context_version": 42,
    "expected_parent_version": 2,
    "subtasks": [
      {
        "local_id": "child_1",
        "title": "Viết test response",
        "description_html": "<p>Kiểm response thành công và lỗi</p>",
        "acceptance_criteria": "Có test cho các trường hợp được giao",
        "dependencies": []
      },
      {
        "local_id": "child_2",
        "title": "Bổ sung tài liệu thao tác",
        "description_html": "<p>Mô tả đầu vào và kết quả</p>",
        "acceptance_criteria": "Tài liệu khớp hành vi API",
        "dependencies": [
          "child_1"
        ]
      }
    ]
  }
  ```
* **Success Response (`HTTP 201 Created`):**
  ```json
  {
    "success": true,
    "message": "Đã phê duyệt và khởi tạo 2 việc con từ AI",
    "data": {
      "parent_task_id": "task_uuid_14",
      "created_count": 2,
      "source": "AI_DECOMPOSED",
      "created_subtask_ids": ["task_uuid_sub_01", "task_uuid_sub_02"]
    },
    "meta": null,
    "error": null
  }
  ```

---

### 7.4. Action từ phân tích rủi ro/workload (P1, đề xuất)
Report thuộc AIDB nhóm AI. Work không thêm bảng ProjectRiskAnalysis; chỉ thực thi action đã user duyệt như deadline/priority/assignment theo command/permission hiện có. Teacher xem risk không được sửa Task/Sprint; không nhận generic patch arbitrary field.

Thiết kế receipt Work có thể thêm ai_proposal_id/ai_item_id logical và operation_id để unique một operation/proposal-item, lưu approved payload hash/affected IDs/versions trong response. Client đổi key hoặc actor khác bấm cùng item không tạo mutation thứ hai. Retention operation identity phải phủ thời gian proposal còn apply, khác cache HTTP replay 24h. Chưa có migration/endpoint action, cần contract phía AI trước implementation.

### 7.5. Kết quả apply và đối soát với nhóm AI
Work commit mutation+Activity+receipt+outbox kết quả trong cùng transaction. Event mục tiêu `work.ai_proposal.applied` chứa project/actor, proposal/run/item refs, operation_id, approved revision/hash, affected IDs/versions và committed_at; tên/schema cần nhóm AI thống nhất.

Nhóm AI quản lý trạng thái phía mình. Work cung cấp receipt/replay/operation-status contract có quyền backend, không REST context cho agent. Response/event mất sau commit thì tra operation, không chạy mutation mới để đoán. Failed attempt không hạ một operation đã commit; Work rollback không có success evidence. Xem [giao tiếp giữa các service](../system/communication.md).

---

## 8. NHÓM 6: TRUY VẾT GITHUB, TRAO ĐỔI & KIỂM TOÁN (EPIC 4 & 5)

### 8.1. Chỉ định Repository Chính của Nhóm Đồ án (Ranh giới Integration Service)

**Connection authority:** Integration mới là nguồn repository chính/installation/trạng thái. Facade Work chuyển command có operation_id và actor proof sang Integration; name/owner/default branch lấy từ response đã xác minh, không tin metadata client. Hai DB không có chung transaction: giữ trạng thái pending khi cần, dedup operation và reconcile projection từ event connection có generation/version. Repo đổi/revoke ngừng sync generation cũ, giữ lịch sử link kèm repo_id; không chỉ GET verify rồi tự quyết định repo chính tại Work.

* **Phương thức & Đường dẫn:** `POST /projects/{project_id}/github/repository/`
* **Mô tả & Căn cứ:** Leader chỉ định 1 repository chính đại diện cho đồ án nhóm (US-5.1, Mục 7.4, BFD 6.1). Chặn Member kết nối repo riêng lẻ.
* **Ranh giới Bounded Context & Bảo mật:** `work-service` **tuyệt đối không kết nối trực tiếp đến GitHub API** (không nắm GitHub App Private Key hay OAuth Client Secret). Ranh giới truy cập GitHub được cô lập hoàn toàn tại `integration-service`. Khi Leader gọi API này:
  1. Work xác thực Leader và scope, chuyển command chọn repository cùng operation_id, actor proof và expected_connection_generation tới API backend Integration. Route command Integration phải được công bố/triển khai trước nghiệm thu; GET verify không là thao tác đổi nguồn kết nối.
  2. Integration kiểm quyền provider, lưu connection nguồn theo operation_id và phát event generation/version; Work cập nhật projection từ kết quả/event. Retry cùng operation_id không tạo connection mới; generation cũ không ghi đè nguồn mới. REST ngoài Work transaction, không hứa atomic giữa hai DB.
  3. Operation chưa hoàn tất trả 202 envelope có operation_id/status=PENDING, không trả is_repo_verified=true. Hoàn tất trả 200 CONNECTED. GET cùng đường dẫn repository đọc trạng thái/projection; reconcile từ Integration khi thiếu event. Work không tự ghi repository chính khác Integration.
* **Phân quyền DRF:** `IsProjectLeader` ONLY.
* **Request Body:**
  ```json
  {
    "github_repo_id": "83749210",
    "operation_id": "operation_uuid_01",
    "expected_connection_generation": 0
  }
  ```
* **Success Response (`HTTP 200 OK`):**
  ```json
  {
    "success": true,
    "message": "Chỉ định repository chính của đồ án thành công",
    "data": {
      "project_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
      "github_repo_id": "83749210",
      "github_repo_name": "utask-team/utask-platform",
      "connection_status": "CONNECTED",
      "connection_generation": 1,
      "operation_id": "operation_uuid_01",
      "is_repo_verified": true,
      "updated_at": "2026-09-28T10:35:00Z"
    },
    "meta": null,
    "error": null
  }
  ```

---

### 8.2. Khai báo Tài khoản GitHub Thành viên (Chống Mạo danh Danh tính)

ProjectMember giữ github_source_version cho contract ordered account đã được Integration thống nhất. Source hiện chưa có implementation chứng minh sequence này; nếu upstream chưa cấp version phải reconcile source, không fake số tăng tại Work hay last-received-wins cho verify/unlink.

Mapping đã xác minh dùng github_user_id ổn định và unique theo project; username normalize không phân biệt hoa/thường. Leader chỉ yêu cầu user xác nhận, không sửa username/bật verified thay user. Event account key=user_id khác key project của activity, có source version để stale verify không ghi đè unlink mới.

* **Phương thức & Đường dẫn:** `PATCH /projects/{project_id}/members/{user_id}/github/`
* **Mô tả & Căn cứ:** Thành viên khai báo username GitHub dùng để đối soát đóng góp cá nhân (Mục 7.4, BFD 6.2).
* **Quy tắc Kiểm soát Danh tính (Identity Boundary - PRD Mục 7.4):**
  1. Khi thành viên cập nhật `github_username`, hệ thống **mặc định gán `is_github_verified = false`**. Tuyệt đối **không tự động coi username là hợp lệ** dựa trên chuỗi nhập liệu từ client nhằm triệt tiêu lỗ hổng mạo danh commit/PR của thành viên khác.
  2. **Ràng buộc Duy nhất:** Mỗi tài khoản GitHub chỉ được ánh xạ tối đa cho 1 thành viên đang hoạt động trong cùng dự án (`uq_project_member_github_username`). Nếu trùng lặp, trả về `409 Conflict` (`DUPLICATE_GITHUB_USERNAME_IN_PROJECT`).
* **Phân quyền DRF:** Chỉ bản thân thành viên ACTIVE (`request.user.id = user_id`); Leader dùng endpoint nhắc xác minh 8.2.1.
* **Request Body:**
  ```json
  {
    "github_username": "thanhvien_dev"
  }
  ```
* **Success Response (`HTTP 200 OK`):**
  ```json
  {
    "success": true,
    "message": "Đã ghi nhận tài khoản GitHub do bạn khai báo.",
    "data": {
      "user_id": "usr_student_02",
      "project_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
      "github_username": "thanhvien_dev",
      "github_user_id": null,
      "is_github_verified": false,
      "updated_at": "2026-09-28T10:38:00Z"
    },
    "meta": null,
    "error": null
  }
  ```

---

### 8.2.1. Yêu cầu Thành viên Xác nhận Tài khoản GitHub (Leader Notification - PRD Mục 7.4)
* **Phương thức & Đường dẫn:** `POST /projects/{project_id}/members/{user_id}/github/request-verification/`
* **Mô tả & Căn cứ:** Leader gửi thông báo nhắc nhở thành viên xác thực lại tài khoản GitHub của mình qua OAuth (PRD Mục 7.4 dòng 577).
* **Quy tắc Nghiệp vụ Bắt buộc (Strict Anti-Spoofing):**
  - **Leader tuyệt đối KHÔNG ĐƯỢC PHÉP tự ý duyệt hoặc đặt `is_github_verified = true` thay cho thành viên** (triệt tiêu nguy cơ Leader tự gán commit/PR của người khác).
  - Cờ `is_github_verified = true` **CHỈ được bật tự động** khi `work-service` nhận được sự kiện Kafka `github.account.verified` phát ra từ `integration-service` sau khi sinh viên hoàn tất luồng OAuth 2.0 có chữ ký chứng thực.
  - **Nguồn bằng chứng đã thống nhất:** Integration đổi OAuth code/gọi GitHub /user qua backend adapter Identity→Integration; Identity kiểm binding rồi ghi link/phát `identity.oauth.github_linked`; Integration nhận, cập nhật mapping và phát `github.account.verified` với `user_id,github_user_id,github_username`. Work không trực tiếp bật verified từ event Identity hoặc username client.
  - Work chỉ cập nhật membership ACTIVE của cùng user_id và mapping GitHub phù hợp (ID đã có hoặc username đang chờ trùng username đã xác minh, không phân biệt hoa/thường); dùng consumed_events để deduplicate event_id.
  - Unlink: `identity.oauth.github_unlinked` → Integration → `github.account.unverified`; Work clear verified chỉ cho cùng GitHub ID, giữ link/commit lịch sử. Account events key=user_id, xử lý theo thứ tự của user; replay lịch sử phải đối soát mapping hiện hành trước khi bật lại xác minh.
* **Phân quyền DRF:** `IsProjectLeader` ONLY.
* **Request Body:** Không yêu cầu body.
* **Success Response (`HTTP 200 OK`):**
  ```json
  {
    "success": true,
    "message": "Đã ghi nhận yêu cầu nhắc thành viên xác minh tài khoản GitHub.",
    "data": {
      "user_id": "usr_student_02",
      "project_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
      "requested_by_user_id": "usr_student_01",
      "requested_at": "2026-09-28T10:40:00Z"
    },
    "meta": null,
    "error": null
  }
  ```

---

### 8.3. Sinh viên Liên kết Thủ công Commit/PR vào Task (Không Tin cậy Client Metadata)

Canonical PR ref lưu number dạng chuỗi không dấu #, UI thêm # khi hiển thị; input #24 được server normalize thành 24 trước unique/upsert. github_status nullable theo loại, không ép COMMIT/BRANCH có OPEN/MERGED/CLOSED. CONFIRMED có confirmer/time và is_verified=true, provider verified không tự thành human CONFIRMED.

Link gồm repo_id/connection_generation đã được Integration xác minh, link_type và ref. Unique `(task_id,github_repo_id,link_type,github_ref_id)`; linked record trạng thái CONFIRMED, có confirmer/time. Metadata hiện hành có source version; xác nhận cần kiểm lại generation để không link repo vừa bị ngắt. Client chỉ gửi ref/loại, server derive repo và metadata.

* **Phương thức & Đường dẫn:** `POST /tasks/{task_id}/github-links/`
* **Mô tả & Căn cứ:** Thành viên chủ động dán commit SHA hoặc số PR từ repository chính của đồ án vào task (US-5.2, BFD 6.3, UC18.4).
* **Quy tắc Kiểm soát Toàn vẹn Dữ liệu:**
  1. Client **tuyệt đối không được gửi các trường `github_title`, `github_status`, `github_author`**. Client chỉ được phép gửi `link_type` và `github_ref_id`.
  2. `work-service` kiểm tra xem đồ án có liên kết `github_repo_id` hợp lệ hay chưa, sau đó xác thực thông tin tham chiếu thông qua cache đồng bộ hoặc gọi nội bộ sang `integration-service` để lưu trữ dữ liệu chính xác từ GitHub.
  3. **Quy tắc An toàn US-5.2:** Liên kết commit/PR **tuyệt đối không tự động đổi trạng thái task sang COMPLETED**.
* **Phân quyền DRF:** `IsProjectMember`.
* **Request Body:**
  ```json
  {
    "link_type": "PULL_REQUEST",
    "github_ref_id": "#24"
  }
  ```
* **Success Response (`HTTP 201 Created`):**
  ```json
  {
    "success": true,
    "message": "Liên kết hoạt động GitHub vào công việc thành công",
    "data": {
      "id": "git_link_uuid_01",
      "task_id": "task_uuid_14",
      "link_type": "PULL_REQUEST",
      "github_ref_id": "#24",
      "github_title": "feat(auth): integrate JWT authentication middleware",
      "github_status": "OPEN",
      "github_url": "https://github.com/utask-team/utask-platform/pull/24",
      "github_repo_id": "83749210",
      "connection_generation": 1,
      "source_version": 8,
      "confirmation_status": "CONFIRMED",
      "confirmed_by_user_id": "usr_student_02",
      "is_verified": true,
      "created_by_user_id": "usr_student_02",
      "synced_at": "2026-09-28T10:30:00Z"
    },
    "meta": null,
    "error": null
  }
  ```

---

### 8.4. Hủy Liên kết Hoạt động GitHub Gán nhầm
* **Phương thức & Đường dẫn:** `DELETE /tasks/{task_id}/github-links/{link_id}/`
* **Mô tả & Căn cứ Nghiệp vụ:** Thành viên hoặc Leader hủy liên kết commit/PR bị gán nhầm vào task. **Quy tắc US-5.2: Việc hủy liên kết chỉ xóa bản ghi trong CSDL UTask, không xóa commit/branch/PR trên GitHub; hệ thống tự động ghi nhật ký biến động Activity** (US-5.2).
* **Phân quyền DRF:** `IsProjectMember`.
* **Success Response (`HTTP 200 OK`):**
  ```json
  {
    "success": true,
    "message": "Đã hủy liên kết hoạt động GitHub khỏi công việc thành công",
    "data": {
      "deleted_link_id": "git_link_uuid_01",
      "task_id": "task_uuid_14"
    },
    "meta": null,
    "error": null
  }
  ```

---

### 8.5. Consumer GitHub: cập nhật link và tạo gợi ý chờ xác nhận
Topic mục tiêu `utask.integration.events`, group `work-service.github-activity-consumer`, activity key project_id. Event `github.activity.normalized` là contract mục tiêu cần producer/consumer thống nhất; account verified/unverified key user_id theo handoff Identity→Integration đã mô tả tại 8.2.1.

Envelope dùng event_id/type/version/aggregate_id/occurred_at/trace_id/producer/data. data bắt buộc có project_id, github_repo_id, connection_generation, source_version, link_type/ref, metadata chuẩn hóa và raw_message. Không fallback root payload hoặc chọn project mơ hồ từ repo_id. producer là integration-service; schema/version không hợp lệ không được apply.

1. Validate envelope/producer, scope và schema. Trong transaction claim unique consumed_events; duplicate hash giống bỏ effect, khác hash lưu lỗi hợp đồng.
2. Kiểm project hiện hành, repo/generation trùng projection và connection chưa bị ngắt; source_version cũ không ghi đè metadata mới.
3. Regex dùng project.identifier thực; resolve task bằng project_id+sequence_id. Không join counter như bảng mapping mỗi task.
4. Link CONFIRMED hiện có: cập nhật metadata/status nguồn. Mã task mới chỉ tạo/update candidate PENDING, không tự thành liên kết chính thức. Activity chỉ ghi khi dữ liệu đổi thật.
5. Effect, Activity/Outbox khi cần và consumed receipt commit cùng transaction; offset sau DB commit. PR MERGED không tự chuyển Task COMPLETED.
6. Lỗi transient retry; lỗi schema hoặc retry vượt chính sách đưa DLQ bền có ACK trước commit offset, có đường replay/reconcile và audit. Partition key không bảo đảm mọi race đã biến mất.

**Xác nhận candidate:** `POST /tasks/{task_id}/github-links/{link_id}/confirm/`, IsProjectMember ACTIVE và Idempotency-Key. Khóa link, kiểm lại scope/repo generation; chuyển PENDING→CONFIRMED, ghi confirmed_by/confirmed_at, Activity/Outbox/receipt cùng transaction. API list có confirmation_status để UI phân biệt gợi ý và bằng chứng đã xác nhận; Teacher chỉ xem. Hủy link chỉ tombstone UTask, không xóa GitHub ref.

---

### 8.6. Quản lý Bình luận Task & Phản hồi Feedback của Giảng viên (US-4.1, US-4.5)

**Một subject:** POST body chỉ task_id (Task comment) HOẶC project_id (Project feedback), không cả hai. DB Comment có CHECK XOR; scope Task comment suy bằng task.project, không lưu project_id copy. Response có thể trả project_id đã suy ra để UI điều hướng, field này read-only. Queryset/permissions phải lọc subject Project hoặc task.project trước resolve comment.

**Mention và audit:** Body có mentioned_user_ids được kiểm member ACTIVE hoặc Teacher đúng lớp theo policy, không suy quyền từ display name/HTML. Author và is_teacher_feedback do server derive. Comment/edit/tombstone, mention recipients, Activity và Outbox cùng transaction; Notification dedup event_id+recipient. Project feedback ghi Activity subject comment_id; Task timeline có thể join Comment, không ghi thêm audit trùng; mọi sửa/xóa cần quyền truy cập hiện hành, không chỉ author_id. Không thay state/deadline/assignment qua feedback.


* **`GET /tasks/{task_id}/comments/` (Lấy danh sách trao đổi trong Task):**
  * **Phân quyền:** `IsProjectMember` hoặc `IsClassTeacher`.
  * **Success Response (`HTTP 200 OK`):**
    ```json
    {
      "success": true,
      "message": "Lấy danh sách trao đổi thành công",
      "data": [
        {
          "id": "cmt_uuid_01",
          "user_id": "usr_teacher_01",
          "display_name": "TS. Giảng Viên Hướng Dẫn",
          "avatar_url": "https://r2.utask.edu.vn/avatars/teacher_01.png",
          "content_html": "<p>Nhóm cần bổ sung thêm bài test kiểm tra race condition cho Advisory Lock</p>",
          "is_teacher_feedback": true,
          "created_at": "2026-09-28T10:45:00Z"
        }
      ],
      "meta": {
        "pagination": {
          "total_count": 1,
          "page_size": 50,
          "next_cursor": null,
          "prev_cursor": null,
          "has_next": false
        }
      },
      "error": null
    }
    ```

* **`GET /projects/{project_id}/comments/` (Lấy feedback cấp Project Dashboard của Giảng viên):**
  * **Phân quyền:** `IsProjectMember` hoặc `IsClassTeacher`.
  * **Success Response (`HTTP 200 OK`):**
    ```json
    {
      "success": true,
      "message": "Lấy danh sách phản hồi cấp đồ án thành công",
      "data": [
        {
          "id": "cmt_uuid_proj_01",
          "user_id": "usr_teacher_01",
          "display_name": "TS. Giảng Viên Hướng Dẫn",
          "avatar_url": "https://r2.utask.edu.vn/avatars/teacher_01.png",
          "content_html": "<p>Nhóm cần đẩy nhanh tiến độ hoàn thành Sprint 1 trước tuần 7.</p>",
          "is_teacher_feedback": true,
          "created_at": "2026-09-28T08:00:00Z"
        }
      ],
      "meta": {
        "pagination": {
          "total_count": 1,
          "page_size": 50,
          "next_cursor": null,
          "prev_cursor": null,
          "has_next": false
        }
      },
      "error": null
    }
    ```

* **`POST /comments/` (Gửi bình luận trong Task hoặc Feedback cấp Project):**
  * **Phân quyền:** `IsProjectMember` hoặc `IsClassTeacher`.
  * **Request Body:**
    ```json
    {
      "task_id": "task_uuid_14",
      "content_html": "<p>Nhóm cần bổ sung thêm bài test kiểm tra race condition cho Advisory Lock</p>"
    }
    ```
  * **Xử lý An toàn US-4.5:** Nếu người gửi là Giảng viên (`IsClassTeacher`), hệ thống tự động gán `is_teacher_feedback = true`. **Phản hồi của Giảng viên tuyệt đối không làm thay đổi trạng thái, deadline hay phân công của task.**
  * **Success Response (`HTTP 201 Created`):**
    ```json
    {
      "success": true,
      "message": "Gửi bình luận trao đổi thành công",
      "data": {
        "id": "cmt_uuid_02",
        "project_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
        "task_id": "task_uuid_14",
        "user_id": "usr_teacher_01",
        "content_html": "<p>Nhóm cần bổ sung thêm bài test kiểm tra race condition cho Advisory Lock</p>",
        "is_teacher_feedback": true,
        "created_at": "2026-09-28T10:45:00Z"
      },
      "meta": null,
      "error": null
    }
    ```

* **`PATCH /comments/{comment_id}/` (Chỉnh sửa nội dung bình luận):**
  * **Phân quyền:** Chỉ tác giả bình luận (`user_id = request.user.id`).
  * **Request Body:** `{"content_html": "<p>Nội dung cập nhật...</p>"}`
  * **Success Response (`HTTP 200 OK`):**
    ```json
    {
      "success": true,
      "message": "Cập nhật bình luận thành công",
      "data": {
        "id": "cmt_uuid_02",
        "content_html": "<p>Nội dung cập nhật...</p>",
        "updated_at": "2026-09-28T10:50:00Z"
      },
      "meta": null,
      "error": null
    }
    ```

* **`DELETE /comments/{comment_id}/` (Xóa mềm bình luận):**
  * **Phân quyền:** Tác giả bình luận HOẶC `IsProjectLeader`.
  * **Căn cứ US-4.1:** **Xóa phải giữ dấu vết phù hợp** (`deleted_at = now()`).
  * **Success Response (`HTTP 200 OK`):**
    ```json
    {
      "success": true,
      "message": "Bình luận đã được xóa mềm thành công",
      "data": {
        "id": "cmt_uuid_02",
        "deleted_at": "2026-09-28T10:55:00Z"
      },
      "meta": null,
      "error": null
    }
    ```

---

### 8.7. Attachment: một bản ghi PENDING → CONFIRMED/EXPIRED
**Quyết định Work:** baseline mục 12 có Task attachment và Project attachment. Dùng chung bảng attachments/Attachment với đúng một subject FK (task_id hoặc project_id), không tạo hai bảng file hoặc lưu copied project_id cho tệp Task. Server lấy subject từ route; client không được đổi owner bằng body. Member ACTIVE có quyền upload trong Project ghi được; Teacher đúng lớp chỉ list/download. Activity dùng subject Task hoặc Project tương ứng.

| Thao tác | Tệp Task | Tệp Project |
| --- | --- | --- |
| Cấp upload | POST /tasks/{task_id}/attachments/presigned-url/ | POST /projects/{project_id}/attachments/presigned-url/ |
| Confirm / list | POST hoặc GET /tasks/{task_id}/attachments/ | POST hoặc GET /projects/{project_id}/attachments/ |
| Download | GET /tasks/{task_id}/attachments/{attachment_id}/download/ | GET /projects/{project_id}/attachments/{attachment_id}/download/ |
| Xóa | DELETE /tasks/{task_id}/attachments/{attachment_id}/ | DELETE /projects/{project_id}/attachments/{attachment_id}/ |

1. POST presigned-url ở đúng route scope. Body file_name/file_size/content_type, tối đa 25 MiB; allowlist image/jpeg, image/png, image/webp, application/pdf, application/zip, text/plain, application/json. Server tạo **Attachment PENDING**: id=attachment_id, đúng một task_id/project_id, uploaded_by_user_id, key UNIQUE do server cấp, file_name/size/type, expires_at và created_at. Trả attachment_id, presigned PUT, expires_in=900; không có upload receipt/table/FK riêng, chưa public URL.
2. Client PUT R2 hoặc local adapter. Key/task/owner/metadata không sửa sau cấp. PENDING không xuất hiện trong danh sách/count/download của attachment đã hoàn tất.
3. POST confirm ở đúng route scope, body attachment_id, Idempotency-Key bắt buộc. Kiểm đúng subject/uploader/quyền/expiry; HEAD/content validation ngoài transaction kiểm size/type thực khớp metadata đã cấp. MIME metadata không tự chứng minh bytes hợp lệ. Khóa chính hàng Attachment, kiểm lại scope/expiry/status rồi UPDATE PENDING→CONFIRMED và confirmed_at, Activity/Outbox/response idempotency receipt trong cùng transaction; không INSERT hàng thứ hai. CONFIRMED retry trả cùng ID sau kiểm quyền, EXPIRED bị từ chối. Task route không đọc/confirm tệp Project và ngược lại, dù chung project.
4. GET attachments trả metadata **CONFIRMED chưa deleted** theo scope; count/subquery cũng dùng filter này. Signed download qua endpoint download sau kiểm quyền; chỉ CONFIRMED, không dùng URL public hoặc stored URL hết hạn làm quyền.
5. DELETE attachment: uploader còn scope hoặc Leader, tombstone/Activity/Outbox transaction; job xóa object sau commit có retry. Cleanup PENDING quá hạn chuyển EXPIRED và xử lý orphan object; không rollback DB chỉ vì R2 lỗi. Không thể confirm chỉ bằng storage_key prefix.

IdempotencyRecord ở 1.5 vẫn cần để bảo vệ mutation/replay; đây là receipt **request**, không phải một bảng receipt upload khác. Các response dùng envelope năm trường; không log signed URL/secret.

### 8.8. Xem Nhật ký Lịch sử Biến động Task (Audit Trail)

Đọc bảng activities với task_id subject hoặc comment_id của task khi cần; scope suy qua FK, không copy project_id vào audit task. Activity có đúng một subject FK, entity_type/entity_id response suy từ FK. Xem invariant ERD.
* **Phương thức & Đường dẫn:** `GET /tasks/{task_id}/activities/`
* **Mô tả & Căn cứ:** Xem toàn bộ dòng thời gian thay đổi trạng thái, phân công, deadline (US-4.1, BFD 7.4).
* **Phân quyền DRF:** `IsProjectMember` hoặc `IsClassTeacher`.
* **Success Response (`HTTP 200 OK`):**
  ```json
  {
    "success": true,
    "message": "Lấy nhật ký lịch sử công việc thành công",
    "data": [
      {
        "id": "act_uuid_01",
        "actor_user_id": "usr_student_01",
        "verb": "updated",
        "field": "state",
        "old_value": "In Progress",
        "new_value": "Done",
        "created_at": "2026-09-28T10:00:00Z"
      },
      {
        "id": "act_uuid_02",
        "actor_user_id": "usr_student_01",
        "verb": "created",
        "field": null,
        "old_value": null,
        "new_value": null,
        "created_at": "2026-09-28T09:30:00Z"
      }
    ],
    "meta": {
      "pagination": {
        "total_count": 2,
        "page_size": 20,
        "next_cursor": null,
        "prev_cursor": null,
        "has_next": false
      }
    },
    "error": null
  }
  ```

---

## 9. Quy tắc cài đặt Django/DRF (thiết kế mục tiêu)
Các đoạn middleware/renderer/paginator cũ không phải mã triển khai và đã được thay bằng yêu cầu dưới đây để tránh sao chép một mẫu không bảo đảm transaction.

### 9.1. Auth, response và hợp đồng
Dùng thư viện JWT theo Identity README; views/serializers/URLconf thật, drf-spectacular annotations. Kế thừa envelope/error conventions từ common Identity, không copy user/session DB của Identity. Ngoại lệ protocol health/JWKS/OpenAPI phải ghi rõ, không double-wrap. Work pagination khác page-number Identity, không gọi meta là đồng nhất toàn hệ thống.

URL nghiệp vụ Work trong service không gắn phiên bản, ví dụ `/projects/` và `/tasks/`; Nginx bỏ prefix `/api/work/` nên gateway công khai các đường tương ứng dưới `/api/work/...`. Work không công khai endpoint nội bộ qua gateway; các lệnh backend-to-backend vẫn phải qua adapter và xác thực service theo hợp đồng của service nhận.

Work giới hạn JSON ở tối đa 100 object/mảng lồng nhau cho cả body `application/json` và nội dung tệp JSON. Request vượt giới hạn trả `400 VALIDATION_ERROR`; tệp vượt giới hạn bị từ chối xác nhận với `422 VALIDATION_ERROR` và giữ nguyên trạng thái `PENDING`.

### 9.2. Exception mapping
Domain lỗi dùng một registry ở mục 2. Đọc SQLSTATE và `diag.constraint_name`, không match câu tiếng Việt hoặc exception text. Nếu chọn trigger cho membership/same-project/DAG, dùng ERRCODE `23514` và CONSTRAINT tên ổn định, hoặc mapper P0001 riêng được test; không giả định bare RAISE EXCEPTION luôn là IntegrityError. Bắt lỗi ngoài atomic/savepoint để transaction rollback đúng; không trả class name/schema/secret DB cho client.

### 9.3. Transaction, lock và idempotency
Command owner giữ transaction cho mutation + Activity + Outbox + durable response receipt như 1.5. Trong MVP các Work writer dùng project row write barrier chung (project IDs tăng dần), sau đó State IDs, Sprint IDs, Task IDs, membership/relation/receipt theo thứ tự thống nhất; Project.current_task_sequence cấp số trong cùng protocol, không thêm bảng counter. Các writer membership/state/scope/assignment/transition/close/delete/restore đều tham gia, không chỉ close khóa Sprint. Có lock timeout/bounded retry; benchmark trước khi bỏ barrier để tăng concurrency.

REST/LLM/R2 HEAD ngoài transaction; sau đó kiểm local version/generation/receipt dưới lock trước ghi. Không xem REST verify là transaction xuyên service. Redis lock không nguồn correctness. Durable receipt replay luôn kiểm DB và quyền hiện hành.

### 9.4. Queries và pagination
Queryset khóa scope trước resolve ID/filter/expand. List cursor created_at/id dùng ordering đã kiểm; board có revision/rank cursor riêng ở 5.2.1. fields/expand allowlist, không nạp toàn quan hệ tùy client; counts không lấy deleted children/comment/attachment. select_related cho FK, prefetch cho many; subquery khi tránh join fan-out. Đo query count/EXPLAIN và workload thật trước số phần trăm cải thiện; không hứa index-only scan.

### 9.5. Contract và kiểm thử nghiệm thu
Chưa xuất schema giả vào contracts. Khi source có thật: Ruff lint/format, Django check/migration parity, PostgreSQL/Redis tests, OpenAPI/response contracts và Docker build. CI Work dùng workflow Python có sẵn, bật dependency/test env riêng đúng test; không đổi root env. Các ca bắt buộc: IDOR/quyền/revoked session, counter/batch concurrency, graph disjoint-edge cycle, replay sau Redis/crash, order/ACK/DLQ, board revision/rebalance, candidate-confirm repo switch, upload ownership/download, Sprint close cùng task writer và immutable closure facts. Provider/Kafka/gateway/staging E2E phải được kiểm riêng.

---

## 10. Phạm vi triển khai và các quyết định còn mở
Tài liệu mô tả Thiết kế mục tiêu; Work hiện có source và kiểm thử nội bộ như [hiện trạng backend](../work-service/work-backend.md). Các quyết định thiết kế bên dưới không tự chứng minh tích hợp liên service hoặc deployment đã được nghiệm thu.

- Slice đầu: auth/session-status + scope Project/Member/State + create/list/transition/block Task + Activity/Outbox/receipt; không chờ toàn bộ schema nâng cao.
- P0 hoàn chỉnh theo PRD còn cần Classroom project setup, collaboration/mention/notification, GitHub candidate-confirm, AI projection-draft-apply và Teacher dashboard với số liệu Work. Task/board riêng chưa là MVP đầy đủ.
- P1 Pilot mới thêm Sprint, scope change, closure/rollover, workload/risk và teacher feedback có cấu trúc.
- Đã chọn trong Work: MVP gắn Group, cho nhiều Project hoạt động đồng thời mỗi nhóm và stable membership slot; UTC cho timestamp, Asia/Ho_Chi_Minh cho ngày nghiệp vụ; top-level Work Item/estimate coverage theo 6.9; quyền Member cho nhãn/relation/subtask theo 4.5/5.8/5.9. Ràng buộc cũ một Project hoạt động/nhóm chưa được gỡ trong mã nguồn; xem [ghi chú liên kết Classroom–Work](../work-service/classroom-project-linking.md). Không coi quyết định nhiều dự án đồng thời là mục còn treo.
- Hierarchy dùng Task.parent_id cùng Project, SUBTASK cần parent và cấm cycle; MVP không đặt thêm giới hạn số cấp nghiệp vụ khi PRD chưa yêu cầu. Query/expand phải có giới hạn tài nguyên và kiểm cycle an toàn, không trả cây đệ quy không giới hạn trong một response.
- Hợp đồng liên nhóm cần thống nhất trước khi bật đường tích hợp tương ứng: Classroom scope/source version và ngoại lệ nhóm; Integration generation/source ordering; AI proposal/item/revision/proof và apply-result. Có thể triển khai command/query/constraint nội bộ Work trước; adapter mock chỉ phục vụ local tests, không thay nghiệm thu liên service.
- Project độc lập và admin support bypass ngoài phạm vi MVP đã chọn; không tự mở quyền để lấp contract thiếu. Các yêu cầu sản phẩm mới này không chặn slice Task/board hiện tại.
- Tham khảo Plane tại commit `7466675e471efe1c96b122615f7a0d30c9b2eb05`: scope/query, advisory sequence ledger, grouped offset và cycle snapshot; counter block, revision cursor, DAG same-project và lịch sử Sprint là điều chỉnh UTask. Không có benchmark xác nhận “100 lần/15ms/70%/80%”.

---


## 11. Đồng bộ schema theo ERD audit

[ERD v6](../diagram/work-service/erd.md) là nguồn column/nullability/FK/constraint mục tiêu và mô tả schema thiết kế của Work. Biên bản audit lịch sử ngày 08/10/2026 không có trong checkout hiện tại. Không có AIDB/Risk table trong Work. Đây là schema mục tiêu đã chọn cho phạm vi hiện tại; thay đổi yêu cầu mới dùng quyết định/version mới.

Ví dụ JSON có các chuỗi alias như task_uuid_01/usr_student_01 để đọc dễ; chúng không là UUID literal gọi API được. Wire schema UUID phải theo từ điển/Identity source và được xuất từ serializer thật khi có code; JSON parse pass không chứng minh validation schema. Mọi request/error phải qua response envelope, mọi source-specific proof/version cần contract với owner trước tích hợp.


## 12. Chi tiết backend Người 1 đã khép ngày 09/10/2026

[Backend Task/Collaboration](../work-service/task-collaboration-backend.md) ghi
phạm vi code/test hiện tại và giới hạn tích hợp. Tài liệu mục tiêu bên trên không
đồng nghĩa toàn bộ service/provider đã chạy.

- PATCH/lifecycle/transition/block và action gán nhãn Task cần expected_version.
  Create Task/Subtask, AI apply và confirm attachment bắt buộc Idempotency-Key.
  Create/patch Leader nhận acceptance_criteria; Member chỉ sửa description_html.
- List Task nhận thêm parent_id và status active/archived/deleted/all; all gồm
  active + archived, không gồm deleted. Detail expand quan hệ nặng giới hạn 100
  item mỗi loại; list chỉ expand state/epic/labels/assignees. Trường nặng không
  chứa bytes/signed URL. Query sai allowlist bị từ chối.
- AI item phải có ai_revision bên cạnh local_id. Không nhận proof/source từ body.
  `GET /projects/{project_id}/ai-operations/{operation_id}/` đọc outcome đã
  commit, có Project scope hiện hành. Đây là Work lookup, không context REST cho AI.
- P1 Work có `POST /projects/{project_id}/ai-actions/apply/`, Leader-only,
  Idempotency-Key bắt buộc. Body proposal_id/item_id/ai_revision/context_version
  và actions; mỗi action có task_id/expected_version và một kind:
  SET_DEADLINE + due_date, SET_PRIORITY + priority, SET_ASSIGNEES + assignee_ids,
  hoặc SPRINT_SCOPE + sprint_id/scope_action/reason/expected_sprint_version.
  Không nhận arbitrary JSON patch. Nhiều Task đổi cùng transaction; cùng
  proposal-item/hash qua actor/key khác trả operation cũ, khác hash trả 422.
- Verifier AI/Classroom là interface nội bộ Work; scope Sprint gọi command Work thật, không
  hợp đồng đã công bố của các service khác. Runtime thiếu dependency từ chối 503
  và không có success receipt/event. Retention AI operation không theo TTL HTTP.
- Mã lỗi bổ sung: 409 EPIC_NAME_EXISTS/LABEL_NAME_EXISTS/AI_OPERATION_CONFLICT;
  422 AI_ITEM_PAYLOAD_CONFLICT/AI_PROVENANCE_INVALID;
  503 AI_DEPENDENCY_UNAVAILABLE/SPRINT_COMMAND_UNAVAILABLE/CLASSROOM_UNAVAILABLE/
  STORAGE_UNAVAILABLE/INTEGRATION_COMMAND_UNAVAILABLE; 404 UPLOAD_NOT_FOUND.
  HTTP/error envelope và schema typed cụ thể lấy từ OpenAPI đã sinh và testcase
  producer/response tương ứng, không tạo schema service khác để lấp contracts.
