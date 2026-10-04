# ERD AI Service — MVP

**Trạng thái: Thiết kế mục tiêu; chưa triển khai và chưa có migration để kiểm chứng.**

Có thể tối giản ERD đáng kể cho phiên bản đầu. AI Service chỉ cần lưu:

1. yêu cầu và kết quả AI;
2. projection (bản sao đọc tối thiểu) của project/task/sprint;
3. một vài chỉ số tiến độ và hoạt động GitHub đã chuẩn hóa;
4. event đã nhận để chống xử lý trùng.

Các bảng nguồn vẫn thuộc service nghiệp vụ tương ứng. Những ID như `user_id`,
`project_id` và `scope_id` trỏ sang service khác là logical reference, không
phải foreign key xuyên database.

## ERD MVP

```mermaid
erDiagram
    CONTEXT_PROJECT ||--o{ CONTEXT_TASK : "co"
    CONTEXT_PROJECT ||--o{ CONTEXT_SPRINT : "co"
    CONTEXT_SPRINT ||--o{ CONTEXT_TASK : "contains"
    CONTEXT_PROJECT ||--o{ CONTEXT_GITHUB_ACTIVITY : "has"

    AI_REQUEST {
        uuid id PK
        uuid requester_user_id "logical ref Identity"
        varchar intent_type
        jsonb target_scope "logical refs: project/task/user"
        varchar status
        varchar idempotency_key "giá trị từ header Idempotency-Key"
        jsonb input_payload
        jsonb result_payload
        varchar output_schema_version
        varchar provider
        varchar model
        varchar prompt_version
        timestamptz context_as_of
        varchar context_fingerprint
        int attempt_count
        varchar error_code
        text error_message
        timestamptz requested_at
        timestamptz completed_at
        timestamptz updated_at
    }

    CONTEXT_EVENT {
        uuid event_id PK
        varchar event_type
        varchar event_version
        varchar producer
        timestamptz occurred_at
        timestamptz received_at
        jsonb payload
        varchar processing_status
        int failure_count
        timestamptz processed_at
        text last_error
    }

    CONTEXT_PROJECT {
        uuid id PK
        uuid class_id "logical ref Classroom"
        uuid group_id "logical ref Classroom"
        varchar name
        varchar status
        varchar source_version
        timestamptz source_updated_at
        timestamptz synced_at
    }

    CONTEXT_TASK {
        uuid id PK
        uuid project_id FK
        uuid sprint_id FK
        uuid assignee_user_id "logical ref Identity"
        varchar title
        varchar status
        varchar priority
        numeric estimate_points
        timestamptz due_at
        varchar source_version
        timestamptz source_updated_at
        timestamptz synced_at
    }

    CONTEXT_SPRINT {
        uuid id PK
        uuid project_id FK
        varchar name
        varchar status
        date start_at
        date end_at
        text goal
        varchar source_version
        timestamptz source_updated_at
        timestamptz synced_at
    }

    CONTEXT_GITHUB_ACTIVITY {
        uuid id PK
        uuid project_id FK
        uuid task_id "logical ref Project"
        uuid actor_user_id "logical ref Identity"
        varchar repository_key
        varchar activity_type
        varchar external_id
        varchar activity_status
        timestamptz occurred_at
        varchar source_version
        timestamptz source_updated_at
        timestamptz synced_at
    }

    CONTEXT_PROGRESS_METRIC {
        uuid id PK
        varchar scope_type
        uuid scope_id "logical ref Progress"
        varchar metric_key
        numeric metric_value
        timestamptz measured_at
        varchar calculation_version
        varchar source_version
        timestamptz source_updated_at
        timestamptz synced_at
    }
```

## Vì sao chỉ cần các bảng này?

- `ai_request` chứa cả trạng thái, metadata lần gọi và kết quả JSON đã validate.
  Với MVP, chỉ lưu lần xử lý hiện tại; chưa cần tách `ai_run`, `ai_result` và
  `ai_suggestion`.
- `target_scope` ghi rõ request áp dụng cho project, task hoặc user nào. Các ID
  trong đó là logical reference; không phải foreign key sang database khác.
- `context_project` và `context_task` đủ cho các use case tạo backlog và phân rã
  task; `context_sprint`, `context_progress_metric` và
  `context_github_activity` bổ sung dữ liệu cho `risk_analysis`.
- `context_progress_metric` cho phép AI diễn giải chỉ số do Progress Service
  tính; AI không tự tính lại chỉ số nguồn.
- `context_event` giữ `event_id` và trạng thái xử lý để consumer Kafka
  idempotent. Đây là bảng vận hành, không thay thế event contract.

Context được lưu như **trạng thái mới nhất**, không phải lịch sử đầy đủ. Các
cột `source_version`, `source_updated_at`, `synced_at` và `context_as_of` cho
biết kết quả AI đã dùng dữ liệu đến thời điểm nào.

## Ràng buộc và index tối thiểu

- Khóa chính dùng `uuid`; thời gian dùng `timestamptz`.
- `UNIQUE (requester_user_id, idempotency_key)` trên `ai_request` khi key khác
  `NULL`.
- `CHECK` cho `status` và `attempt_count >= 1`.
- `CHECK (jsonb_typeof(input_payload) = 'object')` nếu API luôn nhận object.
- Index `ai_request (requester_user_id, requested_at DESC)` và
  `ai_request (status, requested_at DESC)`.
- Index `context_task (project_id, status, due_at)` và
  `context_task (assignee_user_id, status, due_at)`.
- Index `context_github_activity (project_id, occurred_at DESC)` và
  `context_github_activity (task_id, occurred_at DESC)`.
- Index `context_progress_metric (scope_type, scope_id, metric_key,
  measured_at DESC)`.
- Primary key trên `context_event.event_id`; index retry theo
  `(processing_status, received_at)`.

## Khi nào cần mở rộng?

Chỉ thêm bảng khi có yêu cầu thật:

- Tách `ai_execution` nếu cần lưu lịch sử retry, token usage hoặc nhiều kết
  quả cho một request.
- Tách `ai_suggestion` nếu UI cần truy vấn/chấp nhận từng gợi ý độc lập thay vì
  đọc một `result_payload`.
- Thêm context project member hoặc group member khi use case AI tương ứng được
  chốt.
- Thêm bảng lineage chi tiết nếu cần audit chính xác từng bản ghi context đã
  được dùng.

Không đưa vào MVP: user/project/task nguồn, vector database, conversation dài
hạn, raw provider response và trạng thái “đã áp dụng” của suggestion. Việc áp
dụng thay đổi vẫn do service sở hữu domain thực hiện sau khi người dùng xác
nhận.

## Quyết định cần chốt trước migration

1. Output schema cụ thể cho `backlog_generation`, `task_decomposition` và
   `risk_analysis`.
2. Quyền gọi `task_decomposition` của Member hay chỉ Leader.
3. Schema Kafka cụ thể cho các event context và retention của `context_event`.
4. Retention/ẩn danh cho `input_payload`, `result_payload` và event payload.
5. Có cần tách lịch sử execution ngay từ v1 hay chấp nhận lưu lần xử lý hiện
   tại trong `ai_request`.
