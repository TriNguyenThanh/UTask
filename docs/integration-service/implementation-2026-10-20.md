# Biên bản triển khai provider Work/AI — 20/10/2026

**Trạng thái: Đã triển khai và kiểm thử phía Integration; chưa nghiệm thu
tích hợp Work/AI thật.** Thực hiện theo [plan](plans/plan.md) tại nhánh
`feat/integration-service`, HEAD đầu phiên `b81ab01`. Plan là snapshot được
người dùng cung cấp; giữ nguyên nội dung. Thay đổi chưa commit, không deploy
staging/production và không sửa source Work/AI.

**Cập nhật sau khắc phục:** lỗi P2 budget publisher sau claim chậm đã sửa;
906 test Integration/PostgreSQL và 125 test hạ tầng đạt. Kafka thật dừng /
khởi động lại/replay đạt, broker dừng trả về sau 25,08 giây; image
`utask/integration-service:timeout-check` build và smoke API/worker/Beat đạt.
Xem [review](review-2026-10-20.md) và
[checkpoint mới nhất](checkpoint-2026-10-20.md). Các kết quả 887/106 bên dưới
được giữ như bằng chứng của lượt triển khai trước khắc phục.

## Kết quả triển khai

- App `github_connections`: aggregate Project, operation idempotent/CAS,
  prepare/confirm/abort/status, snapshot prepare bất biến, receipt Work và
  TTL/tombstone. Binding đã confirm được giữ riêng reservation; abort/expire
  không mất receipt hoặc tái sử dụng generation đã dành.
- Internal service keys theo caller; actor xác minh qua Identity. Work client
  đọc receipt và authorize, timeout 2/3 giây, không redirect, không network
  trong transaction; lỗi/sai schema từ chối thay vì cho phép.
- GitHub project client tách khỏi discovery M4: tìm repo live, metadata,
  branch/commit/PR, context giới hạn 20 item/loại; schema/URL/time/body budget
  được kiểm chặt. Credential generation/version và provider/project revision
  chặn response cũ qua mutation đồng thời.
- Revoke account/authorization, uninstall/suspend/repository removed ngắt
  connection và ghi outbox nguyên tử. Positive event chỉ yêu cầu revalidation.
- Outbox Kafka bền vững, head từng Project, lease/CAS/retry/replay, cleanup
  chỉ event đã publish. Flags connection/Kafka/AI mặc định tắt; Compose/env,
  topic local và certificate mount được bổ sung cho Integration.
- OpenAPI 1.4/event v1 đánh dấu provider `implemented`; guide Work/AI,
  ADR-005 và tài liệu vận hành phân biệt source với integration thật.

## Bằng chứng kiểm tra trong phiên

- **887 test Integration đạt** trên PostgreSQL 16 tạm, các database tên
  `integration_*_test`, cổng loopback tự cấp. Unit/contract, API, concurrency,
  lifecycle, retention và outbox nằm trong cùng suite; không chạy pytest vào
  database runtime.
- **106 test script/hạ tầng đạt**, gồm Integration, local/staging Compose,
  Kafka profile, AI/Classroom và smoke M4. Compose render bằng `.env.example`,
  có/không broker tùy chọn; kiểm thêm JSON inbound keys qua bốn process.
- **E2E HTTP localhost đạt**: Work driver → Integration live server →
  Identity/GitHub/Work stub thật qua socket; confirm receipt → event; AI
  reader → Work authorize → GitHub context. Chỉ rewrite host provider về stub
  trong test; không giả kết quả semantic của adapter. Kafka trong ca CI này
  dùng MemoryBroker, không phải broker thật.
- **Kafka thật đạt** với apache/kafka 3.9.0 và dữ liệu tổng hợp trong database
  riêng: nhận bốn ID gốc theo sequence 1–4, cùng Project key/partition, offset
  tăng và envelope đúng JSON Schema. Dừng broker test làm sequence3 pending,
  sequence4 chưa gửi; restart/replay gửi tiếp cùng ID. Cuối ca bốn row
  PUBLISHED; sequence3 thử hai lần. Không thao tác broker runtime.
- Ruff lint/format, Django check, migration drift, apply → rollback → apply
  hai migration connection trên database riêng đạt. Image
  `utask/integration-service:connections-check` build thành công; migrate/check
  trên database image riêng đạt, health 200, thiếu Bearer 401, sai caller 403,
  ba task Beat đã đăng ký và librdkafka import thành công.

Review phát hiện và đã sửa: receipt binding bị cleanup sau reconnect thất bại,
operation ID `.`/`..` không thống nhất với Work adapter, default branch vượt
giới hạn contract, JSON lồng sâu và timestamp sai định dạng. Regression tests
được thêm cùng sửa; review lại không thấy lỗi tác động cao trong các nhánh đó.

## Phần chưa nghiệm thu

- Work HTTP adapter, receipt/authorize endpoint, durable dispatcher, Kafka
  consumer và AI service-key adapter thật: thực hiện theo
  [guide Work](work-service-integration-guide.md), [guide AI](ai-service-integration-guide.md).
- GitHub dev theo luồng Project mới: connect, verify branch/commit/PR, đổi
  quyền, revoke và reconnect; các ca M4 cũ không thay bằng chứng này.
- Kafka SASL/TLS/cloud, crash ngay sau ACK, staging/production và rollout flags.
  At-least-once có thể tạo duplicate cũ; consumer phải dedupe và chặn version cũ.

Chi tiết cấu hình, khóa, TTL, replay và rollout là nguồn chuẩn tại
[vận hành provider](runtime-connections.md). Không đổi trạng thái thành
“đã tích hợp runtime” trước E2E với service thật.

## Giới hạn phân tích graph

GitNexus đã refresh PDG với runner 1.6.12/schema4 tại HEAD `b81ab01`; status
runner current, không có incomplete reasons. `detect_changes` được chạy với
index Git tạm để tính cả file mới, không stage vào index người dùng. Kết quả
báo **CRITICAL**, có flow web/Work/Classroom không liên quan từ symbol tên
chung như `allowed_callers`; quá trình index cũng cảnh báo cắt bớt execution
flows. Không dùng các quan hệ này làm bằng chứng bao phủ hoặc gate an toàn
sạch. Đã đối chiếu source, kiểm thử hồi quy và review độc lập các điểm
credential/webhook, transaction/CAS và contract. Không commit trong phiên.
