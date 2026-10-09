# Biến môi trường

`docker-compose.yml` khai báo các service, volume, mạng và cấu hình khởi động.
Các giá trị được tách giữa tệp `.env` cục bộ và các tệp ánh xạ theo service:

- `database.env`: thông tin PostgreSQL dùng chung (`POSTGRES_*`).
- `django.env`: cấu hình dùng chung cho các dịch vụ Django.
- `postgres.env`: tên database do script khởi tạo sử dụng.
- `<service>.env`: cấu hình riêng của từng service, gồm tên database và khóa service hoặc URL service.

AI Service chỉ dùng `infra/env/ai-service.env` cho biến thường/cờ chế độ
và `.env` root cho secret. AI_ENVIRONMENT và MOCK_TEST chọn context mock;
chỉ development/test được bật mock; dữ liệu mẫu được đọc ngay tại adapter,
không cần server/mock microservice hay launcher riêng. SDK nhận key từ Settings, không cần
export secret ra terminal. Compose chỉ inject AI_CREDENTIAL_KEY,
AI_JWT_PUBLIC_KEY và GOOGLE_API_KEY vào AI; DB local nhận AI_DB_PASSWORD.
CI/CD tiếp tục dùng `infra/env/*.env`, không upload `.env` root. Xem
[cấu hình AI](../ai-service/README.md#cấu-hình) và
[mock data](../ai-service/mock-data.md).

Không ghi bí mật thật vào các tệp được theo dõi trong Git. Tạo `.env` cục bộ
theo mẫu repository rồi kiểm tra cấu hình Compose:

```powershell
Copy-Item .env.example .env
docker compose config --quiet
docker compose up --build
```

Các tệp ánh xạ Compose không phải kho chứa mật khẩu. Không commit `.env`, khóa
Django, token hoặc thông tin xác thực môi trường dùng chung.

## Phân tách theo môi trường

- Local dùng `.env` không commit.
- CI dùng `.env.example` với giá trị kiểm tra an toàn.
- Staging giữ `.env` với giá trị thật trên máy staging; workflow cập nhật các tệp ánh xạ `infra/env/`.
- Production dùng cấu hình của nền tảng và hạ tầng bên ngoài theo baseline; không đặt secret trong repository.

**Một phần:** cấu hình local/staging hiện dùng chung `POSTGRES_USER` và
`POSTGRES_PASSWORD`, mỗi service nhận `DATABASE_NAME` riêng. Baseline mục 8
yêu cầu database và user/credential riêng cho từng service. Script khởi tạo
hiện chỉ tạo database, chưa tạo role hoặc giới hạn quyền theo service; đây là
khoảng trống triển khai, không phải lựa chọn bảo mật production.

Celery broker, Kafka client và R2 là công nghệ mục tiêu theo baseline; biến
môi trường của từng adapter chỉ được liệt kê như đã có sau khi kiểm tra mã
triển khai. Không xem URL service trong file env là bằng chứng client đã gọi
service đó. Xem [job nền](background-jobs.md), [Kafka](kafka.md) và
[lưu trữ file](storage.md).

`env_file` chỉ đưa các biến của file đó vào service được khai báo; không gán một file chung chứa toàn bộ secret cho mọi service.

Nếu đổi tên database, phải cập nhật tệp môi trường tương ứng và tạo lại volume PostgreSQL có chủ đích vì script khởi tạo chỉ chạy khi volume còn trống.
