# ADR-005 — Hợp đồng Integration với Work và AI

- Ngày: 20/10/2026.
- Trạng thái: **Đã chốt thiết kế; runtime M5/M6 chưa triển khai.**
- Phạm vi: REST nội bộ Work/AI và event trạng thái connection của Integration.

## Bối cảnh

Integration đã xác minh GitHub account, installation và repository live. Work
đã có projection repository và `TaskGitHubLink`, nhưng adapter mặc định vẫn là
`UnavailableIntegration`. AI đã có Context Layer nhận domain
`github_activity`, nhưng chưa có endpoint provider và chưa gửi service key.

Việc chỉ thay adapter HTTP sẽ tạo lỗi commit lệch: Integration có thể chuẩn bị
connection trong khi Work mất quyền hoặc từ chối ghi projection. Event cũng
không được dùng để tự chấp nhận operation mà Work chưa lưu.

## Quyết định

### Caller và quyền

- Work là caller duy nhất được prepare/confirm/abort connection và xác minh
  branch, commit hoặc Pull Request. Work kiểm quyền Project/Task trước khi gọi.
- AI chỉ đọc GitHub context đã lọc. Integration hỏi Work action `github.read`
  bằng internal REST trước khi trả context; lỗi hoặc timeout phải fail closed.
- Mỗi chiều caller/callee dùng key riêng trong `X-Service-Key`. Request có actor
  forward Bearer UTask; callback async không tái sử dụng Bearer đã lưu.
- Internal path bị chặn tại gateway. Service key hoặc Bearer riêng lẻ không cấp
  quyền Project.

### Kết nối Project

Work gọi prepare với `operation_id`, action `CONNECT`/`DISCONNECT` và expected
generation. Integration kiểm idempotency, quyền GitHub live và tạo operation
`PREPARED`; response là `ConnectionFact` `PENDING`. Lời gọi GitHub không giữ
khóa database.

Work kiểm quyền/generation lần hai, rồi lưu projection, receipt và confirm hoặc
abort intent trong cùng transaction. Dispatcher Work gọi confirm idempotent.
Integration đọc receipt Work qua internal API, chỉ finalize khi Project,
operation, generation, repository và trạng thái khớp. Confirm tạo trạng thái
cuối và outbox trong cùng transaction. Pending quá 24 giờ thành `EXPIRED`; giữ
tombstone 30 ngày. Timeout phải đọc operation status trước khi retry.

`GitHubInstallation` tiếp tục chỉ là metadata hint. Connection là aggregate
riêng, giữ `installation_id` và `user_id` tham chiếu logic, không foreign key
xuyên service. Credential của actor tạo connection được dùng để kiểm provider;
revoke hoặc mất quyền làm context/reference unavailable và connection được
reconcile về `DISCONNECTED` khi có bằng chứng thu hồi.

### Reference và AI context

Reference verification chỉ chạy trên connection `CONNECTED` với repository và
generation hiện hành. Integration trả metadata allowlist; không tạo
`TaskGitHubLink` và không đổi trạng thái Task.

AI gọi REST đồng bộ để lấy `ContextDocument(domain="github_activity")`. Mỗi
loại commits, Pull Requests và issues tối đa 20 item. Thiếu một permission tạo
`partial`; connection cần kiểm lại tạo `stale`; chưa kết nối tạo `missing`.
Không chuyển token, raw provider payload, Kafka offset hoặc dữ liệu hạ tầng cho
AI. Milestone này không tạo Kafka projection cho AI.

### Kafka

Integration phát `integration.project.connection.changed` v1 sau khi confirm
thành công hoặc khi thu hồi quyền làm connection bị ngắt. Event chỉ có trạng
thái cuối `CONNECTED`/`DISCONNECTED`, key `project_id`, được ghi outbox cùng
transaction connection. Work là consumer đầu tiên, phải dedupe `event_id` và
chỉ áp dụng operation đã chấp nhận cùng generation/source version mới hơn.

Kafka không thay REST command, không cấp quyền và không tự xác nhận Task link.
Broker lỗi giữ outbox pending; không rollback mutation đã commit.

## Contract và rollout

Contract nguồn là
[`integration-service-v1.yaml`](../../contracts/api/integration-service-v1.yaml)
v1.4.0 và
[`integration.project.connection.changed.v1.json`](../../contracts/events/integration.project.connection.changed.v1.json).
Các operation mới mang trạng thái `design-approved-m5` cho đến khi source và
contract test đạt; event chỉ chuyển sang implemented sau khi publisher chạy.

Rollout theo thứ tự: migration; deploy Integration với connection/Kafka/AI
flags tắt; cấu hình key và Work callback; smoke internal REST; bật Work REST;
bật Kafka; cuối cùng bật AI context. Work phải giữ adapter unavailable làm
rollback cho tới khi E2E đạt.

## Hệ quả

- Integration có thể hoàn thiện provider side mà không sửa source Work/AI.
- Chưa được ghi “đã tích hợp runtime” cho tới khi Work dispatcher/consumer và
  AI adapter thật hoàn tất E2E.
- GitHub App cần Metadata, Contents và Pull requests read; Issues read là tùy
  chọn, thiếu quyền phải phản ánh `partial` thay vì mở rộng quyền âm thầm.
