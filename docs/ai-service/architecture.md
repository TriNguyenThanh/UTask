# Kiến trúc AI Service

**Trạng thái: Một phần.** Pipeline API → PostgreSQL → dispatcher → Redis/Celery
→ ADK workflow đã triển khai trong source. JWT, domain tools và adapter REST
đã có; integration với Identity/Work/Integration và LLM production **chưa xác
minh**. Work provider mới có hợp đồng, **Chưa triển khai**. Retention terminal
đã có source/migration/Celery beat; Kafka và specialist **Chưa triển khai**.

Thiết kế theo [baseline](../architecture/README.md),
[ADR-001](../adr/001-adopt-architecture-baseline.md) và
[ADR-002](../adr/002-ai-request-pipeline.md). Hiện trạng được đối chiếu với
source/test và cấu hình M3. Xem [mức sẵn sàng production](production-readiness.md),
[code map](code-map.md), [API v1](api.md),
[workflow](workflow.md), [ERD](erd.md) và [hướng dẫn chạy](README.md).

## Responsibilities — thiết kế mục tiêu

AI nhận ý định, kiểm tra quyền, lấy context tối thiểu qua domain tools, chạy
bounded agent (agent có giới hạn), kiểm tra output theo schema và lưu proposal.
API v1 chỉ hỗ trợ `backlog_generation`, `task_decomposition`, `risk_analysis`.
Các intent khác cần contract và implementation riêng.

ADK Workflow kiểm soát luồng bắt buộc, retry/revise và validation. `LlmAgent`
tự chọn domain tool trong phạm vi được cấp. Application sở hữu tiếp nhận,
trạng thái và lưu kết quả; adapter lắp ghép framework/provider bên ngoài.

## Non-responsibilities — boundary

- Identity sở hữu user/token; AI xác minh JWT ký bất đối xứng với issuer,
  audience và public key/JWKS được cấu hình. Không tin identity header client.
- Work sở hữu Project/ProjectMember, Sprint, Task, Comment và tiến độ theo quy
  tắc; Classroom sở hữu Group/GroupMember. ID xuyên service chỉ là tham chiếu.
- Integration là service duy nhất gọi GitHub API. AI lấy dữ liệu đã chuẩn hóa.
- AI không đọc database service khác, tạo FK xuyên service hoặc áp dụng
  proposal. User xác nhận; service sở hữu kiểm tra quyền/business rule và áp dụng.
- Auth, dashboard và nghiệp vụ chính không phụ thuộc AI/LLM.

## Request flow

### Implementation hiện tại

```text
POST /api/ai/v1/requests
  → JWT + input validation → Application → REST kiểm tra quyền target
  → transaction AI PostgreSQL: request queued + delivery job
  → API chờ persistence tối đa 10 giây → 200 hoặc 202 + Location

Dispatcher → claim delivery có lease → Redis → Celery task(request_id)
  → Application worker claim queued → running + execution token + deadline
  → giải mã credential → xác minh lại JWT/quyền
  → ADK ProposalWorkflow → LlmAgent → domain tool pool → REST adapter
  → kiểm tra output đúng intent/version → revise/retry trong budget
  → transaction: lưu ai_completion + xóa credential + pg_notify(request_id)

API listener LISTEN utask_ai_completed → Application tiếp nhận ai_completion
  → transaction: kiểm tra token/output → cập nhật succeeded/result hoặc failed/error
  → xóa ai_completion; GET/POST đọc trạng thái cuối từ ai_request

GET /api/ai/v1/requests/{request_id}
  → JWT → ownership AI request → đọc cùng PostgreSQL → response hiện tại
```

**Đã triển khai:**

1. `main.create_app` lắp repository PostgreSQL, JWT verifier, credential vault,
   REST authorizer và application. API không import/chạy ADK hoặc worker.
2. Application kiểm tra quyền trước khi enqueue. Backlog chưa có target vẫn
   cần identity hợp lệ. Endpoint quyền chưa cấu hình hoặc kết quả không có
   `allowed: true` thì từ chối; không dùng projection làm bằng chứng quyền.
3. Repository chuẩn hóa payload, tính SHA-256 và dùng unique `(user_id,
   idempotency_key)` cùng `INSERT ... ON CONFLICT`. Request và delivery được
   lưu trong cùng transaction. POST đồng thời cùng key dùng một request/job;
   payload khác trả `409`; request đã kết thúc không chạy model lại.
