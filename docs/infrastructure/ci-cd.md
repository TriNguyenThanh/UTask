# CI/CD

UTask dùng một workflow điều phối và hai workflow dùng lại trong GitHub Actions:

1. `ci.yml` chạy khi có pull request vào `main` hoặc khi đẩy mã lên `main`. Workflow lọc theo đường dẫn, kiểm tra service bị ảnh hưởng và cả Compose local/staging. Pull Request dựng image để kiểm tra Dockerfile; push lên `main` chỉ gọi phát hành sau khi các kiểm tra liên quan thành công.
2. `python-service.yml` không tự khởi động. Đây là workflow dùng lại được `ci.yml` gọi cho từng service Python để tránh lặp các bước cài dependency, lint, format, test và kiểm tra image.
3. `release-staging.yml` chỉ phát hành các service đang bật: dựng/đẩy image đổi, tái sử dụng manifest `main` cho image không đổi. Staging dùng riêng `docker-compose.staging.yml`, chạy migration rồi `up --no-build` qua SSH.

## Phạm vi service đang triển khai

Danh sách chuẩn nằm tại `env.STAGING_SERVICES` trong `ci.yml`, hiện là
`["identity-service"]`. CI kiểm tra đủ `pyproject.toml`, `uv.lock`, Dockerfile của từng
service được bật; thiếu đầu vào là lỗi, không tự bỏ qua để báo xanh. Service chưa bật
không chạy job test/build, không xuất hiện trong matrix phát hành. Web chưa có source
thì không chạy; khi có thư mục Web, thiếu manifest/lockfile cũng là lỗi.

Khi thêm service, cập nhật danh sách này sau khi code/test và cấu hình runtime sẵn sàng,
rồi khai báo dependency kiểm thử tại job tương ứng. AI còn yêu cầu Work và Integration
cùng được bật. Job có lỗi hoặc bị hủy vẫn chặn release; job không được chọn có thể skipped.
Chỉ thay đổi service chưa bật không kích hoạt release.

Compose staging mặc định chạy PostgreSQL, Redis, Identity và Nginx. Các app còn lại dùng
profile cùng tên service; Kafka có profile `kafka`, chưa bật trong phạm vi hiện tại.
Workflow cấp profile từ danh sách đang bật, không lấy `COMPOSE_PROFILES` tùy ý trên VPS.
Nginx dùng Docker DNS khi nhận request, không cần các app chưa chạy để khởi động;
backend chưa khả dụng trả HTTP 503. Route Identity nội bộ vẫn bị gateway chặn bằng 404.

`docker-compose.yml` dành cho local, có build context và port hỗ trợ phát triển.
`docker-compose.staging.yml` là file độc lập dùng image đã phát hành, chỉ publish Nginx.
PostgreSQL/Redis/Kafka vẫn thuộc stack staging; không dùng cấu hình này làm production.
Hai file giữ project name `utask` và tên volume để server staging đang dùng có thể chuyển
file mà không tạo một bộ dữ liệu khác. Không chạy cả hai stack trong cùng Docker host/project.

Thay riêng Compose local chạy CI nhưng không kích hoạt deploy.
Thay Compose staging, mapping `infra/env/*.env`, Nginx, init script hoặc datasets
có thể kích hoạt release trên push `main`. Đổi `ci.yml` hoặc `release-staging.yml` cũng
kích hoạt release để áp dụng phạm vi/cách deploy mới và dựng image đang bật cho lần đầu.

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
Hiện chỉ Identity có `pyproject.toml`, `uv.lock` và Dockerfile. Bộ lọc `shared` kiểm tra
các service đang bật; không dùng source thiếu của service chưa bật để chặn Identity.

Schema tests xuất OpenAPI từ URLconf/serializers thật và kiểm response của các API.
Không so với `contracts/api/identity.openapi.json` khi artifact này không được lưu trong
repository; xem [cách xuất hợp đồng](../../contracts/api/README.md).

## Kiểm tra CI local trước khi đẩy mã

Chạy từ thư mục gốc repository:

```powershell
python scripts/ci_local.py
```

Script này vẫn kiểm tra toàn bộ sáu service Python và Web, nên cần source của chúng;
không phải lệnh kiểm tra riêng phạm vi staging hiện tại. GitHub Actions lọc theo
`STAGING_SERVICES` như trên. Script local không đẩy image hoặc triển khai staging.

Kiểm tra regression của cấu hình lựa chọn service và việc dừng deploy khi migration lỗi:

```bash
uv run --project apps/identity-service --locked python -m unittest discover -s scripts/tests -p test_staging_deployment.py
```

Test shell deploy chạy trên Linux (cùng nền tảng runner). Kiểm tra cú pháp workflow bằng
actionlint; kiểm tra Compose với `.env.example`, image prefix/tag mẫu và các profile đang bật.

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
giá trị local của service đang bật bằng cấu hình staging, gồm secrets, domain và đường dẫn
PEM. Workflow không upload/ghi đè `.env` hoặc file PEM.

