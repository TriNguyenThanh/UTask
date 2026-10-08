# API AI Service — giai đoạn 1

**Trạng thái: Một phần.** API, persistence và pipeline worker đã triển khai;
integration domain/LLM production và gateway **Chưa xác minh**.
Schema máy đọc được nằm tại
[`contracts/api/ai-service-v1.yaml`](../../contracts/api/ai-service-v1.yaml).

Tài liệu này mô tả API mà client dùng để yêu cầu AI xử lý một ý định cụ thể.
API chỉ nhận yêu cầu và trả bản phân tích hoặc proposal có cấu trúc. Theo
[baseline](../architecture/README.md), AI lấy context qua internal API sau
Context Layer/domain tool; projection qua Kafka có thể bổ sung khi cần.
Client không gửi toàn bộ dữ liệu nghiệp vụ; agent không tự gọi HTTP tùy ý,
Kafka hoặc database service khác. Xem [kiến trúc](architecture.md).

## 1. Phạm vi

Giai đoạn 1 chỉ hỗ trợ ba giá trị `intent`:

| Intent               | Mục đích                                                                | Phạm vi đích                                   |
| -------------------- | ----------------------------------------------------------------------- | ---------------------------------------------- |
| `backlog_generation` | Tạo backlog nháp từ mô tả project hoặc một chức năng                    | Project hiện có hoặc bản nháp chưa gắn project |
| `task_decomposition` | Phân rã một task phức tạp thành các subtask                             | Task                                           |
| `risk_analysis`      | Phân tích và giải thích nguy cơ ảnh hưởng tiến độ, Sprint hoặc deadline | Project hoặc Sprint                            |

`deadline_check` độc lập, gợi ý priority, tạo mô tả task, tự phân bổ lại
workload và các hành động tự động thuộc giai đoạn sau. API giai đoạn 1 không
nhận các intent này.

## 2. Boundary và nguyên tắc

```text
Client/Web
   |
   | REST request
   v
AI Service API
   |
   v
Application -> AI DB: request + ý định giao job
   |
   v
Dispatcher -> Redis -> Celery worker -> Application -> ADK Workflow / LlmAgent
                                                               |
                                                               v
                                 Context Tool Pool -> Context Layer / REST adapters

Worker lưu kết quả vào AI DB; API đọc AI DB để trả POST/GET response.
```

- API nhận ý định, phạm vi đối tượng và các chỉ dẫn bổ sung cần thiết.
- `requester_user_id` lấy từ ngữ cảnh xác thực của request, không lấy từ body
  do client tự khai báo. Source xác minh Bearer JWT; cấu hình issuer/key và
  integration Identity production cần kiểm chứng.
- Quyền trên target được service sở hữu xác nhận qua internal REST API trước
  khi giao job. Context adapter tiếp tục kiểm tra quyền khi lấy dữ liệu; không
  dùng Kafka hỏi–đáp hoặc projection để cấp quyền.
- Workflow kiểm tra request, chạy agent, kiểm tra structured output, revise hoặc
  retry trong giới hạn rồi lưu kết quả.
- Agent chỉ được chọn các domain context tool. Agent không biết topic Kafka,
  offset, cache, database hoặc consumer group.
- Kết quả là proposal. AI không tạo task, sửa task, assign member, thay đổi
  Sprint, cập nhật deadline hoặc ghi vào database nghiệp vụ.
- Sau khi user xác nhận, service sở hữu dữ liệu phải tự kiểm tra quyền, kiểm tra
  business rule và áp dụng thay đổi. AI Service không cung cấp endpoint
  `apply` cho các proposal này.

## 3. Base path và quy ước chung

Nginx hiện có route `/api/ai/`. Prefix đã được contract v1 đặc tả là:

```text
/api/ai/v1
```

Source dùng route canonical trên và xác minh JWT. Integration gateway root
chưa xác minh; Nginx hiện rewrite prefix khác route app, cần cấu hình deployment.

