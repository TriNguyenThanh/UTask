# CI/CD

**Trạng thái: Một phần.** Workflow đã được cấu hình; staging/production và
branch protection trên GitHub chưa được xác minh. Thiết kế vận hành theo
[baseline](../architecture/README.md), mục 20–26.

UTask dùng một workflow điều phối và hai workflow dùng lại trong GitHub Actions:

1. `ci.yml` chạy khi có pull request vào `main` hoặc khi đẩy mã lên `main`. Workflow lọc theo đường dẫn, kiểm tra đúng service bị ảnh hưởng và kiểm tra Compose. Pytest của AI cần bao gồm regression evaluation khi bộ evaluation được triển khai; bootstrap hiện chỉ có unit/API/workflow test. Pull Request dựng image để kiểm tra Dockerfile; lần đẩy lên `main` chỉ gọi phát hành sau khi mọi kiểm tra liên quan thành công.
2. `python-service.yml` không tự khởi động. Đây là workflow dùng lại được `ci.yml` gọi cho từng service Python để tránh lặp các bước cài dependency, lint, format, test và kiểm tra image.
3. `release-staging.yml` build các service đang bật từ commit đã qua CI, chuyển digest (mã xác định nội dung image) giữa các job bằng artifact của GitHub Actions. VPS dùng `docker-compose.staging.yml` cùng file ghi đè `staging-images.json` để chạy đúng image, migration rồi cập nhật container qua SSH.

## Phạm vi service đang triển khai

CI và script local dùng `scripts/discover_services.py` để tự nhận diện thư mục trực
tiếp trong `apps/` có đủ `pyproject.toml`, `uv.lock` và Dockerfile. Không còn danh sách
`STAGING_SERVICES` phải sửa tay trong workflow. Thư mục
chỉ có README được bỏ qua. Có một phần đầu vào thì báo lỗi thiếu file, không bỏ qua để
báo xanh. Kết quả nhận diện là đầu vào build/test, chưa phải xác nhận tính năng hoàn thiện.

Mỗi service phải có cấu hình trong Compose staging; app có thể chạy mặc định hoặc
dùng profile cùng tên service, không có ngoại lệ theo tên Identity. Dependency `depends_on` phải tồn tại; nếu phụ thuộc app chưa có code
thì CI dừng. Đây là cấu hình runtime vốn phải khai báo khi thêm service, không phải danh
sách bật CI thứ hai. Web chưa có source thì không chạy; khi có thư mục Web, thiếu
manifest/lockfile cũng là lỗi.

Service được nhận diện phải khai báo
`x-deploy.gateway_health_path`: path health qua gateway, ví dụ Identity dùng
`/api/auth/healthz`. Service chỉ dùng nội bộ khai báo giá trị `null`; workflow vẫn
chờ healthcheck của container nhưng không gọi nó qua gateway. Discovery cũng kiểm tra
healthcheck của mọi container runtime được profile ứng dụng kích hoạt, gồm app, worker,
scheduler, Nginx và dependency; migration một lần được kiểm tra bằng exit status.
Thiếu healthcheck hoặc dùng `NONE`/`disable: true` ở container runtime thì dừng.
Metadata này nằm ngay trong cấu hình Compose của service, không phải danh sách service thứ hai
trong workflow. Thiếu metadata, path không hợp lệ hoặc trùng path thì discovery
dừng trước khi phát hành. Thêm service không cần sửa workflow nghiệm thu.

Container ngoài app khai báo `x-deploy.role`: `infrastructure` cho database/cache/broker,
`gateway` cho Nginx, `worker` cho tiến trình dùng image app và `migration` cho tiến trình
migration một lần. Worker/migration khai báo thêm `x-deploy.application` là app sở hữu
image. Discovery kiểm tra quan hệ này, không đoán vai trò từ chuỗi image. App nội bộ
khai báo `x-deploy.gateway_health_path: null`; app có route health qua gateway khai báo
path tuyệt đối. Stack staging có một gateway; tên lấy từ Compose.
Trong Compose, `x-work-runtime` dùng YAML anchor để chia sẻ image, env mappings
và dependency giữa API/worker Work. Mỗi tiến trình vẫn khai báo command, healthcheck
và phần dependency riêng; cấu hình này được Compose resolve trước khi chạy.