4. Dispatcher dùng `FOR UPDATE SKIP LOCKED` nhận quyền giao delivery. Lease
   hết hạn cho phép dispatcher khác tiếp tục. Broker lỗi được retry có backoff,
   jitter và giới hạn. Sau publish, delivery còn bền vững và được giao lại nếu
   worker chưa claim, kể cả Redis mất task; worker claim thì xóa delivery.
5. Celery task chỉ nhận UUID và gọi application. Claim khóa request; chỉ
   `queued` được chuyển sang `running`. Job trùng/terminal không gọi LLM.
   Deadline bắt đầu từ lần claim, không được đặt lại khi task giao lại.
6. Worker giải mã Bearer bằng Fernet và xác minh lại JWT/quyền trước chạy.
   Credential không xuất hiện trong task/prompt/log, được xóa khi bàn giao kết
   quả hoặc ở trạng thái cuối do timeout/dispatch lỗi. Token hết hạn trong
   queue làm request thất bại; không giữ quyền cũ.
7. Model/tool budget được trừ trong PostgreSQL trước lời gọi. Output token
   được tính theo usage; lần model tiếp theo chỉ được cấp phần cap còn lại.
   SDK thiếu usage thì trừ toàn bộ cap đã cấp. Retry provider tạm lỗi và revise
   output dùng chung số vòng, budget và deadline; SDK retry ẩn bị tắt.
8. Worker có execution token hiện hành bàn giao kết quả vào `ai_completion`
   và phát notification cùng transaction; chưa cập nhật terminal state. API
   kiểm tra lại token/schema/intent/version rồi cập nhật request và xóa inbox
   cùng transaction. Success phải bàn giao trước deadline; bàn giao quá hạn
   thành lỗi timeout. Dispatcher chỉ timeout request chưa có completion.

