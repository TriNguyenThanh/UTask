# Integration Service

**Trạng thái tài liệu: Thiết kế mục tiêu; hiện trạng triển khai chưa xác minh.**

[Baseline](<../architecture/UTask_Architecture_Technology_Baseline (1).md>)
mục 4.4 chọn Python + Django + DRF và **GitHub App + Webhooks** làm kiến trúc
chính; Personal Access Token không phải phương án chính. OAuth đăng nhập
thuộc Identity, không thay thế quyền cài GitHub App cho repository.

Integration Service là service duy nhất được gọi trực tiếp GitHub API. Phạm vi
mục tiêu gồm GitHub App/OAuth theo quyết định sản phẩm, kết nối repository,
webhook, xác minh chữ ký, chống xử lý lặp, đồng bộ repository/commit/branch/
issue/pull request, liên kết tới Project/Task, chuẩn hóa dữ liệu và phát sự kiện
Kafka.

```text
GitHub → webhook → Integration Service → Integration DB → Kafka: github.*
```

Các service khác nhận dữ liệu GitHub đã chuẩn hóa qua sự kiện hoặc API được
Integration Service công bố; không gọi GitHub trực tiếp. `project_id` và
`task_id` là tham chiếu logic, không phải khóa ngoại xuyên database.

Đồng bộ theo lịch, retry và xử lý nặng dùng worker Celery thuộc Integration
Service; Redis chuyển job nội bộ. Lưu thay đổi và outbox cùng transaction,
publisher gửi event Kafka sau commit; xem [Kafka/outbox](../infrastructure/kafka.md).

**Cần quyết định hoặc xác minh trước khi xem là hợp đồng:** quy trình cài GitHub App;
quy tắc map repository/project/task; endpoint webhook; cơ chế xác minh
chữ ký và chống lặp; tập dữ liệu lưu; tên/schema sự kiện và service nhận sự kiện. Không endpoint
nào được xác nhận là đang chạy trong tài liệu này.
