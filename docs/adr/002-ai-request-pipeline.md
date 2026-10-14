# ADR-002 — Pipeline request và job nền của AI Service

- Ngày: 2026-10-08.
- Trạng thái: Thiết kế mục tiêu đã chốt theo trao đổi với người dùng;
  chưa triển khai worker, persistence production hoặc Kafka runtime.
- Tiếp nối [ADR-001](001-adopt-architecture-baseline.md), giữ ranh giới
  REST / Celery + Redis / Kafka của baseline.

## Bối cảnh và các lựa chọn

AI bootstrap đang gọi provider trong request HTTP và lưu in-memory. Cần làm
rõ cách tiếp nhận request, giao job, chạy workflow và trả kết quả khi tách API
và worker thành các process của cùng AI Service.

Phương án dùng Kafka để hỏi quyền, giao job nội bộ và nhận kết quả sẽ cần
correlation/reply topic và cơ chế bàn giao Kafka sang Celery. Phương án đã chọn
dùng REST cho kiểm tra đồng bộ, Redis cho Celery task và persistence chung của
AI để API đọc kết quả. Kafka giữ vai trò truyền sự kiện giữa service.

## Quyết định

1. AI xác thực user, validate input và kiểm tra quyền trên target qua internal
   REST API của service sở hữu. Domain tools lấy context qua adapter REST;
   projection chỉ bổ sung khi cần và không làm bằng chứng phân quyền.
2. Application kiểm tra idempotency theo user/key/payload, lưu request và ý
   định giao job bền vững trong cùng transaction của AI DB trước khi xác nhận
   nhận job. Dispatcher gửi task qua Redis và có cơ chế giao lại khi lỗi.
3. Celery worker thuộc AI Service, gọi application/workflow dùng chung. Worker
   kiểm soát xử lý trùng và lưu trạng thái/kết quả qua repository của AI;
   không cần phát event về API process để cập nhật database.
4. Giữ contract API v1: POST chờ tối đa 10 giây, thành công trả `200`, chưa
   hoàn tất trả `202`; client GET polling. Workflow có hard timeout 30 giây.
   Luôn trả `202` hoặc SSE/WebSocket là thay đổi contract cần chốt riêng.
5. Kafka consumer chạy ngoài agent loop, chỉ cập nhật context hoặc tạo job
   khi có use case/contract. Event kết quả chỉ phát qua outbox sau khi đã chốt
   schema; không dùng Kafka hỏi–đáp cho quyền/context hoặc response client.
6. Retry có giới hạn, phối hợp budget workflow/Celery; có phục hồi worker,
   chống trùng, ghi trạng thái lỗi cuối và cách ly thông điệp dead-letter.
   Retry phát event không được chạy lại LLM.

## Hệ quả và công việc tiếp theo

- Nguồn pipeline chi tiết là [kiến trúc AI](../ai-service/architecture.md).
  [API](../ai-service/api.md) giữ wire contract; [workflow](../ai-service/workflow.md)
  giữ luồng suy luận; [job nền](../infrastructure/background-jobs.md) giữ yêu
  cầu giao job/phục hồi. Không coi ADR là bằng chứng implementation.
- API/worker có thể dùng chung package/image, scale độc lập; số process,
  container và concurrency chưa được ấn định.
- Cần thiết kế schema lưu ý định giao job, nhận quyền xử lý/phục hồi, timeout
  chờ queue, retry và dead-letter trước migration/runtime. Không tạo schema
  placeholder hoặc event kết quả chưa được chốt.
- Không đổi URL, status, intent hoặc schema YAML v1 trong lần cập nhật tài
  liệu này; không thêm migration, dependency hay entry point giả.
