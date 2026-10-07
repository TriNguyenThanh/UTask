# Kiến trúc AI Service

**Trạng thái hiện trạng: Một phần.** Source bootstrap có FastAPI, healthcheck,
request/result schema, application, provider protocol, timeout và repository
in-memory. Provider thật, ADK, Celery worker, Kafka, internal API adapter và
PostgreSQL persistence **chưa triển khai**. Xem [code map](code-map.md).

Thiết kế bên dưới theo [baseline](../architecture/README.md), mục 4.6, 9–11,
18 và 24; quyết định chuyển từ kiến trúc cũ nằm trong
[ADR-001](../adr/001-adopt-architecture-baseline.md).
Pipeline API/worker được chốt trong
[ADR-002](../adr/002-ai-request-pipeline.md); phần dưới là nguồn chuẩn cho
luồng xử lý và trách nhiệm từng thành phần, chưa xác nhận runtime đã có.

## Responsibilities — thiết kế mục tiêu

AI Service là capability nội bộ nhận ý định và phạm vi đối tượng, chạy workflow/
agent, validate structured output (kết quả theo schema), lưu và trả proposal.
Baseline định hướng sinh/phân rã task, gợi ý priority/mô tả task, phân tích
workload, tiến độ/rủi ro deadline và gợi ý phân bổ lại công việc.

API v1 hiện chỉ đặc tả `backlog_generation`, `task_decomposition` và
`risk_analysis`. Đây là phạm vi contract AI, không đồng nghĩa với thứ tự
Phase 1–4 của roadmap toàn hệ thống trong baseline. Các khả năng khác cần
contract/version và triển khai riêng, không mở rộng intent chỉ bằng tài liệu.

Giữ bounded agent: ADK Workflow kiểm soát luồng lớn (macro-flow); `LlmAgent`
suy luận và chọn domain tool trong giới hạn. Specialist chỉ thêm khi có bài
toán thật, ưu tiên agent-as-tool. Provider/model đặt sau adapter/router.

## Non-responsibilities — boundary

- Identity sở hữu user, vai trò toàn hệ thống và token; service kiểm tra quyền
  tài nguyên ở backend, không xem header bootstrap là xác thực production.
- Classroom sở hữu lớp, Group/GroupMember; Work sở hữu Project/ProjectMember,
  Sprint, Task, Comment và tiến độ theo quy tắc.
- Integration là service duy nhất gọi GitHub API. AI lấy dữ liệu GitHub đã
  chuẩn hóa qua API/event được công bố.
- AI không đọc database service khác, tạo foreign key xuyên service hoặc tự
  ghi Project/Task. User xác nhận; Work kiểm tra quyền và business rule rồi áp dụng.
- Dashboard và luồng nghiệp vụ chính không phụ thuộc AI/LLM.

## Request flow

### Implementation hiện tại

```text
FastAPI → AiApplicationService → BoundedWorkflow → provider.generate
           └── InMemoryRequestRepository
```

Provider mặc định trả `502 PROVIDER_UNAVAILABLE`; test thành công dùng fake
provider. Timeout hiện là giới hạn một lời gọi provider, chưa phải ADK budget.

**Đã triển khai:** các module nằm trực tiếp dưới `apps/ai-service/src/`, gồm
`main.py`, `config.py`, `errors.py` và các layer `api/`, `application/`,
`workflow/`, `infrastructure/`, `models/`. Application dùng protocol `RequestWorkflow` và
`RequestRepository`; bounded workflow dùng protocol `ModelProvider`. Adapter
provider/repository nằm trong infrastructure và được `main.py` lắp ghép.
Application/workflow không import FastAPI hoặc adapter cụ thể. Vị trí file và
pipeline chi tiết nằm trong [code map](code-map.md).

### Thiết kế mục tiêu

```text
Client POST → AI API / Application
    → xác thực identity, validate input, kiểm tra quyền qua internal REST API
    → kiểm tra Idempotency-Key
    → transaction AI DB: lưu request queued + bản ghi chờ giao job
    → dispatcher → Redis broker → Celery worker thuộc AI Service
    → Application: nhận quyền xử lý job, chống chạy trùng, cập nhật running
    → ADK Workflow → LlmAgent → proposal theo schema → validate output
                       ↕
                 Context Tool Pool → Context Layer/adapters
                       → internal REST API của service sở hữu
    → Application/Repository: lưu succeeded + result hoặc failed + error

Client GET → AI API: kiểm tra ownership → đọc trạng thái/kết quả từ AI DB
```

1. API xác thực user và kiểm tra input. Application dùng adapter internal REST
   để service sở hữu target xác nhận quyền; không phát Kafka event để hỏi quyền.
   Nếu không xác minh được quyền thì không giao job. Backlog nháp không có
   target vẫn phải xác thực user theo contract.
