# Provider kết nối Work/AI và vận hành outbox

**Trạng thái: Đã triển khai trong source và kiểm thử phía Integration.**
Work/AI thật và GitHub live trong luồng Project mới **Chưa xác minh**. Kết quả
nghiệm thu GitHub account M4 trước đây không thay thế nghiệm thu này.
Contract chuẩn tại [OpenAPI 1.4](../../contracts/api/integration-service-v1.yaml)
và [event v1](../../contracts/events/integration.project.connection.changed.v1.json).

## Source và tính nhất quán

App [github_connections](../../apps/integration-service/apps/github_connections/)
sở hữu ProjectConnection, ConnectionOperation và IntegrationOutboxEvent;
không có FK hoặc truy vấn database Work/Identity. Installation vẫn là metadata
hint; mọi truy cập reference/context đều kiểm installation và repository live.

Connection khóa theo Project. Generation actor, version credential và revision
provider fence loại bỏ response HTTP đã lỗi thời. Thứ tự khóa khi cần nhiều
loại là actor generation → provider fence → Project; không giữ khóa qua HTTP
hoặc broker. Webhook installation tăng provider fence ngay cả khi chưa có
metadata hint, ngăn response chuẩn bị cũ được ghi sau invalidation.

Prepare cấp generation một lần; CONFIRMED/ABORTED/EXPIRED không chạy lại như
command mới. Snapshot prepare được giữ riêng kết quả confirm. Operation đã
confirm đại diện binding được giữ riêng reservation mới, không bị cleanup xóa.
Thu hồi authorization/account hoặc uninstall/suspend/removed repository ngắt
connection và ghi event trong cùng transaction. Added/unsuspend chỉ đánh dấu
cần revalidation; không tự reconnect. Connection không phục vụ khi còn pending.

Beat expire operation mỗi 60 giây; TTL 24 giờ, tombstone đến ngày 31 từ lúc
prepare, tương đương ít nhất 30 ngày sau expiry. Operation đang đại diện binding
được giữ lâu hơn. Cleanup khóa Project rồi kiểm lại tham chiếu trước khi xóa.

Provider client mới pin GitHub REST `2026-03-10`; client discovery M4 giữ nguyên
version cũ. Discovery Project giới hạn tổng 30 trang, không kết luận thiếu repo
khi đã hết ngân sách. Metadata/default branch phải khớp giới hạn contract.
Reference URL chỉ HTTPS github.com đúng repo, không query/credential/fragment.
Context đọc live tối đa 20 item mỗi loại; thiếu permission trả `partial`.

## Cấu hình và rollout

| Biến | Mặc định / yêu cầu |
| --- | --- |
| `INTEGRATION_CONNECTIONS_ENABLED` | `false`; bật provider connection/reference/status |
| `INTEGRATION_AI_CONTEXT_ENABLED` | `false`; chỉ bật sau connection và Work authorize |
| `INTEGRATION_KAFKA_ENABLED` | `false`; tắt vẫn giữ outbox bền vững |
| `INTEGRATION_SERVICE_KEYS` | JSON object `work`/`ai` → key hoặc list 1–2 key; tối thiểu 32 ký tự ASCII; không trùng nhau |
| `INTEGRATION_WORK_URL` | `http://work-service:8000`; internal origin, không query/path/credential |
| `INTEGRATION_WORK_SERVICE_KEY` | Key riêng Integration→Work, khác các inbound key |
| `INTEGRATION_KAFKA_BOOTSTRAP_SERVERS` | `kafka:9092`; có thể override riêng Integration |
| `INTEGRATION_KAFKA_SECURITY_PROTOCOL` | `PLAINTEXT`, `SSL`, `SASL_PLAINTEXT`, `SASL_SSL` |
| `INTEGRATION_KAFKA_SASL_*` | Mechanism/user/password khi dùng SASL; không đưa credential vào log |
| `INTEGRATION_KAFKA_SSL_*` | CA/certificate/key location và key password; mount read-only `/run/kafka-certificates` |

Khi bật connection, startup kiểm GitHub App enabled, inbound caller và key
outbound riêng; khi bật AI cần cả key AI. Cấu hình Kafka chỉ validate khi bật,
không nối broker trong startup/health. Xoay inbound key bằng list current/previous;
operator bỏ previous trong tối đa 24 giờ, runtime không tự suy ra thời điểm cấp key.
Giữ secret trong môi trường triển khai, không copy `.env` thật vào repo.

