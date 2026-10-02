# Classroom Service

Tài liệu:

- [Phân tích chức năng và hiện trạng triển khai](chuc-nang.md)
- [Chức năng theo tác nhân](objects.md)
- [Mô hình dữ liệu đề xuất](data-model.md)

Classroom Service là service quản lý cấu trúc học tập và quan hệ học tập.
Service chỉ dùng **khóa học** (`Course`) để quản lý, không tách thêm tầng lớp
học riêng biệt. Câu hỏi service này trả lời là: **ai học với ai, thuộc khóa học
nào và thuộc nhóm nào?**


```text
Teacher → Course → Group → Project → Sprint → Task
   └────────── Classroom Service ─────┘
                         └── Project Service ──┘
```

Phạm vi dữ liệu mục tiêu gồm khóa học (`Course`), giảng viên khóa học
(`CourseInstructor`), sinh viên khóa học (`CourseStudent`), nhóm (`Group`) và
thành viên nhóm (`GroupMember`). Classroom Service sở hữu quan hệ thành viên
nhóm; Project Service sở hữu thành viên dự án. Giảng viên theo dõi project qua
quan hệ giảng viên → khóa học → nhóm → project, không cần được thêm làm thành
viên dự án. `course_id` và `group_id` ở Project Service chỉ là ID tham chiếu,
không phải khóa ngoại xuyên database.

Các API và sự kiện cụ thể cần được xác nhận bằng hợp đồng trước khi xem là đã
chốt.

## Trạng thái khởi tạo

**Đã triển khai**: khung Django tối thiểu, endpoint kiểm tra sức khỏe `/healthz`,
kết nối PostgreSQL qua biến môi trường, Dockerfile và dependency được quản lý
bằng `uv` với lockfile. **Chưa triển khai**: mô hình dữ liệu và chức năng nghiệp
vụ nêu trong tài liệu này.

Classroom Service được cấu hình địa chỉ Kafka qua `KAFKA_BOOTSTRAP_SERVERS`
(Compose local dùng `kafka:9092`) và có factory tạo JSON producer tại
`config.kafka.create_producer()`. Producer chỉ được khởi tạo khi được gọi; lỗi
hoặc chưa sẵn sàng của Kafka không làm hỏng khởi động Django hay `/healthz`.
Chưa có luồng nghiệp vụ nào gọi producer: schema, phiên bản và topic cho các sự
kiện thành viên nhóm vẫn cần chốt trước khi phát sự kiện.

Chạy qua Docker Compose từ thư mục gốc repo:

```sh
docker compose up --build classroom-service
```

Để chạy trực tiếp trong môi trường Python:

```sh
cd apps/classroom-service
uv sync --locked
uv run python manage.py runserver 0.0.0.0:8000
```

Khi chạy trực tiếp, cung cấp `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`,
`DATABASE_NAME`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST` và
`POSTGRES_PORT` theo cấu hình local trong [biến môi trường](../infrastructure/environment.md).
