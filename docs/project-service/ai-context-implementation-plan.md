# Kế hoạch Work cung cấp quyền và context cho AI

Ngày lập và cập nhật: **22/10/2026**. Trạng thái: **Đã triển khai phía Work và kiểm thử local;
nghiệm thu đầy đủ mọi intent AI: Một phần**. Bằng chứng ở mục 10 và
[kiểm chứng HTTP staging local](ai-context-staging-validation-20261022.md).

Mục tiêu là bổ sung lớp đọc nội bộ vào Work để AI dùng adapter REST đang có,
giữ nguyên cấu trúc context mà AI đang đọc. Tận dụng xác thực, quyền Project,
query, công thức metrics và cấu hình hiện tại; không xây thêm hệ thống context.

Checkbox đánh dấu phần đã có source và kiểm thử tương ứng. Checkbox vận hành
và smoke service thật còn mở; không suy ra đã triển khai staging từ test local.

## 1. Phạm vi và tài liệu bắt buộc

- [x] Chọn REST nội bộ cho kiểm quyền và đọc context; Kafka tiếp tục dùng cho sự kiện bất đồng bộ.
- [x] Giữ nguyên JSON contract AI; không thêm trường đơn vị ngoài schema team.
- [x] Capacity là giờ/tuần; workload là story points còn lại, không quy đổi giữa hai đơn vị.
- [x] Đọc lại toàn bộ [AGENTS.md](../../AGENTS.md), rule thư mục liên quan và [mục lục hệ thống](../system/README.md) trước triển khai.
- [x] Đọc [kiến trúc](../system/architecture.md), [quyền sở hữu dữ liệu](../system/data-ownership.md), [cấu hình môi trường](../infrastructure/environment.md), [tài liệu Work](README.md).
- [x] Đọc [guide Work–AI](ai-service-integration-guide.md), [contract context](../../contracts/api/work-ai-context-v1.yaml), [contract Work](../../contracts/api/work-service.yaml) và [ADR-005](../adr/005-integration-work-ai-contracts.md).
- [x] Kiểm tra worktree hiện tại, đọc source/config/tests thực tế; không ghi đè công việc có sẵn.
- [x] Dùng skill Django và PostgreSQL phù hợp, GitNexus truy vết và impact trước khi sửa symbol hiện hữu. Kết quả graph phải được đối chiếu source.

Đường dẫn task cũ `docs/task/work-service.md` không còn trong checkout lúc lập
kế hoạch. Không suy diễn phân công từ tài liệu không có; nếu người triển khai
cần đối chiếu task cũ thì tìm bản thay thế hoặc ghi rõ giới hạn này.

Được sửa khi triển khai: `apps/work-service/**`, cấu hình **của Work** trong
`infra/env/work-service.env`, `.env.example`, contract và tài liệu Work liên quan.
Chỉ sửa phần Work trong cấu hình dùng chung nếu kiểm chứng cơ chế hiện tại chưa
đáp ứng; không chỉnh mặc định hay credential của service khác.

Không sửa nghiệp vụ AI/Integration/Identity/Classroom, frontend hoặc adapter
áp dụng proposal. Không thêm model, migration, dependency, cache, projection,
consumer, container hay broker cho lớp đọc này. Nếu phát hiện điều kiện thực tế
buộc phải vượt phạm vi, ghi bằng chứng và báo lại trước khi mở rộng.
Không tự commit hoặc triển khai lên môi trường dùng chung.

## 2. Căn cứ mã nguồn và phần tái sử dụng

Các vị trí dưới đây đã được đọc để lập kế hoạch; cần kiểm tra lại nếu source đổi.
Đây là bằng chứng cơ chế đang có, không phải bằng chứng ba API mới đã chạy.