Quy ước dữ liệu:

- Request và response dùng `application/json; charset=utf-8`.
- ID được biểu diễn bằng chuỗi UUID; các ID của Project, Task, Sprint và User
  là logical reference, không phải foreign key trong database AI.
- Thời gian dùng RFC 3339 UTC, ví dụ `2026-10-04T09:30:00Z`.
- Mỗi request nên có `X-Request-ID` để trace. Nếu client không gửi, API tạo
  một giá trị mới và trả lại trong response/header.
- Header `Idempotency-Key` là bắt buộc cho `POST`. Cùng một key phải đi kèm
  cùng user và payload; dùng lại key với payload khác phải trả lỗi `409`.
  Request lặp hợp lệ dùng lại request ID và trạng thái/kết quả đã lưu, không
  tạo job mới. Cần bảo vệ request đồng thời bằng persistence và chống xử lý
  trùng ở worker khi task được giao lại.

## 4. Tạo yêu cầu AI

### `POST /api/ai/v1/requests`

Tạo một yêu cầu xử lý cho một trong ba intent giai đoạn 1.

#### Request body chung

```json
{
  "intent": "task_decomposition",
  "target": {
    "type": "task",
    "id": "2b7f4e0a-4a7d-4f69-9f4c-111111111111"
  },
  "input": {
    "acceptance_criteria": [
      "Người dùng có thể đăng nhập bằng email và mật khẩu"
    ],
    "dependencies": ["Identity Service"],
    "additional_instruction": "Ưu tiên chia theo vertical slice"
  },
  "output_schema_version": "task_decomposition.v1"
}
```

| Field                   | Bắt buộc        | Mô tả                                                                                                    |
| ----------------------- | --------------- | -------------------------------------------------------------------------------------------------------- |
| `intent`                | Có              | Một trong ba intent được hỗ trợ ở phase 1.                                                               |
| `target`                | Tùy intent      | Logical reference tới project, task hoặc Sprint. Không gửi target nếu tạo backlog nháp chưa gắn project. |
| `target.type`           | Khi có `target` | `project`, `task` hoặc `sprint`; phải phù hợp với `intent`.                                              |
| `target.id`             | Khi có `target` | ID của đối tượng trong service sở hữu dữ liệu.                                                           |
| `input`                 | Có              | Dữ liệu trực tiếp do user cung cấp; không thay thế context từ service sở hữu hoặc bản sao đã kiểm soát.  |
| `output_schema_version` | Không           | Phiên bản schema client mong muốn; mặc định là phiên bản hiện hành nếu API cho phép bỏ qua.              |
| `Idempotency-Key`       | Có ở header     | Khóa chống tạo cùng một yêu cầu nhiều lần; không đặt trong body.                                         |

`requester_user_id` không xuất hiện trong request body. API lấy user từ JWT
đã xác minh chữ ký, issuer, audience và thời hạn.

### Input theo intent

#### `backlog_generation`

```json
{
  "intent": "backlog_generation",
  "target": {
    "type": "project",
    "id": "3b7f4e0a-4a7d-4f69-9f4c-222222222222"
  },
  "input": {
    "description": "Nền tảng đặt lịch phòng họp cho nhóm trong công ty",
    "goals": ["Đặt và hủy lịch", "Tránh trùng lịch"],
    "tech_stack": ["React", "Django", "PostgreSQL"],
    "deadline": "2026-12-31T00:00:00Z",
    "constraints": ["Phải hỗ trợ phân quyền theo nhóm"]
  }
}
```

`description` là bắt buộc. `goals`, `tech_stack`, `deadline` và `constraints`
là dữ liệu bổ sung; nếu có project đích, agent có thể chọn lấy thêm project
context và task context hiện có.

#### `task_decomposition`

