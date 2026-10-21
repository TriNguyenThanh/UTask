# Hướng dẫn Work Service cung cấp context cho AI

**Trạng thái: Đã triển khai provider Work; đã kiểm quyền/context với service thật
trên staging local. Nghiệm thu đầy đủ mọi intent AI: Một phần.**
Ba API và đủ 10 cặp context đã kiểm với Identity/Classroom thật. Một ca Task
đi hết queue/worker/LLM khi runtime AI tạm development để dùng endpoint HTTP;
ba ca khác timeout. Đã khôi phục staging. Xem [báo cáo runtime](ai-context-staging-validation-20261022.md)
để phân biệt cấu hình smoke và giới hạn, không suy ra mọi intent đã nghiệm thu.
Xem [kết quả và cách chạy lại](ai-context-implementation-plan.md#10-kết-quả-triển-khai-và-giới-hạn-kiểm-chứng).

Nguồn chuẩn cho path, schema và mã lỗi là
[Work AI context v1](../../contracts/api/work-ai-context-v1.yaml), được
[contract Work](../../contracts/api/work-service.yaml) tham chiếu. Khi có khác
biệt, sửa đồng bộ contract, consumer, provider và test; không tự thêm trường
vào response. Xem thêm [ADR-005](../adr/005-integration-work-ai-contracts.md)
và [điều kiện phát hành AI](../ai-service/production-readiness.md).

Checklist triển khai, vị trí sửa và cách kiểm thử nằm trong
[kế hoạch context Work–AI](ai-context-implementation-plan.md). Kế hoạch này ghi
quyết định nghiệp vụ mới; các checkbox chưa hoàn tất không phải bằng chứng API đã có.

## 1. Phạm vi và thứ tự thực hiện

Đội Work sở hữu endpoint, xác thực actor, quyền trên target, truy vấn và tính
chỉ số. AI chỉ đọc context để tạo proposal; không được ghi Task/Project hoặc
đọc trực tiếp Work DB. Chỉ Integration được gọi GitHub API.

Thực hiện theo thứ tự:

1. Giữ xác thực Bearer và service key bắt buộc theo provider Work đã triển khai.
2. Triển khai POST authorize `ai.analyze`, gồm ma trận intent/target.
3. Triển khai GET context, serializer allowlist, giới hạn kích thước và phiên bản.
4. Triển khai POST authorize `github.read` dành riêng cho Integration.
5. Chạy provider contract test và phối hợp smoke thật với AI/Integration.

Ba API này không thay thế luồng connect/disconnect repository, receipt,
dispatcher hoặc consumer sự kiện. Nếu cần GitHub connected thật, triển khai
các điều kiện riêng trong
[hướng dẫn Work–Integration](../integration-service/work-service-integration-guide.md).
Không đưa proposal apply, Kafka projection mới hoặc specialist agent vào phạm vi này.

## 2. Xác thực và quyền dùng chung

Provider Work hiện yêu cầu cả Bearer và service key. AI trên `dev` có tùy chọn
`AI_WORK_SERVICE_AUTH_ENABLED`, mặc định `false`; khi nối provider này phải đặt
`true` để AI gửi key. Cờ phía AI không tắt kiểm key trong Work và không cấp
quyền cho actor. Integration→Work cũng cần cả hai header.

```http
Authorization: Bearer <JWT hiện hành của actor>
X-Service-Key: <key của đúng caller>
```

Service key xác định service gọi; Bearer xác định người dùng. Cả hai luôn bắt buộc
đối với provider Work hiện tại. Không nhận `actor_id` từ body và không dùng JWT
của service thay cho actor. Kiểm tra session bị thu hồi theo cơ chế Work hiện hành; lỗi
nguồn xác minh quyền không được biến thành cho phép.

Tái dùng quyền đọc Project: membership phải `ACTIVE`, hoặc quyền teacher
được Work xác minh qua Classroom. Không áp điều kiện Leader/quyền ghi cho
thao tác chỉ đọc AI. Với Task/Sprint, Work phải resolve Project và kiểm target
thuộc đúng scope trước khi trả dữ liệu. Target không tồn tại hoặc actor không
được đọc trả `404`, không tiết lộ tài nguyên. Không tin quyền đã kiểm ở lần gọi trước.

Tham chiếu source có thể tái dùng:

- [JWT/session authentication](../../apps/work-service/common/authentication.py),
  [Identity adapter](../../apps/work-service/infrastructure/identity.py).
- [read_project_scope, visible_project và readable_project](../../apps/work-service/apps/projects/queries/projects.py).
- [read_context_snapshot](../../apps/work-service/apps/projects/queries/context.py)
  và [test snapshot](../../apps/work-service/tests/integration/test_context_snapshot.py).

Snapshot hiện có là query nội bộ với chunks/checksum, không phải REST API AI.
Chỉ tái dùng logic scope/lọc dữ liệu phù hợp; không trả nguyên snapshot,
snapshot ID, chunks hoặc checksum thay cho `ContextDocument`. Endpoint mới
không ghi snapshot, outbox hay dữ liệu nghiệp vụ.

Luồng hiện tại: query chụp dữ liệu thuần và version dưới barrier Project;
view gọi `ContextDocumentSerializer` để lọc nội dung, giới hạn danh sách/byte
và tạo response. Serializer không đọc DB. Authorize Integration dùng
`readable_project` chung, không phụ thuộc module context AI. Schema context
được khai báo trực tiếp bằng extension `drf-spectacular`, không tạo proxy rồi
ghi đè schema; chi tiết và kiểm chứng ở kế hoạch triển khai.

## 3. API cần triển khai

### 3.1. AI kiểm quyền target

`POST /api/v1/internal/ai/targets/{target_type}/{target_id}/authorize`

Chỉ caller `ai`. `target_type` viết thường; ID là UUID. Ví dụ body cho Project:

```json
{"action":"ai.analyze","intent":"risk_analysis"}
```

| Intent | Target được chấp nhận |
| --- | --- |
| `backlog_generation` | `project` |
| `task_decomposition` | `task` |
| `risk_analysis` | `project`, `sprint` |

Response `200` dùng envelope Work, có `Cache-Control: no-store`:

```json
{
  "success": true,
  "data": {
    "target_type": "project",
    "target_id": "11111111-1111-4111-8111-111111111111",
    "action": "ai.analyze",
    "allowed": true
  }
}
```

Chỉ `allowed: true` rõ ràng mới cấp quyền. Body sai action, intent hoặc cặp
intent/target không hợp lệ phải bị từ chối; không tự đổi target. Dữ liệu trong
`data` phải khớp request và schema, không trả object Project đầy đủ.

### 3.2. AI đọc context

`GET /api/v1/internal/ai/targets/{target_type}/{target_id}/contexts/{domain}`

Chỉ caller `ai`; không nhận body hoặc query parameter. Kiểm quyền lại ở mỗi
lần đọc, kể cả khi POST authorize vừa thành công.

| Target | Domain hỗ trợ |
| --- | --- |
| `project` | `project`, `team`, `progress` |
| `task` | `task`, `project`, `team`, `progress` |
| `sprint` | `project`, `team`, `progress` |

Work tự ánh xạ Task/Sprint sang Project. Không nhận `project_id` khác do AI
chọn để mở rộng scope. Domain `task` không được dùng với Project/Sprint.

Trả JSON `ContextDocument` trực tiếp, **không bọc `success/data` của Work**;
header `Cache-Control: no-store`. Ví dụ progress của Project không có task:

```json
{
  "domain": "progress",
  "as_of": "2026-10-21T03:00:00Z",
  "status": "available",
  "source_version": "42",
  "data": {
    "metrics": [],
    "blocked_tasks": [],
    "completed_tasks": 0,
    "total_tasks": 0,
    "as_of": "2026-10-21T03:00:00Z"
  },
  "warning": null
}
```

Timestamp trong ví dụ chỉ minh họa, không dùng cố định trong fixture smoke
thật. `as_of` phải phản ánh thời điểm dữ liệu, dạng RFC 3339 có múi giờ.

### 3.3. Integration kiểm quyền đọc GitHub

`POST /api/v1/internal/integration/projects/{project_id}/authorize`

Chỉ caller `integration`, Bearer actor và key Integration→Work; phải từ chối
key của AI dù cùng actor. Body cố định:

```json
{"action":"github.read"}
```

Response `200` dùng envelope Work:

```json
{
  "success": true,
  "data": {
    "project_id": "11111111-1111-4111-8111-111111111111",
    "action": "github.read",
    "allowed": true
  }
}
```

Đây là quyền đọc Project hiện hành, không phải xác nhận repository đã connect
hoặc user đã consent GitHub. Integration tự kiểm tra mapping/consent rồi mới
trả GitHub context. AI không gọi trực tiếp endpoint này và không tự kiểm quyền
GitHub bằng Work key; AI vẫn kiểm `ai.analyze` và lấy progress từ Work.

Lưu ý consumer Integration hiện phân biệt: `200` với `allowed: false` thành
access denied; HTTP khác `200` thành Work unavailable. Không giả định Work
`404` sẽ được Integration ánh xạ thành `403`. Cả hai trường hợp đều phải
fail-closed, không trả context. Không đổi quy tắc che giấu target của Work
chỉ để làm smoke thành công.

## 4. Dữ liệu, phiên bản và giới hạn

### Shape theo domain

Tạo serializer riêng, chỉ xuất trường trong contract; không serialize model
hoặc profile nguyên khối. Mọi trường required phải có mặt, kể cả trường nullable.

| Domain | Dữ liệu cần ánh xạ |
| --- | --- |
| `project` | `id`, `name`, `description`, `goals` từ `target_goals`, `deadline` từ `end_date`, cùng `tasks` và `sprints` dạng summary. `goals` là chuỗi, không phải mảng. |
| `task` | `id`, `project_id`, `title`, `description` đã strip HTML, `status` dạng chuỗi, `priority` dạng chuỗi, `deadline` từ `due_date`, `estimate_points` từ `story_points`, `dependencies` là mảng UUID, `acceptance_criteria` là chuỗi. Không trả object state/dependency. |
| `team` | `members` chỉ có `user_id`, `capacity`, `workload`; thêm tổng `capacity`, `workload`. Không có display name, email, avatar hay GitHub identity. |
| `progress` | `metrics` gồm `name/value/unit/observed_at`, `blocked_tasks` dạng task summary, `completed_tasks`, `total_tasks`, `as_of`. Work tự tính, không gọi AI để sinh chỉ số. |

Task summary gồm `id/title/status`; chỉ thêm `priority/deadline/estimate_points`
theo schema. Sprint summary gồm `id/name/status/deadline`, status là
`DRAFT/ACTIVE/COMPLETED`. Deadline là ngày `YYYY-MM-DD` hoặc `null`;
estimate là số không âm hoặc `null`, không thay missing estimate bằng số 0
nếu quy tắc Work chưa quy định. Các trường text dài tối đa theo contract,
không đưa HTML hoặc secret trong nội dung vào response.

Quy tắc scope và chỉ số:

- Loại task deleted/archived và thành viên không `ACTIVE`; cô lập Project.
- Progress Project dùng toàn bộ task active thuộc Project, không chỉ 100 task
  được đưa vào summary. Khi target Task, resolve scope Project tương ứng.
- Progress Sprint dùng scope Sprint, không dùng toàn Project. Tái dùng
  [scope query](../../apps/work-service/apps/sprints/queries/scope.py): membership
  hiện hành cho Sprint `DRAFT/ACTIVE`; khi hỗ trợ đọc Sprint `COMPLETED` phải
  giữ quy tắc snapshot bất biến của Work, không tự dựng lại từ task hiện tại.
- Tái dùng công thức trong
  [work-metrics-v1](../../apps/work-service/apps/projects/metrics.py). Ghi rõ
  cách xử lý mẫu số 0, task bị chặn, thiếu estimate và chia workload nhiều assignee
  trong test/provider docs; không tạo công thức riêng cho AI.

Quy tắc triển khai `team` đã chốt: `capacity` lấy `weekly_capacity` theo giờ/tuần;
`workload` là điểm ước lượng còn lại của task cấp gốc, loại `COMPLETED/CANCELLED`,
phân bổ bằng `allocate_points` hiện có. Task thiếu estimate phải được báo qua
`partial/warning`, không được coi là đã biết đầy đủ khối lượng.
[Dashboard query](../../apps/work-service/apps/projects/queries/dashboard.py)
chưa loại task `COMPLETED/CANCELLED` khỏi phép phân bổ này; cần lọc đúng scope
cho context AI, không sửa ngầm ý nghĩa dashboard. Schema team chưa có trường unit;
ghi đơn vị qua `warning` và tài liệu, giữ nguyên shape consumer đang dùng.
Không lấy workload chia capacity hoặc gọi hai giá trị là cùng đơn vị.
Chi tiết scope, thiếu dữ liệu và các ca biên nằm trong mục team của
[kế hoạch triển khai](ai-context-implementation-plan.md). Quy tắc này **đã triển khai
và có provider tests**. Không thêm `unit` ngoài schema hoặc tự quy đổi
story points thành giờ.

### Source version và thời điểm

| Context | `source_version` |
| --- | --- |
| Project, team, progress theo Project | Chuỗi `Project.event_sequence`, ví dụ `"42"` |
| Task | Chuỗi `Task.version` |
| Progress theo Sprint đang mở | Chuỗi `sprint.version:project.event_sequence`, ví dụ `"3:42"` |
| Progress theo Sprint đã đóng | Phiên bản Sprint kèm `cut_project_sequence` của snapshot; không dùng Project sequence hiện tại cho payload lịch sử |

Project/team đọc qua target Task/Sprint vẫn dùng phiên bản Project. Đọc dữ
liệu và phiên bản nhất quán; không trả phiên bản mới với payload cũ.
Với Sprint đã đóng, thiết kế provider giữ `captured_at`, trả `stale` và warning
về dữ liệu lịch sử; không ghép summary task hiện tại vào totals snapshot.
AI hiện từ chối context `stale`; không coi đây là luồng phân tích dữ liệu hiện hành
đã hỗ trợ. Xem giới hạn snapshot và checklist trong kế hoạch triển khai.
`as_of` không thay thế `source_version`. AI mặc định từ chối context quá 300
giây hoặc timestamp tương lai quá 30 giây; đồng bộ đồng hồ môi trường.

### Kích thước và trạng thái

JSON UTF-8 sau serialize tối đa **65536 byte**, không phải 65536 ký tự.
Mỗi mảng tối đa 100 mục; chọn thứ tự ổn định. Khi giới hạn summary/dependency/
member hoặc rút gọn nội dung, phải báo `partial` và warning rõ ràng, không
âm thầm cắt rồi gắn `available`. Counts và metrics vẫn tính toàn bộ scope.
Nếu không tạo được document đúng schema trong giới hạn, trả lỗi `422`,
không trả JSON cắt ngang hoặc protocol phân trang/chunks mới.

`ContextDocument` luôn có `domain/as_of/status/source_version/data/warning`:

| Status | Quy tắc |
| --- | --- |
| `available` | Đủ context đúng shape; `warning` có thể `null`. Project rỗng vẫn có dữ liệu hợp lệ với mảng/count rỗng, không mặc định là missing. |
| `partial` | Dữ liệu đúng typed shape nhưng thiếu một phần; bắt buộc warning không rỗng, tối đa 500 ký tự. |
| `missing` | Context thực sự không có; không đủ thỏa required context của workflow. Không dùng để che permission denied hoặc lỗi nguồn. |
| `stale` | Dữ liệu cũ; AI trả `CONTEXT_STALE`, không coi là trạng thái hiện tại. |
| `unavailable` | Không lấy được context; AI coi là lỗi retryable, không thay bằng fixture. |

Required context của AI: backlog cần `project`, decomposition cần `task`, risk
cần `progress`; chỉ `available/partial` hợp lệ. Giới hạn 100 cũng áp dụng
`metrics`, `blocked_tasks`, `dependencies`, không chỉ task/sprint summary.

## 5. Mã lỗi và an toàn

| HTTP Work | Ý nghĩa / yêu cầu |
| --- | --- |
| `400` | Target/domain/body hoặc cặp intent/target không hợp lệ. |
| `401` | Actor/Bearer không hợp lệ hoặc session không còn hiệu lực. |
| `403` | Service key sai, thiếu hoặc không đúng caller. |
| `404` | Target không tồn tại hoặc actor không được đọc. |
| `422` | Context vượt giới hạn và không thể trả document hợp lệ. |
| `429`, `503` | Lỗi tạm thời; không được trả allowed=true hoặc dữ liệu giả. |

Lỗi dùng `WorkErrorEnvelope` hiện hành. AI ánh xạ `401/403/404` thành từ chối
truy cập không retry; timeout, `429` và `5xx` thành lỗi retryable. Payload sai
schema và `409` không được retry như lỗi tạm thời. Không redirect sang login
hoặc trả HTML. Không fallback fixture khi quyền thật bị từ chối.

Không log Bearer, service key, raw context hoặc nội dung task. Log metadata
đủ truy vết request/trace, caller/domain, status, duration, payload size;
giữ nội dung text là dữ liệu không đáng tin, không phải chỉ thị cho agent.
Provider phải lọc PII/secret, không dựa hoàn toàn vào bộ lọc prompt của AI.

## 6. Cấu hình phối hợp với AI và Integration

`WORK_SERVICE_KEYS` **đã được Work đọc trong settings**, map caller sang danh
sách key hiện tại/trước để xoay vòng. Default `{}` không cấp quyền cho AI.
Map chỉ nhận `ai/integration`, mỗi caller 1–2 key hợp lệ, không dùng chung key.
Caller Integration dùng map mới hoặc fallback `WORK_INTEGRATION_INBOUND_KEYS`
đang có; nếu cùng khai báo thì hai bộ key phải khớp, không lấy hợp danh sách.
JSON sai hoặc cấu hình xung đột đóng quyền. Receipt hiện hữu dùng cùng bộ key
Integration hiệu lực nhưng vẫn key-only; hai API authorize mới cần thêm Bearer.
Chỉ chấp nhận key thuộc caller đúng endpoint; so sánh an toàn, không log key.
Dùng secret ngẫu nhiên riêng từng chiều, inject qua secret store/Compose;
không commit giá trị thật. Key Integration cần tuân thủ giới hạn định dạng
của Integration (ít nhất 32 ký tự ASCII hợp lệ).

| Bên giữ key gửi | Phải khớp bên nhận |
| --- | --- |
| AI: `AI_WORK_SERVICE_KEY`, với `AI_WORK_SERVICE_AUTH_ENABLED=true` | Work: key caller `ai` trong `WORK_SERVICE_KEYS` |
| Integration: `INTEGRATION_WORK_SERVICE_KEY` | Work: một key trong `WORK_SERVICE_KEYS["integration"]` |
| AI: `AI_INTEGRATION_SERVICE_KEY` | Integration: một key trong `INTEGRATION_SERVICE_KEYS["ai"]` |

Key Work→Integration cho connect là chiều khác, xem guide Work–Integration;
không tái sử dụng key trên. `INTEGRATION_WORK_URL=http://work-service:8000`.
Các URL bên dưới dùng DNS nội bộ, không dùng prefix gateway `/api/work`.
Gateway phải tiếp tục chặn route internal.

Đội AI/infra cấu hình `AI_AUTHORIZATION_URLS` đủ ba target:

```json
{
  "project": "http://work-service:8000/api/v1/internal/ai/targets/{target_type}/{target_id}/authorize",
  "task": "http://work-service:8000/api/v1/internal/ai/targets/{target_type}/{target_id}/authorize",
  "sprint": "http://work-service:8000/api/v1/internal/ai/targets/{target_type}/{target_id}/authorize"
}
```

`AI_CONTEXT_URLS` cần đủ 10 cặp hỗ trợ:

```json
{
  "project:project": "http://work-service:8000/api/v1/internal/ai/targets/{target_type}/{target_id}/contexts/project",
  "project:team": "http://work-service:8000/api/v1/internal/ai/targets/{target_type}/{target_id}/contexts/team",
  "project:progress": "http://work-service:8000/api/v1/internal/ai/targets/{target_type}/{target_id}/contexts/progress",
  "task:task": "http://work-service:8000/api/v1/internal/ai/targets/{target_type}/{target_id}/contexts/task",
  "task:project": "http://work-service:8000/api/v1/internal/ai/targets/{target_type}/{target_id}/contexts/project",
  "task:team": "http://work-service:8000/api/v1/internal/ai/targets/{target_type}/{target_id}/contexts/team",
  "task:progress": "http://work-service:8000/api/v1/internal/ai/targets/{target_type}/{target_id}/contexts/progress",
  "sprint:project": "http://work-service:8000/api/v1/internal/ai/targets/{target_type}/{target_id}/contexts/project",
  "sprint:team": "http://work-service:8000/api/v1/internal/ai/targets/{target_type}/{target_id}/contexts/team",
  "sprint:progress": "http://work-service:8000/api/v1/internal/ai/targets/{target_type}/{target_id}/contexts/progress"
}
```

Chỉ hai placeholder `{target_type}` và `{target_id}` được hỗ trợ; không dùng
`{domain}` hoặc `{project_id}`. Khi đủ điều kiện bật GitHub, thêm key
`project:github_activity` trỏ tới
`http://integration-service:8000/api/v1/internal/projects/{target_id}/github/context`.
Xác nhận port theo Compose của môi trường trước khi dùng.

Chạy thật phải tắt mock (`MOCK_TEST=false`), dùng JWT Identity còn hiệu lực
và target có quyền thật. API, worker, dispatcher và beat AI phải nhận cùng
map/key; staging/production fail startup khi thiếu cấu hình Work bắt buộc.
Health check thành công không chứng minh các endpoint này hoạt động.

Giữ `AI_GITHUB_CONTEXT_ENABLED=false` đến khi Work authorization, Integration
smoke và release gate thật đạt. Phía Integration cũng cần các flag tương
ứng theo [guide AI–Integration](../integration-service/ai-service-integration-guide.md).
GitHub chỉ được cấp cho risk Project với focus phù hợp; Sprint không gọi
Integration dù focus có `github_activity`. Tắt GitHub không tắt risk analysis:
AI vẫn dùng Work progress và trả limitation.

## 7. Kiểm thử và bàn giao

Work cần có unit test cho mỗi nhánh mới và provider contract test bằng
PostgreSQL thật; mock consumer AI không thay thế việc này.

- Authorization: đúng caller/key; key xoay vòng; thiếu/sai header; actor hết
  hạn/revoked; member active/removed; teacher; outsider; target không tồn tại;
  intent/target sai; membership bị thu hồi giữa authorize và GET.
- Scope: đủ 10 cặp target/domain và các cặp bị cấm; Task/Sprint khác Project
  không làm lộ dữ liệu; chỉ nhận path ID, không nhận query/body mở rộng scope.
- Shape: response authorize dùng envelope, context không envelope; UUID/date/
  version đúng; nullable khác missing; task HTML đã strip; không PII/secret.
- Giới hạn: 0/100/101 mục; text Unicode sát 65536 byte; partial có warning;
  thứ tự ổn định; counts/metrics không bị tính trên mảng đã cắt.
- Metrics: mẫu số 0, blocked/deadline/thiếu estimate, nhiều assignee; scope
  Sprint hiện hành và snapshot Sprint đã đóng; đơn vị capacity/workload rõ ràng.
- Read-only: không mutation, snapshot mới, outbox hoặc side effect; nguồn lỗi
  fail-closed, error/log không chứa credential hoặc raw payload.

Checklist nghiệm thu liên service:

1. Work bàn giao route chạy được, cấu hình caller, bộ test provider và quy tắc
   mapping/metric/đơn vị; contract vẫn khớp AI consumer.
2. Trên môi trường test/staging, dùng actor/Project thật chạy qua gateway AI:
   enqueue → dispatcher → worker → Work context → terminal result. Kiểm tra
   ba intent, partial, missing, stale và deny; không chỉ gọi health endpoint.
3. Nếu bật GitHub: có connection/consent hợp lệ, kiểm tra connected/partial/
   missing/stale/deny; xác nhận Sprint risk không gọi Integration.
4. Chạy evaluation/release gate trong
   [production readiness](../ai-service/production-readiness.md), lưu báo cáo;
   chỉ đổi trạng thái tài liệu sang **Đã triển khai** cho phần đã có bằng chứng.

Provider Work đã có; khi môi trường chưa đủ key/URL/dependency thật thì giữ
trạng thái nghiệm thu runtime là **Chưa xác minh**. Không né blocker bằng đọc
DB Work, bỏ kiểm quyền hoặc bật fixture trong staging.
