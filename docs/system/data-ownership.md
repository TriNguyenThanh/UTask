# Quyền sở hữu dữ liệu

**Trạng thái: Thiết kế mục tiêu.** Theo baseline mục 8, mỗi service sở hữu dữ
liệu gốc và database riêng. Có thể dùng chung PostgreSQL server/cluster,
nhưng database user/credential phải riêng và chỉ có quyền trong phạm vi service.
Xem [baseline](../architecture/README.md).

| Database mục tiêu | Service sở hữu | Dữ liệu                                                                                             |
| ----------------- | -------------- | --------------------------------------------------------------------------------------------------- |
| `identity_db`     | Identity       | User, profile, global role, phiên/token metadata                                                    |
| `work_db`         | Work           | Project/ProjectMember, backlog, Sprint, Task, Comment, Workflow, Activity và tiến độ                |
| `classroom_db`    | Classroom      | Môn học, lớp, Group/GroupMember, điểm danh/điểm số và liên kết nhóm–project                         |
| `integration_db`  | Integration    | GitHub App, repository, webhook và dữ liệu GitHub đã chuẩn hóa                                      |
| `notification_db` | Notification   | Notification, người nhận, trạng thái gửi, template/tùy chọn khi được chọn                           |
| `ai_context_db`   | AI             | Tên thiết kế riêng của AI cho yêu cầu/kết quả và context khi cần; baseline chưa đặt tên database AI |

Tên database không chứng minh database hoặc migration đã tồn tại.
`project_db` và `progress_db` là tên thiết kế cũ, không phải mục tiêu triển
khai theo baseline mới. Không tạo database Progress riêng cho tiến độ Work.

## ID tham chiếu và dữ liệu đọc

Các ID xuyên service như `user_id`, `group_id`, `project_id` chỉ là tham
chiếu logic, không phải foreign key. Khi cần xác minh đồng bộ, dùng API của
service sở hữu. Khi thường xuyên cần tên/avatar hoặc dữ liệu đọc khác, có
thể giữ local projection (bản sao chỉ các trường cần thiết), đồng bộ bằng event.

AI lấy Project/Task context qua internal API của Work theo baseline. Nếu lưu
snapshot/projection ở AI, dữ liệu đó phục vụ phân tích và audit, không thay
thế dữ liệu nguồn hay bằng chứng phân quyền. Chỉ số tiến độ được Work tính
bằng quy tắc; AI có thể giải thích nhưng không quyết định giá trị nguồn.

Schema job, result, context và retention chi tiết nằm tại
[ERD AI](../ai-service/erd.md); chưa có migration hoặc database client.
Không coi toàn bộ các bảng projection cũ là bắt buộc nếu internal API đã đáp
ứng use case.

Trong [pipeline AI đã chốt](../ai-service/architecture.md), API và Celery
worker thuộc cùng AI Service nên dùng chung PostgreSQL của AI qua repository.
Persistence AI giữ request, idempotency, ý định giao job, trạng thái và kết
quả; Redis là broker, không thay thế bản ghi bền vững. Worker lưu kết quả,
API kiểm tra ownership và đọc lại cho client. Outbox event kết quả chỉ thêm
khi có contract; projection context vẫn tùy use case. Schema giao job,
phục hồi worker và dead-letter cần thiết kế trước migration.

## Hiện trạng hạ tầng

**Một phần:** script PostgreSQL hiện tạo năm database nghiệp vụ theo Compose;
chưa tạo database AI hoặc credential/role riêng. Local/staging đang dùng
chung tài khoản PostgreSQL. Đây là khoảng trống so với baseline, xem
[biến môi trường](../infrastructure/environment.md). Không sửa dữ liệu hoặc
migration trong lần cập nhật tài liệu này.