```json
{
  "intent": "task_decomposition",
  "target": {
    "type": "task",
    "id": "2b7f4e0a-4a7d-4f69-9f4c-111111111111"
  },
  "input": {
    "task_description": "Xây dựng API đăng nhập bằng email và mật khẩu",
    "acceptance_criteria": [
      "Sai thông tin đăng nhập trả lỗi phù hợp",
      "Mật khẩu không được lưu dạng rõ"
    ],
    "dependencies": ["Identity Service"]
  }
}
```

`target.type` phải là `task`. Nếu lấy được task qua context adapter hoặc read model, API có
thể chỉ cần `target`; các field trong `input` dùng để bổ sung hoặc làm rõ yêu
cầu, không được dùng để giả mạo quyền truy cập task.

#### `risk_analysis`

```json
{
  "intent": "risk_analysis",
  "target": {
    "type": "sprint",
    "id": "4b7f4e0a-4a7d-4f69-9f4c-333333333333"
  },
  "input": {
    "analysis_window": {
      "from": "2026-10-01T00:00:00Z",
      "to": "2026-10-15T23:59:59Z"
    },
    "focus": ["deadline", "blocked_task", "github_activity"]
  }
}
```

`target.type` phải là `project` hoặc `sprint`. Các tín hiệu tiến độ và rủi ro
được tính theo rule bởi service nguồn; AI chỉ tổng hợp, giải thích và đưa ra
đề xuất. API phải thể hiện rõ khi context thiếu, cũ, chưa đồng bộ hoặc không có
hoạt động, không suy diễn thành kết luận chắc chắn.

## 5. Response

### Thành công đồng bộ — `200 OK`

Khi workflow hoàn tất trong thời gian cho phép, API trả envelope chung:

```json
{
  "request_id": "8b7f4e0a-4a7d-4f69-9f4c-444444444444",
  "intent": "task_decomposition",
  "status": "succeeded",
  "result": {
    "subtasks": [
      {
        "title": "Thiết kế schema request đăng nhập",
        "description": "Xác định field, validation và lỗi đầu vào",
        "acceptance_criteria": ["Schema được kiểm tra trước khi gọi service"],
        "dependencies": [],
        "estimate_points": 2
      }
    ],
    "warnings": []
  },
  "context": {
    "as_of": "2026-10-04T09:20:00Z",
    "sources": [
      {
        "domain": "task",
        "status": "available",
        "as_of": "2026-10-04T09:18:00Z"
      }
    ],
    "fingerprint": "context-fingerprint"
  },
  "output_schema_version": "task_decomposition.v1",
  "created_at": "2026-10-04T09:30:00Z",
  "completed_at": "2026-10-04T09:30:08Z"
}
```

`result` thay đổi theo `intent`, nhưng luôn phải qua schema validation trước khi
trả cho backend hoặc client. `warnings` không được làm mất thông tin về context
stale/missing hoặc giới hạn của phân tích.

### Kết quả theo intent

#### `backlog_generation.v1`

```json
{
  "items": [
    {
      "type": "task",
      "title": "Thiết kế API đặt phòng",
      "description": "...",
      "priority": "medium",
      "estimate_points": 3,
      "dependencies": [],
      "acceptance_criteria": ["..."],
      "rationale": "..."
    }
  ],
  "warnings": []
}
```

#### `task_decomposition.v1`

```json
{
  "subtasks": [
    {
      "title": "...",
      "description": "...",
      "acceptance_criteria": ["..."],
      "dependencies": ["..."],
      "estimate_points": 2
    }
  ],
  "warnings": []
}
```

#### `risk_analysis.v1`

```json
{
  "overall_level": "medium",
  "risks": [
    {
      "code": "deadline_slippage",
      "level": "high",
      "title": "Một số task có nguy cơ trễ Sprint",
      "reason": "...",
      "evidence": [
        {
          "source_type": "progress_metric",
          "source_id": "metric-1",
          "observed_at": "2026-10-04T09:18:00Z"
        }
      ],
      "suggested_actions": ["Ưu tiên review task đang bị block"]
    }
  ],
  "limitations": []
}
```