Các script CI là automation chung của repository, không phải Python service hoặc
project triển khai riêng. Khi chạy script cần đọc YAML, workflow dùng
`uv run --no-project --with PyYAML==6.0.3`: uv tạo môi trường tạm với dependency
được pin, không mượn dependency của Identity và không tạo `pyproject.toml` trong
`scripts/`. `read_python_services` đọc manifest, `validate_runtime` kiểm tra
Compose, `discover_services` xuất matrix; các hàm này không khởi động container
hoặc đọc secret.

Workflow tự tạo matrix cho service bị thay đổi hoặc bị ảnh hưởng bởi cấu hình chung,
không cần thêm job/path filter cho từng service. PostgreSQL/Redis dành test được chọn
từ dependency Compose; biến test riêng đặt tại `x-ci.test_env` của service trong Compose
(chỉ chứa giá trị kiểm thử, không chứa secret thật). Các dependency khác cần hỗ trợ
kiểm thử thực tế; nhận diện thư mục không tự dựng broker/provider hoặc service bên ngoài.
Job lỗi hoặc bị hủy vẫn chặn release. Thay đổi scaffolding chưa triển khai không kích
hoạt release. Django được nhận diện từ dependency trong `pyproject.toml` để chọn migration.
Settings kiểm thử lấy từ `tool.pytest.ini_options.DJANGO_SETTINGS_MODULE`, dùng chung
cho pytest và gate Django. CI chạy `check`, `makemigrations --check --dry-run` trước
tests. PR kiểm diff với cha thứ nhất của merge commit để chặn sửa/xóa/đổi tên
migration đã trên nhánh gốc; migration mới được phép thêm. Gate này bảo vệ lịch sử
đã merge, không xác định migration nào đã áp dụng trên từng VPS.

Compose staging mặc định chạy PostgreSQL, Redis, Identity và Nginx. Các app còn lại dùng
profile cùng tên service; Kafka có profile `kafka` và được bật cùng profile Work.
Workflow cấp profile từ kết quả nhận diện, không lấy `COMPOSE_PROFILES` tùy ý trên VPS.
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

Workflow dùng chung nhận các input tùy chọn từ job gọi trong `ci.yml`:

| Input | Mặc định | Trách nhiệm |
| --- | --- | --- |
| `postgres` | `false` | Khởi tạo PostgreSQL 16 tại `127.0.0.1:5432`, database `ci`, user `utask_ci`, password `ci-only-postgres-password`. |
| `redis` | `false` | Khởi tạo Redis 7 tại `127.0.0.1:6379`. |
| `test_env` | `{}` | JSON chứa biến kiểm thử không bí mật, truyền vào pytest và gate Django. |
| `django` | `false` | Chạy system check, kiểm tra lệch model/migration và bảo vệ lịch sử migration trên PR. |

Hai container thuộc riêng từng job trên runner tạm thời. Health checks phải đạt trước
khi chạy các bước kiểm tra. Credential trên chỉ dành cho CI; không dùng secrets
staging/production hoặc `.env` local cho pytest. `test_env` không phải cơ chế truyền secrets.

Job Identity bật cả hai dependency và truyền `POSTGRES_*`, `DATABASE_NAME=ci`,
`IDENTITY_TEST_DB_NAME=test_identity_ci` cùng `IDENTITY_TEST_REDIS_URL` dùng Redis DB15.
pytest-django tự tạo/migrate/xóa test database. Workflow chung chạy một bước
`uv run pytest`, không rẽ nhánh theo tên service.

Các service khác tự nhận dependency PostgreSQL/Redis theo Compose. Discovery nhận diện
PostgreSQL từ image của dependency, không dựa vào tên service; service dùng database
riêng có thể khai báo tên database test trong `x-ci.test_env`, workflow tạo database cô
lập trước pytest. Nếu cần biến test khác với quy ước chung, khai báo `x-ci.test_env` cạnh
service, không cần sao chép workflow hoặc tạo môi trường staging cho test. Bộ lọc `shared`
kiểm tra các service được nhận diện từ source hiện tại; không dùng source thiếu của service
chưa bật để chặn service khác.

