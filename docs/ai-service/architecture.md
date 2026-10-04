# Kiến trúc AI Service

**Trạng thái hiện trạng: Chưa triển khai / Chưa xác minh.** Audit ngày
2026-10-04 không tìm thấy source code, test, package manifest, Dockerfile,
consumer Kafka, context store, agent/workflow hoặc provider adapter trong
`apps/ai-service/`. Nội dung “thiết kế mục tiêu” bên dưới được tách rõ khỏi
bằng chứng implementation.

## Bằng chứng đã kiểm tra

- `apps/ai-service/` chưa có source implementation; hiện chỉ có instruction và
  plan phục vụ công việc phát triển.
- `docs/ai-service/README.md` trước audit chỉ mô tả thiết kế mục tiêu.
- Root Compose build `./apps/ai-service`, nạp `infra/env/ai-service.env`, mount
  dataset read-only và kiểm tra `GET /healthz`; đây là cấu hình hạ tầng, không
  chứng minh endpoint đã có code.
- Nginx route `/api/ai/` tới `ai-service:8000`.
- CI gọi `uv sync --all-groups --locked`, Ruff, Pytest và Docker build cho
  service; hiện checkout không có project files để chạy các lệnh đó.
- `contracts/events/` chưa có schema máy đọc được cho AI.

## Responsibilities — thiết kế mục tiêu

AI Service giai đoạn 1 là capability hỗ trợ nội bộ cho ba intent:

- `backlog_generation`: tạo backlog nháp từ mô tả project hoặc chức năng;
- `task_decomposition`: phân rã một task phức tạp thành các subtask;
- `risk_analysis`: tổng hợp và giải thích nguy cơ ảnh hưởng Sprint hoặc
  deadline.

API nhận ý định và phạm vi đối tượng cần xử lý. Service có thể lưu yêu cầu/kết
quả và bản sao đọc tối thiểu phục vụ phân tích, nhưng kết quả chỉ là đề xuất.

Kiến trúc workflow giai đoạn 1 là bounded agent dùng Google ADK 2.0. Workflow
kiểm soát macro-flow; `LlmAgent` tự reasoning, tự chọn domain tool trong
Context Tool Pool và tự review trong budget cho phép. Agent không biết Kafka,
database hay cache tồn tại.

Các intent như kiểm tra deadline độc lập, gợi ý priority, tạo mô tả task,
phân bổ lại workload tự động và agent tự thực hiện hành động thuộc giai đoạn
sau, không phải phạm vi API giai đoạn 1.

Nguồn dữ liệu gốc vẫn thuộc service nghiệp vụ tương ứng. Người dùng xác nhận
đề xuất; service sở hữu dữ liệu kiểm tra quyền và thực hiện thay đổi.

## Non-responsibilities — boundary

- Identity Service sở hữu tài khoản, vai trò, xác thực và phiên.
- Classroom Service sở hữu lớp, nhóm và `GroupMember`.
- Project Service sở hữu project, `ProjectMember`, sprint, task và comment.
- Integration Service là service duy nhất gọi GitHub API và sở hữu dữ liệu
  GitHub đã chuẩn hóa.
- Progress Service tính chỉ số bằng công thức/quy tắc; dashboard không phụ
  thuộc AI.
- Web Application là transport/UI client; không gọi LLM hoặc database trực tiếp.
- PostgreSQL, Kafka, Redis, Nginx và Docker Compose là hạ tầng; AI Service
  không được mở rộng boundary thành quyền sở hữu chung.

Không tạo khóa ngoại hoặc đọc database xuyên service. AI không tự ghi ngược dữ
liệu nghiệp vụ và không được là dependency bắt buộc của workflow cốt lõi.

## Request flow

### Implementation hiện tại

**Chưa có flow runtime để xác minh.** Không có API entry point, application
layer, workflow, tool, schema output hay provider call trong source tree.

### Thiết kế mục tiêu