Các field `priority`, `estimate_points`, `overall_level` và
`suggested_actions` đều là đề xuất. Chúng không tạo ra thay đổi nếu user chưa
xác nhận và service sở hữu dữ liệu chưa áp dụng.

### Xử lý lâu — `202 Accepted`

Nếu request vượt ngưỡng xử lý đồng bộ đã cấu hình, API có thể trả:

```json
{
  "request_id": "8b7f4e0a-4a7d-4f69-9f4c-444444444444",
  "intent": "risk_analysis",
  "status": "queued",
  "status_url": "/api/ai/v1/requests/8b7f4e0a-4a7d-4f69-9f4c-444444444444",
  "created_at": "2026-10-04T09:30:00Z"
}
```

`202` chỉ xác nhận AI Service đã nhận request, không xác nhận kết quả đã có.
Kafka không được dùng để client chờ response; client truy vấn status bằng REST.
Trước khi xác nhận nhận job, request và ý định giao job phải được lưu bền vững
trong cùng transaction của AI DB. Dispatcher có thể giao lại khi Redis lỗi.
API chờ kết quả được worker lưu trong persistence theo ngưỡng 10 giây; hết
ngưỡng chờ không hủy workflow đang chạy. Chi tiết giao job/phục hồi nằm trong
[pipeline AI](architecture.md).

## 6. Xem trạng thái và kết quả

### `GET /api/ai/v1/requests/{request_id}`

Trả về trạng thái của request thuộc user đã xác thực.

| `status`    | Ý nghĩa                                                  |
| ----------- | -------------------------------------------------------- |
| `queued`    | Đã nhận nhưng workflow chưa bắt đầu.                     |
| `running`   | Workflow hoặc agent đang xử lý.                          |
| `succeeded` | Đã có result hợp lệ.                                     |
| `failed`    | Không thể tạo result hợp lệ trong budget/retry cho phép. |

Request ở trạng thái `succeeded` trả cùng envelope và `result` như response
`200` của POST. Request ở trạng thái `queued` hoặc `running` chỉ trả metadata
trạng thái, thời gian cập nhật và context nếu đã có. Request `failed` trả
`error` theo format ở mục kế tiếp.

API và worker dùng chung persistence của AI Service. Worker lưu trạng thái và
kết quả qua application/repository; GET đọc bản ghi đó sau khi kiểm tra
ownership. Không có bước nhận Kafka event kết quả để API process cập nhật
database. SSE/WebSocket là khả năng tương lai cần contract riêng; polling
hiện dùng HTTP GET mới.

## 7. Lỗi

Response lỗi dùng format thống nhất:

```json
{
  "error": {
    "code": "INVALID_INTENT",
    "message": "intent không thuộc phạm vi giai đoạn 1",
    "details": {
      "field": "intent",
      "allowed": ["backlog_generation", "task_decomposition", "risk_analysis"]
    },
    "request_id": "8b7f4e0a-4a7d-4f69-9f4c-444444444444",
    "retryable": false
  }
}
```

| HTTP        | Error code mẫu                                       | Khi dùng                                                     |
| ----------- | ---------------------------------------------------- | ------------------------------------------------------------ |
| `400`       | `INVALID_REQUEST`, `INVALID_INTENT`, `INVALID_INPUT` | JSON hoặc field không hợp lệ.                                |
| `401`       | `AUTHENTICATION_REQUIRED`                            | Không có identity hợp lệ.                                    |
| `403`       | `TARGET_ACCESS_DENIED`                               | User không được yêu cầu phân tích target.                    |
| `404`       | `REQUEST_NOT_FOUND`                                  | Không tìm thấy request thuộc user hiện tại.                  |
| `409`       | `IDEMPOTENCY_CONFLICT`                               | Idempotency key đã gắn với payload khác.                     |
| `422`       | `OUTPUT_VALIDATION_FAILED`                           | Agent không tạo được output đúng schema sau retry hữu hạn.   |
| `429`       | `RATE_LIMITED`                                       | Vượt giới hạn request hoặc budget dùng chung.                |
| `500`       | `INTERNAL_ERROR`                                     | Lỗi không xác định trong AI Service.                         |
| `502`/`504` | `PROVIDER_UNAVAILABLE`, `WORKFLOW_TIMEOUT`           | Provider lỗi hoặc workflow vượt timeout; tùy khả năng retry. |

