# Kafka và transactional outbox

**Trạng thái: Thiết kế mục tiêu; đã có cấu hình broker trong Compose.** Theo
[baseline](<../architecture/UTask_Architecture_Technology_Baseline (1).md>)
mục 9–11, Kafka truyền domain/integration event giữa service. REST vẫn dùng
cho command/query cần phản hồi trực tiếp; job nội bộ dùng
[Celery + Redis](background-jobs.md).

## Client và hợp đồng

Python service ưu tiên `confluent-kafka` theo baseline. Client có thể đổi nếu
có quyết định phù hợp, nhưng không làm thay đổi event contract. Đây là lựa
chọn mục tiêu, chưa xác nhận SDK đã được cài ở từng service.

Danh mục sự kiện nằm trong [tài liệu hệ thống](../system/kafka-events.md).
Schema máy đọc được thuộc [`contracts/events/`](../../contracts/events/);
không publish JSON tùy ý hoặc tạo schema từ wildcard trong danh mục.

## Transactional outbox

Outbox là bản ghi thông điệp chờ gửi, được lưu cùng thay đổi nghiệp vụ trong
một transaction của database service sở hữu:

```text
Transaction: cập nhật dữ liệu + ghi outbox → COMMIT
    → Celery publisher worker → Kafka → consumer service khác
```

Publisher retry khi Kafka tạm ngừng. Có thể gửi trùng nếu process dừng sau
khi publish nhưng trước khi đánh dấu đã gửi; consumer phải xử lý lặp theo
`event_id` và cập nhật dữ liệu nhất quán. Không cam kết xử lý đúng một lần chỉ
vì có outbox. Django service dùng `transaction.atomic()`; AI dùng transaction
của lớp persistence đã chọn khi được triển khai.

Giai đoạn đầu dùng outbox + Celery publisher; Debezium CDC là lựa chọn mở
rộng khi có nhu cầu, không phải dependency bắt buộc của MVP.

Với AI, event kết quả chỉ được phát khi đã có contract: application lưu kết
quả và outbox trong cùng transaction, publisher gửi Kafka sau commit. API
đọc kết quả từ persistence AI; không chờ event để cập nhật database. Publisher
gửi lại event không được chạy lại workflow/LLM.

## Consumer, bàn giao job và dead-letter

AI consumer chạy ngoài agent loop. Khi có use case/contract, consumer có thể
cập nhật projection hoặc gọi application tạo job; job đi qua bản ghi chờ giao
job → dispatcher → Redis → Celery worker của AI. Cần lưu dấu chống trùng
`event_id` cùng cập nhật/job một cách nhất quán trước khi commit offset.
Thông điệp giao lại không được tạo thêm job hoặc kết quả trùng. Xem
[giao job bền vững](background-jobs.md).

Retry consumer phải phân loại lỗi tạm thời và lỗi không thể xử lý, có backoff
và giới hạn. Event sai schema/version hoặc hết giới hạn xử lý phải được lưu
bền vững vào nơi dead-letter (thông điệp lỗi chờ điều tra), cùng thông tin nguồn
và lỗi cần thiết trước khi bỏ qua/commit offset. Cần chốt nơi lưu/topic,
retention và thao tác replay; không có topic DLQ mặc định được xác minh.
Replay phải qua validation và chống trùng, không bypass quyền hoặc budget.

Kafka thông báo thay đổi đã xảy ra; không dùng request/reply topic để kiểm
tra quyền hoặc lấy context đồng bộ. Các bước này dùng internal REST API của
service sở hữu. Event đổi quyền có thể làm mất hiệu lực cache, nhưng bản sao
context không thay quyết định quyền hiện hành. Pipeline chuẩn nằm tại
[kiến trúc AI](../ai-service/architecture.md).

## Hiện trạng và vận hành

Compose khai báo Kafka 3.9.0, cấu hình KRaft, volume và healthcheck. Chưa xác
minh producer/consumer hoặc outbox runtime của các service; AI bootstrap chưa
có Kafka client. Production dùng Kafka bên ngoài theo baseline. Topic,
partition, consumer group, retention, replay và SLA cần quyết định/kiểm tra
riêng, không suy ra từ việc broker local khởi động được.