```text
Client
  ↓
AI API / transport
  ↓
Application layer
  ↓
ADK Workflow
  ↓
LlmAgent
  ↓
Context Tool Pool
  ↓
Context Layer / local read model
  ↓
LLM provider / model adapter
  ↓
Validated structured result
```

Sơ đồ là hướng dẫn kiến trúc, không phải bằng chứng các layer đã tồn tại.

### Request semantics — thiết kế mục tiêu

Request AI giai đoạn 1 phải mang đủ thông tin để workflow biết cần làm gì và áp
dụng vào đối tượng nào, nhưng không mang toàn bộ dữ liệu nghiệp vụ. Các thành
phần khái niệm gồm:

- `requester_user_id`: user đã xác thực và gửi request;
- `intent_type`: một trong `backlog_generation`, `task_decomposition` hoặc
  `risk_analysis`;
- `target_scope`: logical reference tới `project_id`, `task_id` hoặc `sprint_id`,
  tùy intent;
- tham số của intent, idempotency key và phiên bản output khi cần.

Danh sách field và giá trị cụ thể vẫn cần chốt trong hợp đồng API; nội dung trên
không phải schema máy đọc được. `project_id`, `task_id` và `user_id` chỉ là
tham chiếu logic, không tạo foreign key xuyên service.

Input tối thiểu theo intent:

- `backlog_generation`: mô tả project/chức năng, mục tiêu, tech stack, deadline
  và các ràng buộc do người dùng cung cấp;
- `task_decomposition`: task cha, mô tả, acceptance criteria và dependency;
- `risk_analysis`: `project_id` hoặc `sprint_id`, cùng khoảng thời gian hoặc
  phạm vi phân tích nếu use case yêu cầu.

Workflow đọc dữ liệu canonical đã đồng bộ trong context nội bộ. Requester được
phép xem đối tượng nào phải được xác định bởi cơ chế xác thực/phân quyền; AI
không được coi bản sao context là bằng chứng quyền truy cập.

Agent chỉ thấy Context Tool Pool. Tool nên ở mức domain như
`get_task_context`, `get_project_context`, `get_team_context`,
`get_progress_context` và `get_development_context`; không expose các tool hạ
tầng như `consume_topic`, `read_kafka` hoặc `query_database`.

Context Tool Pool phải trả dữ liệu đã lọc/tổng hợp ở mức cần thiết cho intent.
SQL/Python xử lý các phép tính deterministic; LLM chỉ reasoning trên context
đã chọn. Agent không tự quyết định topic, offset, consumer group, replay hoặc
schema event.

Kết quả của cả ba intent là bản nháp hoặc đề xuất. Project Service phải kiểm tra
quyền và xử lý bước xác nhận trước khi tạo task/subtask hoặc thay đổi dữ liệu.

Output tối thiểu theo intent:

- `backlog_generation`: loại Work Item, tiêu đề, mô tả, priority, ước lượng,
  dependency và acceptance criteria;
- `task_decomposition`: tiêu đề subtask, kết quả cần đạt và dependency nếu có;
- `risk_analysis`: mức cảnh báo, nguyên nhân, dữ liệu nguồn, thời điểm phân tích
  và đề xuất hành động.

`risk_analysis` phải phân biệt không có dữ liệu, dữ liệu chưa đồng bộ, thành viên
chưa ánh xạ tài khoản GitHub và thành viên không có hoạt động. Các tín hiệu cơ
bản do rule xác định trước; AI chỉ tổng hợp và giải thích, không tự kết luận
năng lực hoặc tự thay đổi dữ liệu.

Quyền gọi `task_decomposition` cần được chốt trước khi tạo API contract: tài liệu
nghiệp vụ có chỗ mô tả Team Member được yêu cầu, nhưng ma trận quyền hiện chỉ
cho Leader quyền này.

