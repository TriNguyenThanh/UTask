# Kiến trúc AI Service

**Trạng thái: Một phần.** Pipeline API → PostgreSQL → dispatcher → Redis/Celery
→ ADK workflow đã triển khai trong source. JWT, domain tools và adapter REST
đã có; integration với Identity/Work/Integration và LLM production **chưa xác
minh**, cần cấu hình và hợp đồng domain. Kafka, specialist và retention job
**chưa triển khai**, không phải dependency của pipeline MVP.

Thiết kế theo [baseline](../architecture/README.md),
[ADR-001](../adr/001-adopt-architecture-baseline.md) và
[ADR-002](../adr/002-ai-request-pipeline.md). Hiện trạng được đối chiếu với
source/test ngày 2026-10-08. Xem [code map](code-map.md), [API v1](api.md),
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
  → Application lưu succeeded/result hoặc failed/error; xóa credential

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
   Credential không xuất hiện trong task/prompt/log, được xóa ở mọi trạng thái
   cuối. Token hết hạn trong queue làm request thất bại; không giữ quyền cũ.
7. Model/tool budget được trừ trong PostgreSQL trước lời gọi. Output token
   được tính theo usage; lần model tiếp theo chỉ được cấp phần cap còn lại.
   SDK thiếu usage thì trừ toàn bộ cap đã cấp. Retry provider tạm lỗi và revise
   output dùng chung số vòng, budget và deadline; SDK retry ẩn bị tắt.
8. Chỉ worker có execution token hiện hành, request còn `running` và chưa hết
   deadline được ghi kết quả. Dispatcher kết thúc request quá hạn, lưu
   dead-letter và xóa credential; worker đến muộn không ghi đè terminal result.

API/dispatcher/worker là process của cùng AI Service, cùng code và AI DB;
không bắt buộc singleton. ADK session chỉ ở memory trong một job, không phải
request repository. Nguồn schema là [migration](../../apps/ai-service/migrations/versions/0001_request_pipeline.py),
không tạo bảng khi API startup.

### Thiết kế mục tiêu

Đường chạy trên triển khai pipeline ADR-002. Phần **Chưa xác minh** là token
production, contract REST của service sở hữu, quota/evaluation LLM và tích
hợp gateway. Kafka projection/event kết quả, specialist, SSE/WebSocket và
retention tự động là phần mở rộng; chỉ thêm khi có nhu cầu/contract.

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
| PostgreSQL của AI | Request/input/result, idempotency, delivery lease, budget, dead-letter |
| Dispatcher | Giao lại delivery và kết thúc queue/worker quá hạn |
| Redis | Broker Celery, không là nguồn result/trạng thái |
| Celery worker | Entry point gọi application xử lý request |
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

### Implementation hiện tại

`ContextToolPool` gắn với target của request đã xác thực. Tool không nhận URL,
credential hoặc ID tùy ý từ agent: `get_task_context`, `get_project_context`,
`get_team_context`, `get_progress_context`, `get_development_context`.

REST adapter dùng URL template từ cấu hình, kiểm tra lại quyền, không theo
redirect, có timeout và giới hạn byte. Adapter kiểm tra domain/thời điểm,
từ chối context thiếu/cũ/sai schema; lọc allowlist trường và giới hạn độ sâu,
số phần tử và độ dài trước khi đưa cho agent. Metadata lưu nguồn/status,
thời điểm và fingerprint của context đã lọc. Workflow kiểm tra context thiết
yếu trước khi chấp nhận proposal: backlog có target cần project context,
task decomposition cần task context, risk cần progress context. Chỉ gọi team
hoặc development tool không thay thế dữ liệu thiết yếu. Agent vẫn tự chọn thứ
tự lấy context và tool bổ sung.

**Một phần:** adapter và unit test đã có; response domain thực tế chưa công bố.
`ContextDocument` là hợp đồng nội bộ adapter, không tuyên bố Work đã cung cấp
endpoint/schema này. Cần ánh xạ REST domain vào hợp đồng đó trước tích hợp;
xem [cấu hình](README.md). Risk thiếu/cũ context kết thúc failed, không dùng
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
- Auth source production và REST quyền/context cần service sở hữu công bố;
  credential key phải giống giữa API/worker và được quản lý ngoài source.
- Nginx root hiện bỏ `/api/ai/` trước proxy, khác route canonical của app;
  cần cấu hình gateway riêng. Local gọi API trực tiếp, chưa kiểm chứng gateway.
- Compose root chưa thêm DB/worker/dispatcher AI. Service có Compose local
  riêng và hướng dẫn tại [README](README.md); không coi đó là integration
  toàn hệ thống đã chạy.
- Event context v1 cũ có producer Project/Progress; không dùng nguyên trạng
  với Work. Không tạo Progress Service riêng hoặc Kafka runtime không có contract.
