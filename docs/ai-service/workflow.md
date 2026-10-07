# UTask AI Service Workflow

**Trạng thái: Thiết kế mục tiêu; ADK, agent, tool và worker chưa triển khai.**

Tài liệu này là nguồn mô tả workflow bounded agent của AI Service. API v1 chỉ
đặc tả `backlog_generation`, `task_decomposition` và `risk_analysis`.
Các intent khác thuộc giai đoạn sau. Kafka, database, cache và provider trong
tài liệu là chi tiết thiết kế, không phải bằng chứng runtime đã tồn tại.

## 1. Mục tiêu

AI Service của UTask được thiết kế theo mô hình **bounded agent**:

- Agent có quyền tự suy luận.
- Agent tự quyết định cần lấy loại context nào.
- Agent tự chọn tool phù hợp từ Context Tool Pool.
- Agent có thể gọi thêm specialist agent khi use case thực sự cần.
- Agent có thể tự đánh giá và sửa kết quả trong giới hạn cho phép.
- Agent **không được trực tiếp thay đổi dữ liệu nghiệp vụ**.
- Agent **không biết Kafka tồn tại**.

Nguyên tắc cốt lõi:

> Developer quyết định biên giới. Agent quyết định đường đi bên trong biên giới đó.

---

## 2. Kiến trúc tổng thể

Thiết kế theo [baseline](../architecture/README.md), mục 4.6, 9–11 và 18.
Các layer dưới đây là thiết kế, chưa phải ADK/Celery/context runtime.

```text
AI API / task entry point
    → Application → ADK Workflow → LlmAgent → proposal
                                      │
                                Context Tool Pool
                                      │
                                Context Layer/adapters
                                      │
                         internal API của Work/service sở hữu
```

Agent chỉ thấy domain tool; Context Layer kiểm soát quyền, phạm vi dữ liệu,
HTTP timeout và số lời gọi. Adapter provider phục vụ lời gọi LLM riêng.
Projection/cache qua Kafka có thể bổ sung khi có nhu cầu, không bắt buộc là
nguồn context duy nhất theo baseline mới.

Pipeline đã chọn lưu request và ý định giao job trước khi dispatcher gửi
Celery task qua Redis. Worker thuộc AI gọi Application/Workflow rồi lưu kết
quả vào persistence chung của AI để API trả cho client. Consumer Kafka chạy
ngoài agent loop; khi có use case/contract, consumer cập nhật projection hoặc
tạo job qua cùng application/dispatcher. Xem nguồn chi tiết tại
[pipeline AI](architecture.md) và [ADR-002](../adr/002-ai-request-pipeline.md).

API/worker có thể tách process/container, không bắt buộc singleton. MVP dùng
polling và giữ ngưỡng chờ 10 giây của [API v1](api.md); luôn trả `202` hoặc
SSE/WebSocket cần contract riêng. Các thành phần này **chưa triển khai**.

---

## 3. Workflow và LlmAgent

### 3.1. LlmAgent

`LlmAgent` là thành phần dùng LLM để tự suy luận và quyết định hành động.

Developer cung cấp:

- instruction;
- model;
- tool được phép sử dụng;
- output schema;
- giới hạn thực thi.

Agent tự quyết định:

- cần context nào;
- tool nào cần gọi;
- thứ tự gọi tool;
- có cần thêm context không;
- có cần gọi specialist agent không;
- khi nào đã đủ thông tin;
- kết quả cuối cùng là gì.

Ví dụ:

```text
Goal: "Phân rã task 42"

Agent
  |
  |-- get_task_context(42)
  |
  |-- reasoning
  |
  |-- get_project_context(project_id)
  |
  |-- reasoning
  |
  |-- không cần workload
  |
  `-- structured result
```

Đây là phần tạo nên tính **agentic** của AI Service.

### 3.2. Workflow

Workflow là lớp điều phối cấp cao do developer kiểm soát.

Workflow phù hợp cho các bước cần chắc chắn luôn xảy ra, ví dụ:

```text
START
  |
  v
Validate Request
  |
  v
Run Domain Agent
  |
  v
Validate Structured Output
  |
  +---- invalid ----> retry/revise trong giới hạn
  |
  v
Persist Result
  |
  v
END
```

Workflow không thay thế agent.

Workflow kiểm soát **macro-flow**.  
LlmAgent tự quyết định **micro-flow**.

### 3.3. Kết hợp Workflow + LlmAgent

Kiến trúc UTask sử dụng cả hai:

```text
Developer
   |
   | định nghĩa macro-flow
   v
Workflow
   |
   v
LlmAgent
   |
   | tự reasoning
   | tự chọn context tool
   v