Không trả raw prompt, API credential, raw provider response hoặc thông tin
database trong `message`/`details`.

## 8. Context và tính đúng đắn

API không nhận `context` tùy ý từ client để thay dữ liệu của service sở hữu. Context
được chọn qua các domain tool ở mức như:

- `get_task_context`;
- `get_project_context`;
- `get_team_context`;
- `get_progress_context`;
- `get_development_context`.

Context Layer lọc và tổng hợp dữ liệu trước khi đưa cho agent. Response phải
cho biết `as_of`, nguồn dữ liệu và cảnh báo stale/missing/partial khi có. Bản
đọc/snapshot AI không phải nguồn đúng; Work, Classroom và Integration vẫn
sở hữu dữ liệu tương ứng. Work tính chỉ số tiến độ bằng công thức/quy tắc.

Context lấy đồng bộ qua internal REST API sau domain tool/adapter hoặc bản
sao đã đồng bộ khi use case chọn projection. Không phát Kafka request để chờ
context trả về. Metadata nguồn/thời điểm không thay thế kiểm tra quyền hiện
hành tại service sở hữu dữ liệu.

## 9. Luồng xác nhận proposal

API AI không có bước áp dụng proposal:

```text
POST AI request
    ↓
AI trả proposal có cấu trúc
    ↓
User xem và xác nhận ở client
    ↓
Domain service kiểm tra quyền + business rule
    ↓
Domain service áp dụng thay đổi
    ↓
Domain service phát domain event nếu cần
```

Ví dụ, `task_decomposition` chỉ trả danh sách subtask nháp. Việc tạo subtask
thật phải do Work Service thực hiện sau khi user xác nhận. Tương tự,
`backlog_generation` không tự tạo Work Item và `risk_analysis` không tự đổi
deadline hoặc trạng thái task.

## 10. Mapping API với workflow

| Bước API                | Thành phần workflow                  | Quy tắc                                                                     |
| ----------------------- | ------------------------------------ | --------------------------------------------------------------------------- |
| Parse và kiểm tra body  | API/Application                      | Kiểm tra intent, target, input, identity, quyền qua REST và idempotency.    |
| Lưu và giao job         | Application/Dispatcher               | Transaction lưu queued + ý định giao job; gửi Celery task qua Redis.        |
| Thực thi job            | Celery task/Application              | Chống chạy trùng, cập nhật running, gọi workflow dùng chung.                |
| Điều phối xử lý         | ADK Workflow                         | Điều phối macro-flow, không hard-code mọi context fetch.                    |
| Suy luận và lấy context | `LlmAgent` + Context Tool Pool       | Agent tự chọn domain tool trong budget; không thấy Kafka/database.          |
| Kiểm tra kết quả        | Workflow + typed schema              | Reject hoặc revise/retry có giới hạn nếu output không hợp lệ.               |
| Lưu kết quả             | Application/Persistence trong worker | Lưu succeeded/result hoặc failed/error, schema version và context metadata. |
| Trả kết quả             | API/Application                      | Đọc persistence, trả POST theo ngưỡng chờ hoặc GET sau kiểm tra ownership.  |

Budget tối thiểu cần cấu hình cho mỗi workflow: số model call, số context-tool
call, số specialist call, output token và wall-clock timeout. Không có retry vô
hạn.

