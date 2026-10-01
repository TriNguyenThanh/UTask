# Quyền sở hữu dữ liệu

Mỗi service là nơi ghi dữ liệu gốc trong phạm vi nghiệp vụ của mình. Một
service có thể lưu ID tham chiếu tới dữ liệu của service khác, nhưng không trở
thành chủ sở hữu dữ liệu đó.

| Database | Service sở hữu | Dữ liệu mục tiêu |
| --- | --- | --- |
| `identity_db` | Identity Service | Tài khoản, hồ sơ, vai trò, thông tin xác thực và phiên |
| `classroom_db` | Classroom Service | Môn học, lớp, giảng viên, sinh viên, ghi danh, nhóm và thành viên nhóm |
| `project_db` | Project Service | Project, Project Member, backlog, sprint, task, comment, label và workflow |
| `integration_db` | Integration Service | Kết nối, repository, webhook và hoạt động GitHub đã chuẩn hóa |
| `progress_db` | Progress Service | Chỉ số, tiến độ và kết quả tính toán |
| `ai_context_db` | AI Service | Bản sao đọc tối thiểu để phân tích; yêu cầu và kết quả AI nếu cần lưu |
| `notification_db` | Notification Service | Thông báo, trạng thái gửi và tùy chọn |

Tên database là tên mục tiêu. Một PostgreSQL server/cluster có thể chứa nhiều
database này.

## ID tham chiếu và quan hệ

Ví dụ, Project Service có thể lưu `class_id` và `group_id`, nhưng không tạo
foreign key sang Classroom DB. `user_id`, `project_id`, `task_id` và các ID
xuyên service khác cũng là tham chiếu logic.

## AI Context DB

AI Context DB là bản sao dữ liệu được tổ chức để đọc và phân tích. Nó không phải
dữ liệu gốc, không được ghi ngược vào nghiệp vụ và chỉ nên giữ các trường cần
cho use case AI.

Nếu Task trong Project DB có trạng thái `DONE` nhưng bản sao AI cũ ghi trạng
thái khác, Project Service vẫn là nguồn đúng. Context AI được cập nhật từ Kafka;
quy trình dựng lại bản sao phải dựa trên hợp đồng và khả năng đọc lại sự kiện đã
được quyết định, không giả định đã có sẵn.
