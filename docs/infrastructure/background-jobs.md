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

## Trả kết quả cho client

Job dài có thể dùng `202` kèm ID và endpoint xem trạng thái. Nếu chọn polling,
client gửi GET mới để lấy kết quả; nếu cần chủ động thông báo, phải thiết kế
SSE/WebSocket riêng. Kafka không tự gửi response HTTP thứ hai cho request
đã kết thúc. Hành vi cụ thể của AI v1 nằm trong [API AI](../ai-service/api.md).

## Kiểm thử khi triển khai

Kiểm tra thành công, lỗi có thể retry/không thể retry, thông điệp trùng,
timeout, worker dừng giữa chừng và broker tạm ngừng. Kiểm tra quyền trên API
tạo/xem job và xác nhận job chỉ truy cập dữ liệu của service sở hữu.
