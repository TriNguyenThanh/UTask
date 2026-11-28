# Kiến trúc UTask

**Trạng thái: Một phần (`Đã triển khai (local)` cho `core-service`; thiết kế mục tiêu cho toàn hệ thống và staging `Chưa xác minh`).** Tài liệu kết hợp [architecture baseline](architecture-baseline.md) với quyết định hợp nhất ba miền lõi tại [ADR-006](adr/006-consolidate-core-monolith.md). Không suy luận mọi service hoặc môi trường staging đã nghiệm thu hoàn chỉnh.

## Các thành phần

UTask áp dụng kiến trúc lai giữa **Modular Monolith (nguyên khối phân tách mô-đun)** cho ba miền nghiệp vụ lõi và **coarse-grained microservices** cho các dịch vụ biên độc lập. Work là core domain (nghiệp vụ trung tâm).

```text
Web → Nginx / reverse proxy
       ├── Core Service (`apps/core-service`, alias: identity-service, classroom-service, work-service)
       │     ├── Miền Identity (`/api/auth/*`)
       │     ├── Miền Classroom (`/api/classroom/*`)
       │     └── Miền Work (`/api/work/*`)
       ├── Integration Service → GitHub
       ├── Notification Service → email / kênh thông báo
       └── AI Service → nhà cung cấp LLM

Hạ tầng: PostgreSQL · Kafka · Redis · Cloudflare R2 ở production
```

| Service / Miền | Phạm vi sở hữu |
| --- | --- |
| **Core Service** (`apps/core-service`) — **Identity** | User, profile, global role, xác thực, access/refresh token và OAuth đăng nhập |
| **Core Service** (`apps/core-service`) — **Work** | Project, ProjectMember, backlog, Epic/UserStory, Sprint, Task, assignment, label, Comment, Workflow, Activity và tiến độ task/project |
| **Core Service** (`apps/core-service`) — **Classroom** | Môn học, lớp, giảng viên/sinh viên, Group/GroupMember, điểm danh, điểm số và liên kết nhóm–project |
| **Integration** (`apps/integration-service`) | GitHub user/link/consent/credential, GitHub App, kết nối kỹ thuật repository, webhook, commit/branch/issue/PR và dữ kiện/ứng viên mapping task–GitHub |
| **Notification** (`apps/notification-service`) | Bản ghi thông báo, người nhận, kênh và trạng thái gửi |
| **AI** (`apps/ai-service`) | Yêu cầu, context phục vụ phân tích và kết quả đề xuất; không sở hữu dữ liệu nghiệp vụ gốc |

Theo [ADR-004](adr/004-integration-github-account-ownership.md), mapping
GitHub cá nhân nằm ở Integration. Identity xác thực tài khoản UTask/phiên qua
API hiện có; luồng Integration mới không phụ thuộc OAuth mapping legacy của Identity.

Work Service có tên triển khai `work-service`. Tên Project Service trong tài
liệu cũ chỉ cùng service này, không phải một microservice riêng. Giữ đường
dẫn [docs/project-service/](../project-service/README.md) để bảo toàn liên kết.

Work sở hữu liên kết Task–GitHub đã xác nhận và quyền thay đổi repository
của Project. Integration thực hiện kết nối kỹ thuật theo Work command, cung
cấp dữ kiện GitHub và không tự sửa Task. Ma trận quyền và phạm vi thu thập
GitHub ở [Integration: phạm vi và quyền](../integration-service/scope-access.md).

Tiến độ task/project thuộc Work; tính bằng công thức/quy tắc rõ ràng, không
phụ thuộc AI. Không triển khai Progress Service riêng trong baseline ban đầu.
Analytics và Realtime là khả năng giai đoạn sau khi có nhu cầu; chưa tạo
service hoặc hạ tầng cho chúng chỉ từ sơ đồ mục tiêu.

## Quan hệ Identity, Classroom và Work trong Core Service

Theo [ADR-006](adr/006-consolidate-core-monolith.md), ba miền Identity, Classroom
và Work chạy trong cùng một Django Modular Monolith (`apps/core-service`) trên cơ
sở dữ liệu thống nhất `core_db`, nhưng vẫn giữ ranh giới sở hữu rõ ràng ở cấp
mô-đun:

- Classroom sở hữu Group/GroupMember và liên kết nhóm–project trong nghiệp vụ lớp
  học; Work sở hữu Project/ProjectMember; Identity sở hữu User/Profile/Role/Session.
- Các miền bên trong `core-service` giao tiếp đồng bộ trong tiến trình (in-process)
  qua các module giao diện công khai (`apps.accounts.interface`,
  `apps.groups.interface`, `apps.projects.interface`) thay vì gọi HTTP hoặc đẩy
  Kafka nội bộ; không tự ý truy vấn trực tiếp bảng thuộc quyền sở hữu của miền
  khác (được kiểm soát bởi `tests/test_architecture_boundaries.py`).
- Với các service bên ngoài (`ai-service`, `integration-service`,
  `notification-service`), `core-service` vẫn giữ nguyên ranh giới vật lý qua
  REST nội bộ (nhờ Docker network aliases `identity-service`, `classroom-service`,
  `work-service`) và Kafka outbox/consumer.

## Công nghệ và runtime

Backend nghiệp vụ dùng Django + DRF, AI dùng FastAPI + Google ADK, Web dùng
React + Vite + TypeScript. Mỗi service có package/dependency và Docker image
riêng. Một service có thể có API process, Celery worker và Kafka consumer;
worker không tự trở thành một service mới và không bắt buộc singleton.

AI Service đã chọn tách đường nhận HTTP và thực thi AI: API tiếp nhận request,
dispatcher giao job qua Redis, Celery worker chạy application/workflow và lưu
kết quả vào PostgreSQL của AI. API và worker dùng chung code nghiệp vụ và
persistence của cùng service; client đọc kết quả qua API. Kafka consumer chỉ
thêm khi có use case/event contract, chạy ngoài vòng suy luận. Quyết định tại
[ADR-002](adr/002-ai-request-pipeline.md); pipeline chi tiết tại
[kiến trúc AI](../ai-service/architecture.md). Đây là thiết kế mục tiêu,
bootstrap chưa có các process/persistence này.

- REST: command/query cần phản hồi trực tiếp.
- Celery + Redis: job nội bộ service.
- Kafka: sự kiện giữa các service; dùng outbox khi lưu thay đổi và phát event.
- R2: lưu file production qua S3-compatible API; local dùng filesystem.

Chi tiết nằm trong [giao tiếp](communication.md) và
[hạ tầng](infrastructure/README.md).

## Ranh giới phải giữ

- Database và credential riêng theo service, có thể cùng PostgreSQL cluster.
  Không đọc chéo database, không tạo foreign key xuyên service.
- Service sở hữu tài nguyên kiểm tra quyền nghiệp vụ ở backend; Nginx là
  reverse proxy, không thay thế kiểm tra permission của service.
- Integration là service duy nhất gọi trực tiếp GitHub API.
- AI lấy context qua internal API được service sở hữu công bố, đặt sau Context
  Layer/domain tool. Projection qua event là tối ưu tùy nhu cầu; agent không
  tự gọi HTTP tùy ý hoặc truy cập database service khác.
- AI chỉ đề xuất. User xác nhận; Work/service sở hữu dữ liệu kiểm tra quyền
  và business rule rồi áp dụng thay đổi.
- Lỗi AI không chặn auth, quản lý lớp/project/task, dashboard hoặc thông báo
  chính. Work vẫn cung cấp tiến độ khi AI hoặc LLM lỗi.

Production dùng container ứng dụng không giữ dữ liệu bền vững trong memory,
hạ tầng PostgreSQL/Redis/Kafka bên ngoài và R2. Kubernetes, Debezium, Keycloak,
service mesh hoặc realtime service riêng chỉ thêm khi có nhu cầu và quyết định.

## Chuyển từ thiết kế cũ

[ADR cập nhật baseline](adr/001-adopt-architecture-baseline.md) ghi việc
thay Project/Progress bằng Work và cập nhật cách lấy context AI.
[ADR-006](adr/006-consolidate-core-monolith.md) ghi quyết định hợp nhất
Identity, Classroom và Work thành `apps/core-service` (Modular Monolith trên
`core_db`) đồng thời giữ nguyên 100% đường dẫn Gateway, Docker aliases, Kafka
producer và tệp hợp đồng trong `contracts/api/`. Contract đã chốt được kiểm tra
riêng; không tự đổi URL, producer hoặc envelope bằng cách thay tên trong tài liệu.
