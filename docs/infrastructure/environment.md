# Biến môi trường

`docker-compose.yml` khai báo các service, volume, mạng và cấu hình khởi động.
Các giá trị được tách giữa tệp `.env` cục bộ và các tệp ánh xạ theo service:

- `database.env`: thông tin PostgreSQL dùng chung (`POSTGRES_*`).
- `django.env`: cấu hình dùng chung cho các dịch vụ Django.
- `postgres.env`: tên database do script khởi tạo sử dụng.
- `<service>.env`: cấu hình riêng của từng service, gồm tên database và khóa service hoặc URL service.
- `classroom-service.env`: cấu hình riêng Classroom Service, gồm
  `KAFKA_BOOTSTRAP_SERVERS` để kết nối tới broker Kafka.

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

Các service Django dùng chung `POSTGRES_USER` và `POSTGRES_PASSWORD` theo baseline, nhưng mỗi service vẫn nhận `DATABASE_NAME` riêng của mình.

`env_file` chỉ đưa các biến của file đó vào service được khai báo; không gán một file chung chứa toàn bộ secret cho mọi service.

Nếu đổi tên database, phải cập nhật tệp môi trường tương ứng và tạo lại volume PostgreSQL có chủ đích vì script khởi tạo chỉ chạy khi volume còn trống.