Thiết kế mục tiêu v1 dùng REST request-response để trả kết quả có cấu trúc sau
khi workflow hoàn tất. Nếu một request cần chạy lâu, API có thể trả job/status
và cho client truy vấn lại qua REST. Kafka chỉ phục vụ cập nhật context hoặc
phát sự kiện kết quả đã hoàn tất, không phải kênh request-response.

## Context flow

### Implementation hiện tại

**Chưa xác minh.** Không có Kafka consumer, topic binding, transform, context
model, database connection hoặc replay process trong `apps/ai-service/`.

### Thiết kế mục tiêu

```text
Domain Service
  ↓ Kafka event theo contract
AI Service consumer
  ↓ transform/idempotency
Local AI context representation
  ↓
AI workflow
```

Giai đoạn 1 cần tối thiểu context project/task/sprint, tiến độ và hoạt động
GitHub đã được Integration Service chuẩn hóa. `risk_analysis` chỉ sử dụng dữ
liệu GitHub thuộc repository chính của project. Danh mục hệ thống nêu các nhóm
event `project.*`, `sprint.*`, `task.*`, `github.*` và `progress.*`; đây chưa
phải schema đã chốt. Chưa có topic, version, producer/consumer, replay hoặc SLA
nào được xác nhận. Không được tạo schema từ dấu `*`.

Context mục tiêu là bản sao đọc tối thiểu trong `ai_context_db`, không phải
nguồn đúng. Dữ liệu có thể stale; quy trình replay/snapshot và retention còn
cần quyết định. Agent không biết context được cập nhật bằng Kafka; việc đó do
deterministic consumer và Context Layer xử lý.

## Dependency direction

Hướng mong muốn khi implementation xuất hiện:

```text
API / Transport
  ↓
Application
  ↓
ADK Workflow (macro-flow)
  ↓
LlmAgent (micro-flow/reasoning)
  ↓
Context Tool Pool
  ↓
Infrastructure adapters
```

Provider, Kafka, storage và HTTP client (nếu contract cho phép) phải nằm sau
adapter phù hợp. Không để agent gọi trực tiếp các adapter hạ tầng. Chưa có
abstraction nào để reuse; không tạo abstraction chỉ vì sơ đồ này.

## Failure isolation

Thiết kế mục tiêu yêu cầu timeout/provider unavailable/invalid model output làm
giảm khả năng AI hoặc trả lỗi cục bộ, không chặn authentication, classroom,
project/task, integration, progress dashboard hay notification. Kafka unavailable
hoặc context thiếu/stale phải được biểu diễn rõ để workflow không dùng dữ liệu
không hợp lệ.

Hiện chưa có code để xác minh timeout, retry, circuit breaker, dead-letter,
validation hoặc fallback. Mỗi agent/workflow phải có budget giới hạn cho model
call, context tool call, specialist call, output token và tổng thời gian; không
cho agent loop vô hạn. Output dùng bởi backend phải qua schema validation và
retry/revise có giới hạn khi không hợp lệ.

## Discrepancy cần theo dõi

`docker-compose.yml` và `infra/env/ai-service.env` hiện khai báo
`WORK_SERVICE_URL`, `INTEGRATION_SERVICE_URL` và `depends_on` tới hai service.
Trong khi đó, kiến trúc hệ thống yêu cầu AI lấy context qua bản đọc/event và
không gọi REST service khác trong lúc xử lý. Vì AI source chưa có, chưa thể
kết luận runtime có dùng các URL này. Không tự ý sửa root config trong task
setup này; cần quyết định/triển khai contract ngoài scope nếu muốn thay đổi.
Các biến URL và `depends_on` không được xem là quyền cho phép AI gọi trực tiếp
Project/Integration Service. Khi triển khai AI, cần loại bỏ hoặc ghi rõ mục đích
của chúng nếu không có contract REST được phê duyệt.

Workflow mục tiêu chọn Google ADK 2.0. OpenAI hoặc Gemini chỉ là model/provider
được đặt sau adapter/router; chưa có dependency, credential config hoặc adapter
nào được xác minh. Không coi đó là stack hiện tại.
