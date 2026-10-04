# API AI Service — giai đoạn 1

**Trạng thái: Thiết kế mục tiêu; chưa triển khai và chưa phải hợp đồng máy đọc
được.**

Tài liệu này mô tả API mà client dùng để yêu cầu AI xử lý một ý định cụ thể.
API chỉ nhận yêu cầu và trả về bản phân tích hoặc đề xuất có cấu trúc. Ngữ cảnh
nghiệp vụ được AI Service đồng bộ vào bản đọc nội bộ qua Kafka; client không gửi
toàn bộ dữ liệu nghiệp vụ và AI không gọi Kafka, database hoặc REST của service
khác trong lúc xử lý.

## 1. Phạm vi

Giai đoạn 1 chỉ hỗ trợ ba giá trị `intent`:

| Intent | Mục đích | Phạm vi đích |
| --- | --- | --- |
| `backlog_generation` | Tạo backlog nháp từ mô tả project hoặc một chức năng | Project hiện có hoặc bản nháp chưa gắn project |
| `task_decomposition` | Phân rã một task phức tạp thành các subtask | Task |
| `risk_analysis` | Phân tích và giải thích nguy cơ ảnh hưởng tiến độ, Sprint hoặc deadline | Project hoặc Sprint |

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
Application -> ADK Workflow -> LlmAgent -> Context Tool Pool
                                      |
                                      v
                              Context Layer / read model
```

- API nhận ý định, phạm vi đối tượng và các chỉ dẫn bổ sung cần thiết.
- `requester_user_id` lấy từ ngữ cảnh xác thực của request, không lấy từ body
  do client tự khai báo. Cơ chế header/token cụ thể cần chốt trong hợp đồng
  xác thực chung.
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

Gateway hiện có route mục tiêu `/api/ai/`. Prefix version được đề xuất cho API
v1 là:

```text
/api/ai/v1
```

Các chi tiết gateway, port nội bộ và xác thực hiện chưa được xác minh trong
source implementation.

Quy ước dữ liệu:

- Request và response dùng `application/json; charset=utf-8`.
- ID được biểu diễn bằng chuỗi UUID; các ID của Project, Task, Sprint và User
  là logical reference, không phải foreign key trong database AI.
- Thời gian dùng RFC 3339 UTC, ví dụ `2026-10-04T09:30:00Z`.
- Mỗi request nên có `X-Request-ID` để trace. Nếu client không gửi, API tạo
  một giá trị mới và trả lại trong response/header.
- `Idempotency-Key` là khóa tùy chọn nhưng được khuyến nghị cho request tạo
  kết quả. Cùng một key phải đi kèm cùng payload; dùng lại key với payload khác
  phải trả lỗi `409`.

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
    "dependencies": [
      "Identity Service"
    ],
    "additional_instruction": "Ưu tiên chia theo vertical slice"
  },
  "output_schema_version": "task_decomposition.v1",
  "idempotency_key": "decompose-task-2b7f4e0a-v1"
}
```

| Field | Bắt buộc | Mô tả |
| --- | --- | --- |
| `intent` | Có | Một trong ba intent được hỗ trợ ở phase 1. |
| `target` | Tùy intent | Logical reference tới project, task hoặc Sprint. Không gửi target nếu tạo backlog nháp chưa gắn project. |
| `target.type` | Khi có `target` | `project`, `task` hoặc `sprint`; phải phù hợp với `intent`. |
| `target.id` | Khi có `target` | ID của đối tượng trong service sở hữu dữ liệu. |
| `input` | Có | Dữ liệu trực tiếp do user cung cấp; không thay thế context canonical từ read model. |
| `output_schema_version` | Không | Phiên bản schema client mong muốn; mặc định là phiên bản hiện hành nếu API cho phép bỏ qua. |
| `idempotency_key` | Không | Khóa chống tạo cùng một yêu cầu nhiều lần. Header `Idempotency-Key` có thể được dùng thay cho field này sau khi contract chốt. |

`requester_user_id` không xuất hiện trong request body. API lấy user từ identity
context đã được gateway hoặc cơ chế xác thực nội bộ kiểm tra.

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
    "goals": [
      "Đặt và hủy lịch",
      "Tránh trùng lịch"
    ],
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

`target.type` phải là `task`. Nếu task đã có trong context read model, API có
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

## 6. Xem trạng thái và kết quả

### `GET /api/ai/v1/requests/{request_id}`

Trả về trạng thái của request thuộc user đã xác thực.

| `status` | Ý nghĩa |
| --- | --- |
| `queued` | Đã nhận nhưng workflow chưa bắt đầu. |
| `running` | Workflow hoặc agent đang xử lý. |
| `succeeded` | Đã có result hợp lệ. |
| `failed` | Không thể tạo result hợp lệ trong budget/retry cho phép. |

