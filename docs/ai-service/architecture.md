# Kiến trúc AI Service

**Trạng thái hiện trạng: Một phần.** Source bootstrap có FastAPI, healthcheck,
request/result schema, application, provider protocol, timeout và repository
in-memory. Provider thật, ADK, Celery worker, Kafka, internal API adapter và
PostgreSQL persistence **chưa triển khai**. Xem [code map](code-map.md).

Thiết kế bên dưới theo [baseline](../architecture/README.md), mục 4.6, 9–11,
18 và 24; quyết định chuyển từ kiến trúc cũ nằm trong
[ADR-001](../adr/001-adopt-architecture-baseline.md).

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
AI API → Application → ADK Workflow → LlmAgent → structured proposal
                                         │
                                  Context Tool Pool
                                         │
                                  Context Layer/adapters
                                         │
                         internal API của service sở hữu
```

Đây là hướng phụ thuộc logic. LLM provider nằm sau adapter gọi mô hình, không
phải một bước bắt buộc tiếp sau mọi lần lấy context. Workflow validate input,
chạy agent, kiểm tra output, revise/retry có giới hạn và lưu kết quả.

### Request semantics

Request mang intent, target, input, idempotency key và output schema version
theo [API v1](api.md). User lấy từ ngữ cảnh xác thực, không lấy từ body.
ID Project/Task/Sprint/User là tham chiếu logic. Quyền trên target phải được
service sở hữu xác nhận; dữ liệu context hoặc snapshot không tự cấp quyền.

Kết quả là proposal có cấu trúc, không tạo side effect nghiệp vụ. Work thực
hiện tạo task/subtask hoặc thay đổi khác sau xác nhận và kiểm tra quyền.
`risk_analysis` cần phân biệt thiếu/cũ dữ liệu, thiếu mapping GitHub và không
có hoạt động; không suy diễn năng lực người dùng từ dữ liệu thiếu.

### Job nền và cách trả kết quả

Baseline chọn Celery + Redis cho job nội bộ. Nếu triển khai xử lý AI nền:

```text
Application → Redis → Celery worker thuộc AI → Workflow → lưu kết quả AI
Client → AI API → đọc trạng thái/kết quả từ persistence AI
```

API và worker thuộc cùng service, có thể chung package/image và tách process/
container. Không bắt buộc singleton; số worker/concurrency cần giới hạn theo
quota LLM, database và yêu cầu vận hành. Task chỉ gọi application/workflow,
không chứa lặp lại logic nghiệp vụ hay có quyền vượt Context Tool Pool.

Đây là hướng triển khai, chưa có worker source hoặc queue trong Compose.
Cơ chế giao job bền vững, chống lặp, retry và phục hồi worker cần thiết kế/test;
xem [job nền](../infrastructure/background-jobs.md).

Baseline không quy định mọi POST trả `202` ngay. Contract v1 hiện chờ tối đa
10 giây, trả `200` nếu xong hoặc `202` để client GET polling; workflow có
hard timeout 30 giây. SSE/WebSocket hoặc mô hình luôn trả `202` là thay đổi
cần chốt riêng, không tự thêm từ baseline.

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
