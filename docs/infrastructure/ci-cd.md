# CI/CD

UTask dùng một workflow điều phối và hai workflow dùng lại trong GitHub Actions:

1. `ci.yml` chạy khi có pull request vào `main` hoặc khi đẩy mã lên `main`. Workflow lọc theo đường dẫn, kiểm tra service bị ảnh hưởng và cả Compose local/staging. Pull Request dựng image để kiểm tra Dockerfile; push lên `main` chỉ gọi phát hành sau khi các kiểm tra liên quan thành công.
2. `python-service.yml` không tự khởi động. Đây là workflow dùng lại được `ci.yml` gọi cho từng service Python để tránh lặp các bước cài dependency, lint, format, test và kiểm tra image.
3. `release-staging.yml` dựng/đẩy image của service đổi; service không đổi được gắn thẻ SHA mới từ manifest `main`. Staging dùng riêng `docker-compose.staging.yml`, pull bộ sáu image theo SHA và chạy `up --no-build` qua SSH.

`docker-compose.yml` dành cho local, có build context và port hỗ trợ phát triển.
`docker-compose.staging.yml` là file độc lập dùng image đã phát hành, chỉ publish Nginx.
PostgreSQL/Redis/Kafka vẫn thuộc stack staging; không dùng cấu hình này làm production.
Hai file giữ project name `utask` và tên volume để server staging đang dùng có thể chuyển
file mà không tạo một bộ dữ liệu khác. Không chạy cả hai stack trong cùng Docker host/project.

Thay riêng Compose local chạy CI nhưng không kích hoạt deploy.
Thay Compose staging, mapping `infra/env/*.env`, Nginx, init script hoặc datasets
có thể kích hoạt release trên push `main`. Đổi workflow riêng vẫn chỉ kiểm CI như quy tắc
phát hành hiện tại.

Workflow dùng chung nhận ba input tùy chọn từ job gọi trong `ci.yml`:

| Input | Mặc định | Trách nhiệm |
| --- | --- | --- |
| `postgres` | `false` | Khởi tạo PostgreSQL 16 tại `127.0.0.1:5432`, database `ci`, user `utask_ci`, password `ci-only-postgres-password`. |
| `redis` | `false` | Khởi tạo Redis 7 tại `127.0.0.1:6379`. |
| `test_env` | `{}` | Chuỗi JSON chứa biến môi trường không bí mật, chỉ truyền vào bước pytest. |

Hai container thuộc riêng từng job trên runner tạm thời. Health checks phải đạt trước
khi chạy các bước kiểm tra. Credential trên chỉ dành cho CI; không dùng secrets
staging/production hoặc `.env` local cho pytest. `test_env` không phải cơ chế truyền secrets.

Job Identity bật cả hai dependency và truyền `POSTGRES_*`, `DATABASE_NAME=ci`,
`IDENTITY_TEST_DB_NAME=test_identity_ci` cùng `IDENTITY_TEST_REDIS_URL` dùng Redis DB15.
pytest-django tự tạo/migrate/xóa test database. Workflow chung chạy một bước
`uv run pytest`, không rẽ nhánh theo tên service.

Các job khác hiện dùng mặc định, không khởi tạo hai container. Khi service được triển
khai, khai báo dependency và biến kiểm thử tại job của service đó trong `ci.yml` theo
code/test thực tế; không cần sao chép workflow hoặc tạo môi trường staging cho test.
Hiện chỉ Identity có `pyproject.toml`, `uv.lock` và Dockerfile. Bộ lọc `shared` vẫn gọi
cả sáu job, nên thay đổi file dùng chung có thể khiến các service chưa triển khai thất
bại do thiếu đầu vào; cấu hình dependency không thay thế việc triển khai service.

Schema tests xuất OpenAPI từ URLconf/serializers thật và kiểm response của các API.
Không so với `contracts/api/identity.openapi.json` khi artifact này không được lưu trong
repository; xem [cách xuất hợp đồng](../../contracts/api/README.md).

## Kiểm tra CI local trước khi đẩy mã

Chạy từ thư mục gốc repository:

```powershell
python scripts/ci_local.py
```

Lệnh này kiểm tra Compose, Nginx, script PostgreSQL, lint/format/test của sáu service Python, lint/typecheck/test/build của Web và dựng Docker image. Dùng `python scripts/ci_local.py --skip-images` để bỏ qua bước dựng image khi cần vòng lặp nhanh hơn. GitHub Actions vẫn là bước kiểm tra bắt buộc trên remote; script local không đẩy image hoặc triển khai staging.

Khi chạy tests Identity trên máy local, chuẩn bị PostgreSQL có quyền tạo test database
và Redis dành kiểm thử, rồi cấp các biến kết nối tương ứng. Script local không tự tạo
service containers như GitHub Actions; không dùng credential staging/production cho test.

## Cấu hình GitHub

Tạo Environment có tên `staging` và giới hạn nhánh triển khai là `main`. Việc yêu cầu người duyệt trước khi triển khai là tùy chọn quản trị, không thay đổi cơ chế workflow tự khởi động sau CI.

| Tên | Khai báo tại | Bắt buộc | Mục đích |
| --- | --- | --- | --- |
| `STAGING_WORKDIR` | Environment variable | Có | Thư mục triển khai, ví dụ `/opt/utask`. |
| `STAGING_URL` | Environment variable | Không | Địa chỉ hiển thị trong GitHub Deployment. |
| `STAGING_HOST` | Environment secret | Có | Tên máy hoặc địa chỉ máy staging. |
| `STAGING_USER` | Environment secret | Có | Tài khoản SSH dùng để triển khai. |
| `STAGING_SSH_PRIVATE_KEY` | Environment secret | Có | Khóa riêng SSH tương ứng với máy staging. |
| `STAGING_KNOWN_HOSTS` | Environment secret | Có | Nội dung `known_hosts` đã xác minh cho máy staging. |
| `STAGING_REGISTRY_USERNAME` | Environment secret | Có | Tài khoản có quyền đọc package trên GHCR. |
| `STAGING_REGISTRY_TOKEN` | Environment secret | Có | Token chỉ có quyền đọc package trên GHCR. |

