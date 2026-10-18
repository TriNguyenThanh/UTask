# Kafka và transactional outbox

**Trạng thái: Một phần; đã có broker Compose và client Work/Classroom trong source.** Theo
[baseline](<../architecture/UTask_Architecture_Technology_Baseline (1).md>)
mục 9–11, Kafka truyền domain/integration event giữa service. REST vẫn dùng
cho command/query cần phản hồi trực tiếp; job nội bộ dùng
[Celery + Redis](background-jobs.md).

## Client và hợp đồng

Python service ưu tiên `confluent-kafka` theo baseline. Client có thể đổi nếu
có quyết định phù hợp, nhưng không làm thay đổi event contract. Đây là lựa
chọn đã có trong manifest và client Work/Classroom; không suy ra các service
khác đã dùng Kafka.

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

Phạm vi source đã kiểm tra gồm publisher Work, publisher Classroom và consumer
`consume_work` của Classroom. Các client dùng `confluent-kafka`; kiểm thử cấu
hình dùng client giả, không thay cho nghiệm thu broker thật.

| Luồng | Topic mặc định | Partition key | Consumer / DLQ |
| --- | --- | --- | --- |
| Work tạo dự án | `utask.work.events` | Project UUID | Classroom `consume_work` / `utask.classroom.work.dlq` |
| Classroom đổi thành viên | `utask.classroom.events` | Class UUID | Chưa có `consume_classroom` trong source Work của checkout này |

Publisher chỉ ghi `published_at` sau delivery callback thành công, lỗi thử
lại tăng dần tối đa 300 giây và không gửi vượt đầu hàng lỗi cùng aggregate.
Consumer tắt auto commit/offset store; sự kiện không áp dụng được vào DLQ
và phải ACK trước commit offset. Lỗi dữ liệu/quyền không được đổi thành thành
công. Consumer Work của Classroom nhận giới hạn retry từ mapping;
chưa có công cụ tự động replay DLQ. Khi xử
lý lại, sửa nguyên nhân, giữ event ID/nội dung nghiệp vụ và đưa qua cùng
validation/chống lặp; không ghi thẳng database hoặc bỏ qua quyền.

Broker mặc định retention 7 ngày qua `KAFKA_LOG_RETENTION_MS`; áp dụng cả
topic nghiệp vụ/DLQ không có override. Topic có cấu hình riêng phải kiểm tra
thực tế. JSON Schema nằm trong `contracts/events/`; envelope triển khai dùng
`data`. Kết quả HTTP/Kafka thật tại
nghiệm thu Classroom, không xác nhận staging.

Compose khai báo Kafka 3.9.0, cấu hình KRaft, volume và healthcheck. Ngoài
phạm vi Classroom–Work nêu trên, chưa xác minh producer/consumer runtime; AI bootstrap chưa
có Kafka client. Production dùng Kafka bên ngoài theo baseline. Topic,
partition, consumer group, retention, replay và SLA cần quyết định/kiểm tra
riêng, không suy ra từ việc broker local khởi động được.

## Kafka bên ngoài

**Đã triển khai:** client Kafka của Work và Classroom nhận địa chỉ cùng các
tùy chọn kết nối qua biến môi trường. Mọi client gửi sự kiện, nhận sự kiện và
gửi thông điệp lỗi (DLQ) trong hai service dùng cùng cấu hình kết nối của service.
**Chưa xác minh:** kết nối và gửi/nhận với Kafka cloud thật.

Bỏ `kafka` khỏi `COMPOSE_PROFILES` trong `.env` của máy triển khai và điền
địa chỉ `KAFKA_BOOTSTRAP_SERVERS`. Khi đó Compose không khởi động broker Docker
và worker không bắt buộc chờ broker này. Chạy bằng lệnh Docker Compose thông
thường; deploy staging giữ cùng lựa chọn profile. Để dùng lại broker Docker,
thêm `kafka` vào `COMPOSE_PROFILES` và đặt địa chỉ `kafka:9092`.
Cách điền tài khoản/mật khẩu nếu cần nằm tại
[cấu hình môi trường](environment.md#chọn-kafka-docker-hoặc-kafka-bên-ngoài).

Trước khi chuyển, chuẩn bị các topic đang dùng trên broker bên ngoài:

- `utask.work.events`, `utask.classroom.events` cho sự kiện nghiệp vụ.
- `utask.classroom.work.dlq` cho thông điệp lỗi phía Classroom.
- `utask.work.profile.dlq` nếu bật consumer Identity của Work; topic nguồn
  phải được thống nhất và cấu hình bằng `WORK_IDENTITY_KAFKA_TOPIC`.

Danh sách trên theo client có trong checkout; cấu hình topic riêng phải khớp
giữa bên gửi và bên nhận. Thay đổi kết nối này không thêm consumer nghiệp vụ.

Cấp quyền gửi/nhận trên topic, ghi DLQ và sử dụng consumer group tương ứng.
Producer hiện bật gửi chống trùng (`enable.idempotence`), nên quyền phía
broker cũng phải cho phép cấu hình này. Cấu hình thời gian lưu trên nhà cung cấp;
`KAFKA_LOG_RETENTION_MS` chỉ cấu hình broker Docker, không thay được broker cloud.
Các địa chỉ broker trả về khi client lấy metadata cũng phải truy cập được từ VPS.

Chuyển địa chỉ không tự chuyển sự kiện cũ, consumer offset (vị trí đã đọc)
hoặc các tùy chọn topic. Nếu cần giữ lịch sử, lập kế hoạch chuyển dữ liệu riêng
trước khi đổi. Không xóa volume Kafka Docker để đổi sang cloud.
