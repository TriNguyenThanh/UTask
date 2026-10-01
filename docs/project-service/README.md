# Project Service

**Tên triển khai hiện tại có thể là `work-service`; trạng thái mã nguồn chưa
được xác minh trong lần chuẩn hóa tài liệu này.** Tài liệu kiến trúc dùng tên
Project Service.

Project Service quản lý việc thực hiện dự án: Project, Project Member, backlog,
sprint, task/subtask, assignment, comment, label, milestone, workflow và activity.
Các đối tượng này cùng thuộc một service; không tách Task, Sprint hoặc Comment
thành microservice riêng.

Project có thể tham chiếu `class_id` và `group_id`. Classroom Service vẫn sở hữu
lớp và nhóm; không tạo foreign key xuyên database. `GroupMember` mô tả nhóm học
tập, còn `ProjectMember` mô tả vai trò trong dự án.

Project độc lập không gắn lớp/nhóm có được hỗ trợ hay không là **Cần quyết
định** theo yêu cầu sản phẩm; tài liệu này không tự giả định.

Khi cần xác minh lớp hoặc nhóm đồng bộ, Project Service gọi API Classroom
Service. Thay đổi project, sprint và task được thông báo cho service khác qua
Kafka. Hợp đồng API và sự kiện chưa được xác nhận trong tài liệu này.