Schema tests xuất OpenAPI từ URLconf/serializers thật và kiểm response của các API.
Không so với `contracts/api/identity.openapi.json` khi artifact này không được lưu trong
repository; xem [cách xuất hợp đồng](../../contracts/api/README.md).

## Kiểm tra CI local trước khi đẩy mã

Chạy từ thư mục gốc repository:

```bash
uv run --no-project --with PyYAML==6.0.3 python scripts/ci_local.py
```

Script tự nhận diện service bằng cùng hàm với GitHub Actions, kiểm tra tất cả service
đã có đầu vào trên máy và chỉ kiểm tra Web nếu có source. Kết nối PostgreSQL/Redis local
được cấp qua biến môi trường của người chạy; các giá trị này ưu tiên hơn mẫu kết nối CI.
Script chạy cùng bộ regression deployment với GitHub trước khi kiểm tra Compose và
service. Regression shell yêu cầu Linux/WSL có Bash; chạy CI local trong môi trường
này, không coi Python Windows là môi trường đã được kiểm chứng. Script không đẩy
image hoặc triển khai staging. `--skip-images` chỉ bỏ bước build image, vẫn chạy
regression deployment.

Kiểm tra regression của cấu hình lựa chọn service và việc dừng deploy khi migration lỗi:

```bash
uv run --no-project --with PyYAML==6.0.3 python -m unittest discover -s scripts/tests -p 'test_*.py'
```

Test shell deploy chạy [deploy_staging.sh](../../scripts/deploy_staging.sh) trên Linux,
với fake Docker/SSH dùng chung tại [fixtures/deployment.py](../../scripts/tests/fixtures/deployment.py).
Regression không thực hiện deploy. Kiểm tra cú pháp workflow bằng
actionlint; kiểm tra Compose với `.env.example`, image prefix/tag mẫu và các profile đang bật.

Khi chạy tests Identity trên máy local, chuẩn bị PostgreSQL có quyền tạo test database
và Redis dành kiểm thử, rồi cấp các biến kết nối tương ứng. Script local không tự tạo
service containers như GitHub Actions; không dùng credential staging/production cho test.

## Cấu hình GitHub

Tạo Environment có tên `staging` và giới hạn nhánh triển khai là `main`. Việc yêu cầu người duyệt trước khi triển khai là tùy chọn quản trị, không thay đổi cơ chế workflow tự khởi động sau CI.

| Tên                         | Khai báo tại         | Bắt buộc | Mục đích                                            |
| --------------------------- | -------------------- | -------- | --------------------------------------------------- |
| `STAGING_WORKDIR`           | Environment variable | Có       | Thư mục triển khai, ví dụ `/opt/utask`.             |
| `STAGING_URL`               | Environment variable | Không    | Địa chỉ hiển thị trong GitHub Deployment.           |
| `STAGING_HOST`              | Environment secret   | Có       | Tên máy hoặc địa chỉ máy staging.                   |
| `STAGING_USER`              | Environment secret   | Có       | Tài khoản SSH dùng để triển khai.                   |
| `STAGING_SSH_PRIVATE_KEY`   | Environment secret   | Có       | Khóa riêng SSH tương ứng với máy staging.           |
| `STAGING_KNOWN_HOSTS`       | Environment secret   | Có       | Nội dung `known_hosts` đã xác minh cho máy staging. |
| `STAGING_REGISTRY_USERNAME` | Environment secret   | Có       | Tài khoản có quyền đọc package trên GHCR.           |
| `STAGING_REGISTRY_TOKEN`    | Environment secret   | Có       | Token chỉ có quyền đọc package trên GHCR.           |

Các giá trị sau do GitHub hoặc workflow cung cấp, không cấu hình thủ công: `GITHUB_TOKEN`, `STAGING_REGISTRY`, `STAGING_IMAGE_PREFIX` và `STAGING_IMAGE_TAG`.

Không đưa khóa SSH, token registry, khóa Django hoặc `.env` staging vào repository.

