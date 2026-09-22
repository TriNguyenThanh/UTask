# Docker cục bộ

Mỗi ứng dụng có Dockerfile riêng. `docker-compose.yml` chạy Nginx, PostgreSQL, Redis, Kafka và sáu dịch vụ Python theo baseline.

Trước khi chạy lần đầu, tạo cấu hình cục bộ:

```powershell
Copy-Item .env.example .env
docker compose config --quiet
docker compose up --build
```

`.env` không được commit. PostgreSQL khởi tạo database riêng cho Identity, Work, Classroom, Integration và Notification; các service dùng chung một tài khoản PostgreSQL. Tệp khởi tạo chỉ chạy khi volume PostgreSQL còn trống; nếu đổi tên database, hãy tạo volume cục bộ mới có chủ đích.

Các biến chạy trong container được nạp bằng `env_file` từ `infra/env/`. Tệp `.env` là nguồn giá trị theo từng môi trường; các tệp trong `infra/env/` chỉ giữ ánh xạ biến cho từng service và không chứa bí mật thật. Staging hoặc production dùng một `.env` riêng bên ngoài repository.

Dừng môi trường nhưng giữ dữ liệu:

```powershell
docker compose down
```

Production không được suy ra từ việc chạy nguyên stack local. Baseline yêu cầu hạ tầng PostgreSQL, Redis và Kafka bên ngoài; khi chọn nền tảng production, cấu hình triển khai và secrets phải do nền tảng đó quản lý.