Luồng chi tiết và trách nhiệm retry/dead-letter là thiết kế tại
[kiến trúc AI](architecture.md), được ghi nhận trong
[ADR-002](../adr/002-ai-request-pipeline.md); không bổ sung status, endpoint
hoặc event schema mới vào contract v1.

## 11. Các quyết định contract v1

Các quyết định dưới đây đã được ghi vào schema máy đọc được:

1. API dùng Bearer token; AI Service xác minh chữ ký JWT, issuer, audience và
   thời hạn bằng public key/JWKS cấu hình. Không tin header identity từ client.
   AI kiểm tra quyền target qua REST của service sở hữu trước khi enqueue,
   worker xác minh lại JWT/quyền trước khi chạy workflow.
2. `POST` chờ persistence tối đa 10 giây. Nếu chưa xong, trả `202` và client dùng
   `GET` để polling. Hard timeout của workflow là 30 giây.
3. V1 chỉ hỗ trợ các status `queued`, `running`, `succeeded`, `failed`; không
   có endpoint liệt kê lịch sử.
4. `input` có giới hạn kích thước và số phần tử theo từng intent trong OpenAPI;
   output cũng giới hạn số item để bảo vệ budget.
5. Quyền `task_decomposition` được kiểm tra theo quyền trên target của domain
   service; contract không tự cấp quyền Member hoặc Leader.
6. Output schema hiện hành được version theo intent: `backlog_generation.v1`,
   `task_decomposition.v1` và `risk_analysis.v1`.
7. Rate limit và retention cụ thể là cấu hình vận hành, nhưng lỗi và boundary
   đã cố định trong error schema; không lưu raw provider response.
8. V1 chưa phát event kết quả AI. Contract context projection cũ nằm tại
   [`ai-context-v1.yaml`](../../contracts/events/ai-context-v1.yaml); cần đối chiếu
   producer/envelope với baseline trước khi dùng cho Work.

Contract không xác nhận endpoint hoặc event producer/consumer đã chạy. Mọi thay
đổi contract sau v1 phải tăng version hoặc bổ sung quy tắc tương thích ngược.

## 12. Đối chiếu baseline và công việc chuyển đổi

Giữ URL, intent, status và envelope v1. Baseline là chuẩn kiến trúc, không
tự đổi wire contract (cấu trúc truyền qua API/event). Đối chiếu source và các
giới hạn tích hợp:

| Chủ đề        | Baseline / thiết kế mới                                            | Hợp đồng hoặc hiện trạng còn lại                                                            |
| ------------- | ------------------------------------------------------------------ | ------------------------------------------------------------------------------------------- |
| Xác thực      | Identity cấp JWT; các service xác thực token và kiểm tra quyền     | Đã có JWT verifier và REST authorizer; integration Identity/domain chưa xác minh |
| Context       | Internal API của Work qua adapter/domain tool                      | Đã có adapter/tool pool; endpoint/schema domain cần công bố; projection v1 dùng producer cũ |
| Job nội bộ    | Request + ý định giao job bền vững; dispatcher → Redis → worker AI | Đã có PostgreSQL/Celery/dispatcher, giữ ngưỡng chờ/polling v1 |
| Event kết quả | Baseline nêu `ai.analysis.completed`, `ai.project.risk.detected`   | Chưa có event schema/topic/consumer; v1 chưa phát event                                     |
| URL/version   | Nginx reverse proxy và API có version                              | Giữ `/api/ai/v1/requests`; ví dụ URL trong baseline không tự đổi route                      |

Cơ chế luôn trả `202` hoặc SSE/WebSocket cần quyết định và cập nhật contract
riêng. Sau `202`, polling dùng HTTP GET mới; Kafka không gửi response thứ hai
trên request POST đã kết thúc. Xem [ADR-001](../adr/001-adopt-architecture-baseline.md).
Pipeline job nền đã được chốt riêng trong [ADR-002](../adr/002-ai-request-pipeline.md).
