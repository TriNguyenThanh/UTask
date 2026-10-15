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
User → AI API / Application
    → kiểm tra identity, input, quyền qua internal REST API và idempotency
    → AI DB: request queued + bản ghi chờ giao job
    → dispatcher → Redis → Celery worker của AI
    → Application → Workflow/Agent → proposal có cấu trúc
                      ↕
              Context Tool Pool / Context Layer
                      → internal REST API của Work / service sở hữu
    → lưu succeeded/result hoặc failed/error vào AI DB

User GET polling → AI API: kiểm tra ownership → đọc AI DB → status/result

User xác nhận proposal → Work: kiểm tra quyền + business rule → áp dụng
```

Context nội bộ được lọc/tổng hợp trước khi đưa cho agent. Snapshot hoặc
projection qua Kafka có thể bổ sung khi cần; AI không đọc database service khác.

Pipeline này đã được chọn cho thiết kế AI, **chưa triển khai**. API và worker
cùng thuộc AI Service, dùng chung persistence; worker không phải service mới
và không cần phát event về API process để lưu kết quả. POST chờ tối đa 10 giây:
thành công trả `200`, chưa xong trả `202`; workflow có hard timeout 30 giây.
MVP dùng polling. Số worker/concurrency và SSE/WebSocket chưa chốt. Chi tiết
nằm trong [pipeline AI](../ai-service/architecture.md),
[API AI](../ai-service/api.md) và [ADR-002](../adr/002-ai-request-pipeline.md).

Kafka consumer của AI có thể nhận event Work/Integration để cập nhật context
hoặc tạo job qua application và dispatcher khi có use case/contract; agent
không consume event. Không dùng Kafka để hỏi quyền hoặc lấy context đồng bộ.
Giao job, xử lý trùng, retry có giới hạn và dead-letter phải được thiết kế/test
trước runtime; hết retry phải lưu `failed` cho client.

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