Context Tool Pool
```

UTask không nên dùng workflow để định nghĩa cứng từng context mà agent phải lấy.

Không nên:

```text
get_task
  ->
get_project
  ->
get_team
  ->
get_progress
  ->
LLM
```

Nên:

```text
Workflow
  |
  v
TaskDecompositionAgent
  |
  +-- get_task_context
  +-- get_project_context
  +-- get_team_context
  +-- get_progress_context
  `-- get_github_context

Agent tự quyết định tool nào thực sự cần.
```

---

## 4. Context Tool Pool

Context Tool Pool là giao diện duy nhất mà agent dùng để lấy dữ liệu nghiệp vụ.

Ví dụ:

```text
get_task_context()
get_project_context()
get_team_context()
get_progress_context()
get_development_context()
```

Agent không biết:

- dữ liệu đến từ internal API hay projection Kafka;
- database nào đang được dùng;
- cache nào đang được dùng;
- topic nào đang tồn tại;
- consumer group nào đang xử lý event.

Nguyên tắc:

> Agent quyết định **WHAT** context cần lấy.  
> Hệ thống quyết định **HOW** context được lấy.

### 4.1. Tool nên ở mức domain

Không nên tạo quá nhiều tool rất nhỏ:

```text
get_task_title()
get_task_description()
get_task_deadline()
get_task_assignee()
get_task_comments()
```

Nên gom thành tool cấp nghiệp vụ:

```text
get_task_context()
get_project_context()
get_team_context()
get_progress_context()
get_development_context()
```

Cách này giảm:

- số lần tool call;
- số vòng LLM -> tool -> LLM;
- token;
- latency;
- độ phức tạp của agent.

### 4.2. Tool chỉ trả dữ liệu cần thiết

Không nên trả toàn bộ dữ liệu thô.

Không nên:

```text
500 tasks
3000 commits
5000 comments
```

Nên để Context Layer lọc và tổng hợp trước:

```json
{
  "task_summary": {
    "todo": 12,
    "doing": 5,
    "blocked": 2
  },
  "relevant_tasks": [],
  "progress": {},
  "recent_development_activity": {}
}
```

SQL/Python xử lý phần deterministic.  
LLM chỉ làm phần reasoning cần thiết.

---

## 5. Kafka

### 5.1. Agent không truy cập Kafka trực tiếp

Không expose cho agent các tool như:

```text
consume_topic()
read_kafka()
publish_kafka()
commit_offset()
```

Agent không nên quyết định:

- topic nào cần consume;
- offset;
- retry;
- replay;
- consumer group;
- schema version;
- event ordering.

Đây là trách nhiệm infrastructure.

### 5.2. Kafka truyền sự kiện giữa service

Baseline dùng Kafka cho Work → AI, Integration → Work/AI và AI → Notification
khi có event contract. AI lấy Project/Task context qua internal API; Kafka có
thể kích hoạt phân tích tự động hoặc cập nhật projection khi use case cần.

```text
Domain service → transaction + outbox → publisher → Kafka
    → AI consumer: validate schema/version + chống lặp
        ├── cập nhật projection (nếu được chọn)
        └── Application: lưu job + ý định giao job
            → dispatcher → Redis → Celery worker → Application/Workflow
```

Consumer cập nhật context ngoài agent loop; agent không quyết định topic,
offset hoặc replay. Không bắt LlmAgent consume/publish Kafka.
Consumer không dùng Kafka để hỏi quyền hoặc lấy context đồng bộ. Khi tạo job,
consumer phải bàn giao bền vững và chống trùng trước khi xác nhận xử lý event;
retry/dead-letter không được làm mất job hoặc chạy AI ngoài budget. Chi tiết
nằm trong [job nền](../infrastructure/background-jobs.md) và
[Kafka/outbox](../infrastructure/kafka.md).

Sau khi lưu kết quả, AI có thể phát event theo baseline cho Notification.
`ai.analysis.completed`/`ai.project.risk.detected` chưa có schema/topic được
chốt; API v1 hiện chưa phát event kết quả. Cần contract/version trước runtime,
không coi đây là response HTTP cho client.
Khi có contract, application lưu kết quả và outbox trong cùng transaction;
publisher retry việc phát event độc lập, không gọi lại workflow. API đọc
persistence của AI, không chờ event hoàn tất để cập nhật database.

`ai-context-v1.yaml` là contract projection cũ có Project/Progress producer;
cần mapping/version nếu dùng với Work. Xem [danh mục event](../system/kafka-events.md).

### 5.3. Không dùng Kafka như request-response thông thường

Không nên:

```text
Agent
  |
  v
Context Tool
  |
  v
Kafka request
  |
  v
Other Service
  |
  v
Kafka response
  |
  v
Agent
```

Cách này tạo thêm:

- correlation ID;
- reply topic;
- timeout;
- retry;
- duplicate handling;
- latency;
- lifecycle phức tạp.

Context được lấy qua internal API sau adapter hoặc projection đã đồng bộ;
không dựng cơ chế hỏi–đáp Kafka cho mỗi lần agent cần dữ liệu.

---

## 6. Bounded Autonomy

Agent được phép:

```text
- reasoning
- chọn context tool
- gọi tool theo thứ tự tự quyết định
- yêu cầu thêm context
- bỏ qua context không cần thiết
- gọi specialist agent
- tự đánh giá kết quả
- retry/revise trong giới hạn
- tạo proposal
```

Agent không được phép:

```text
- consume Kafka trực tiếp
- gọi database của service khác
- gọi REST tùy ý ngoài domain tool/adapter được kiểm soát
- ghi trực tiếp Work DB
- assign member
- thay đổi sprint
- sửa task
- bypass authorization
```

Tính tự chủ nằm ở **reasoning**, không nằm ở quyền thay đổi hệ thống.

---

## 7. Side Effect và xác nhận người dùng

AI chỉ tạo proposal.

Ví dụ:

```json
{
  "action": "assign_task",
  "task_id": 42,
  "member_id": 7,
  "reason": "..."
}
```

Luồng thực thi:

```text
Agent Proposal
      |
      v
User confirms
      |
      v
Domain Service
      |
      +-- authorization
      +-- business validation
      |
      v
Apply change
      |
      v
Database
      |
      v
Domain event -> Kafka
```

Agent không được trực tiếp thực thi thay đổi nghiệp vụ.

---

## 8. Multi-agent

Không nên dùng multi-agent cho mọi request.

Task đơn giản:

```text
TaskDecompositionAgent
        |
        v
Context Tool Pool
```

Use case lớn hơn mới cần specialist agent:

```text
ProjectAdvisorAgent
        |
        +-- WorkloadAgent
        +-- RiskAgent
        `-- ProgressAgent
```

Nên ưu tiên mô hình **agent-as-tool**:

```text
ProjectAdvisorAgent
        |
        +-- analyze_workload()
        |       |
        |       `-- WorkloadAgent
        |
        +-- analyze_risk()
        |       |
        |       `-- RiskAgent
        |
        `-- tổng hợp kết quả cuối
```

Manager giữ trách nhiệm tạo final recommendation.

---

## 9. Agent Budget

Mỗi agent phải có giới hạn.

Ví dụ:

```text
max model calls      = 4
max context tools    = 5
max specialist calls = 1
max output tokens    = giới hạn theo use case
timeout              = cấu hình phù hợp
```

Không cho agent loop vô hạn.
Workflow có hard timeout 30 giây theo API v1, bao gồm revise/retry thực thi;
retry task hoặc giao lại job không tự đặt lại budget đã dùng. Phân biệt retry
lời gọi model, revise output và retry giao thông điệp; phối hợp các lớp để
không nhân số lần gọi LLM. Quy tắc phục hồi và dead-letter nằm trong
[kiến trúc AI](architecture.md).

---

## 10. Structured Output

Agent phải trả structured output thay vì văn bản tự do nếu kết quả được backend sử dụng.

Ví dụ:

```json
{
  "analysis": {
    "complexity": "medium",
    "reason": "..."
  },
  "subtasks": [
    {
      "title": "Create login API",
      "description": "...",
      "estimate_hours": 4,
      "dependencies": []
    }
  ],
  "warnings": [],
  "context": {
    "version": 142,
    "updated_at": "..."
  }
}
```

Luồng:

```text
Agent
  |
  v
Structured Output
  |
  v
Schema Validation
  |
  +---- invalid ----> revise trong giới hạn
  |
  v
Return
```

---

## 11. Framework được chọn

### Lựa chọn chính: Google ADK 2.0

UTask chọn Google ADK 2.0 vì kiến trúc cuối cùng là hybrid:

```text
Developer-controlled Workflow
            +
Autonomous LlmAgent
            +
Context Tool Pool
```

ADK phù hợp vì hỗ trợ rõ hai tầng:

```text
Workflow
   |
   v
LlmAgent
   |
   v
Tools
```

Developer kiểm soát macro-flow.

LlmAgent tự quyết định micro-flow và context cần lấy.

### Khi nào OpenAI Agents SDK phù hợp hơn?

OpenAI Agents SDK rất phù hợp nếu kiến trúc chỉ cần:

```text
Agent
  |
  +-- tool
  +-- tool
  `-- agent-as-tool
```

và muốn một agent loop đơn giản với ít abstraction.

Nếu UTask bỏ phần workflow cấp cao và chủ yếu dùng một hoặc vài autonomous agent, OpenAI Agents SDK là một lựa chọn rất mạnh.

### Kết luận framework

Với kiến trúc UTask đã chốt:

```text
Workflow
  ->
