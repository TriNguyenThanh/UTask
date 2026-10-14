# Kế hoạch triển khai pipeline AI — 2026-10-08

## Mục tiêu và phạm vi

Thay bootstrap đồng bộ bằng pipeline ADR-002 trong `apps/ai-service/`, cập
nhật tài liệu chuẩn ở `docs/ai-service/`. Giữ ba intent và wire contract v1.
Không thêm Kafka khi chưa có event contract; không sửa service khác hoặc
gateway root. Hợp đồng context/quyền và issuer JWT còn cần đội domain cung cấp.

## Thiết kế triển khai

- API xác minh JWT với public key/JWKS, issuer/audience cố định từ cấu hình;
  bỏ identity header bootstrap. Application kiểm tra quyền bằng REST adapter.
- SQLAlchemy + PostgreSQL; Alembic migration tách khỏi app startup. Unique
  user/key và insert-on-conflict bảo vệ idempotency; cùng transaction tạo
  request và delivery job. Input JSONB, thời gian UTC, UUID nội bộ; không FK
  xuyên service. Bearer phục vụ kiểm tra quyền tại worker được mã hóa Fernet,
  không đưa vào prompt/log, xóa khi request kết thúc.
- Dispatcher claim delivery bằng FOR UPDATE SKIP LOCKED, gửi Celery task chỉ
  chứa request ID, retry có backoff/jitter và giới hạn. Redis không lưu result.
- Worker claim request nguyên tử với ownership token. Deadline bắt đầu ở lần
  claim đầu, budget model/tool được trừ trước lời gọi. Job trùng không chạy
  lại; token cũ không ghi đè terminal result. Dispatcher kết thúc queue/job
  quá hạn và lưu dead-letter có mã lỗi, không chứa output/token thô.
- ADK custom workflow kiểm soát LlmAgent, schema theo intent, revise hữu hạn,
  budget và timeout. Domain tool chỉ lấy context target đã xác thực; REST
  adapter giới hạn URL cấu hình, timeout, kích thước và lọc trường dữ liệu.
- Application/executor và budget dùng protocol có kiểu; worker kiểm tra
  proposal đúng request/intent/version trước persistence. Prompt nghiệp vụ
  nằm trong workflow, provider adapter chỉ lắp ghép SDK. Workflow kiểm tra
  context thiết yếu theo intent, không fetch cứng mọi domain.
- Stack Compose local riêng trong service gồm PostgreSQL, Redis, migration,
  API, dispatcher và worker. Root Compose/gateway/service domain ngoài scope.
- POST chờ persistence tối đa 10 giây, trả 200 hoặc 202 với Location; GET đọc
  trạng thái/kết quả sau ownership. API không chạy model.

## Bước và điều kiện hoàn thành

1. Model/ports/config/error; test schema và lỗi/biên.
2. Migration/repository PostgreSQL; test transaction, đồng thời, claim,
   fencing, dispatch retry, timeout, xóa credential và dead-letter.
3. Auth/REST/context/ADK; test với JWT và model/HTTP fake deterministic.
4. Application/API/Celery/dispatcher; test 200/202, replay, permission,
   worker lỗi/chạy trùng và process entry points.
5. Tài liệu, task log, formatter/lint/test, migration/build và smoke pipeline.

## Giới hạn xác minh

Không gọi LLM trả phí hoặc API domain chưa công bố. Test ADK dùng model fake;
test database dùng PostgreSQL thật. Chạy worker/broker thật khi hạ tầng local
cho phép. Ghi rõ các bước chưa kiểm chứng, không coi adapter cấu hình được
là integration Work/Identity đã hoàn tất.
