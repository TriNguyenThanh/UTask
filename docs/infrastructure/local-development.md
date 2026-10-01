# Chạy môi trường local

Các lệnh dưới đây dùng PowerShell. Trước khi chạy lần đầu, tạo cấu hình cục bộ:

```powershell
Copy-Item .env.example .env
docker compose config --quiet
docker compose up --build
```

Không commit `.env`. Mỗi service giữ quyền sở hữu database riêng, kể cả khi
cùng dùng một PostgreSQL server. Nếu đổi tên database sau khi volume đã được
khởi tạo, cần xử lý volume có chủ đích.

Các biến chạy trong container được nạp qua cấu hình Compose. Xem [biến môi
trường](environment.md) để biết cách tách giá trị local và thông tin bí mật.

Dừng môi trường nhưng giữ dữ liệu:

```powershell
docker compose down
```

Môi trường local không đại diện cho cấu hình production. Cách triển khai
production cần được ghi riêng khi nền tảng và cách quản lý thông tin bí mật đã
được quyết định.
