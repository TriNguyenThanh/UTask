# ADR-001 — Đồng bộ tài liệu với architecture baseline

- Ngày: 2026-10-07.
- Trạng thái: Thiết kế mục tiêu được cập nhật theo yêu cầu dùng baseline;
  chưa triển khai thay đổi runtime hoặc migration contract.
- Nguồn: [UTask Architecture & Technology Baseline 1.0](<../architecture/UTask_Architecture_Technology_Baseline (1).md>).

## Bối cảnh

Tài liệu trước dùng Project Service và Progress Service riêng, bắt buộc AI
lấy context qua projection Kafka. Baseline mới đặt Project/Task/Sprint/Comment
và tiến độ trong Work, cho AI gọi internal API, chọn Celery + Redis cho job
nội bộ và Kafka cho event giữa service. Người dùng yêu cầu dùng baseline để
cập nhật tài liệu; không yêu cầu triển khai mã nguồn.

## Các lựa chọn

Giữ thiết kế cũ sẽ duy trì hai nguồn chuẩn khác nhau. Theo yêu cầu cập nhật
bằng baseline, chọn đồng bộ tài liệu về Work và internal-context API, đồng
thời giữ version contract cũ để có kế hoạch chuyển đổi rõ ràng.

## Quyết định

1. Dùng Work làm tên kiến trúc và `work_db` làm database nghiệp vụ mục tiêu;
   Project là phạm vi bên trong Work. Giữ đường dẫn tài liệu project-service
   và progress-service làm điểm tương thích liên kết.
2. Đặt tiến độ task/project ở Work, tính bằng quy tắc và không phụ thuộc AI.
   Analytics/Realtime thuộc giai đoạn sau theo nhu cầu.
3. AI lấy context qua internal API của service sở hữu, sau Context Layer/domain
   tool có kiểm soát quyền. Projection/snapshot chỉ thêm khi có use case;
   agent không được gọi HTTP tùy ý hay database service khác.
4. Job nội bộ dùng Celery + Redis; worker thuộc service sở hữu nghiệp vụ.
   Kafka truyền sự kiện giữa service. Baseline chưa ấn định worker singleton
   hoặc bắt mọi request AI phải trả `202` ngay.
5. Dùng các chuẩn baseline về JWT, database credential riêng, GitHub App,
   outbox, R2, trace ID, kiểm thử và phát hành làm thiết kế mục tiêu.

## Hệ quả và công việc tiếp theo

- AI bootstrap, Compose và hợp đồng YAML hiện hữu không được thay đổi runtime
  trong lần cập nhật tài liệu này. Không suy ra implementation từ baseline.
- API AI v1 giữ payload, URL, ngưỡng chờ đồng bộ và polling đã chốt. Cơ chế
  gateway-auth và internal-context API cần đối chiếu hợp đồng auth/API trước
  khi implementation; không tin identity header từ client.
- `ai-context-v1.yaml` có producer Project/Progress và envelope cũ; chưa áp
  dụng nguyên trạng cho Work. Cần version hoặc mapping, test contract và
  kế hoạch chuyển đổi nếu tiếp tục dùng projection Kafka.
- Event kết quả AI theo baseline chưa có schema; phải chốt producer, payload,
  topic, service nhận và quyền dữ liệu trước khi tạo contract/runtime.
- Credential database local/staging đang dùng chung; cần role/credential riêng
  trước khi đáp ứng baseline production. Không sửa database trong task này.
- Đồng bộ quy tắc agent với tài liệu chuẩn, không sao chép kiến trúc dài vào
  AGENTS hoặc skill. Khi skill cũ khác baseline, dùng quyết định này theo
  instruction người dùng và cập nhật workflow cần thiết trước khi sửa code.
