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
Theo [baseline](<../system/architecture-baseline.md>)
mục 4.2, Work là core service, dùng Python + Django + DRF và sở hữu `work_db`.

Project Service là tên cũ của cùng phạm vi; giữ thư mục tài liệu này để không
làm hỏng liên kết. Không tạo Project, Task, Sprint hoặc Comment Service riêng.

Tài liệu cùng service: [đặc tả API](api-specification.md),
[sơ đồ Work](diagram/README.md), [liên kết Classroom–Work](classroom-project-linking.md),
[tích hợp Identity](identity-events.md) và [tích hợp GitHub](github-integration.md).

## Phạm vi

Project, ProjectMember, product backlog, Epic/UserStory, Sprint, Task/subtask,
assignment, label, Comment, Workflow, Activity History và tiến độ task/project
cùng thuộc Work vì cần transaction và quan hệ nghiệp vụ chặt.

Tiến độ được tính bằng công thức/quy tắc rõ ràng, chẳng hạn tỷ lệ task hoàn
thành; không phụ thuộc LLM. AI phân tích/giải thích hoặc đề xuất hành động,
không quyết định giá trị chỉ số. Chỉ số, cửa sổ tính và xử lý dữ liệu thiếu
cần đặc tả và test trước khi công bố API.

**Bổ sung Đợt 3 đã triển khai trong mã nguồn (kiểm thử local trên PostgreSQL 16; chưa xác minh staging):**
- Tổng hợp cá nhân xuyên dự án trong `work_db`: `GET /me/tasks/` và `GET /me/overview/` (`work-metrics-v1`).
- Giám sát dự án theo lớp cho giảng viên với tín hiệu rủi ro tất định (xác minh phạm vi từ Classroom internal API, fail-closed `503`): `GET /teacher/oversight/projects/` (dựa trên `Project.last_activity_at` cập nhật tự động qua `record_activities`).
- Làm giàu thẻ `/projects/{id}/kanban/` (19 trường, 5 bộ lọc mới gồm `include_subtasks` mặc định `false`), mở `GET /projects/{id}/activities/` (chỉ mục `Activity.scope_project`) và lọc `?is_teacher_feedback=true|false` cho bình luận. Hợp đồng chuẩn cập nhật tại [Work contract](../../contracts/api/work-service.yaml).

**Bổ sung Đợt 5 phía Work đã triển khai trong mã nguồn (kiểm thử local trên PostgreSQL 16 + Redis 7 + Kafka Cloud với HTTP stub đúng hợp đồng; chờ provider thật từ Team AI & Team Integration; chưa xác minh staging):**
- Adapter xác thực AI proposal thật `RemoteProposals` ([infrastructure/ai.py](../../apps/work-service/infrastructure/ai.py)) gọi `POST {WORK_AI_BASE_URL}/api/ai/v1/internal/requests/{proposal_id}/verify-proposal` ngoài DB transaction (chuyển tiếp actor Bearer + `X-Service-Key`), hỗ trợ `BACKLOG` (`AI_BACKLOG`) và `SUBTASK` (`AI_DECOMPOSED`), hoãn `ACTION` sang AI v2 theo DG5; giữ `WORK_AI_ADAPTER=infrastructure.ai.UnavailableProposals` mặc định an toàn.
- Consumer `utask.integration.events` ([integration_consumer.py](../../apps/work-service/apps/messaging/integration_consumer.py)) định tuyến đủ 3 sự kiện: `integration.project.connection.changed`, `integration.github.account.changed` (gọi `apply_account_fact()` cập nhật `ProjectMember.is_github_verified`) và `integration.github.reference.detected` (giải mã `task_code` → `ingest_reference()` tạo ứng viên `TaskGitHubLink` ở trạng thái `PENDING`).
- Public BFF `GET /projects/{project_id}/github/activity/` trả ngay `DISCONNECTED`/`PENDING` từ `work_db`, còn khi `CONNECTED` gọi `RemoteIntegration.fetch_project_activity()` kèm cache Redis ngắn (`WORK_GITHUB_ACTIVITY_CACHE_TTL_SECONDS`, mặc định 45 giây; chỉ cache `CONNECTED`/`PARTIAL`, không cache `STALE`/`REAUTH_REQUIRED`) và luôn gộp mới `linked_task_ids` từ các `TaskGitHubLink(confirmation_status="CONFIRMED")`. Hợp đồng đối tác chi tiết xem tại [hướng dẫn bàn giao Team AI & Integration](../system/ai-integration-team-handoff-guide.md).

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
[job nền](../system/infrastructure/background-jobs.md).

## Bàn giao tích hợp Notification

Work đã có producer sự kiện được Notification hỗ trợ và API resolve đơn/lô
để kiểm quyền, dữ liệu hiện tại. Xem
[hướng dẫn liên service](../notification-service/implementation.md) và
[checkpoint Notification](../notification-service/checkpoint-2026-10-22.md).
Không coi test provider là nghiệm thu toàn tuyến Work thật → Kafka → Gmail.