| Thành phần | Hiện trạng và cách sử dụng |
| --- | --- |
| AI chọn nguồn context | **Đã triển khai trong code**: [context_factory.py:11](../../apps/ai-service/src/infrastructure/context_factory.py#L11) chọn fixture khi bật mock, còn lại chọn HTTP adapter. Không sửa factory. |
| AI gọi Work | **Đã triển khai trong code**: [context_http.py:75](../../apps/ai-service/src/infrastructure/context_http.py#L75) gửi Bearer + service key; [context.py:11](../../apps/ai-service/src/models/context.py#L11) quy định document/domain. Runtime hai service: **Chưa xác minh**. |
| Xác thực người dùng | Tái sử dụng [WorkJWTAuthentication:19](../../apps/work-service/common/authentication.py#L19) và cơ chế kiểm session Identity hiện hữu. Không tự giải mã JWT để bỏ qua session. |
| Quyền đọc Project | Tái sử dụng [read_project_scope:79](../../apps/work-service/apps/projects/queries/projects.py#L79); Member đang hoạt động hoặc Teacher đúng phạm vi. Không áp quyền ghi của Leader lên API đọc. |
| Đọc nhất quán | Theo [read_context_snapshot:244](../../apps/work-service/apps/projects/queries/context.py#L244) và [khóa Project:7](../../apps/work-service/apps/projects/services/locking.py#L7); không xuất nguyên chunks/checksum. |
| Metrics và chia điểm | Tái sử dụng [metric_totals:10 và allocate_points:44](../../apps/work-service/apps/projects/metrics.py#L10). [Dashboard:18](../../apps/work-service/apps/projects/queries/dashboard.py#L18) là tham khảo; bộ lọc dashboard không mặc nhiên là workload còn lại. |
| Sprint đã đóng | [closure.py:81](../../apps/work-service/apps/sprints/services/closure.py#L81) lưu totals, task facts, thời điểm và cut project sequence; [scope.py](../../apps/work-service/apps/sprints/queries/scope.py) giữ lịch sử đóng bất biến. |
| Receipt Integration hiện tại | [receipts.py:15](../../apps/work-service/apps/integrations/views/receipts.py#L15) xác thực bằng key; [base.py:153](../../apps/work-service/config/settings/base.py#L153) đọc danh sách inbound cũ. Không bắt receipt gửi thêm JWT. |
| Cấu hình/test | Dùng [mapping Work](../../infra/env/work-service.env), [test settings](../../apps/work-service/config/settings/test.py), [pytest/ruff hiện hành](../../apps/work-service/pyproject.toml), [fixtures chung](../../apps/work-service/tests/conftest.py). |

## 3. Hành vi phải cung cấp

### 3.1. Ba endpoint

| Method và path nội bộ | Caller và đầu vào | Kết quả |
| --- | --- | --- |
| `POST /api/v1/internal/ai/targets/{target_type}/{target_id}/authorize` | `ai`; Bearer + `X-Service-Key`; body `action=ai.analyze`, `intent` hợp lệ | Envelope authorize theo contract, gồm target, action, allowed; không trả context. |
| `GET /api/v1/internal/ai/targets/{target_type}/{target_id}/contexts/{domain}` | `ai`; cùng hai header; không nhận actor/scope do client tự khai | Trả trực tiếp `ContextDocument`, không bọc envelope Work. Kiểm quyền lại mỗi lần. |
| `POST /api/v1/internal/integration/projects/{project_id}/authorize` | `integration`; cùng hai header; body `action=github.read` | Envelope authorize theo contract; không kiểm token GitHub hoặc tự gọi GitHub. |

Giữ path nội bộ theo contract trên; không đổi API công khai `/api/work`.
URL service-to-service dùng DNS/port nội bộ của Compose. Route nội bộ không
được mở qua gateway công khai; kiểm chứng cấu hình Nginx hiện hữu khi nghiệm thu.

### 3.2. Ma trận cố định

| Intent authorize AI | Target được phép |
| --- | --- |
| `backlog_generation` | `project` |
| `task_decomposition` | `task` |
| `risk_analysis` | `project`, `sprint` |

| Target context | Domain được phép |
| --- | --- |
| `project` | `project`, `team`, `progress` |
| `task` | `task`, `project`, `team`, `progress` |
| `sprint` | `project`, `team`, `progress` |

Tổng cộng **10 cặp** target/domain. Không nhận domain tùy ý hoặc biến context
thành bộ query do AI tự điều khiển. Task/Sprint phải được resolve về Project
từ dữ liệu Work; không tin Project ID được gửi kèm.

### 3.3. Quyền và lỗi

- [x] Leader/Member đang hoạt động được đọc theo quyền Project; Assignee không tự có quyền nếu đã mất membership.
- [x] Teacher chỉ đọc Project thuộc phạm vi Classroom hiện hành mà họ được phép đọc.
- [x] Outsider, thành viên bị loại, target không thấy được và target không tồn tại không làm lộ dữ liệu: trả `404` theo contract.
- [x] Bearer thiếu/sai/hết hạn/session bị thu hồi: `401`; key thiếu/sai/sai caller: `403` khi Bearer hợp lệ.
- [x] Body/target/domain sai: `400`; document không thể thu nhỏ hợp lệ: `422`.
- [x] Khi đồng thời nhiều đầu vào sai, giữ thứ tự xác thực DRF và contract hiện hữu; không tạo quy tắc lỗi khác giữa các endpoint.
- [x] Lỗi nguồn xác minh quyền không được coi là có quyền. Giữ mã lỗi/trạng thái hiện hành có căn cứ; không blanket-map mọi exception thành lỗi retry được.
- [x] Success và error có `Cache-Control: no-store`; lỗi theo Work error envelope, thông báo tiếng Việt tự nhiên, không lộ key/cấu hình/exception.

## 4. Quy tắc dữ liệu

### 4.1. Scope, field và chỉ số

Ánh xạ chi tiết theo mục mapping trong guide và schema YAML; không duy trì
một schema thứ hai trong kế hoạch này. Serializer chỉ xuất field được cho phép.

- [x] Project: `target_goals` → `goals`, `end_date` → `deadline`; task/sprint summary có thứ tự ổn định.
- [x] Task: đúng Project, nội dung văn bản thuần, state/priority theo contract, `due_date` → `deadline`, `story_points` → `estimate_points`, dependency đúng chiều và trong phạm vi được phép đọc.
- [x] Loại task deleted/archived và membership không hoạt động theo cơ chế Work; kiểm target archived/deleted bằng quy tắc visibility hiện có, không tạo quyền đọc vòng qua API nội bộ.
- [x] Project/team qua target Task hoặc Sprint vẫn có scope Project. Chỉ **progress Sprint** giới hạn theo Sprint.
- [x] Progress Project tính trên toàn phạm vi task được phép, trước giới hạn summary; dùng đúng task count và root work-item count, không trộn hai mẫu số.
- [x] Dùng công thức completion/blocked/overdue hiện hữu. Mẫu số 0 giữ giá trị `null` nếu công thức Work quy định; không bịa tỷ lệ 0% hoặc 100%.
- [x] `observed_at`, `data.as_of` và document `as_of` nhất quán với thời điểm đọc thực tế.
- [x] Không trả email, display name, avatar, session, token, attachment credential hoặc identity GitHub. Không xuất nguyên model/dict chứa field ngoài allowlist.

Tái sử dụng xử lý nội dung hiện có, kiểm tra riêng bước chuyển HTML thành text
và chính sách lọc thông tin nhạy cảm. Sanitizer HTML không chứng minh đã lọc PII
hay secret. Không log raw context; ghi rõ giới hạn lọc thực tế, không hứa phát
hiện mọi secret do người dùng tự nhập.

### 4.2. Team: đơn vị và workload đã chốt

1. Chỉ xuất ProjectMember `ACTIVE`. `capacity` mỗi người lấy `weekly_capacity`,
   đơn vị **giờ/tuần**; số 0 là giá trị đã lưu, không tự hiểu là vô hạn hay thiếu dữ liệu.
2. `workload` mỗi người là phần **story points còn lại** được phân cho người đó:
   task cấp gốc, chưa deleted/archived, state group không thuộc `COMPLETED/CANCELLED`.
   Không cộng cả task cha và subtask.
3. Chia điểm bằng `allocate_points` hiện có, giữ quy tắc làm tròn và bảo toàn
   tổng điểm. Ví dụ một task 5 points có hai assignee hợp lệ cho mỗi người 2.5 points.
4. Task chưa có estimate không mặc nhiên là công việc 0 points: tổng là phần
   đã biết, document `partial` và warning nêu còn task thiếu estimate.
5. **Cách xử lý biên đã triển khai để giữ phép phân bổ hiện hành**: chia theo assignment
   hiện có rồi chỉ xuất phần của thành viên active; không chuyển ngầm phần của
   người đã rời nhóm sang người khác. Task chưa có assignee không gán cho một
   user giả. Nếu có phần chưa thể quy cho thành viên active, trả `partial` và
   warning; có test ghi rõ phần đã biết, phần bỏ qua.
6. Team tổng `capacity/workload` là tổng của **toàn bộ thành viên active trước
   khi cắt danh sách 100 người**; workload không bao gồm điểm chưa được gán cho
   những thành viên này. Thành viên không có việc có workload 0.
7. Giữ JSON hiện hành. Warning ngắn nêu “Năng lực tính bằng giờ/tuần; khối lượng
   còn lại tính bằng điểm ước lượng.” Khi dữ liệu đầy đủ vẫn có thể `available`
   kèm warning đơn vị; khi thiếu/cắt dữ liệu phải `partial` và nêu thêm lý do.

Không lấy workload chia capacity, không tính phần trăm quá tải từ hai đơn vị,
không sửa công thức dashboard công khai chỉ để phục vụ context AI.

### 4.3. Đọc nhất quán, version và Sprint đóng

- [x] Lấy chứng cứ Teacher qua adapter Classroom **trước** transaction khóa Project; không gọi mạng trong lúc giữ khóa.
- [x] Trong transaction dùng barrier Project hiện có, kiểm lại local membership/target visibility rồi đọc dữ liệu và version cùng một lần nhất quán.
- [x] Kiểm các đường ghi liên quan có tham gia barrier trước khi khẳng định tính nhất quán; không coi `atomic()` một mình là snapshot nhiều query.
- [x] Project/team/progress Project dùng `Project.event_sequence`; task domain dùng `Task.version`; progress Sprint đang mở dùng `sprint.version:project.event_sequence`, dạng chuỗi.
- [x] Không ghi snapshot, Activity, Outbox, receipt mới, tăng version hay gọi adapter ghi dữ liệu trong luồng đọc/authorize.
- [x] Sprint `DRAFT/ACTIVE`: scope hiện hành như query Work đang dùng.
- [x] Sprint `COMPLETED`: đọc snapshot đóng, giữ `captured_at`; không trộn totals cũ với blocked task/title lấy từ hiện tại.

Snapshot đóng hiện có totals và task facts nhưng không đủ mọi field summary
AI cần. **Đã triển khai trong phạm vi hiện tại**: trả document `stale` có
warning rõ là dữ liệu lịch sử, dùng metadata snapshot thật; không tạo summary
giả hoặc thêm migration để lấp dữ liệu. Source version lịch sử phải phản ánh
`cut_project_sequence` đã lưu, không gắn Project sequence mới lên payload cũ;
đồng bộ giải thích source version trong guide khi triển khai.

AI hiện từ chối `status=stale` hoặc context quá thời hạn, xem
[context_http.py:198](../../apps/ai-service/src/infrastructure/context_http.py#L198).
Vì vậy nghiệm thu không tuyên bố AI phân tích Sprint đã đóng thành công; kiểm
đúng việc không dùng lịch sử làm dữ liệu hiện hành. Không đổi timestamp thành
“bây giờ” để vượt kiểm tra độ mới, không sửa AI trong kế hoạch này.

### 4.4. Giới hạn document

- [x] Mỗi mảng, kể cả dependency/metrics, tối đa 100 phần tử; thứ tự ổn định, có tie-breaker ID.
- [x] Aggregate counts/totals trên toàn scope trước khi cắt mảng; không tải toàn bộ model rồi mới slice trong Python.
- [x] Áp maxLength từng field; field bắt buộc vẫn có mặt, giá trị nullable đúng schema.
- [x] Đo **toàn bộ JSON UTF-8 thực sự trả ra** không quá 65536 byte, gồm metadata/warning; không đo số ký tự.
- [x] Rút ngắn văn bản/mảng theo thứ tự cố định, giữ ID/số liệu/scope; mỗi lần rút gọn cập nhật `partial/warning`, đo lại sau serialize.
- [x] Warning không quá 500 ký tự, đủ lý do thiếu dữ liệu và đơn vị team; không cắt JSON bytes hoặc loại field bắt buộc.
- [x] Không thể đạt giới hạn mà vẫn hợp schema thì trả `422`; Project rỗng hợp lệ vẫn là dữ liệu có sẵn, không phải `missing`.

## 5. Các bước triển khai và đầu ra

### Bước 1 — Service key và cấu hình Work

- [x] Thêm đọc/kiểm tra `WORK_SERVICE_KEYS`, map caller `ai/integration` sang 1–2 key; default đóng quyền khi thiếu/sai cấu hình.
- [x] Key ngẫu nhiên riêng từng caller/chiều; 32–4096 ký tự ASCII in được, không khoảng trắng đầu/cuối, không trùng; dùng so sánh an toàn `compare_digest`.
- [x] Một key không hợp lệ cho cả `ai` và `integration`, cũng không được trùng key Work gửi đi Integration.
- [x] Đặt helper dùng chung tại `common/service_permissions.py`, không tạo hệ thống quản lý credential hoặc middleware toàn cục mới.
- [x] Endpoint mới kết hợp WorkJWTAuthentication với permission đúng caller; key không thay thế Bearer hay quyền người dùng.
- [x] Đồng bộ `.env.example` → `infra/env/work-service.env` → Compose `env_file` hiện có → settings; default không cấp quyền, không hardcode key/flag vào Compose.

**Tương thích key Integration đang chạy:** `WORK_INTEGRATION_INBOUND_KEYS`
đã phục vụ receipt. Tận dụng giá trị này, không yêu cầu đổi secret đang dùng.
Helper trả danh sách hiệu lực cho caller Integration: dùng map mới nếu có,
hoặc fallback danh sách cũ nếu map chưa khai báo Integration. Nếu cả hai cùng
có, yêu cầu chúng trùng bộ key; sai khác phải từ chối quyền, không hợp hai
danh sách thành nhiều key hợp lệ. Receipt và authorize dùng cùng bộ key hiệu lực,
nhưng receipt giữ cơ chế **key-only**, không bị buộc gửi actor JWT.

- [x] Viết test key cũ, map mới, cấu hình đồng thời khớp/lệch, sai caller, danh sách rỗng, malformed JSON và rotation.
- [x] Hướng dẫn xoay key: Work chấp nhận current + previous, caller chuyển sang current, xác minh rồi bỏ previous; cửa sổ chuyển tối đa 24 giờ theo guide, vận hành thủ công, không thêm scheduler.

### Bước 2 — Resolve target và authorize

- [x] Bổ sung query domain tại `apps/projects/queries/ai_context.py`: resolve Project/Task/Sprint và kiểm quyền đọc bằng cơ chế hiện hữu.
- [x] Bổ sung serializer input/response tại `apps/projects/serializers/ai_context.py`; từ chối action/intent/field ngoài contract.
- [x] Handler AI tại `apps/projects/views/ai_context.py` chỉ lo HTTP, validation, permission và gọi query.
- [x] Handler `github.read` đặt trong domain `apps/integrations/views/` theo cấu trúc đang có; tái sử dụng query quyền Project, không sao chép phép kiểm quyền.
- [x] Đăng ký URL qua URLconf domain và `config/urls.py` hiện hành; khai báo rõ method/schema/security trong OpenAPI.
- [x] Authorize không ghi receipt/idempotency key; gọi lặp vẫn đọc quyền hiện tại, không replay kết quả cho người đã mất quyền.

### Bước 3 — Bốn domain context

- [x] Query xử lý scope, aggregate và batch-read; serializer định dạng/giới hạn; view không chứa ORM hay công thức nghiệp vụ.
- [x] Tái sử dụng `metric_totals`, `allocate_points`, query scope Sprint và sanitizer phù hợp; không tạo ORM wrapper hoặc một file cho mỗi hàm.
- [x] Batch assignments/dependencies/states cần dùng; dùng projection có chủ đích. Kiểm actual query path, không coi có `prefetch_related` là hết N+1.
- [x] Không gọi lại Classroom hoặc Identity cho từng task/member trong vòng lặp; mỗi request vẫn phải xác thực quyền mới theo boundary hiện hữu.
- [x] Hoàn thành các quy tắc mục 4, raw ContextDocument, no-store và lỗi framework tiếng Việt.

### Bước 4 — Contract, tài liệu và hồi quy

- [x] Dùng extension/hook schema hiện có; hook context đặt tại `apps/projects/api_documentation.py`, mô tả Bearer **AND** service key, không vô tình phát hành thành lựa chọn OR.
- [x] Xuất schema vào file kiểm tra riêng trước, đối chiếu contract chuẩn; chỉ đổi endpoint đã thực sự triển khai từ planned sang implemented.
- [x] Giữ nguyên schema/event/route ngoài phạm vi và các tham chiếu contract khác; không ghi đè YAML đã bổ sung thủ công bằng output thiếu chúng.
- [x] Cập nhật guide/README Work về đơn vị, key compatibility, version lịch sử và bằng chứng kiểm thử; không tuyên bố runtime thật nếu chỉ test fixture.
- [x] Kiểm liên kết, tài liệu lỗi thời, file rỗng liên quan; rà diff bảo đảm không có secrets hoặc thay đổi service khác.

## 6. Ma trận kiểm thử bắt buộc

Các file dưới đây **đã bổ sung**, trừ trường hợp ghi rõ gộp vào file có cùng trách nhiệm.
Fixture chung nằm trong `tests/conftest.py` hoặc `tests/fixtures/`; không import
fixture từ một `test_*.py` khác. Dùng PostgreSQL test riêng cho quyền/scope/transaction.

| Nhóm | File và ca kiểm chính |
| --- | --- |
| Service/caller | `tests/contract/test_internal_service_permissions.py`: Bearer + key, caller chéo, rotation, legacy receipt vẫn key-only, cấu hình hỏng đóng quyền. |
| Authorize | Gộp vào `tests/contract/test_ai_context_api.py`: từng method, action, intent/target; `github.read` chỉ Integration; response/error/no-store. |
| Context schema | `tests/contract/test_ai_context_api.py`: đủ 10 cặp, field allowlist, kiểu số/null/date, raw document, sai domain/body, không redirect/HTML. |
| Quyền/scope | `tests/integration/test_ai_context_permissions.py`: Leader/Member/Assignee/Teacher/outsider, Project khác, task/sprint deleted/archived, session revoke, membership mất giữa authorize và GET. |
| Dữ liệu/chỉ số | `tests/integration/test_ai_context_data.py`: Project rỗng, root/subtask, terminal, nhiều assignee, thiếu estimate, inactive/unassigned, totals trước slice, Sprint hiện hành/đóng. |
| Giới hạn và query | `tests/integration/test_ai_context_limits.py`: 100/101 items, Unicode nhiều byte, text dài, 65536-byte boundary, partial/warning, không N+1 khi tăng quy mô. |
| Tính nhất quán | `tests/integration/test_ai_context_consistency.py`: cạnh tranh ghi/đọc/mất quyền qua barrier bằng connection riêng, payload/version đồng bộ; không Activity/Outbox/receipt/ghi DB nghiệp vụ phát sinh. |

- [x] Test đủ trường hợp trên, gồm dependency permission provider lỗi và key đúng nhưng actor không có quyền.
- [x] Đo query cho đường HTTP → permission → query → serializer; tách chi phí auth khỏi query dữ liệu, kiểm số query không tăng tuyến tính theo số phần tử.
- [x] Hồi quy receipt Integration, context snapshot, dashboard, Sprint và auth hiện hữu bị ảnh hưởng; không đổi kết quả dashboard chỉ vì team AI lọc khác.
- [x] Đối chiếu document với JSON Schema Draft 2020-12 bằng `jsonschema` hiện có; không cài thêm dependency hoặc import source AI vào runtime Work.

### Cách chạy tại môi trường test

Trước khi chạy, xác minh `WORK_TEST_DB_*` và `WORK_TEST_DATABASE` trỏ PostgreSQL
test tách biệt, user có quyền tạo test DB; không dùng DB local có dữ liệu thật
hoặc staging. Không chạy script LIVE ghi dữ liệu. `config.settings.test` dùng
fixture Classroom; fixture Identity là HTTP mock trong test, không phải provider thật.

Ví dụ PowerShell từ root repo, dùng interpreter của môi trường Work đã có:

```powershell
Set-Location apps/work-service
.\.venv\Scripts\python.exe manage.py check --settings=config.settings.test
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m pytest
```

Nếu `.venv` nằm nơi khác, dùng đúng interpreter đang được dự án dùng; không
tự cài dependency để làm lệnh chạy được. Kiểm exit code từng lệnh; thiếu DB/tool
thì ghi rõ chưa chạy. Lần đầu có thể chạy các file mới rồi nhóm hồi quy; chạy
suite mặc định trước nghiệm thu. Không thay default pytest để kéo provider thật
hoặc bài e2e vào CI.

Để kiểm schema, dùng lệnh `manage.py spectacular --file <file-kiểm-tra> --validate`
với test settings, sau đó so sánh với contract trước khi cập nhật bản chuẩn.
Không chạy lệnh xuất trực tiếp đè contract Work khi chưa rà khác biệt.

## 7. Cấu hình và smoke giữa các service

### 7.1. Phần Work phải hoàn thành

- [x] Mẫu cấu hình mới có `WORK_SERVICE_KEYS` mặc định `{}`; mọi key thật chỉ ở nguồn secret của môi trường, không ghi vào tài liệu/Git/log.
- [x] `ai` nhận đúng key AI gửi; `integration` nhận đúng inbound key Integration hiện hữu theo quy tắc tương thích bước 1.
- [x] Kiểm Compose local/staging render và chỉ kiểm tên biến/boolean kết quả; không in toàn bộ cấu hình đã nội suy chứa secret.
- [x] Kiểm Nginx vẫn chặn internal từ public route; không mở thêm port/route để AI gọi vòng qua gateway.
- [x] Build/push registry local và recreate Work trên stack staging local hiện hữu; không SSH/VPS. Xem báo cáo runtime. Restart đơn thuần không nạp lại Compose env.

### 7.2. Điều kiện bàn giao, không sửa service khác

AI đã có HTTP adapter nhưng chạy thật còn cần `MOCK_TEST=false`, key đúng,
`AI_AUTHORIZATION_URLS` đủ 3 target và `AI_CONTEXT_URLS` đủ 10 cặp. Dùng nguyên
map trong mục cấu hình của guide, chỉ có placeholder `{target_type}/{target_id}`,
không thêm `{domain}` vào template được AI format.

Ghi nhận cấu hình AI/Integration hiện có là đủ hay còn thiếu rồi bàn giao cho
đơn vị phụ trách môi trường; không tự sửa code/config của họ trong gói Work.
Đây là điều kiện ghép runtime, không phải lý do để bỏ dở cấu hình phía Work.
GitHub là nhánh nghiệm thu riêng: Work cung cấp `github.read`, Integration giữ
quyền gọi GitHub và kiểm repository/credential; không bật GitHub để chứng minh
luồng đọc bốn domain Work.

### 7.3. Smoke có kiểm soát

Thực hiện trong môi trường test được phép, dùng Project/Task/Sprint và actor
thử nghiệm có quyền thật. Lấy Bearer/key từ env hoặc secret store vào HTTP client;
không dán token vào chat, file evidence hoặc output. Gửi request đúng bảng mục 3,
kiểm status/schema/caller/scope và chỉ ghi metadata đã lọc.

- [x] Gọi AI authorize → context Project/Task/Sprint đang mở qua mạng nội bộ thật; đầy đủ domain tương ứng, Identity/Classroom thật.
- [x] Dùng key caller Integration gọi `github.read` qua HTTP thật; dùng AI key trên cùng route bị từ chối. Không đồng nghĩa đã nghiệm thu GitHub trong AI.
- [ ] Kiểm người ngoài, Teacher ngoài lớp, session bị thu hồi và membership mất sau authorize; GET không được dùng kết quả quyền cũ.
- [x] Một yêu cầu phân rã Task đã đi hết API → queue/worker → Work → LLM → 3 subtask, không fixture. Smoke LLM dùng AI development tạm để gọi endpoint HTTP; ba ca khác timeout, chưa nghiệm thu mọi intent/staging LLM.
- [x] Nếu LLM/queue/Identity/Classroom thật chưa sẵn sàng, ghi chính xác chặng chưa xác minh; không coi HTTP stub hay provider tests là end-to-end thật.
- [ ] Sprint đóng trả lịch sử/stale đúng quy tắc, không tuyên bố phân tích dữ liệu hiện hành thành công.
- [x] Hash/version Project/Task/Sprint qua HTTP trước/sau AI không đổi. Chỉ logout session thử vừa tạo; chưa thay membership thật.

## 8. CI và điều kiện hoàn tất

Tận dụng Python service workflow và test discovery hiện hữu. Những API này
không yêu cầu thêm Kafka broker, job, profile hoặc container vào
`.github/workflows/python-service.yml`. PostgreSQL/fixture test đủ cho provider
tests; smoke nhiều service chạy riêng có kiểm soát, không giả làm CI đã nghiệm thu.

- [x] Lint/format/check và test mới + hồi quy Work thực sự chạy thành công, hoặc ghi rõ blocker có bằng chứng.
- [x] Mọi method/endpoint và đủ 10 cặp target/domain có kiểm thử; success/business/framework error tuân rule thông báo.
- [x] Có test bảo vệ quyền từng lần đọc, snapshot/version, 100 items/64 KiB, totals toàn scope và workload khác đơn vị capacity.
- [x] Receipt Integration tiếp tục hoạt động đúng key cũ; endpoint authorize mới không làm thay đổi nghiệp vụ connect/receipt/consumer.
- [x] Contract xuất ra khớp runtime, guide không mô tả planned là implemented, không có liên kết hỏng hoặc schema trùng nguồn.
- [x] Báo cáo file đã sửa, lệnh/exit code/số test thật; tách fixture, PostgreSQL thật, HTTP thật, e2e và staging.
- [x] Chỉ ghi **Hoàn tất phía Work** khi code + cấu hình + contract + provider tests đạt; chỉ ghi **Đã nghiệm thu kết nối AI thật** khi có bằng chứng mục 7.3.
- [x] Rà worktree và phạm vi trước bàn giao; không stage toàn repo, không tự commit/deploy.

## 9. Cách dùng kế hoạch khi giao triển khai

> Tiếp tục các mục chưa đánh dấu của kế hoạch này, đọc rule và căn cứ trước khi sửa. Tận dụng
> source hiện có; chỉ sửa Work và cấu hình/contract/tài liệu thuộc Work trong phạm
> vi mục 1. Thực hiện test theo mục 6, cập nhật checkbox bằng bằng chứng và ghi
> phần chưa xác minh. Không đổi JSON AI, sửa nghiệp vụ service khác, thêm hạ tầng,
> hoặc mở rộng sang proposal apply. Khi gặp khác biệt source/contract, nêu đúng
> đường gọi và lựa chọn nhỏ nhất, không tự bịa schema/quyền. Không tự commit/deploy.

## 10. Kết quả triển khai và giới hạn kiểm chứng

### Phạm vi đã hoàn thành

**Đã triển khai** ba route trong mục 3, bộ nhận diện caller dùng chung, xác thực
người dùng hiện hữu, bốn domain context, giới hạn response và OpenAPI runtime.
Receipt Integration giữ key-only. Không thêm model/migration/dependency hoặc
thay consumer/Compose/CI workflow; chỉ bổ sung biến Work qua pipeline env hiện có.

Nguồn code mới: [permission caller](../../apps/work-service/common/service_permissions.py),
[biên HTTP nội bộ](../../apps/work-service/common/internal_api.py),
[query context](../../apps/work-service/apps/projects/queries/ai_context.py),
[serializer](../../apps/work-service/apps/projects/serializers/ai_context.py),
[view AI](../../apps/work-service/apps/projects/views/ai_context.py),
[authorize Integration](../../apps/work-service/apps/integrations/views/authorization.py),
[hook OpenAPI](../../apps/work-service/apps/projects/api_documentation.py).
Contract Work giữ các tham chiếu tới `work-ai-context-v1.yaml`; ba operation
trong contract context chuyển sang `implemented`. Schema được xuất vào file
kiểm tra riêng và xác minh các path/schema cũ ngoài phạm vi giữ nguyên.

Test query count đã phát hiện và sửa N+1 do deferred `project_id` khi dùng
reverse relation: bổ sung field liên kết trong projection task/sprint. Test
qua HTTP so sánh 1 với 51 task, query count giữ nguyên cho project/team/progress.
Kiểm cạnh tranh dùng hai PostgreSQL connection, xác minh reader chờ khóa thật,
sau đó đọc đúng version đã commit hoặc bị từ chối sau khi membership bị thu hồi.

### Kiểm tra đã chạy ngày 22/10/2026

| Kiểm tra | Kết quả và giới hạn |
| --- | --- |
| Work suite mặc định | Sau giản lược: **944 passed, 6 deselected** trong 139 giây. Sáu test external/e2e không thuộc suite mặc định; một test HTTP adapter đã chạy riêng ở dòng dưới. PostgreSQL test riêng tại port 55439, không dùng DB nghiệp vụ. |
| OpenAPI và representation bổ sung | **3 passed**: schema runtime gắn đúng domain, hai header cùng bắt buộc, raw context và giới hạn byte chính xác/422. |
| Cấu hình bổ sung | **4 passed**: JSON lỗi không cấp quyền, mapping theo env_file, default đóng quyền, không thêm consumer. |
| Adapter AI → HTTP Work | **1 passed** với `-m external`: adapter `InternalContextAdapter` thật đọc đủ 10 cặp; session fixture bị thu hồi thì ba target bị từ chối. Không chạy AI API/queue/LLM. |
| Ruff | `ruff check --no-cache .` và `ruff format --check --no-cache .` đã qua trên toàn Work. |
| Django/migration | `manage.py check --settings=config.settings.test`: không lỗi; `makemigrations --check --dry-run`: không thay đổi. |
| OpenAPI | `manage.py spectacular --settings=config.settings.test --validate --file <file-kiểm-tra>` qua. |
| Cấu hình Work/CI/Compose | **20 tests passed**: `test_work_integration_configuration`, `test_ci_environment`, `test_local_compose`. Render cả local/staging với profile đầy đủ: 4 process Work nhận default map `{}`, chỉ 1 consumer. |
| CI discovery | Truyền danh sách file đổi thực tế: discovery chọn `work-service`, PostgreSQL/Redis/Django checks theo cấu hình có sẵn; không thêm job hoặc Kafka vào workflow. |
| Cấu hình staging hiện có | Chỉ đọc và kiểm boolean: AI/Integration key gửi khớp key Work nhận, legacy/map khớp, caller tách key. Không in/đổi secret hoặc recreate container. Local `.env` chưa có key caller thật; default đóng quyền. |
| Test script staging Linux | Chạy trong image Work sẵn có, mount repo read-only, network off, Docker/SSH là stand-in: **53 passed, 1 skipped, 1 error** do image thiếu `ssh-keygen`. Lần chạy Windows trước đó lỗi Bash/WSL; không sửa script để che lỗi môi trường. |

Các test script staging dùng stand-in để kiểm shell, **không deploy thật**.
Không coi kết quả render Compose hoặc key khớp là bằng chứng image đang chạy
đã chứa endpoint mới. Build/publish/recreate và hosted CI/staging thật chưa chạy.
Các kiểm tra source/check/pytest có exit code 0. Bộ script staging Linux có
exit code 1 vì thiếu `ssh-keygen`, không được ghi là đã qua toàn bộ CI/release.

Chạy lại phép HTTP adapter riêng sau suite mặc định, từ `apps/work-service`:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/integration/test_ai_context_http.py -m external -q
```

Test dùng interpreter AI đã có; có thể đặt `WORK_AI_TEST_PYTHON` tới interpreter
tương ứng trên máy khác. Credential test truyền qua stdin cho tiến trình con,
không qua tham số CLI hay file. Không cài dependency AI vào Work, không sửa source AI.

### Giản lược tổ chức code

Đợt giản lược ngày 22/10/2026 giữ nguyên ba API và contract JSON:

- Query context chỉ đọc/chụp dữ liệu và version; không import serializer hoặc
  lọc văn bản/giới hạn JSON. Dữ liệu được materialize trong transaction, không
  trả queryset/model để serializer vô tình đọc DB sau khi nhả khóa.
- View gọi `ContextDocumentSerializer`; serializer chịu trách nhiệm lọc nội
  dung, cắt mảng, warning và giới hạn byte. Các công thức metrics/workload vẫn
  tái sử dụng Work như trước.
- Quyền đọc Project dưới barrier dùng chung tại
  [readable_project](../../apps/work-service/apps/projects/queries/projects.py).
  Authorize Integration không còn import module AI; serializer authorize của
  Integration nằm trong serializer repository hiện hữu của domain Integration.
- Bỏ `PolymorphicProxySerializer`, `ContextDataField` và component trung gian
  `WorkAIContextData`. Dùng `OpenApiSerializerExtension` của thư viện đã có để
  mô tả trực tiếp các domain. Hook còn lại chỉ bổ sung metadata HTTP.

Đã đối chiếu schema trước/sau: toàn bộ operation/path giữ nguyên; chỉ bỏ
component proxy không dùng và cập nhật cách biểu diễn `ContextDocument.data`
tương đương. Không tạo module nghiệp vụ, dependency, bảng hoặc cấu hình mới;
không sửa `.env.staging`, Compose hay CI trong đợt giản lược.

Kiểm chứng riêng cho ranh giới query/serializer: đủ 10 cặp target/domain có
test xác nhận serialize dữ liệu đã chụp không phát sinh bất kỳ query DB nào.
Sau giản lược, `manage.py check`, kiểm migration, Ruff lint/format và xuất
OpenAPI `--validate` đều qua. Toàn bộ operation giữ nguyên; mọi schema còn lại
tương đương trước đó (kiểu object cho phép thuộc tính bất kỳ có thể được xuất
với `additionalProperties: {}` hoặc bỏ thuộc tính này).

### Phần còn mở

**Một phần:** đã chạy staging local với Identity/Classroom/Work thật và một ca
API → queue/worker → Work → LLM thành công khi tạm cho runtime AI development
gọi endpoint HTTP. Ba ca khác timeout 30 giây; sau lượt smoke đã khôi phục
staging. Theo yêu cầu tiếp theo, điều kiện chặn HTTP đã được bỏ và image AI
staging local đã cập nhật; chưa chạy lại bốn workflow sau bản sửa HTTP.
Xem [báo cáo runtime](ai-context-staging-validation-20261022.md).
Chưa nghiệm thu mọi intent, GitHub trong AI, public TLS/VPS hoặc hosted CI.
Một số tài liệu AI còn ghi provider Work chưa triển khai; bàn giao bằng chứng
phía Work này để đội AI cập nhật trạng thái trong phạm vi tài liệu của họ.

GitNexus đã hỗ trợ truy vết quyền và impact receipt. Symbol mới chưa có trong
index nên impact trả `UNKNOWN/not found`; không coi đó là bằng chứng không có
ảnh hưởng. Các import/URL/call path mới đã được đọc trực tiếp và kiểm bằng test.
