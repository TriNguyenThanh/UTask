# Tái hiện lỗi consumer bằng cấu hình staging ngày 21/10/2026

## Kết luận và phạm vi

**Đã tái hiện trên local:** khi bật đủ profile như script deploy, consumer
Classroom và Work restart liên tục. Lỗi poll thực tế là
`UNKNOWN_TOPIC_OR_PART (3)`, không phải bằng chứng mật khẩu SASL sai. Client
trong container xác thực được, đọc metadata của ba broker cùng cấu hình cloud.
Trước xử lý, sáu topic Work/Classroom/Identity và DLQ đang dùng không xuất hiện
trong metadata; sau tạo các topic, lỗi poll này không còn.

Log VPS được cung cấp chỉ có `Kafka consumer error` và một số lỗi kết nối SASL;
không đủ để khẳng định mọi lỗi VPS cùng nguyên nhân với local. Không đổi mật
khẩu, cơ chế SASL hoặc hạ TLS để né lỗi. Chưa truy cập hoặc deploy VPS trong lượt này.

## Cách tái hiện

Dùng `docker-compose.staging.yml`, `.env.staging` và image build từ source
hiện tại; project kiểm tra là `utask-staging-check-20261021`, PostgreSQL/Redis
có volume riêng. Chỉ đổi cổng host thành `127.0.0.1:18080` vì cổng 80 đang dùng.
Không sửa file env thật hoặc dùng Kafka Docker thay broker staging.

Profile lấy theo cách [deploy script](../../scripts/deploy_staging.sh) bổ sung
profile app từ danh sách release: Identity, Work, Classroom, Integration và AI.
Lượt chạy local trước chỉ lấy `COMPOSE_PROFILES` nên đã bỏ sót Work/Classroom;
healthcheck của subset đó không phải nghiệm thu toàn stack.

Thứ tự thực hiện: kiểm Compose/mount/image → hạ tầng → migration Django của
các backend → khởi động runtime với các profile app → kiểm HTTP/consumer.
Không tái hiện SSH/registry login; dùng image build local thay digest VPS, nên
không gọi đây là bằng chứng image đã phát hành trên VPS chạy đúng.

Tái hiện quan sát được: Classroom consumer restart ít nhất 7 lần, Work consumer
ít nhất 5 lần; có lúc lệnh `up --wait` và healthcheck báo đạt trong khi process
sau đó lại restart. Probe dùng chính Kafka client của Classroom trả mã 3.

## Phần đã khắc phục

Chuẩn bị trên broker cloud sáu topic đang dùng:

- `utask.work.events`, `utask.classroom.events`, `utask.identity.events`.
- `utask.classroom.work.dlq`, `utask.work.classroom.dlq`, `utask.work.profile.dlq`.

Chỉ tạo các topic chưa có, dùng số partition/replica mặc định của broker;
không xóa hoặc cấu hình lại topic nghiệp vụ, không thay ACL/credential.
Việc tạo topic là chuẩn bị môi trường một lần, không thêm broker/container hay
khối Kafka trong workflow. Nếu môi trường override tên topic, phải chuẩn bị
theo mapping của chính môi trường đó; không tạo song song tên mặc định để né mapping sai.

Đã cập nhật bốn command nhận event trong Work/Classroom: lỗi poll ghi tên và
mã Kafka, ví dụ `Kafka consumer error: UNKNOWN_TOPIC_OR_PART (3)`; không đưa
raw exception, password hoặc client options vào thông báo. Vẫn dừng khi lỗi
broker để không coi xử lý thất bại là thành công; không commit offset/DLQ cho
broker error. Code tại
[Classroom command](../../apps/classroom-service/apps/messaging/management/commands/consume_work.py),
[Work Identity](../../apps/work-service/apps/messaging/management/commands/consume_identity.py),
[Work Classroom](../../apps/work-service/apps/messaging/management/commands/consume_classroom.py),
[Work Integration](../../apps/work-service/apps/messaging/management/commands/consume_integration.py).

## Kiểm chứng

- Topic chẩn đoán riêng trên cùng broker: tạo bằng cấu hình cloud, producer
  bật idempotence nhận delivery ACK, consumer group chẩn đoán nhận message và
  commit offset thành công, không có poll error. Topic chẩn đoán đã xóa sau thử.
  Không phát event nghiệp vụ giả vào các topic dùng chung.
- Unit Work: **292 passed**; unit Classroom: **264 passed**. Test mới dùng lỗi
  Kafka thật để kiểm mã topic/ACL/xác thực/kết nối, không lộ raw error và luôn
  close consumer, không commit khi poll lỗi. Không coi các unit test này là
  bằng chứng credential của VPS đúng.
- Ruff check/format Work và Classroom đạt; build lại image hai service đạt.
- Đã recreate Work API/publisher/Beat/consumer và Classroom API/publisher/Beat/
  consumer bằng các image vừa build; kiểm health, restart và log sau recreate.
- HTTP qua gateway cho Identity, Work, Classroom, Integration trả 200.
  Trong đúng một container Work consumer có runner `consume_work` và hai
  tiến trình con Identity/Classroom; Integration adapter vẫn unavailable theo
  cấu hình hiện tại nên nguồn Integration không được bật.

Sau recreate, đã theo dõi hai consumer ít nhất **155 giây**: cả hai healthy,
**0 restart**, log không có `Kafka consumer error` hoặc `SASL authentication error`.
Toàn bộ runtime của stack 5 profile đạt health; migration Integration exit 0 và
`migrate --check` của bốn backend Django đạt. Các test cấu hình/CI liên quan có
36 ca được chọn: 33 đạt, 3 skipped POSIX trên Windows.

Sau kiểm chứng đã dừng project local kiểm tra, giữ volume/log để xem lại;
không để consumer local tranh partition với VPS dùng cùng group. Không dừng,
deploy hoặc đổi env VPS; không đổi file `.env.staging`, không commit. Không suy
chạy dài hạn hoặc trạng thái VPS từ kết quả này. Hai lỗi operation
Work đã báo trước (phân loại lỗi status/cleanup đồng thời) nằm ngoài thay đổi
consumer Kafka này.
