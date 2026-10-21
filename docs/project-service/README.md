# Work Service

Phần tích hợp hồ sơ Identity đã có source và nghiệm thu local riêng; xem
[Work nhận sự kiện Identity](identity-events.md). Trạng thái dưới đây mô tả tài liệu
kiến trúc tổng quan, không phủ nhận phần tích hợp đã kiểm chứng này.

Phía Work nối repository/Task link với Integration đã có adapter HTTP,
operation/receipt bền vững, recovery và consumer trong source; kiểm thử ghép
hai backend bằng HTTP/PostgreSQL/Kafka riêng đã chạy, GitHub/Identity dùng stub.
Tính năng mặc định tắt, chưa nghiệm thu GitHub live/staging; xem
[kết nối GitHub của Work](github-integration.md).

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

Work boundary cho AI đã chốt trong
[Work AI context v1](../../contracts/api/work-ai-context-v1.yaml), được
[Work contract](../../contracts/api/work-service.yaml) tham chiếu. Các endpoint
được đánh dấu `implemented`: **Đã triển khai provider Work** và kiểm thử bằng
PostgreSQL riêng; quyền/context đã kiểm trên staging local với Identity/Classroom
thật. Luồng AI/LLM **Một phần**: một ca thành công với HTTP local, ba ca timeout;
xem [báo cáo runtime](ai-context-staging-validation-20261022.md) để biết cấu hình
smoke tạm và phần chưa nghiệm thu. Không suy ra đã triển khai VPS.
Boundary gồm POST authorize `ai.analyze` theo intent/target,
GET project/task/team/progress context và POST authorize `github.read` chỉ
dành cho caller Integration. Bearer actor và service key cùng bắt buộc;
context tối đa 65536 byte, theo shape allowlist và không chứa PII. Work tự
resolve Project từ target, tính tiến độ bằng quy tắc và kiểm quyền mỗi lần đọc.
Đội Work triển khai theo
[hướng dẫn cung cấp context cho AI](ai-service-integration-guide.md): thứ tự
công việc, ba API, mapping dữ liệu, cấu hình key và tiêu chí nghiệm thu.
Xem [điều kiện tích hợp AI](../ai-service/production-readiness.md).

Thay đổi nghiệp vụ được lưu cùng outbox, publisher Celery gửi event Kafka
sau commit. Job nội bộ như deadline scan dùng Celery + Redis thuộc Work.
AI proposal chỉ được áp dụng sau user xác nhận, kiểm tra quyền và business rule.
Xem [giao tiếp](../system/communication.md) và
[job nền](../infrastructure/background-jobs.md).

## Bàn giao tích hợp Notification

Work đã có producer sự kiện được Notification hỗ trợ và API resolve đơn/lô
để kiểm quyền, dữ liệu hiện tại. Xem
[hướng dẫn liên service](../notification-service/implementation.md) và
[checkpoint Notification](../notification-service/checkpoint-2026-10-22.md).
Không coi test provider là nghiệm thu toàn tuyến Work thật → Kafka → Gmail.