Thứ tự: migration → API/worker/Beat với flags tắt → cấu hình key và Work
receipt/authorize → thử REST nội bộ → bật Work REST → bật Kafka → bật AI context.
Hướng dẫn caller cụ thể: [Work](work-service-integration-guide.md),
[AI](ai-service-integration-guide.md). Giữ unavailable adapter phía Work để rollback.
Public gateway luôn từ chối `/api/integrations/api/v1/internal/*`.

## Kafka, retry và phục hồi

Topic cố định `utask.integration.events`, key `project_id`. Local startup
provision topic; broker staging bên ngoài phải được operator provision cùng
ACL Integration produce / Work consume trước khi bật flag. Không phát PENDING.

Worker claim một head mỗi Project bằng `SKIP LOCKED`, lease 120 giây; chỉ
claim sequence tiếp sau khi head đã ACK. Broker I/O ngoài transaction; failure
giữ ID/envelope, backoff tối đa 300 giây. Producer bật idempotence, acks all,
delivery timeout 30 giây. Mỗi lượt publisher có budget chủ động 35 giây,
dành 10 giây cuối cho database; kiểm lại sau claim và khởi tạo producer,
trừ cả thời gian `produce` trước khi tính timeout `flush` (tối đa khoảng 25
giây khi task vừa bắt đầu). Budget broker có thể ngắn hơn delivery timeout;
timeout hoặc ACK chưa rõ vẫn phải giữ cùng ID khi retry.

Riêng SQL của publisher dùng transaction cục bộ: mỗi thao tác claim/ACK/retry
có budget 3 giây sau khi nối DB, mỗi câu SQL dùng `SET LOCAL` với
`statement_timeout`/`lock_timeout` tối đa 1 giây và giảm theo phần còn lại.
Kết nối vẫn dùng `connect_timeout=5`; không bắt đầu thao tác DB khi còn tối đa
6 giây. Timeout cục bộ được khôi phục khi transaction kết thúc, không đổi
cấu hình job khác. Query chậm làm rollback thao tác chưa commit; claim đã
commit nhưng không còn budget ghi retry/ACK được giữ để phục hồi sau lease.
`SoftTimeLimitExceeded` thoát task ngay, không tiếp tục gọi DB/broker. Budget
Python/SQL không bảo đảm ngắt ngay native call/socket/commit bị treo; Celery
soft/hard limit 40/45 giây vẫn là lớp bảo vệ cuối.

Không rollback connection khi Kafka lỗi. Cleanup chỉ
xóa event PUBLISHED sau 30 ngày, tuyệt đối giữ pending/in-flight.

Replay một event chưa publish hoặc lease đã hết hạn:

```bash
python manage.py replay_integration_outbox <event-uuid>
```

Event có thể lặp nếu process chết sau ACK hoặc delivery không rõ kết quả.
Lease bảo vệ trạng thái database, không fence được kết nối broker cũ: event
cũ vẫn có thể được gửi lại sau event mới. Work phải dedupe `event_id`, so
generation/source version và giữ thông tin binding đã chấp nhận riêng pending.
Theo dõi tuổi pending lâu nhất, số attempts và `last_error_class`; log chỉ
ghi nhóm lỗi an toàn, không ghi exception/credential. Health vẫn chỉ kiểm DB.
Log `integration_outbox_database_unavailable` báo publisher dừng vì lỗi hoặc
hết budget database; kiểm tra row PUBLISHING và tuổi lease khi cần phục hồi.

## Phạm vi nghiệm thu

Unit/contract và PostgreSQL tests bao phủ caller, receipt, CAS/idempotency,
hai prepare đồng thời, command muộn, expiry/retention, rollback outbox,
webhook/revoke, context/reference và lỗi provider. Test HTTP localhost dùng
Identity/Work/GitHub stub với adapter thật; Kafka publisher dùng broker giả
trong CI. Không dùng mock hoặc nhãn `implemented` để khẳng định Work/AI thật
đã tích hợp. Kiểm tra broker riêng và kết quả cuối ở
[biên bản triển khai provider](implementation-2026-10-20.md).