Request ở trạng thái `succeeded` trả cùng envelope và `result` như response
`200` của POST. Request ở trạng thái `queued` hoặc `running` chỉ trả metadata
trạng thái, thời gian cập nhật và context nếu đã có. Request `failed` trả
`error` theo format ở mục kế tiếp.

## 7. Lỗi

Response lỗi dùng format thống nhất:

```json
{
  "error": {
    "code": "INVALID_INTENT",
    "message": "intent không thuộc phạm vi giai đoạn 1",
    "details": {
      "field": "intent",
      "allowed": [
        "backlog_generation",
        "task_decomposition",
        "risk_analysis"
      ]
    },
    "request_id": "8b7f4e0a-4a7d-4f69-9f4c-444444444444",
    "retryable": false
  }
}
```

| HTTP | Error code mẫu | Khi dùng |
| --- | --- | --- |
| `400` | `INVALID_REQUEST`, `INVALID_INTENT`, `INVALID_INPUT` | JSON hoặc field không hợp lệ. |
| `401` | `AUTHENTICATION_REQUIRED` | Không có identity hợp lệ. |
| `403` | `TARGET_ACCESS_DENIED` | User không được yêu cầu phân tích target. |
| `404` | `REQUEST_NOT_FOUND` | Không tìm thấy request thuộc user hiện tại. |
| `409` | `IDEMPOTENCY_CONFLICT` | Idempotency key đã gắn với payload khác. |
| `422` | `OUTPUT_VALIDATION_FAILED` | Agent không tạo được output đúng schema sau retry hữu hạn. |
| `429` | `RATE_LIMITED` | Vượt giới hạn request hoặc budget dùng chung. |
| `500` | `INTERNAL_ERROR` | Lỗi không xác định trong AI Service. |
| `502`/`504` | `PROVIDER_UNAVAILABLE`, `WORKFLOW_TIMEOUT` | Provider lỗi hoặc workflow vượt timeout; tùy khả năng retry. |

Không trả raw prompt, API credential, raw provider response hoặc thông tin
database trong `message`/`details`.

## 8. Context và tính đúng đắn

API không nhận `context` tùy ý từ client để thay thế dữ liệu đã đồng bộ. Context
được chọn qua các domain tool ở mức như:

- `get_task_context`;
- `get_project_context`;
- `get_team_context`;
- `get_progress_context`;
- `get_development_context`.

Context Layer lọc và tổng hợp dữ liệu trước khi đưa cho agent. Response phải
cho biết `as_of`, nguồn dữ liệu và cảnh báo stale/missing/partial khi có. Bản
đọc AI không phải nguồn đúng; Project, Classroom, Integration và Progress
Service vẫn là chủ sở hữu dữ liệu tương ứng.

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
thật phải do Project Service thực hiện sau khi user xác nhận. Tương tự,
`backlog_generation` không tự tạo Work Item và `risk_analysis` không tự đổi
deadline hoặc trạng thái task.

## 10. Mapping API với workflow

| Bước API | Thành phần workflow | Quy tắc |
| --- | --- | --- |
| Parse và kiểm tra body | API/Application | Kiểm tra intent, target, input, identity và idempotency. |
| Chọn xử lý | ADK Workflow | Điều phối macro-flow, không hard-code mọi context fetch. |
| Suy luận và lấy context | `LlmAgent` + Context Tool Pool | Agent tự chọn domain tool trong budget; không thấy Kafka/database. |
| Kiểm tra kết quả | Workflow + typed schema | Reject hoặc revise/retry có giới hạn nếu output không hợp lệ. |
| Lưu và trả kết quả | Application/Persistence | Lưu request, result, schema version và context metadata. |

Budget tối thiểu cần cấu hình cho mỗi workflow: số model call, số context-tool
call, số specialist call, output token và wall-clock timeout. Không có retry vô
hạn.

## 11. Các điểm cần chốt trước khi tạo contract/OpenAPI

Tài liệu này chưa thay thế schema trong `contracts/`. Trước khi implementation
hoặc tạo OpenAPI chính thức, cần quyết định:

1. Header/token cụ thể để gateway truyền identity và cách kiểm tra quyền target.
2. POST luôn synchronous hay cho phép `202`; ngưỡng timeout chuyển sang queue.
3. Enum/status/error code chính thức và format pagination nếu bổ sung history.
4. Giới hạn kích thước `input`, số item tối đa và quy tắc estimate/priority.
5. Quyền gọi `task_decomposition` của Member hay chỉ Leader.
6. Output schema version chính thức và chính sách tương thích ngược.
7. Rate limit, retention/ẩn danh của input/result và cơ chế truy vấn lịch sử.
8. Event `ai.completed` có cần phát hay không; event contract phải được chốt
   riêng, không dùng API này để suy ra schema Kafka.

