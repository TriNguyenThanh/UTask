# Kiến trúc UTask

Tài liệu này ghi lại **thiết kế mục tiêu** theo yêu cầu kiến trúc hiện hành.
Nó không xác nhận thiết kế đã được triển khai trong mã nguồn.

## Các thành phần

UTask chia service theo nhóm nghiệp vụ lớn. Không tách service theo từng bảng.

```text
Người dùng
    │
Web Application ── API Gateway / Nginx
    │                    │
    ├── Identity Service ├── Classroom Service
    ├── Project Service  ├── Integration Service ── GitHub
    ├── Progress Service ├── AI Service ── nhà cung cấp LLM
    └── Notification Service ── email / nhà cung cấp push
              │
       PostgreSQL · Kafka · Redis
```

Các service nghiệp vụ:

| Service | Phạm vi sở hữu |
| --- | --- |
| Identity Service | Tài khoản, hồ sơ, vai trò toàn hệ thống, xác thực và phiên đăng nhập |
| Classroom Service | Môn học, lớp, giảng viên, sinh viên, ghi danh, nhóm và thành viên nhóm |
| Project Service | Project, thành viên dự án, backlog, sprint, task, bình luận và workflow |
| Integration Service | Kết nối GitHub, repository, webhook và dữ liệu GitHub đã chuẩn hóa |
| Progress Service | Chỉ số, tiến độ và tín hiệu rủi ro tính theo quy tắc rõ ràng |
| AI Service | Yêu cầu AI, bản sao dữ liệu phục vụ phân tích và kết quả gợi ý |
| Notification Service | Bản ghi thông báo, trạng thái gửi, kênh và tùy chọn thông báo |

Tên triển khai `work-service`, nếu còn được dùng, tương ứng với **Project
Service** trong kiến trúc mục tiêu. Không đổi tên thư mục hoặc mã nguồn trong
một thay đổi chỉ về tài liệu.

## Quan hệ Classroom và Project

```text
Teacher → Class → Group → Project → Sprint → Task
```

Classroom Service sở hữu Teacher, Class, Group và Group Member. Project Service
sở hữu Project, Project Member, Sprint và Task. `GroupMember` cho biết người
học thuộc nhóm nào; `ProjectMember` mô tả vai trò của một người trong dự án.
Hai quan hệ này không thay thế cho nhau. Giảng viên xem dự án thông qua quan hệ
giảng viên → lớp → nhóm → dự án, không cần trở thành Project Member.

## Các ranh giới phải giữ

- Mỗi service sở hữu dữ liệu và database riêng. Có thể dùng chung cụm
  PostgreSQL, nhưng không đọc chéo database và không tạo khóa ngoại xuyên
  service.
- Service khác chỉ giữ ID tham chiếu như `user_id`, `class_id` hoặc `group_id`.
- Project, Task, Sprint, Comment và các chức năng workflow cùng thuộc Project
  Service; không tách thành service riêng nếu chưa có quyết định nghiệp vụ mới.
- Integration Service là service duy nhất gọi GitHub API.
- Progress Service tự tính số liệu; dashboard không phụ thuộc AI.
- AI Service là service nội bộ. OpenAI, Gemini hoặc nhà cung cấp mô hình ngôn
  ngữ lớn (LLM) khác là hệ thống bên ngoài.
- AI chỉ đề xuất. Thay đổi dữ liệu nghiệp vụ phải được người dùng xác nhận và
  thực hiện qua service sở hữu dữ liệu.
- Lỗi AI hoặc nhà cung cấp LLM chỉ làm giảm khả năng AI, không chặn đăng nhập,
  quản lý lớp, project, task, tích hợp GitHub, dashboard hay thông báo chính.

Không thêm service hoặc công nghệ mới nếu chưa có quyết định kiến trúc được
ghi nhận.
