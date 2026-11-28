# Quyền sở hữu dữ liệu

**Trạng thái: Một phần (`Đã triển khai (local)` cho `core_db` theo [ADR-006](adr/006-consolidate-core-monolith.md); tách credential toàn cluster và staging `Chưa xác minh`).** Mỗi service độc lập sở hữu dữ liệu gốc và database riêng. Ba miền lõi Identity, Classroom và Work dùng chung cơ sở dữ liệu `core_db` trong `apps/core-service` nhưng vẫn phân tách quyền sở hữu ở cấp mô-đun Django (11 app phẳng trong DAG 4 tầng). Các service ngoài (`integration-service`, `notification-service`, `ai-service`) tiếp tục giữ database tách biệt. Xem [baseline](architecture-baseline.md) và [ADR-006](adr/006-consolidate-core-monolith.md).

| Database hiện hành / mục tiêu | Service sở hữu | Dữ liệu |
| --- | --- | --- |
| `core_db` | Core Service (`apps/core-service`: Identity, Classroom, Work) | User, profile, global role, phiên/token metadata; môn học, lớp, Group/GroupMember, liên kết nhóm–project; Project/ProjectMember, backlog, Sprint, Task, Comment, Workflow, Activity và tiến độ |
| `integration_db` | Integration (`apps/integration-service`) | GitHub user/link/consent/credential, GitHub App, repository, webhook và dữ liệu GitHub đã chuẩn hóa |
| `notification_db` | Notification (`apps/notification-service`) | Notification, người nhận, trạng thái gửi, template/tùy chọn khi được chọn |
| `ai_context_db` | AI (`apps/ai-service`) | Yêu cầu, idempotency, trạng thái job, kết quả phân tích/đề xuất và context khi cần |

Tên database không chứng minh mọi migration trên staging đã được áp dụng.
`identity_db`, `classroom_db`, `work_db` là tên database riêng trước khi hợp nhất
theo [ADR-006](adr/006-consolidate-core-monolith.md); `project_db` và `progress_db`
là tên thiết kế cũ hơn. Không tạo database Progress riêng cho tiến độ Work.

## ID tham chiếu và dữ liệu đọc

Theo [ADR-004](adr/004-integration-github-account-ownership.md), Integration
sở hữu mapping tài khoản GitHub của user; Identity chỉ xác thực tài khoản
UTask/phiên qua API hiện có. `GitHubAccount.user_id` là UUID logic, không FK tới
Identity, không lấy mapping GitHub legacy/Profile làm nguồn đúng và không tự
chuyển dữ liệu cũ. Model/migration và API đọc/thu hồi mapping đã có trong
Integration. M3 có OAuth App identity-only, pending consent và provider `/user`
trong source; không lưu GitHub token. State/nonce lưu dạng hash, verifier tạm
mã hóa Fernet bằng khóa riêng Integration; consent gắn actor và chính access
Bearer đã được Identity xác minh (không có session ID từ `/users/me`).
Generation của actor chặn callback đến sau DELETE kể cả chưa có mapping.
OAuth thực tế chưa xác minh; xem [API Integration](../integration-service/api.md). Source Identity
legacy giữ nguyên, không làm dependency cho luồng Integration mới.

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

**Một phần:** script `infra/postgres/init-databases.sh` chuẩn bị bốn cơ sở dữ
liệu hiện hành theo Compose (`core_db`, `integration_db`, `notification_db`,
`ai_context_db`).
Integration M1 đã có role/login riêng qua `INTEGRATION_DB_USER` và
`INTEGRATION_DB_PASSWORD`, không nhận tài khoản quản trị trong container app.
Role không có quyền superuser/tạo database/tạo role/replication/bypass RLS,
chỉ sở hữu database và schema Integration. Bootstrap hiện chỉ tạo database còn thiếu, không tạo role hay thu hồi PUBLIC
CONNECT/TEMP; role/grant đã có trong môi trường cũ được giữ nguyên. Custom
role/DB ngoài repo cần ACL rõ ràng; không suy việc tách Integration là đã tách
toàn cluster.

Core Service (`core_db`), Notification (`notification_db`) và AI (`ai_context_db`
trong Compose root) hiện vẫn dùng credential `POSTGRES_USER`/`POSTGRES_PASSWORD`
chung, còn thiếu so với baseline về tách credential.
Kiểm tra bootstrap M1 ở [Integration foundation](../integration-service/foundation.md);
chưa xác minh database/role staging thực tế. Xem [biến môi trường](infrastructure/environment.md).

### Notification dùng credential chung theo yêu cầu hiện tại

Notification vẫn sở hữu database `notification_db`, nhưng runtime dùng chung
`POSTGRES_USER`/`POSTGRES_PASSWORD` với Core Service theo yêu cầu
đơn giản hóa. Bootstrap đã bỏ khối tạo role/ACL riêng của Notification;
không còn kiểm tra username khác quản trị. Đây là hiện trạng chưa đáp ứng
credential riêng theo baseline, không cấp phép đọc DB service khác trong code.
Role/ACL đã tồn tại trong volume cũ không bị xóa hoặc sửa tự động.