API/dispatcher/worker/beat là process của cùng AI Service, cùng code và AI DB;
không bắt buộc singleton. ADK session chỉ ở memory trong một job, không phải
request repository. Nguồn schema là [migration](../../apps/ai-service/migrations/versions/0001_request_pipeline.py),
application lifespan không tạo bảng. Entrypoint container chạy
`alembic upgrade head` trước Uvicorn; migration lỗi thì API không khởi động.
Worker/dispatcher chờ API healthy trong Compose; chạy trực tiếp bằng `uv`
vẫn cần migration thủ công theo [README](README.md#chạy-từng-process-bằng-uv).

### Giới hạn tối thiểu chống spam

**Đã triển khai trong source:** tiếp nhận tối đa 5 request mới/user trong
cửa sổ trượt 60 giây và tối đa 2 request `queued`/`running`/user, chỉnh bằng
config. PostgreSQL khóa transaction theo user; replay/conflict được xử lý
trước giới hạn và request/delivery chỉ được tạo khi còn chỗ. Nhiều API process
dùng chung giới hạn, không có bộ đếm riêng trong memory. Vượt giới hạn trả
`429` và `Retry-After`; xem [API](api.md#giới-hạn-chống-spam).

Budget model/tool/token và timeout mỗi lần chạy, reauthorization tại worker,
domain tools cố định và proposal không tự ghi nghiệp vụ tiếp tục áp dụng.
Không thêm quota theo ngày, framework bảo mật hoặc service mới.

**Thiết kế mục tiêu, chưa triển khai:** khi có chatbot, dùng lại giới hạn
tiếp nhận/budget/quyền; chatbot ban đầu đọc context và trả lời/đề xuất. Khi
triển khai lịch kiểm tra tiến độ, chạy 06:00 và 22:00 theo `Asia/Ho_Chi_Minh`,
mỗi project một job mỗi khung giờ. Lưu khóa occurrence để retry không tạo job
mới, không chạy chồng cùng project hoặc chạy bù hàng loạt sau restart. Job
chỉ phân tích/báo cáo, không tự sửa task. Thông báo cùng cảnh báo cần chống
gửi lặp tại Notification khi có contract và luồng gửi thực tế. Chưa tạo
scheduler, conversation hoặc notification runtime trong thay đổi này.

### Bàn giao kết quả worker cho API

**Đã triển khai trong source và kiểm thử local; production Chưa xác minh.**
Theo yêu cầu cập nhật ngày 2026-10-08, process API nhận thông báo hoàn thành
và ghi trạng thái/kết quả cuối. Cơ chế này bổ sung bước tiếp nhận vào pipeline
[ADR-002](../adr/002-ai-request-pipeline.md), thay việc worker trực tiếp ghi
terminal result ở mục 3 của quyết định ban đầu.

- Worker gọi `stage_completion`: khóa request, kiểm tra execution token,
  lưu kết quả đã validate vào inbox (bảng chờ tiếp nhận) `ai_completion`, xóa
  credential không còn cần và gọi `pg_notify` trong cùng transaction. Payload
  notification chỉ có request UUID, không có kết quả/context/credential.
- Mỗi process API có listener riêng, đăng ký `LISTEN utask_ai_completed`
  trước khi đọc inbox. Khi nhận tín hiệu, listener gọi application để đọc
  và tiếp nhận completion; không chạy workflow/LLM trong API.
- API khóa request bằng `FOR UPDATE SKIP LOCKED`, kiểm tra execution token và
  schema/intent/version/result. Ghi trạng thái cuối, kết quả hoặc lỗi/dead-letter
  và xóa inbox cùng transaction. Nhiều API process hoặc thông báo trùng không
  ghi đè kết quả hay tạo dead-letter trùng. Completion sai schema thành failed;
  completion có token cũ bị bỏ qua và xóa, không sửa request.
- `NOTIFY` chỉ đánh thức listener, không bảo đảm lưu thông báo khi API mất
  kết nối. `ai_completion` là nguồn phục hồi bền vững. Listener đọc inbox sau
  mỗi lần kết nối, khi có tín hiệu và định kỳ mỗi 5 giây theo
  `AI_COMPLETION_RECONCILE_SECONDS`; lỗi kết nối/tiếp nhận được thử lại, không
  chạy lại LLM. Worker chết trước khi commit bàn giao vẫn bị timeout như cũ.
- Khi API tạm dừng, completion đã commit được giữ lại; request vẫn `running`
  đến khi API tiếp nhận. Kết quả bàn giao đúng hạn không bị dispatcher đổi
  thành timeout chỉ vì API xử lý muộn. Bearer đã xóa từ lúc bàn giao.

Listener dùng một connection PostgreSQL riêng, autocommit và đóng khi API
shutdown; cần kết nối trực tiếp hoặc session pooling, không dùng transaction
pooling cho `LISTEN`. Các query/transaction tiếp nhận dùng connection pool
hiện có. Chạy Alembic tới migration `0002` trước khi khởi động phiên bản mới;
phối hợp cập nhật API và worker, không trộn worker cũ ghi terminal trực tiếp
với luồng bàn giao mới.

Đây là thông báo nội bộ cùng AI Service, không phải Kafka domain event hoặc
SSE/WebSocket cho frontend. POST vẫn chờ persistence tối đa 10 giây và GET
vẫn đọc bản ghi cuối theo ownership. Không thay đổi schema/URL public v1.
Xem [ERD](erd.md) và [code map](code-map.md).

### Giới hạn tối thiểu chống spam

**Đã triển khai trong source:** tiếp nhận tối đa 5 request mới/user trong
cửa sổ trượt 60 giây và tối đa 2 request `queued`/`running`/user, chỉnh bằng
config. PostgreSQL khóa transaction theo user; replay/conflict được xử lý
trước giới hạn và request/delivery chỉ được tạo khi còn chỗ. Nhiều API process
dùng chung giới hạn, không có bộ đếm riêng trong memory. Vượt giới hạn trả
`429` và `Retry-After`; xem [API](api.md#giới-hạn-chống-spam).

Budget model/tool/token và timeout mỗi lần chạy, reauthorization tại worker,
domain tools cố định và proposal không tự ghi nghiệp vụ tiếp tục áp dụng.
Không thêm quota theo ngày, framework bảo mật hoặc service mới.

**Thiết kế mục tiêu, chưa triển khai:** khi có chatbot, dùng lại giới hạn
tiếp nhận/budget/quyền; chatbot ban đầu đọc context và trả lời/đề xuất. Khi
triển khai lịch kiểm tra tiến độ, chạy 06:00 và 22:00 theo `Asia/Ho_Chi_Minh`,
mỗi project một job mỗi khung giờ. Lưu khóa occurrence để retry không tạo job
mới, không chạy chồng cùng project hoặc chạy bù hàng loạt sau restart. Job
chỉ phân tích/báo cáo, không tự sửa task. Thông báo cùng cảnh báo cần chống
gửi lặp tại Notification khi có contract và luồng gửi thực tế. Chưa tạo
scheduler, conversation hoặc notification runtime trong thay đổi này.

### Bàn giao kết quả worker cho API

**Đã triển khai trong source và kiểm thử local; production Chưa xác minh.**
Theo yêu cầu cập nhật ngày 2026-10-08, process API nhận thông báo hoàn thành
và ghi trạng thái/kết quả cuối. Cơ chế này bổ sung bước tiếp nhận vào pipeline
[ADR-002](../adr/002-ai-request-pipeline.md), thay việc worker trực tiếp ghi
terminal result ở mục 3 của quyết định ban đầu.

- Worker gọi `stage_completion`: khóa request, kiểm tra execution token,
  lưu kết quả đã validate vào inbox (bảng chờ tiếp nhận) `ai_completion`, xóa
  credential không còn cần và gọi `pg_notify` trong cùng transaction. Payload
  notification chỉ có request UUID, không có kết quả/context/credential.
- Mỗi process API có listener riêng, đăng ký `LISTEN utask_ai_completed`
  trước khi đọc inbox. Khi nhận tín hiệu, listener gọi application để đọc
  và tiếp nhận completion; không chạy workflow/LLM trong API.
- API khóa request bằng `FOR UPDATE SKIP LOCKED`, kiểm tra execution token và
  schema/intent/version/result. Ghi trạng thái cuối, kết quả hoặc lỗi/dead-letter
  và xóa inbox cùng transaction. Nhiều API process hoặc thông báo trùng không
  ghi đè kết quả hay tạo dead-letter trùng. Completion sai schema thành failed;
  completion có token cũ bị bỏ qua và xóa, không sửa request.
- `NOTIFY` chỉ đánh thức listener, không bảo đảm lưu thông báo khi API mất
  kết nối. `ai_completion` là nguồn phục hồi bền vững. Listener đọc inbox sau
  mỗi lần kết nối, khi có tín hiệu và định kỳ mỗi 5 giây theo
  `AI_COMPLETION_RECONCILE_SECONDS`; lỗi kết nối/tiếp nhận được thử lại, không
  chạy lại LLM. Worker chết trước khi commit bàn giao vẫn bị timeout như cũ.
- Khi API tạm dừng, completion đã commit được giữ lại; request vẫn `running`
  đến khi API tiếp nhận. Kết quả bàn giao đúng hạn không bị dispatcher đổi
  thành timeout chỉ vì API xử lý muộn. Bearer đã xóa từ lúc bàn giao.

Listener dùng một connection PostgreSQL riêng, autocommit và đóng khi API
shutdown; cần kết nối trực tiếp hoặc session pooling, không dùng transaction
pooling cho `LISTEN`. Các query/transaction tiếp nhận dùng connection pool
hiện có. Chạy Alembic tới migration `0002` trước khi khởi động phiên bản mới;
phối hợp cập nhật API và worker, không trộn worker cũ ghi terminal trực tiếp
với luồng bàn giao mới.

Đây là thông báo nội bộ cùng AI Service, không phải Kafka domain event hoặc
SSE/WebSocket cho frontend. POST vẫn chờ persistence tối đa 10 giây và GET
vẫn đọc bản ghi cuối theo ownership. Không thay đổi schema/URL public v1.
Xem [ERD](erd.md) và [code map](code-map.md).

### Thiết kế mục tiêu

Đường chạy trên triển khai pipeline ADR-002. Phần **Chưa xác minh** là token
production, provider REST Work, quota/evaluation LLM và tích hợp gateway.
Kafka projection/event kết quả, specialist, SSE/WebSocket **Chưa triển khai**;
retention terminal đã có lịch beat. Xem [retention](erd.md#retention-terminal).

### Request semantics

Wire contract giữ URL, ba intent và bốn trạng thái v1. `output_schema_version`
nhận version đúng intent hoặc `current`, được chuẩn hóa thành version cụ thể.
Output được kiểm tra theo schema của intent, không chấp nhận result thuộc
intent khác chỉ vì cùng union `AiResult`. Lỗi nội bộ được ánh xạ vào enum lỗi
v1; `error.details.reason` cho biết lỗi context, queue, broker hoặc budget.

Idempotency có phạm vi user/key/payload. POST lặp kiểm tra quyền hiện hành rồi
trả kết quả đã lưu hoặc lỗi đã lưu. GET khác owner và ID không tồn tại cùng
trả `404`. GET không áp dụng proposal hoặc xác nhận quyền nghiệp vụ thay Work.

### Job nền và cách trả kết quả

POST chờ persistence tối đa 10 giây. Nếu chưa kết thúc, trả queued envelope
`202` với `Location`; GET có thể đã thấy `running`. Hết thời gian chờ POST
không hủy worker. Workflow có deadline tối đa 30 giây, bao gồm xác minh lại
quyền, context, retry và revise. Thời gian queue riêng, mặc định 300 giây.

| Thành phần | Trách nhiệm |
| --- | --- |
| API | Xác thực, nhận request, chờ/đọc trạng thái cho client |
| PostgreSQL của AI | Request/input/result, idempotency, delivery lease, budget, completion inbox, dead-letter |
| Dispatcher | Giao lại delivery và kết thúc queue/worker quá hạn |
| Redis | Broker Celery, không là nguồn result/trạng thái |
| Celery worker | Chạy application/workflow, bàn giao completion và phát NOTIFY |
| Listener trong API | Nhận NOTIFY/phục hồi inbox, gọi application cập nhật trạng thái/kết quả cuối |
| ADK workflow / agent | Validation/retry có giới hạn và suy luận/chọn domain tool |

### Retry, phục hồi và dead-letter

- Giao broker lỗi dùng backoff/jitter; giới hạn bởi số lần giao và queue TTL.
- Provider HTTP 429/5xx được retry trong số vòng và budget chung. Input/quyền
  sai không được retry như lỗi mạng; output sai được revise hữu hạn.
- Worker chết: request `running` được kết thúc `failed` khi deadline hết bởi
  dispatcher. MVP không tiếp tục một phiên suy luận đã mất; không cấp lại
  budget hoặc tự chạy lại LLM. Task trùng chỉ đọc trạng thái rồi bỏ qua.
- Dead-letter giữ request ID, mã lỗi và thời điểm; không có credential/raw
  provider output. Replay tự động chưa có; request failed được giữ cho polling.
- Kafka publisher chưa có. Khi thêm event kết quả, transaction result/outbox
  và retry publisher phải độc lập với thực thi model.

## Context flow

### Chính sách context hiện tại và mở rộng

**Quyết định cho MVP:** mỗi lần thực thi request cần context, AI lấy dữ liệu
qua domain tool → `ContextGateway` → REST adapter của service sở hữu rồi xử
lý trong bộ nhớ worker. Không lưu nội dung context lấy từ Work/Integration
vào PostgreSQL, MongoDB hoặc Redis; không xây cache dùng chung giữa request
hay projection trong giai đoạn này. Context chỉ tồn tại trong lần thực thi;
request mới cần context thì lấy lại qua adapter. Request idempotent đã kết
thúc vẫn trả kết quả đã lưu theo quy tắc pipeline, không chạy lại AI.

**Đã triển khai trong source:** `ContextToolPool.documents` giữ context trong
bộ nhớ của từng lần chạy; PostgreSQL vẫn lưu request/input, trạng thái,
result/error và metadata context gồm nguồn, thời điểm, phiên bản nếu có,
fingerprint. Metadata không chứa nội dung context và không đủ để dựng lại
snapshot. Redis hiện chỉ là broker Celery. Context cache, snapshot bền vững
và projection **Chưa triển khai**; tích hợp REST thực tế với domain service
**Chưa xác minh**. Xem [code map](code-map.md) và [ERD](erd.md).

Context là dữ liệu nghiệp vụ được chọn cho ý định và target của request,
trong phạm vi quyền của người yêu cầu. Ví dụ: mục tiêu/backlog của project,
mô tả/dependency/subtask của task hoặc tiến độ/workload của sprint. Đây không
phải bản sao toàn bộ database Work hay lịch sử hội thoại của agent.

**Phân công theo thiết kế mục tiêu:** Work kiểm tra quyền, truy vấn quan hệ
nghiệp vụ và tính các chỉ số như tiến độ, task quá hạn, workload bằng quy
tắc rõ ràng. AI Context Layer kiểm tra schema/độ mới, lọc, giới hạn và ghép
dữ liệu cần thiết từ các adapter trước khi đưa cho mô hình. Mô hình phân tích
và đề xuất, không tính lại giá trị nguồn thay Work. Contract REST của Work
phải được công bố trước tích hợp; các ví dụ trên không định nghĩa endpoint
hoặc schema mới.

**Thiết kế mục tiêu khi cần tối ưu:** giữ cách lấy context sau
`ContextGateway`; domain tools và workflow không phụ thuộc Redis, SQL hoặc
Kafka. Khi bổ sung cache/projection, mở rộng adapter/Context Layer và giữ
contract domain tool nếu dữ liệu trả về vẫn tương thích. Không thêm cơ chế
lưu chỉ vì dự đoán sẽ cần hoặc vì context có dạng JSON.

| Nhu cầu đã xác định | Hướng mở rộng |
| --- | --- |
| Nhiều request lấy lặp cùng context từ Work | Redis cache có TTL (thời hạn sống), có thể lấy lại từ service sở hữu khi thiếu/cũ |
| Cần truy vết chính xác dữ liệu AI đã dùng | Snapshot (bản chụp context đã lọc) trong PostgreSQL riêng của AI, gắn với request và có thời hạn lưu |
| Cần bản sao phục vụ phân tích thường xuyên | Projection (bản sao dữ liệu đọc) trong PostgreSQL riêng của AI, đồng bộ qua event đã có contract |
| Work truy vấn hoặc tính chỉ số chậm | Tối ưu tại Work trước khi quyết định tạo bản sao ở AI |
| Lời gọi mô hình chậm do context lớn | Giảm và tổng hợp context trước khi gửi mô hình |

Trước khi triển khai mở rộng, đo riêng thời gian lấy context, thời gian xử lý
LLM, kích thước context và mức gọi lặp. Lưu DB không tự làm AI nhanh hơn;
snapshot phục vụ truy vết, không mặc nhiên là cache cho request mới. Không
thêm MongoDB chỉ để lưu JSON; việc thêm công nghệ cần quyết định kiến trúc.

Khi thêm cache/projection, phải xác định key theo domain, target, bộ lọc và
phạm vi quyền; giữ metadata nguồn/thời điểm/phiên bản, ngưỡng dữ liệu cũ,
cách hết hạn hoặc vô hiệu hóa cache và cách lấy lại dữ liệu. Kiểm tra quyền
hiện hành trước khi dùng bản sao, không dùng cache/projection làm bằng chứng
phân quyền. Work vẫn là nguồn dữ liệu chuẩn. Projection cần quy tắc đồng bộ,
chống lặp và xử lý phiên bản; snapshot cần policy retention (thời hạn lưu).
Kiểm thử mở rộng phải bao phủ lấy được context, cache thiếu/cũ, quyền bị thu
hồi, lỗi service nguồn và ranh giới giữa các phạm vi quyền.

### Implementation hiện tại

**Mock development/test:** MOCK_TEST=true chọn FixtureContextAdapter tại
composition root API và worker, đọc dữ liệu/quyền domain từ fixture trong
package. Không gọi microservice hoặc mở server mock riêng. MOCK_TEST=false
chọn REST adapter như mô tả dưới đây. JWT, queue, ADK/LLM, validation,
completion và polling giữ cùng luồng; fixture không là dữ liệu production.
Xem [cách dùng mock data](mock-data.md).

`ContextToolPool` gắn với target của request đã xác thực. Tool không nhận URL,
credential hoặc ID tùy ý từ agent: `get_task_context`, `get_project_context`,
`get_team_context`, `get_progress_context`, `get_development_context`.

REST adapter dùng URL template từ cấu hình; Work authorize là POST
`{action: ai.analyze, intent}` với Bearer actor và `X-Service-Key` riêng cho
Work. Chỉ envelope `success: true`, `data` đúng target/action và `allowed: true`
mới cấp quyền. Work context là GET `ContextDocument` trực tiếp, không bọc envelope.
Adapter không theo redirect, có timeout và chặn response lớn hơn 65536 byte.
GitHub GET gửi key Integration; Integration chịu trách nhiệm hỏi Work quyền
`github.read`, AI không kiểm tra Work thêm trong nhánh fetch GitHub.
Adapter kiểm tra domain/thời điểm,
từ chối context thiếu/cũ/sai schema; lọc allowlist trường và giới hạn độ sâu,
số phần tử và độ dài trước khi đưa cho agent. Metadata lưu nguồn/status,
thời điểm và fingerprint của context đã lọc. Workflow kiểm tra context thiết
yếu trước khi chấp nhận proposal: backlog có target cần project context,
task decomposition cần task context, risk cần progress context. Chỉ gọi team
hoặc development tool không thay thế dữ liệu thiết yếu. Agent vẫn tự chọn thứ
tự lấy context và tool bổ sung.

**Một phần:** adapter và unit test đã có; Work boundary đã chốt trong
[contract](../../contracts/api/work-ai-context-v1.yaml), provider Work
**Chưa triển khai**. Integration provider đã có source; integration live
**Chưa xác minh**. Shape dữ liệu lồng nhau được kiểm tra theo domain; trường
ngoài allowlist Work bị loại, không đưa tên/email/credential vào prompt.
Tool GitHub chỉ xuất hiện khi risk Project, cờ bật và focus cho phép; Sprint
không fetch GitHub và runtime tự thêm limitation, không dựa vào prompt.
Xem [boundary chi tiết](production-readiness.md#boundary-domain-và-quyền).
Risk thiếu/cũ context kết thúc failed, không dùng
context rỗng như dữ liệu đầy đủ. Backlog nháp có thể thành công không context.

### Thiết kế theo baseline

Work cung cấp task/project/team/progress trong quyền sở hữu của mình;
Integration cung cấp development context đã chuẩn hóa. Projection qua Kafka
chỉ thêm khi cần; consumer xác định chạy ngoài agent loop, chống lặp và kiểm
tra schema/version. Không dùng Kafka hỏi–đáp để lấy quyền/context.

## Dependency direction

```text
API / Celery task → Application → executor protocol → ADK Workflow → LlmAgent
                                                                → domain tools
                                                                → context gateway
Infrastructure triển khai các protocol; main/task lắp ghép adapter cụ thể.
```

Application không import HTTP, SQLAlchemy, ADK hoặc infrastructure. Workflow
không import adapter concrete/API; context tools chỉ biết gateway protocol.
`models/` giữ schema, `infrastructure/` giữ JWT/HTTP/provider/persistence;
`jobs/` là entry point. [Architecture test](../../apps/ai-service/tests/test_architecture.py)
kiểm tra hướng import; [code map](code-map.md) giữ vị trí file.

## Failure isolation

Lỗi auth/context/provider/broker/worker có trạng thái và error envelope rõ
ràng. Output sai không được lưu thành succeeded. Deadline và budget chống
loop/retry vô hạn; không log secret/raw provider response. Work vẫn tính tiến
độ và cung cấp nghiệp vụ khi AI lỗi.

## Contract và khoảng trống triển khai

- OpenAPI v1 sửa cách ghép `allOf` với `unevaluatedProperties`; giữ các trường
  v1, không phát minh schema event. Test kiểm tra payload bằng JSON Schema.
- Auth source production và provider quyền/context Work cần được xác minh;
  credential key phải giống giữa API/worker và được quản lý ngoài source.
- Nginx root giữ nguyên `/api/ai/v1/...`; internal Identity/Work/Integration
  bị chặn ở gateway. Cấu hình và test không chứng minh E2E staging đã chạy.
- Compose root local/staging có bốn process AI, dùng database AI riêng trên
  PostgreSQL chung; Compose standalone vẫn riêng network/volume. Xem
  [README](README.md) và [gate phát hành](production-readiness.md).
- Event context v1 cũ có producer Project/Progress; không dùng nguyên trạng
  với Work. Không tạo Progress Service riêng hoặc Kafka runtime không có contract.
