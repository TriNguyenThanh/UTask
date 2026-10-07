# Work Service

**Trạng thái: Thiết kế mục tiêu; hiện trạng mã nguồn nghiệp vụ chưa xác minh.**
Theo [baseline](<../architecture/UTask_Architecture_Technology_Baseline (1).md>)
mục 4.2, Work là core service, dùng Python + Django + DRF và sở hữu `work_db`.

Project Service là tên cũ của cùng phạm vi; giữ thư mục tài liệu này để không
làm hỏng liên kết. Không tạo Project, Task, Sprint hoặc Comment Service riêng.

## Phạm vi

Project, ProjectMember, product backlog, Epic/UserStory, Sprint, Task/subtask,
assignment, label, Comment, Workflow, Activity History và tiến độ task/project
cùng thuộc Work vì cần transaction và quan hệ nghiệp vụ chặt.

Tiến độ được tính bằng công thức/quy tắc rõ ràng, chẳng hạn tỷ lệ task hoàn
thành; không phụ thuộc LLM. AI phân tích/giải thích hoặc đề xuất hành động,
không quyết định giá trị chỉ số. Chỉ số, cửa sổ tính và xử lý dữ liệu thiếu
cần đặc tả và test trước khi công bố API.

## Giao tiếp

Classroom sở hữu Group/GroupMember; Work sở hữu Project/ProjectMember.
Work giữ `class_id`/`group_id` làm tham chiếu logic, gọi Classroom API khi cần
xác minh; không đọc database hoặc tạo foreign key xuyên service.
Project độc lập không gắn lớp/nhóm cần quyết định sản phẩm.

Work công bố internal API lấy Project/Task context để AI dùng theo baseline.
Endpoint, auth service-to-service, quyền theo user/target, giới hạn dữ liệu và
SLA chưa được chốt; không coi tên tool AI là URL API đã có.

Thay đổi nghiệp vụ được lưu cùng outbox, publisher Celery gửi event Kafka
sau commit. Job nội bộ như deadline scan dùng Celery + Redis thuộc Work.
AI proposal chỉ được áp dụng sau user xác nhận, kiểm tra quyền và business rule.
Xem [giao tiếp](../system/communication.md) và
[job nền](../infrastructure/background-jobs.md).