`Configure SSH` ghi secret nguyên nội dung bằng `printf '%s\n'` như trước, rồi kiểm tra
bằng `ssh-keygen -y -P ''` trước khi kết nối. Bước này không đổi CRLF, không chuyển đổi
định dạng và không tự sửa secret. Public/private key và stderr chứa dữ liệu tùy ý không
được in ra log. Nếu lỗi, workflow chỉ báo thông báo cố định tương ứng với lỗi OpenSSH
(`error in libcrypto`, `incorrect passphrase` hoặc lỗi chưa xác định), rồi dừng.

Trong [mã nguồn OpenSSH](https://github.com/openssh/openssh-portable/blob/V_9_6_P1/ssherr.c),
`error in libcrypto` là một mã lỗi chung, không xác định nguyên nhân CRLF hay dán thiếu
khóa. [Tài liệu ssh-keygen](https://man.openbsd.org/ssh-keygen) mô tả kiểm tra private key
bằng `-y`; `-P ''` thử đọc với passphrase rỗng để tránh prompt trong CI. Test trên khóa
thử chỉ chứng minh bước kiểm tra hoạt động; nguyên nhân của secret thật phải được xác
minh trên runner. Khóa có passphrase chưa được workflow hỗ trợ. Đọc được khóa chưa
chứng minh VPS chấp nhận nó; nếu SSH vẫn trả `Permission denied`, tiếp tục kiểm tra
user, khóa được cấp và cấu hình SSH phía VPS.

## Bảo vệ nhánh chính

Trong cài đặt repository, bảo vệ `main` với các quy tắc sau:

- Chỉ nhập mã qua Pull Request; không cho đẩy trực tiếp hoặc force push.
- Bắt buộc CI thành công trước khi gộp mã và yêu cầu ít nhất một người duyệt.
- Chọn squash merge và xóa nhánh ngắn hạn sau khi gộp.
- Giới hạn Environment `staging` cho nhánh `main`; nếu môi trường có phê duyệt, bật phê duyệt bắt buộc.

## Chuẩn bị máy staging

### HTTP và HTTPS

Cấu hình trong repository hiện chỉ chạy HTTP: [Nginx](../../infra/nginx/nginx.conf)
nghe port 80, [Compose staging](../../docker-compose.staging.yml) publish
`${UTASK_HTTP_PORT:-8080}:80`. Đặt `UTASK_HTTP_PORT=80` trong `.env` VPS nếu muốn
truy cập HTTP không cần ghi port. Security Group/firewall phải cho phép port đã chọn.

Compose không mount chứng chỉ, publish 443 hoặc cấu hình Certbot/gia hạn. TLS trên
VPS thực tế **chưa xác minh**; không dùng workflow hay tài liệu này để kết luận HTTPS
đã hoạt động. Bật TLS cần cấu hình riêng và nghiệm thu HTTPS, nằm ngoài luồng hiện tại.
Kiểm tra HTTP bằng `http://<host>:<UTASK_HTTP_PORT>/api/auth/healthz` và mở Swagger tại
`http://<host>:<UTASK_HTTP_PORT>/api/auth/docs/` (bỏ phần port khi dùng 80).

Máy staging cần Docker Engine/Compose plugin, `.env` tại `STAGING_WORKDIR` và khóa RSA
riêng cho Identity. Dùng [.env.example](../../.env.example) làm mẫu rồi thay toàn bộ
giá trị local của service đang bật bằng cấu hình staging, gồm secrets, domain và đường dẫn
PEM. Workflow không upload/ghi đè `.env` hoặc file PEM.

Workflow upload `docker-compose.staging.yml`, `.env.example`, bộ ánh xạ dùng chung `infra/env/*.env`,
Nginx, init PostgreSQL và script deploy; datasets upload nếu thư mục có trong source,
không rẽ nhánh theo tên AI. Các biến Google/GitHub/R2/caller keys nếu dùng
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
`UTASK_IMAGE_TAG=sha-<commit>` để nội suy file Compose gốc; image app và worker thực tế
được ghi đè bằng `image@sha256:...` trong `staging-images.json`. File này do workflow
ghép từ artifact của đúng lần phát hành rồi upload, không phải file env hoặc danh sách
service phải quản lý tay. Khi thao tác trên VPS sau deploy, giữ cả hai file Compose
và cấp hai biến nội suy như lần phát hành; không chạy riêng file Compose gốc.
Ví dụ với Identity:

```bash
compose=(docker compose --env-file .env -f docker-compose.staging.yml -f staging-images.json --profile identity-service)
"${compose[@]}" config --quiet
"${compose[@]}" pull
"${compose[@]}" up -d --no-build --wait postgres redis
"${compose[@]}" run --rm --no-deps --interactive=false identity-service /app/.venv/bin/python manage.py migrate --noinput < /dev/null
"${compose[@]}" up -d --no-build --wait --wait-timeout 120
```

Không dùng `docker compose down -v` khi chuyển file. File Compose local cũ trên server
không còn được workflow gọi; không cần xóa nó để triển khai bằng `-f` rõ ràng.

## Luồng phát hành

```text
Pull Request → CI theo đường dẫn → merge vào main
                                  ↓
                 build image → artifact digest → staging-images.json
                                  ↓
                    Environment staging gate (nếu cấu hình)
                                  ↓
       SSH → pull → nginx -t → dependency healthy → migrate → app/worker healthy
                                                     ↓
               cập nhật/reload Nginx → migrate --check → JSON health qua gateway
```

Mỗi service đang bật có image độc lập. Khi một thay đổi kích hoạt release, workflow
build tất cả image đang bật bằng BuildKit và đẩy manifest theo digest; cache GitHub
Actions chỉ tái sử dụng layer build. Mỗi job xuất artifact riêng chứa image app cùng
worker sở hữu bởi app đó. Job deploy tải artifact của cùng workflow run, kiểm tra đủ
app được chọn rồi ghép `staging-images.json`. Compose trên VPS đọc image theo digest,
không dùng tag registry để chọn phiên bản. Chạy lại riêng job deploy dùng artifact
cũ còn lưu; chạy lại job build có thể tạo digest khác và thay artifact của job đó.
Quyền registry và thời hạn lưu artifact vẫn cần quản lý; không xóa image còn dùng
trên VPS hoặc cần cho phục hồi.

CI chỉ hủy run cũ khi là Pull Request. Push `main` không hủy run đang migration/deploy;
workflow phát hành dùng một nhóm concurrency `staging` cho cả publish và deploy,
không khai báo thêm nhóm trùng tại job deploy.
Concurrency mặc định không bảo đảm mỗi commit đều được deploy hay thứ tự FIFO;
run đang chờ có thể được thay bằng run mới. Không tự hủy run đang thực thi.

Namespace GHCR luôn chuyển owner repository về chữ thường, ví dụ
`TriNguyenThanh` → `ghcr.io/tringuyenthanh/utask`. Workflow phát hành tính namespace
một lần, dùng chung khi publish image và deploy. Bước kiểm tra Compose
cũng chuẩn hóa cùng quy tắc; tên hiển thị tài khoản GitHub không cần đổi.

Workflow upload `scripts/deploy_staging.sh`; SSH gọi file này trên VPS. Giá trị runtime,
gồm token registry, được truyền qua stdin, không đặt trong đối số secret hay file env mới.
Sau dòng workdir dùng để gọi script, mỗi đầu vào có dạng `tên=giá trị`; thứ tự các
trường không ảnh hưởng. Script chỉ nhận tên trường đã khai báo, từ chối tên lạ hoặc
thiếu trường trước khi gọi Docker, không dùng `eval`/`source` để thực thi giá trị.
Giá trị phải nằm trên một dòng. Token không ghi ra file hay log; script xóa biến token
sau login và logout khi kết thúc.
Docker interactive được đóng stdin; không trộn mã Bash cần thực thi với dữ liệu/migration.
Workflow chạy `manage.py migrate --noinput` cho app có dependency Django được nhận diện,
bằng `/app/.venv/bin/python`. App không có Django không bị ép chạy lệnh Django.
Dependency hạ tầng được lấy từ Compose đang bật, gồm cả dependency của worker;
workflow chờ chúng healthy trước migration, không cố định PostgreSQL/Redis.
Migration Django và Alembic của AI được chạy trước khi khởi động stack app; lỗi migration
dừng deploy trước bước `up` toàn stack. Các service dùng framework/lệnh khác cần khai báo
cơ chế migration riêng khi được đưa vào release.
Riêng AI, deploy chờ PostgreSQL AI và Redis healthy rồi chạy migration bằng `compose up`
với `--force-recreate --exit-code-from ai-migrate` trước app stack. Lệnh trả lỗi sẽ dừng
deploy. Sau đó script khởi động rõ các process runtime bằng `--no-deps`, nên Compose không
duyệt lại dependency và chạy migration lần nữa; các dependency hạ tầng và migration đã
được kiểm tra ở bước trước. Container migration thành công vẫn được giữ lại để
`service_completed_successfully` tiếp tục làm dependency gate khi chạy Compose thủ công.
Nginx config được upload dưới tên `nginx.deployment.conf`, kiểm tra bằng container
chạy `nginx -t` trước migration; file đang dùng được giữ nguyên khi validation lỗi.
Sau khi app/worker healthy, script ghi nội dung mới vào đúng bind mount hiện có,
chạy `compose up` cho gateway để áp dụng cả thay đổi image, port hoặc mount, rồi
`nginx -t` và `nginx -s reload`. Khi cấu hình container không đổi, Compose giữ
container đang chạy và Nginx thay worker bằng graceful reload. Nếu container cần
tạo lại, có thể gián đoạn ngắn; staging không bảo đảm không gián đoạn.
Sau khi các container sẵn sàng, workflow chạy `migrate --check` cho mọi service
Django được nhận diện, rồi chạy probe Python trong một container app để gọi tất cả
path health qua Docker DNS `http://nginx`. Không dùng `localhost` của container
Nginx, tránh lựa chọn IPv6 loopback khi Nginx chỉ nghe IPv4. Probe yêu cầu HTTP 200,
không redirect và JSON có `status: "ok"` ở root hoặc trong envelope `data`;
`success: false` bị từ chối. Mỗi request có timeout 5 giây, tối đa 3 lần thử, chờ
2 giây giữa các lần và ghi path đang kiểm tra, không in response body.
Header `Host: nginx` dùng tên gateway
đã có trong `DJANGO_ALLOWED_HOSTS` chung; giữ tên này trong cấu hình môi trường.
Lệnh lỗi dừng deploy và giữ mã lỗi, không báo thành công khi chỉ một service vượt
kiểm tra. Script không tự phục hồi runtime hoặc đảo ngược migration; các container
đã cập nhật có thể vẫn đang chạy. Khi cần phục hồi, chọn lần phát hành thành công
trước đó và chạy lại riêng job `deploy-staging`, giữ nguyên artifact chứa digest và
source của lần đó. Không chạy lại toàn workflow nếu cần giữ image gốc. Cách này cần
artifact còn hạn và run còn được GitHub cho phép chạy lại (tối đa 30 ngày; xem
[hướng dẫn GitHub](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/re-run-workflows-and-jobs)).
Migration đã chạy vẫn còn, vì vậy phiên bản trước phải tương thích với schema hiện
tại; kiểm tra lại health và nghiệp vụ sau phục hồi. Quy trình này không thay thế
nghiệm thu từng API hoặc kiểm tra HTTPS bên ngoài. Health
response không có mã định danh backend nên probe chưa chứng minh danh tính service
ở đầu kia; route vẫn phải được đối chiếu với Nginx. Work publisher dùng Celery ping
tới đúng node; beat kiểm tra PID còn sống và kết nối broker. Các phép kiểm tra này
chưa chứng minh scheduler tiến triển, task được thực thi hay event tới Kafka.
`work-profile-consumer` dùng profile riêng và không được workflow này tự bật.

Không dùng `--remove-orphans` trong deploy; không tự xóa container hoặc volume của
service nằm ngoài phạm vi. Nếu thu hẹp danh sách, các container đã chạy trước đó phải
được dừng riêng có chủ đích; bỏ profile hoặc source không tự dừng chúng.

Job kiểm tra Python dùng matrix `Check <service>`. Check tổng hợp có tên cố định
`CI result`, thất bại nếu nhận diện hoặc bất kỳ job được chọn nào lỗi/bị hủy/bị bỏ qua;
chỉ cho phép bỏ qua job không được chọn. Release
phải chờ check này thành công. Khi đổi từ cấu hình cũ, quản trị repository chọn
`CI result` làm required check một lần trên GitHub, không phải thêm tên check mỗi khi
có service mới. Thay file workflow không tự đổi branch protection.

Nếu chưa cấu hình Environment hoặc secrets, bước triển khai sẽ dừng với thông báo thiếu cấu hình; không có triển khai giả hoặc tự động bỏ qua lỗi.

## Production

Baseline yêu cầu production từ release/tag hoặc workflow được kiểm soát, với PostgreSQL,
Redis/Kafka bên ngoài và secrets của nền tảng production. Compose local/staging không thay thế quyết
định hạ tầng đó. Khi có production cần Environment/quy trình triển khai riêng và image SHA.

## Pipeline AI trong CI/CD

**Một phần (cấu hình và regression test có trong repository; staging thực tế chưa xác minh):** CI vẫn build/publish một image
`ai-service`; staging dùng cùng tag SHA cho `ai-service`, `ai-worker`,
`ai-dispatcher`, `ai-migrate`. Bốn process và `ai-postgres` cùng profile
`ai-service`. Nhận diện app dựa trên thư mục source; các process phụ không tạo
thêm entry build. `ai-service` là app nội bộ, khai báo
`x-deploy.gateway_health_path: null`; `ai-worker`, `ai-dispatcher` và
`ai-migrate` dùng chung image AI. `ai-postgres` có vai trò `infrastructure`;
`ai-migrate` có vai trò migration của `ai-service`. API không chờ Work/Integration
tại Compose; REST adapter vẫn kiểm tra quyền/context và từ chối khi domain chưa sẵn sàng.

AI phụ thuộc PostgreSQL 17 riêng với volume `ai_database`, không đổi dữ liệu
PostgreSQL Django. Broker dùng Redis chung DB1. API, worker và dispatcher chờ
`ai-migrate` hoàn tất thành công; migration chạy một lần bằng Alembic trước khi
khởi động app stack và lỗi migration làm deploy dừng. `x-ci.test_env` của AI cấp
`TEST_DATABASE_NAME=ai_test`, `TEST_DATABASE_URL`, `TEST_REDIS_URL`; workflow
Python tạo database test theo tên được validate rồi chạy pytest. Script nhận
diện PostgreSQL theo image của dependency, nên `ai-postgres` cũng bật PostgreSQL
cho CI. Bộ workflow hiện khai báo PostgreSQL 16 cho runner; runtime AI dùng 17.

`depends_on: service_completed_successfully` cũng bảo vệ thứ tự khi chạy Compose
thủ công. Migration chạy tới `head`; nếu không bật AI thì không chạy bước Alembic
hoặc khởi động PostgreSQL AI. Không có chuyển dữ liệu tự động từ Compose AI riêng.

Trên VPS, điền password DB, khóa Fernet, JWT issuer/audience và public key hoặc
JWKS, URL REST quyền/context, model/base URL/API key trong `.env` server theo
[biến môi trường](environment.md#cấu-hình-ai-trong-compose-root). Staging mặc
định `AI_ENVIRONMENT=staging`, `MOCK_TEST=false`; không dùng mock development
hoặc endpoint proxy local làm cấu hình staging mặc định.

`--wait` kiểm tra health của API, Celery ping của worker và process liveness của
dispatcher; kiểm tra liveness chưa chứng minh dispatcher đã phát job. Probe gateway
cuối workflow kiểm tra các path health của service đang bật; AI nội bộ không có path
gateway để probe. CI test
pipeline dùng model giả, không xác nhận LLM thật hoặc domain production. Triển
khai trên GitHub/VPS **Chưa xác minh**; thay đổi này không bảo đảm zero downtime
hoặc rollback database tự động.
