# Cấu hình môi trường cho Compose

`docker-compose.yml` chỉ mô tả service, volume, mạng và thứ tự khởi động. Các biến chạy trong container được gom vào các tệp `env_file` tại thư mục này:

- `database.env`: thông tin PostgreSQL dùng chung (`POSTGRES_*`).
- `django.env`: cấu hình dùng chung cho các dịch vụ Django.
- `postgres.env`: tên database do script khởi tạo sử dụng.
- `<service>.env`: cấu hình riêng của từng service, gồm tên database và khóa service hoặc URL service.

Các tệp này không chứa giá trị bí mật thật. Chúng chỉ tham chiếu biến từ `.env` ở thư mục dự án:

```powershell
Copy-Item .env.example .env
docker compose config --quiet
docker compose up --build
```

`infra/env/*.env` được theo dõi trong Git vì đây là các tệp ánh xạ Compose, không phải kho chứa mật khẩu. Tệp `.env` và các bản sao theo môi trường vẫn bị bỏ qua để không đưa mật khẩu, khóa Django hoặc mã cụm vào repository.

## Phân tách theo môi trường

- Local dùng `.env` không commit.
- CI dùng `.env.example` với giá trị kiểm tra an toàn.
- Staging giữ `.env` với giá trị thật trên máy staging; workflow cập nhật các tệp ánh xạ `infra/env/`.
- Production dùng cấu hình của nền tảng và hạ tầng bên ngoài theo baseline; không đặt secret trong repository.

Các service Django dùng chung `POSTGRES_USER` và `POSTGRES_PASSWORD` theo baseline, nhưng mỗi service vẫn nhận `DATABASE_NAME` riêng của mình.

`env_file` chỉ đưa các biến của file đó vào service được khai báo; không gán một file chung chứa toàn bộ secret cho mọi service.

Nếu đổi tên database, phải cập nhật tệp môi trường tương ứng và tạo lại volume PostgreSQL có chủ đích vì script khởi tạo chỉ chạy khi volume còn trống.
