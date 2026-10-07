# Kiến trúc UTask

**Trạng thái: Thiết kế mục tiêu.** Tài liệu được cập nhật theo
[architecture baseline](../architecture/README.md), mục 2–4 và 26–29.
Không xác nhận các service hoặc luồng nghiệp vụ đã chạy.

## Các thành phần

UTask dùng coarse-grained microservices: chia service theo nhóm nghiệp vụ
lớn, không chia theo bảng hay entity. Work là core domain (nghiệp vụ trung tâm).

```text
Web → Nginx / reverse proxy
       ├── Identity Service
       ├── Work Service
       ├── Classroom Service
       ├── Integration Service → GitHub
       ├── Notification Service → email / kênh thông báo
       └── AI Service → nhà cung cấp LLM

Hạ tầng: PostgreSQL · Kafka · Redis · Cloudflare R2 ở production
```

| Service      | Phạm vi sở hữu                                                                                                                        |
| ------------ | ------------------------------------------------------------------------------------------------------------------------------------- |
| Identity     | User, profile, global role, xác thực, access/refresh token và OAuth đăng nhập                                                         |
| Work         | Project, ProjectMember, backlog, Epic/UserStory, Sprint, Task, assignment, label, Comment, Workflow, Activity và tiến độ task/project |
| Classroom    | Môn học, lớp, giảng viên/sinh viên, Group/GroupMember, điểm danh, điểm số và liên kết nhóm–project                                    |
| Integration  | GitHub App, repository, webhook, commit/branch/issue/PR và mapping task–GitHub                                                        |
| Notification | Bản ghi thông báo, người nhận, kênh và trạng thái gửi                                                                                 |
| AI           | Yêu cầu, context phục vụ phân tích và kết quả đề xuất; không sở hữu dữ liệu nghiệp vụ gốc                                             |

Work Service có tên triển khai `work-service`. Tên Project Service trong tài
liệu cũ chỉ cùng service này, không phải một microservice riêng. Giữ đường
dẫn [docs/project-service/](../project-service/README.md) để bảo toàn liên kết.

Tiến độ task/project thuộc Work; tính bằng công thức/quy tắc rõ ràng, không
phụ thuộc AI. Không triển khai Progress Service riêng trong baseline ban đầu.
Analytics và Realtime là khả năng giai đoạn sau khi có nhu cầu; chưa tạo
service hoặc hạ tầng cho chúng chỉ từ sơ đồ mục tiêu.

## Quan hệ Classroom và Work

Classroom sở hữu Group/GroupMember; Work sở hữu Project/ProjectMember.
Hai quan hệ không thay thế nhau. `class_id`, `group_id`, `user_id` là tham
chiếu logic; kiểm tra qua API công bố khi cần, không join database service khác.

Classroom quản lý liên kết nhóm–project trong nghiệp vụ lớp học; Work giữ ID
tham chiếu của project và nhóm. Chi tiết đồng bộ, ma trận quyền giảng viên và
hỗ trợ project độc lập cần hợp đồng sản phẩm/API, không suy ra từ baseline.

## Công nghệ và runtime

Backend nghiệp vụ dùng Django + DRF, AI dùng FastAPI + Google ADK, Web dùng
React + Vite + TypeScript. Mỗi service có package/dependency và Docker image
riêng. Một service có thể có API process, Celery worker và Kafka consumer;
worker không tự trở thành một service mới và không bắt buộc singleton.

- REST: command/query cần phản hồi trực tiếp.
- Celery + Redis: job nội bộ service.
- Kafka: sự kiện giữa các service; dùng outbox khi lưu thay đổi và phát event.
- R2: lưu file production qua S3-compatible API; local dùng filesystem.

Chi tiết nằm trong [giao tiếp](communication.md) và
[hạ tầng](../infrastructure/README.md).

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

[ADR cập nhật baseline](../adr/001-adopt-architecture-baseline.md) ghi việc
thay Project/Progress bằng Work và cập nhật cách lấy context AI. Contract
đã chốt được kiểm tra riêng; không tự đổi URL, producer hoặc envelope bằng
cách thay tên trong tài liệu.
