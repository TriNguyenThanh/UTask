# Các luồng nghiệp vụ

**Trạng thái: Thiết kế mục tiêu.** Các luồng theo
[baseline](../architecture/README.md), không xác nhận đã tích hợp runtime.

## Đăng ký và đăng nhập

```text
User → Web → Nginx → Identity API → Identity DB
                     ← JWT access token + refresh token
```

Service khác xác thực token, kiểm tra quyền tài nguyên và không đọc Identity DB.

## Tạo lớp, nhóm và project

```text
Teacher → Classroom → Classroom DB + outbox → publisher → Kafka
User → Work → Classroom API (nếu cần xác minh nhóm)
            → Work DB + outbox → publisher → Kafka
```

Classroom sở hữu lớp/nhóm/GroupMember; Work sở hữu Project/ProjectMember.
Liên kết nhóm–project chỉ dùng ID tham chiếu, không foreign key xuyên service.

## Sprint, task và tiến độ

```text
User → Work API → Work DB + outbox → publisher → Kafka
                  └── công thức/quy tắc tiến độ → dashboard qua Work API
```

Không tạo service riêng cho Project, Task, Sprint, Comment hoặc tiến độ trong
baseline ban đầu. Dashboard không cần AI để tính và hiển thị chỉ số.

## GitHub

```text
User → Integration → GitHub App installation / repository connection
GitHub webhook → Integration: verify signature + chống lặp + chuẩn hóa
               → Integration DB + outbox → publisher → Kafka
Đồng bộ theo lịch / retry → Redis → Celery worker của Integration → GitHub
```

Integration là service duy nhất gọi GitHub API.

## Yêu cầu AI

```text
User → AI API → Application → Workflow/Agent → proposal có cấu trúc
                                  │
                         Context Tool Pool / Context Layer
                                  │
                         internal API của Work / service sở hữu

User xác nhận proposal → Work: kiểm tra quyền + business rule → áp dụng
```

Context nội bộ được lọc/tổng hợp trước khi đưa cho agent. Snapshot hoặc
projection qua Kafka có thể bổ sung khi cần; AI không đọc database service khác.

Nếu chọn xử lý nền: Application giao job qua Redis tới Celery worker thuộc
AI, worker gọi workflow và lưu kết quả trong database AI. Baseline chưa chốt
trả `202` ngay cho mọi request, singleton hay kênh đẩy kết quả. Chi tiết API
v1 và khác biệt với baseline nằm trong [API AI](../ai-service/api.md).

Event hoàn tất AI có thể phục vụ Notification theo baseline; schema, topic
và quy tắc phát phải được chốt trước khi triển khai. Không dùng event làm
HTTP response cho client.

## Thông báo

```text
Domain event → Kafka → Notification consumer → Notification DB
                       └── Redis → Celery worker → email
```

In-app và email là kênh ban đầu; Web Push thuộc giai đoạn sau. Thông báo
không liên quan AI vẫn hoạt động khi AI lỗi.
