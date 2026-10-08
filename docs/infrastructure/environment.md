# Biến môi trường

`docker-compose.yml` dành local; `docker-compose.staging.yml` dành triển khai staging
bằng image đã phát hành. Hai Compose dùng chung bộ ánh xạ `infra/env/*.env` và
một mẫu [.env.example](../../.env.example). Mỗi máy có `.env` riêng, không commit:

- `database.env`: thông tin PostgreSQL dùng chung (`POSTGRES_*`).
- `django.env`: cấu hình dùng chung cho các dịch vụ Django.
- `postgres.env`: tên database do script khởi tạo sử dụng.
- `<service>.env`: cấu hình riêng của từng service, gồm tên database và khóa service hoặc URL service.

Không ghi bí mật thật vào các tệp được theo dõi trong Git. Khi chưa có `.env`,
tạo từ mẫu rồi điền giá trị của máy đó trước khi chạy Compose:

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
- Staging giữ `.env` trên server, cũng dùng mẫu `.env.example`; thay toàn bộ mật khẩu,
  secret, domain, Kafka cluster ID và đường dẫn PEM bằng giá trị dành cho staging.
  Workflow upload mapping dùng chung, không upload `.env` hoặc PEM.
- Production dùng cấu hình của nền tảng và hạ tầng bên ngoài theo baseline; không đặt secret trong repository.

## Điền biến trên VPS staging

Điền trước lần deploy đầu vào **một file `.env` tại `STAGING_WORKDIR`**, cạnh
`docker-compose.staging.yml`. Ví dụ `STAGING_WORKDIR=/opt/utask` thì dùng
`/opt/utask/.env`. Mẫu nằm trong repository và được upload thành `.env.example`;
chỉ copy thành `.env` nếu chưa có file thật, rồi sửa trên VPS. Không ghi đè file đã có.

```bash
cd /opt/utask
# Chỉ thực hiện khi chưa có .env:
cp -n .env.example .env
nano .env
chmod 600 .env
```

Workflow đọc `.env` này nhưng không upload hoặc ghi đè nó. Secrets GitHub như khóa SSH
và token GHCR phục vụ triển khai; chúng không tự trở thành biến của ứng dụng.

| Giá trị trong `.env` VPS | Container nhận |
| --- | --- |
| `POSTGRES_*` | PostgreSQL và các app cần database, qua mapping dùng chung |
| `IDENTITY_DB_NAME`, `IDENTITY_DJANGO_SECRET_KEY`, `IDENTITY_*` | Identity: `DATABASE_NAME`, `DJANGO_SECRET_KEY` và cấu hình riêng |
| `WORK_DB_NAME`, `WORK_DJANGO_SECRET_KEY` | Work khi bật profile của service |
| `CLASSROOM_DB_NAME`, `CLASSROOM_DJANGO_SECRET_KEY` | Classroom khi bật |
| `INTEGRATION_DB_NAME`, `INTEGRATION_DJANGO_SECRET_KEY` | Integration khi bật |
| `NOTIFICATION_DB_NAME`, `NOTIFICATION_DJANGO_SECRET_KEY` | Notification khi bật |

Giá trị thật nằm trong `.env`; `infra/env/<service>.env` chỉ ánh xạ `${TEN_BIEN}`.
Không tạo thêm `.env` trong từng container và không đưa nguyên `.env` chung vào tất cả
app. Hiện chỉ cần điền secret runtime của Identity và PostgreSQL, cùng khóa mail nếu
dùng đăng ký/reset; các app chưa bật chưa cần secret riêng. Giữ các tên database theo
mẫu cho script khởi tạo PostgreSQL. Xem [phạm vi staging và biến cần có](ci-cd.md).

Sau khi sửa `.env`, phải tạo lại container của service để áp dụng biến mới, không chỉ
`restart`. Workflow deploy lần tiếp theo sẽ áp dụng; nếu thao tác thủ công, cấp đúng
image prefix/SHA đã phát hành rồi dùng `up -d --no-build --force-recreate <service>`.

Các service Django dùng chung `POSTGRES_USER` và `POSTGRES_PASSWORD` theo baseline, nhưng mỗi service vẫn nhận `DATABASE_NAME` riêng của mình.

`env_file` chỉ đưa các biến của file đó vào service được khai báo; không gán một file chung chứa toàn bộ secret cho mọi service.

Image prefix/tag và đường dẫn khóa RSA trên server là bắt buộc trong Compose staging.
Workflow cấp image theo SHA; deploy thủ công cần đặt UTASK_IMAGE_PREFIX/UTASK_IMAGE_TAG.
Khóa phải có trước khi startup và user container đọc được; workflow không vận chuyển PEM.
Các giá trị OAuth/R2/caller keys nằm trong `.env` của từng máy; file ánh xạ chỉ
chứa `${...}` hoặc hằng cấu hình container không bí mật. Không điền credential hoặc
flags trực tiếp vào `infra/env/identity-service.env`.

Local để `IDENTITY_REDIS_URL` trống theo cấu hình cache hiện tại. Compose staging đặt
mặc định Redis `redis://redis:6379/0` và Integration `http://integration-service:8000`;
giá trị không trống trong `.env` có thể thay các mặc định này. Chỉ bật OAuth/avatar sau
khi có đủ credential và callback theo [tài liệu Identity](../identity-service/README.md).

Nếu đổi tên database, cập nhật giá trị trong `.env` và chuẩn bị database tương ứng có
chủ đích. Script khởi tạo chỉ chạy khi volume còn trống; sửa `.env` không tự đổi tên
database hoặc chuyển dữ liệu. Không xóa volume để áp dụng biến môi trường.