Workflow upload `docker-compose.staging.yml`, `.env.example`, bộ ánh xạ dùng chung `infra/env/*.env`,
Nginx và init PostgreSQL; datasets chỉ upload khi AI được bật. Các biến Google/GitHub/R2/caller keys nếu dùng
được cung cấp trong `.env` server, không đặt giá trị bí mật vào file ánh xạ tracked.

Các biến runtime trong `.env` staging khi chỉ bật Identity:

```dotenv
POSTGRES_USER=utask
POSTGRES_PASSWORD=<secret>
POSTGRES_DB=postgres
POSTGRES_HOST=postgres
POSTGRES_PORT=5432

IDENTITY_DB_NAME=identity_db
IDENTITY_DJANGO_SECRET_KEY=<secret>
WORK_DB_NAME=work_db
CLASSROOM_DB_NAME=classroom_db
INTEGRATION_DB_NAME=integration_db
NOTIFICATION_DB_NAME=notification_db

DJANGO_DEBUG=false
DJANGO_ALLOWED_HOSTS=<staging-domain>,localhost,127.0.0.1,nginx,identity-service
IDENTITY_JWT_PRIVATE_KEY_HOST_PATH=/etc/utask/secrets/identity-jwt-private.pem
```

Tên database của app chưa bật vẫn được script PostgreSQL dùng để tạo database rỗng;
không chạy Django migration hoặc truyền secret của app đó. Khi bật app Django khác,
điền `<SERVICE>_DJANGO_SECRET_KEY` tương ứng trong cùng `.env`. Kafka cluster ID cần
khi chủ động bật profile Kafka; việc đó không triển khai publisher/consumer của app.

File PEM phải tồn tại và user trong container Identity (UID10001) đọc được; bind mount
read-only không tự tạo đường dẫn còn thiếu. Không sinh khóa mặc định trên server khi deploy.
Mail key/key ID cần cho đăng ký/recovery; OAuth/R2 cần cấu hình riêng khi bật flags.

`UTASK_HTTP_PORT` mặc định8080. Workflow đặt `UTASK_IMAGE_PREFIX` và
`UTASK_IMAGE_TAG=sha-<commit>` khi triển khai. Chạy thủ công phải cung cấp hai biến đó;
Compose staging không có fallback `utask:*:local`. Ví dụ lệnh trên server sau khi cấu hình:

```bash
docker compose -f docker-compose.staging.yml config --quiet
docker compose -f docker-compose.staging.yml pull
docker compose -f docker-compose.staging.yml up -d --no-build --wait postgres redis
docker compose -f docker-compose.staging.yml run --rm --no-deps identity-service /app/.venv/bin/python manage.py migrate --noinput
docker compose -f docker-compose.staging.yml up -d --no-build --wait --wait-timeout 120
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
       SSH → pull → PostgreSQL/Redis healthy → migrate → up --no-build --wait
                                                     ↓
                              migrate --check + healthz qua Nginx
```

Mỗi service đang bật vẫn có image độc lập. Image thay đổi được gắn hai thẻ: `main` và
`sha-<commit>`. Image không đổi giữ nguyên manifest và nhận thêm thẻ SHA. Thay cấu hình
deploy sẽ dựng lại các image đang bật, nên lần triển khai đầu không cần image của app
chưa làm. Nếu một image cần tái sử dụng chưa tồn tại, phát hành dừng.

Workflow chạy `manage.py migrate --noinput` cho app Django đang bật (AI được bỏ qua),
bằng `/app/.venv/bin/python`. Migration lỗi dừng trước bước khởi động app mới. Khi thêm
service dùng framework hoặc lệnh khác, cập nhật bước chuẩn bị runtime tương ứng.
Đây không phải bảo đảm zero downtime hay rollback database tự động. Bước cuối kiểm tra
migration Identity và health qua gateway, không thay thế nghiệm thu mọi API.

Không dùng `--remove-orphans` trong deploy; không tự xóa container hoặc volume của
service nằm ngoài phạm vi. Nếu thu hẹp danh sách, các container đã chạy trước đó phải
được dừng riêng có chủ đích; bỏ profile không tự dừng chúng.

Nếu chưa cấu hình Environment hoặc secrets, bước triển khai sẽ dừng với thông báo thiếu cấu hình; không có triển khai giả hoặc tự động bỏ qua lỗi.

## Production

Baseline yêu cầu production từ release/tag hoặc workflow được kiểm soát, với PostgreSQL,
Redis/Kafka bên ngoài và secrets của nền tảng production. Compose local/staging không thay thế quyết
định hạ tầng đó. Khi có production cần Environment/quy trình triển khai riêng và image SHA.
