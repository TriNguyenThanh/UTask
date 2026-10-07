# Job nền, Celery và Redis

**Trạng thái: Thiết kế mục tiêu.** Theo baseline, mục 10–11, job nội bộ dùng
Celery + Redis; sự kiện giữa service dùng Kafka. Xem
[baseline](<../architecture/UTask_Architecture_Technology_Baseline (1).md>).
Compose có Redis nhưng chưa khai báo Celery worker, scheduler hoặc outbox
publisher. Có broker trong hạ tầng không chứng minh job đã được triển khai.

## Quyền sở hữu job

Service sở hữu nghiệp vụ cũng sở hữu mã task, trạng thái và kết quả job.
Ví dụ: Integration xử lý đồng bộ GitHub, Notification gửi email, service
nghiệp vụ chạy deadline scan hoặc dọn dữ liệu. Không tạo service worker dùng
chung để truy cập database của tất cả service.

```text
API / scheduler / consumer của service
    → Redis broker → Celery worker của cùng service
                       → application/domain logic
                       → database của service / hệ thống ngoài được phép
```

Broker là nơi chuyển lệnh thực thi tới worker; PostgreSQL vẫn là nơi lưu dữ
liệu gốc. Task không được gọi trực tiếp database service khác.

## Process và source code

Worker là process thực thi job, không đồng nghĩa với một microservice mới.
API và worker có thể dùng chung package/image nhưng chạy bằng entry point
khác nhau, có thể tách container để vận hành độc lập. Đây là hướng triển khai;
baseline chưa ấn định topology hoặc worker singleton.

Baseline mục 17 minh họa `config/celery.py` trong Django service. AI Service
có thể đặt cấu hình Celery và task trong package của `apps/ai-service/`, gọi
application/workflow dùng chung. Tên file và lệnh chạy chỉ được ghi vào code
map sau khi triển khai, không tạo đường dẫn giả như thể đã có source.

## Tin cậy và retry

Job cần định danh, trạng thái, giới hạn thời gian, số lần retry và xử lý lặp
(idempotency): chạy lại không làm sai dữ liệu hay tạo thêm tác động nghiệp vụ.
Giới hạn concurrency phải phù hợp kết nối database và quota hệ thống ngoài.
Các giá trị cụ thể thuộc cấu hình từng service, chưa được baseline chốt.

Không giả định thao tác ghi PostgreSQL và gửi Redis/Kafka là một transaction.
Job quan trọng cần cơ chế phục hồi khi đã ghi dữ liệu nhưng chưa gửi được
thông điệp. Với domain event, dùng transactional outbox theo
[Kafka và outbox](kafka.md). Cơ chế bảo đảm giao job tới Redis cần được thiết
kế và kiểm thử trước khi công bố SLA.

### Giao job bền vững của AI Service

[Pipeline AI](../ai-service/architecture.md) đã chọn lưu request `queued`
cùng bản ghi chờ giao job trong một transaction của PostgreSQL AI. Dispatcher
đọc bản ghi đó và gửi Celery task qua Redis sau commit; khi Redis lỗi hoặc
process dừng giữa chừng, bản ghi bền vững cho phép giao lại. Không xác nhận
đã nhận job trước khi lưu thành công.

Task có thể được giao nhiều lần. Application phải kiểm soát quyền xử lý một
job, phục hồi khi worker chết, bỏ qua request đã kết thúc và ngăn worker cũ
ghi đè kết quả. Kiểm tra idempotency ở API không thay thế kiểm tra ở worker.
Worker lưu kết quả qua repository vào AI DB; API đọc cùng persistence.

Khi Kafka consumer tạo job, cần lưu dấu chống trùng event cùng job/ý định giao
job một cách nhất quán trước khi commit offset. Chỉ commit offset sau khi
bàn giao bền vững; không coi gửi Redis thành công là bằng chứng đã có kết quả.
Tên bảng, cơ chế nhận quyền xử lý, lịch dispatcher và phục hồi cần thiết kế
trước runtime; xem [yêu cầu persistence AI](../ai-service/erd.md).

### Phân loại retry và dead-letter

- Retry lỗi tạm thời như timeout mạng, rate limit hoặc provider chưa sẵn sàng
  theo backoff tăng dần, jitter và số lần giới hạn. Lỗi quyền/input không
  được retry như lỗi hạ tầng.
- Phân biệt retry giao task, retry thực thi và revise output. Với AI, phối hợp
  retry Celery và workflow trong cùng budget/hard timeout; không tự đặt lại
  budget khi task được giao lại.
- Job hết retry phải lưu lỗi cuối và trạng thái `failed`. Worker chết hoặc
  request bị kẹt cần cơ chế phát hiện/phục hồi và thời hạn chờ queue riêng.
- Dead-letter lưu thông điệp không xử lý được cùng thông tin lỗi để điều tra
  và replay có kiểm soát. Không giả định Celery + Redis tự tạo DLQ; nơi lưu,
  retention và quy tắc replay phải được đặc tả/test. Kafka event lỗi có quy
  tắc cách ly riêng trong [Kafka](kafka.md).
- Nếu đã lưu kết quả AI nhưng gửi event thất bại, chỉ retry outbox publisher,
  không chạy lại workflow/LLM.

## Trả kết quả cho client

Job dài có thể dùng `202` kèm ID và endpoint xem trạng thái. Nếu chọn polling,
client gửi GET mới để lấy kết quả; nếu cần chủ động thông báo, phải thiết kế
SSE/WebSocket riêng. Kafka không tự gửi response HTTP thứ hai cho request
đã kết thúc. Hành vi cụ thể của AI v1 nằm trong [API AI](../ai-service/api.md).

AI MVP dùng polling; POST vẫn chờ tối đa 10 giây và trả `200` khi thành công
hoặc `202` nếu chưa hoàn tất. API chờ kết quả từ persistence, không chờ Kafka
event. Hết ngưỡng HTTP không hủy job; hard timeout workflow là 30 giây.

## Kiểm thử khi triển khai

Kiểm tra thành công, lỗi có thể retry/không thể retry, thông điệp trùng,
timeout, worker dừng giữa chừng và broker tạm ngừng. Kiểm tra quyền trên API
tạo/xem job và xác nhận job chỉ truy cập dữ liệu của service sở hữu.

Với pipeline AI, kiểm tra thêm POST đồng thời cùng key, quyền bị thu hồi khi
job đang chờ, lỗi giữa commit database và gửi Redis, gửi trùng task, worker
chết trước/sau khi lưu kết quả, worker cũ ghi muộn, retry không vượt budget,
dead-letter/replay và lỗi publisher không gây gọi LLM lại. Kiểm tra client
vẫn lấy kết quả bằng GET sau khi POST đã trả `202`.
