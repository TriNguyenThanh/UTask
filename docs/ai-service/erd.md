# ERD AI Service — MVP

**Trạng thái: Đã triển khai schema và repository PostgreSQL; production chưa
xác minh.** Nguồn thực thi là
[migration 0001](../../apps/ai-service/migrations/versions/0001_request_pipeline.py)
[migration 0002](../../apps/ai-service/migrations/versions/0002_completion_handoff.py)
và [migration 0003](../../apps/ai-service/migrations/versions/0003_request_admission.py),
cùng [ORM metadata](../../apps/ai-service/src/infrastructure/db/tables.py).
Không giữ các bảng projection cũ như schema bắt buộc khi pipeline dùng REST.

## ERD MVP

```mermaid
erDiagram
    AI_REQUEST ||--o| AI_DELIVERY : "chờ giao job"
    AI_REQUEST ||--o| AI_DEAD_LETTER : "thất bại"
    AI_REQUEST ||--o| AI_COMPLETION : "chờ API tiếp nhận"
    AI_REQUEST {
        uuid id PK
        text user_id "tham chiếu logic"
        text idempotency_key
        text fingerprint
        jsonb payload
        jsonb response
        text status
        text credential "Fernet ciphertext; xóa khi bàn giao/terminal"
        timestamptz created_at
        timestamptz queue_expires_at
        timestamptz execution_deadline
        uuid execution_token
        integer model_calls
        integer tool_calls
        integer output_tokens
    }
    AI_DELIVERY {
        uuid request_id PK,FK
        integer attempts
        timestamptz next_attempt_at
        uuid lease_token
    }
    AI_DEAD_LETTER {
        uuid request_id PK,FK
        text code
        timestamptz created_at
    }
    AI_COMPLETION {
        uuid request_id PK,FK
        uuid execution_token
        jsonb response "result/error và context metadata"
        timestamptz created_at "thời điểm bàn giao"
    }
```

## Vai trò của các bảng đề xuất

Tên bảng SQL là `ai_request`, `ai_delivery`, `ai_dead_letter`, `ai_completion`; chúng là schema
đã triển khai, không còn là placeholder. `user_id` và ID trong payload không
có FK xuyên service. Các FK trên chỉ nằm trong AI database.

- Request giữ input đã chuẩn hóa, response hiện tại, ownership/idempotency và
  metadata thực thi. Response JSONB chứa result/error/context metadata v1.
- Delivery giữ ý định giao job cùng transaction request, lease/attempts/thời
  điểm giao lại. Publish thành công không xóa ý định; worker claim mới xóa,
  tránh mất job nếu Redis làm mất thông điệp trước khi worker nhận.
- Dead-letter giữ mã lỗi terminal và thời điểm, không chứa token/raw output.
- Completion giữ kết quả worker chờ API tiếp nhận, không chứa nội dung context
  hay Bearer. Worker insert và `pg_notify` cùng transaction; API ghi terminal
  response và xóa completion cùng transaction. PK request chống bàn giao trùng;
  execution token chống worker cũ ghi đè. Index `(created_at, request_id)` phục
  vụ nhận theo batch. NOTIFY bị bỏ lỡ không làm mất completion.

## Ràng buộc và index đề xuất khi chọn persistence này

**Đã triển khai:** UUID PK, JSONB cho payload/response, timestamptz UTC,
unique `(user_id, idempotency_key)`, check status/budget không âm, index delivery
đến hạn và request expiry. Repository dùng connection pool, transaction ngắn;
không giữ transaction/lock trong lúc gọi broker, REST hoặc LLM.

Migration `0003` thêm index `(user_id, created_at)` cho cửa sổ 60 giây và
partial index `user_id` với `status IN ('queued','running')` cho slot đang
xử lý. Không thêm bảng bộ đếm. Transaction enqueue dùng advisory lock theo
user để serialize kiểm tra/tạo request giữa nhiều connection/process; lock
tự giải phóng khi commit/rollback. Kiểm tra replay/conflict trước giới hạn.
Xem [giới hạn tiếp nhận](api.md#giới-hạn-chống-spam).

`INSERT ... ON CONFLICT` bảo vệ POST đồng thời. Claim request khóa hàng;
claim delivery và API tiếp nhận completion dùng `FOR UPDATE SKIP LOCKED`.
Bàn giao kiểm tra execution token/status/deadline; API kiểm tra lại token và
schema/intent/version/result. Budget trừ trước model/tool, tính usage output và cấp cap
còn lại cho lần model tiếp theo. Xem [pipeline](architecture.md).

## Khi nào cần mở rộng?

MVP không lưu nội dung context lấy qua REST vào database/cache; context ở
trong bộ nhớ của lần thực thi. PostgreSQL vẫn giữ request/result và metadata
context, không giữ snapshot dữ liệu nguồn. Xem
[chính sách context và điều kiện mở rộng](architecture.md#chính-sách-context-hiện-tại-và-mở-rộng)
trước khi thiết kế schema hoặc cache mới.

Context snapshot/projection, execution history, Kafka outbox và specialist
chỉ thêm khi có use case/contract. Không lưu raw LLM output hoặc dùng projection
để cấp quyền. Retention/ẩn danh tự động và replay dead-letter chưa triển khai.

## Persistence phục vụ pipeline API/worker

API, dispatcher và worker dùng chung PostgreSQL của AI; Redis chỉ là broker.
Bearer cần cho reauthorization tại worker được mã hóa bằng khóa Fernet ngoài
source, cùng khóa ở API/worker. JWT còn được kiểm tra issuer/audience/expiry
sau giải mã. Ciphertext bị xóa khi bàn giao completion hoặc khi succeeded/failed,
kể cả queue timeout, worker timeout và dispatch hết retry. Payload/result cần
policy retention riêng; completion được xóa khi API tiếp nhận. Xem
[cơ chế thông báo và phục hồi](architecture.md#bàn-giao-kết-quả-worker-cho-api).

Worker chết không được chạy lại model trên request đang running; dispatcher
lưu failed khi deadline hết và chưa có completion. Completion đã commit được
giữ lại cho API tiếp nhận sau khởi động lại. Không đặt lại budget hoặc cho worker cũ ghi đè.
Không chạy migration tự động trong process API/worker; Alembic là bước deploy.

## Quyết định cần chốt trước migration

Migration local đã có và được kiểm thử upgrade/downgrade/schema drift.
Trước production cần chốt credential/role AI DB riêng, secret rotation,
retention, quota/concurrency, contract quyền/context và integration JWT.
Tên database mặc định `ai_context_db` không chứng minh Compose root đã tạo nó.