Các giá trị sau do GitHub hoặc workflow cung cấp, không cấu hình thủ công: `GITHUB_TOKEN`, `STAGING_REGISTRY`, `STAGING_IMAGE_PREFIX` và `STAGING_IMAGE_TAG`.

Không đưa khóa SSH, token registry, khóa Django hoặc `.env` staging vào repository.

## Bảo vệ nhánh chính

Trong cài đặt repository, bảo vệ `main` với các quy tắc sau:

- Chỉ nhập mã qua Pull Request; không cho đẩy trực tiếp hoặc force push.
- Bắt buộc CI thành công trước khi gộp mã và yêu cầu ít nhất một người duyệt.
- Chọn squash merge và xóa nhánh ngắn hạn sau khi gộp.
- Giới hạn Environment `staging` cho nhánh `main`; nếu môi trường có phê duyệt, bật phê duyệt bắt buộc.

## Chuẩn bị máy staging

Máy staging cần Docker Engine/Compose plugin, `.env` tại `STAGING_WORKDIR` và khóa RSA
riêng cho Identity. Dùng [.env.example](../../.env.example) làm mẫu rồi thay toàn bộ
giá trị local bằng cấu hình staging, gồm secrets, domain, Kafka cluster ID và đường dẫn
PEM. Workflow không upload/ghi đè `.env` hoặc file PEM.

Workflow upload `docker-compose.staging.yml`, bộ ánh xạ dùng chung `infra/env/*.env`,
Nginx, init PostgreSQL và datasets. Các biến Google/GitHub/R2/caller keys nếu dùng
được cung cấp trong `.env` server, không đặt giá trị bí mật vào file ánh xạ tracked.

Các biến runtime bắt buộc trong `.env` staging:

```dotenv
POSTGRES_USER=utask
POSTGRES_PASSWORD=<secret>
POSTGRES_DB=postgres
POSTGRES_HOST=postgres
POSTGRES_PORT=5432

IDENTITY_DB_NAME=identity_db
IDENTITY_DJANGO_SECRET_KEY=<secret>
WORK_DB_NAME=work_db
WORK_DJANGO_SECRET_KEY=<secret>
CLASSROOM_DB_NAME=classroom_db
CLASSROOM_DJANGO_SECRET_KEY=<secret>
INTEGRATION_DB_NAME=integration_db
INTEGRATION_DJANGO_SECRET_KEY=<secret>
NOTIFICATION_DB_NAME=notification_db
NOTIFICATION_DJANGO_SECRET_KEY=<secret>

DJANGO_DEBUG=false
DJANGO_ALLOWED_HOSTS=<staging-domain>,nginx,identity-service,work-service,classroom-service,integration-service,notification-service
KAFKA_CLUSTER_ID=<kraft-cluster-id>
IDENTITY_JWT_PRIVATE_KEY_HOST_PATH=/etc/utask/secrets/identity-jwt-private.pem
```

File PEM phải tồn tại và user trong container Identity (UID10001) đọc được; bind mount
read-only không tự tạo đường dẫn còn thiếu. Không sinh khóa mặc định trên server khi deploy.
Mail key/key ID cần cho đăng ký/recovery; OAuth/R2 cần cấu hình riêng khi bật flags.

`UTASK_HTTP_PORT` mặc định8080. Workflow đặt `UTASK_IMAGE_PREFIX` và
`UTASK_IMAGE_TAG=sha-<commit>` khi triển khai. Chạy thủ công phải cung cấp hai biến đó;
Compose staging không có fallback `utask:*:local`. Ví dụ lệnh trên server sau khi cấu hình:

```bash
docker compose -f docker-compose.staging.yml config --quiet
docker compose -f docker-compose.staging.yml pull
docker compose -f docker-compose.staging.yml up -d --no-build --remove-orphans --wait --wait-timeout 120
```

Không dùng `docker compose down -v` khi chuyển file. File Compose local cũ trên server
không còn được workflow gọi; không cần xóa nó để triển khai bằng `-f` rõ ràng.

## Luồng phát hành

```text
Pull Request → CI theo đường dẫn → merge vào main
                                  ↓
             build image đổi + gắn thẻ lại image không đổi
                                  ↓
                    Environment staging gate (nếu cấu hình)
                                  ↓
       SSH → staging Compose pull → up --no-build --wait
```

Mỗi service vẫn có image độc lập. Image thay đổi được gắn hai thẻ: `main` và `sha-<commit>`. Image không đổi giữ nguyên manifest và chỉ nhận thêm thẻ `sha-<commit>`, nhờ đó Compose vẫn triển khai một bộ sáu image đồng nhất theo cùng SHA mà không dựng lại service không liên quan. Thẻ `main` là nguồn hiện hành để tái sử dụng; nếu image này chưa tồn tại, phát hành dừng thay vì tạo kết quả giả.

Nếu chưa cấu hình Environment hoặc secrets, bước triển khai sẽ dừng với thông báo thiếu cấu hình; không có triển khai giả hoặc tự động bỏ qua lỗi.

## Production

Baseline yêu cầu production từ release/tag hoặc workflow được kiểm soát, với PostgreSQL,
Redis/Kafka bên ngoài và secrets của nền tảng production. Compose local/staging không thay thế quyết
định hạ tầng đó. Khi có production cần Environment/quy trình triển khai riêng và image SHA.
