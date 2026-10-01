# Các luồng nghiệp vụ

Các sơ đồ dưới đây mô tả **thiết kế mục tiêu**, không xác nhận các luồng đã
được nối trong mã nguồn.

## Đăng ký và đăng nhập

```text
Người dùng → Web → API Gateway → Identity Service → Identity DB
```

Identity Service xác thực người dùng và quản lý token, phiên đăng nhập. Service
khác dùng `user_id` làm tham chiếu, không đọc Identity DB.

## Tạo lớp và nhóm

```text
Giảng viên → Classroom Service → Classroom DB → Kafka
                                      └── sự kiện lớp/nhóm/thành viên
```

Classroom Service quản lý quan hệ lớp học và nhóm.

## Tạo project cho nhóm

```text
Người dùng → Project Service → Classroom Service (REST, nếu cần xác minh)
                    │
                    ├── lưu Project vào Project DB
                    └── phát project.created qua Kafka
```

Project Service kiểm tra thông tin nhóm qua API đồng bộ khi cần câu trả lời
ngay. Không dùng Kafka dạng hỏi-đáp cho việc kiểm tra đơn giản.

## Quản lý sprint và task

```text
Người dùng → Project Service → Project DB
                                  └── Kafka: project.*, sprint.*, task.*
```

Progress, AI và Notification có thể nhận các sự kiện cần thiết của mình.

## Kết nối GitHub và xử lý webhook

```text
Người dùng → Integration Service ↔ GitHub
GitHub → webhook → Integration Service → lưu dữ liệu → Kafka: github.*
```

Integration Service xác minh, chuẩn hóa và lưu dữ liệu trước khi thông báo cho
các service khác. Không service nào khác gọi GitHub API trực tiếp.

## Theo dõi tiến độ

```text
Sự kiện từ Project / Classroom / Integration → Kafka
    → Progress Service → Progress DB → progress.* → Web dashboard
```

Progress Service áp dụng công thức và quy tắc có thể giải thích. Dashboard vẫn
hoạt động khi AI Service lỗi.

## Yêu cầu AI và cập nhật ngữ cảnh

```text
Người dùng → Web → AI Service API → ngữ cảnh nội bộ → tác tử → nhà cung cấp LLM
                                      │
Service nghiệp vụ → Kafka → AI nhận sự kiện → AI Context DB
```

API AI nhận ý định của người dùng, chẳng hạn phân rã task hoặc phân tích nguy
cơ trễ. Ngữ cảnh nghiệp vụ được cập nhật độc lập từ Kafka. AI không gọi REST
sang service nghiệp vụ để lấy ngữ cảnh, không đọc database của service khác và
không tự ghi thay đổi vào dữ liệu nghiệp vụ.

## Gửi thông báo

```text
Sự kiện → Kafka → Notification Service → Notification DB → in-app / email / push
```

Notification Service xử lý trạng thái gửi và kênh. Thông báo không liên quan AI
vẫn phải hoạt động khi AI lỗi.