LlmAgent
  ->
Context Tool Pool
  ->
Context Layer
```

**Google ADK 2.0 là lựa chọn phù hợp hơn.**

---

## 12. Model Strategy

Framework và model không nên bị khóa cứng với nhau.

Kiến trúc:

```text
Google ADK
    |
    v
Model Provider / Router
    |
    +-- cost-efficient model
    |
    +-- stronger model
    |
    `-- fallback model
```

Nguyên tắc:

- model rẻ và nhanh làm mặc định;
- model mạnh hơn chỉ dùng cho request khó;
- không dùng model frontier đắt tiền cho mọi request;
- model phải có thể thay đổi mà không ảnh hưởng business logic.

Ví dụ:

```text
Simple request
      |
      v
Cost-efficient model
      |
      v
Result

Complex request
      |
      v
Stronger model
      |
      v
Result
```

Model cụ thể nên được benchmark lại tại thời điểm triển khai.

---

## 13. Tối ưu chi phí khi có khoảng 1.000 users

Chi phí lớn nhất có khả năng đến từ AI inference, không phải số lượng microservice.

Ưu tiên tối ưu:

1. Giảm context/token đưa vào model.
2. Giảm số vòng `LLM -> tool -> LLM`.
3. Dùng model rẻ làm mặc định.
4. Escalate sang model mạnh chỉ khi cần.
5. Không dùng multi-agent cho request đơn giản.
6. SQL/Python thực hiện calculation deterministic.
7. Giới hạn agent loop.
8. Dùng context/session compaction.
9. Cache dữ liệu phù hợp.
10. Dùng chung hạ tầng ở quy mô nhỏ thay vì mỗi service một server riêng.

### Shared infrastructure

Ở quy mô khoảng 1.000 users có thể dùng:

```text
PostgreSQL cluster/server
├── identity_db
├── classroom_db
├── work_db
├── integration_db
├── notification_db
└── ai_context_db (tên thiết kế AI, chưa có trong Compose)

Redis instance/cluster
└── namespace theo service

Kafka cluster
└── topic theo domain/event
```

Shared infrastructure không làm mất data ownership của từng microservice.

---

## 14. Kiến trúc mục tiêu

```text
AI API / Celery task
    → Application → ADK Workflow → LlmAgent → validated proposal
                                      │
                                Context Tool Pool
                                      │
                                Context Layer/adapters
                                      │
                    internal API của Work / service sở hữu
                    projection/cache nội bộ khi được chọn

Kafka consumer / publisher chạy ngoài vòng suy luận.
Job nội bộ: lưu request + ý định giao job → dispatcher → Redis → Celery worker AI.
Trạng thái/kết quả: persistence AI → API → client.
```

Sơ đồ này là hướng phụ thuộc logic trong lúc thực thi. Pipeline nhận request,
kiểm tra quyền, idempotency, giao job và polling có nguồn chuẩn tại
[kiến trúc AI](architecture.md); không chạy trực tiếp workflow dài trong HTTP
handler của thiết kế mục tiêu.

Side-effect flow:

```text
Agent
  |
  v
Structured Proposal
  |
  v
User Confirmation
  |
  v
Domain Service
  |
  +-- authorization
  +-- business validation
  |
  v
Apply Change
  |
  v
Publish Domain Event
```

---

## 15. Nguyên tắc kiến trúc cần giữ

1. **Agent không biết Kafka.**
2. **Agent chỉ truy cập context thông qua Context Tool Pool.**
3. **Agent quyết định context cần lấy, hệ thống quyết định cách lấy.**
4. **Workflow kiểm soát macro-flow, LlmAgent kiểm soát micro-flow.**
5. **AI chỉ đưa proposal, domain service mới có quyền thay đổi dữ liệu.**
6. **Không dùng multi-agent nếu một agent có thể giải quyết tốt.**
7. **Không dùng LLM cho logic deterministic mà SQL/Python xử lý tốt hơn.**
8. **Framework và model phải tách rời.**
9. **Luôn có budget cho model call, tool call và retry.**
10. **Structured output và validation là bắt buộc với kết quả dùng bởi backend.**

---

## 16. Tóm tắt một câu

> UTask AI Service sử dụng Google ADK 2.0 theo mô hình bounded agent: Workflow kiểm soát luồng lớn, LlmAgent tự reasoning và tự chọn context từ Context Tool Pool; Kafka và dữ liệu nằm hoàn toàn phía sau Context Layer, còn mọi thay đổi nghiệp vụ chỉ được thực hiện bởi domain service sau khi người dùng xác nhận.