2. Idempotency được xét theo user và key, kèm fingerprint của payload. Request
   lặp hợp lệ dùng lại request ID và trạng thái/kết quả đã lưu, không tạo job mới;
   cùng key nhưng khác payload trả `409`. Persistence phải bảo vệ cả trường hợp
   nhiều POST đồng thời, không chỉ kiểm tra trước khi ghi.
3. Application lưu request `queued` cùng ý định giao job trong một transaction
   PostgreSQL của AI. Dispatcher là thành phần gửi các job đang chờ qua Redis,
   retry việc gửi khi broker lỗi. Chỉ xác nhận đã nhận job sau khi lưu bền vững;
   việc ghi database và gửi Redis không phải một transaction chung.
4. Celery task chỉ là entry point gọi application/workflow. Application phải
   kiểm soát quyền xử lý một job để tránh hai worker chạy trùng, đọc input từ
   persistence và cập nhật `running`. Trước khi lấy context, service sở hữu vẫn
   kiểm tra quyền hiện hành; quyền lúc nhận POST không có hiệu lực vô thời hạn.
5. ADK Workflow kiểm soát các bước bắt buộc, budget, timeout và validation/revise.
   Agent tự chọn domain tool bên trong giới hạn. Context Layer lọc/tổng hợp dữ
   liệu; provider/model nằm sau adapter riêng, không buộc mọi lời gọi LLM phải
   có một bước lấy context mới.
6. Kết quả theo schema được lưu qua application/repository vào AI DB. API và
   worker cùng thuộc AI Service và dùng chung persistence; worker không cần
   callback HTTP hoặc Kafka event về API process để cập nhật database.
7. API đọc persistence để trả kết quả theo [API v1](api.md). Sau `202`, client
   dùng GET mới để polling; không giữ request POST chờ event Kafka.

### Request semantics

Request mang intent, target, input, idempotency key và output schema version
theo [API v1](api.md). User lấy từ ngữ cảnh xác thực, không lấy từ body.
ID Project/Task/Sprint/User là tham chiếu logic. Quyền trên target phải được
service sở hữu xác nhận; dữ liệu context hoặc snapshot không tự cấp quyền.
Kafka event thay đổi quyền có thể làm mất hiệu lực cache khi có contract,
nhưng không thay thế kiểm tra quyền qua service sở hữu trong pipeline này.

Kết quả là proposal có cấu trúc, không tạo side effect nghiệp vụ. Work thực
hiện tạo task/subtask hoặc thay đổi khác sau xác nhận và kiểm tra quyền.
`risk_analysis` cần phân biệt thiếu/cũ dữ liệu, thiếu mapping GitHub và không
có hoạt động; không suy diễn năng lực người dùng từ dữ liệu thiếu.

### Job nền và cách trả kết quả

Thiết kế đã chọn Celery + Redis cho job nội bộ, PostgreSQL của AI cho trạng
thái/kết quả và polling cho MVP. Các thành phần vận hành gồm:

| Thành phần                                      | Trách nhiệm                                                         |
| ----------------------------------------------- | ------------------------------------------------------------------- |
| API process                                     | Nhận POST/GET, gọi application, trả response từ persistence         |
| Celery worker                                   | Nhận task qua Redis và gọi application/workflow xử lý AI            |
| Dispatcher                                      | Giao các job đã lưu bền vững; phục hồi việc gửi khi Redis lỗi       |
| Kafka consumer, khi có use case/contract        | Nhận domain event, chống trùng, cập nhật projection hoặc tạo job    |
| Outbox publisher, khi có contract event kết quả | Phát event sau khi lưu kết quả; retry gửi event độc lập với chạy AI |

API và worker thuộc cùng service, có thể chung package/image và tách process/
container. Không bắt buộc singleton; số worker/concurrency cần giới hạn theo
quota LLM, database và yêu cầu vận hành. Task chỉ gọi application/workflow,
không chứa lặp lại logic nghiệp vụ hay có quyền vượt Context Tool Pool.

Dispatcher/publisher có thể chạy bằng job hoặc process riêng; topology và
concurrency chưa chốt. **Chưa triển khai:** worker, dispatcher, database và
consumer; Redis trong Compose không chứng minh pipeline này đã chạy.

Baseline không quy định mọi POST trả `202` ngay. Contract v1 hiện chờ tối đa
10 giây, trả `200` nếu xong hoặc `202` để client GET polling; workflow có
hard timeout 30 giây. SSE/WebSocket hoặc mô hình luôn trả `202` là thay đổi
cần chốt riêng, không tự thêm từ baseline.

### Retry, phục hồi và dead-letter

- Lỗi provider/context tạm thời có thể retry với backoff tăng dần và jitter
  (độ lệch ngẫu nhiên), giới hạn theo budget. Input sai hoặc bị từ chối quyền
  phải kết thúc; không retry như lỗi mạng.
- Workflow revise output sai schema trong giới hạn. Retry ở workflow và
  Celery phải được phối hợp, không nhân số lần gọi LLM ngoài budget. Hard timeout
  30 giây bao gồm các lần revise/retry thực thi; giao lại job không tự cấp lại
  budget/thời hạn đã dùng. Thời hạn chờ queue và phát hiện job bị kẹt cần chốt
  riêng trong cấu hình vận hành, không suy ra từ ngưỡng POST 10 giây.
- Job giao lại phải an toàn: request đã kết thúc không chạy LLM lần nữa; worker
  cũ không được ghi đè kết quả sau khi job được phục hồi bởi worker khác. Cần
  thiết kế cơ chế nhận quyền xử lý và thu hồi quyền đó khi worker chết.
- Dead-letter là nơi lưu thông điệp không xử lý được để điều tra/replay. Event
  sai schema hoặc hết giới hạn xử lý được cách ly; job AI hết retry phải lưu
  `failed` để client không polling vô hạn. Nơi lưu, retention và thao tác replay
  cần thiết kế trước triển khai; không giả định Redis/Celery tự tạo DLQ.
- Gửi Kafka event kết quả thất bại chỉ retry publisher; không chạy lại LLM.
  Lưu kết quả và outbox trong cùng transaction khi đã có contract event.

Yêu cầu kiểm thử phục hồi nằm trong [job nền](../infrastructure/background-jobs.md).

## Context flow

### Implementation hiện tại

**Chưa triển khai:** chưa có domain tool, HTTP context adapter, projection,
consumer, database connection hoặc cache. Metadata bootstrap dùng nguồn rỗng
và fingerprint `bootstrap-no-context`.

### Thiết kế theo baseline

AI lấy Project/Task context qua internal API của Work. Context Layer bọc
adapter, truyền identity/quyền theo hợp đồng, giới hạn target, timeout, số
lời gọi và kích thước dữ liệu. Agent chỉ chọn domain tool như:

- `get_task_context`, `get_project_context`;
- `get_team_context`, `get_progress_context`;
- `get_development_context`.

Agent không có HTTP tool tùy ý, credential, SQL, Kafka offset hoặc consumer
group. Internal API của Work/Integration/Classroom cần được công bố và kiểm
tra quyền; chưa có endpoint context nào được xác minh. Tool trả dữ liệu đã
lọc/tổng hợp và metadata nguồn/thời điểm/thiếu hoặc cũ dữ liệu.

Projection qua Kafka hoặc snapshot tại AI là tối ưu có thể thêm khi cần.
Nếu dùng event: consumer xác định (deterministic) cập nhật bản sao ngoài agent
loop, kiểm tra schema/version và chống lặp. Không dùng Kafka hỏi–đáp để lấy
context đồng bộ. Xem [ERD](erd.md) và [event contract cũ](../system/kafka-events.md).

## Dependency direction

```text
API / task entry point → Application → ADK Workflow → LlmAgent
                                                        ↓
                                                Context Tool Pool
                                                        ↓
                                                Context Layer/adapters
```

Infrastructure adapter phục vụ HTTP API nội bộ, persistence, cache hoặc
provider; Kafka consumer/outbox publisher chạy ngoài vòng suy luận. Không để
agent điều phối hạ tầng hoặc đưa business rule vào HTTP handler/Celery task.

## Failure isolation

Lỗi context/provider/worker phải trả trạng thái rõ ràng, không tạo proposal
giả. Giới hạn model call, context tool call, specialist call, output token,
retry và thời gian. Không lưu raw provider response hoặc log secret.

AI outage không chặn Work/Classroom/Identity/Integration/Notification; Work
vẫn tính tiến độ. Context thiếu/cũ có thể giảm phạm vi phân tích hoặc làm job
failed theo rule của intent; không âm thầm coi context thiếu là dữ liệu rỗng đúng.

## Contract và khoảng trống triển khai

API v1 và context event v1 được giữ nguyên schema trong lần cập nhật này:

- API v1 có quy tắc gateway-auth; baseline yêu cầu các service xác thực token.
  Cần thống nhất hợp đồng xác thực trước khi triển khai, không tin header client.
- Context event v1 dùng Project/Progress producer và envelope cũ; cần version/
  mapping nếu dùng cùng Work theo baseline. Không áp dụng nguyên trạng để tạo
  Progress Service riêng.
- Baseline nêu `ai.analysis.completed` và `ai.project.risk.detected`; chưa có
  schema/topic/consumer được chốt, API v1 chưa phát event kết quả.
- Nginx rewrite prefix chưa khớp route bootstrap. Env có URL Work/Integration
  nhưng chưa có adapter dùng URL đó; không coi cấu hình là runtime đã tích hợp.
