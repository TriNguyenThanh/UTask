# Biến môi trường

`docker-compose.yml` dành local; `docker-compose.staging.yml` dành triển khai staging
bằng image đã phát hành. Hai Compose dùng chung bộ ánh xạ `infra/env/*.env` và
một mẫu [.env.example](../../.env.example). Mỗi máy có `.env` riêng, không commit:

- `database.env`: thông tin PostgreSQL dùng chung (`POSTGRES_*`).
- `django.env`: cấu hình dùng chung cho các dịch vụ Django.
- `postgres.env`: tên database do script khởi tạo sử dụng.
- `<service>.env`: cấu hình riêng của từng service, gồm tên database và khóa service hoặc URL service.
- `classroom-service.env`: cấu hình riêng Classroom Service, gồm
  `KAFKA_BOOTSTRAP_SERVERS` để kết nối tới broker Kafka.

## Chọn Kafka Docker hoặc Kafka bên ngoài

**Đã triển khai ở cấu hình và client Work/Classroom.** Đã kiểm tra đăng nhập
Aiven và đọc thông tin broker bằng hàm cấu hình của cả hai service từ máy
phát triển; chưa nghiệm thu gửi/nhận sự kiện hoặc deploy VPS.
Dùng cùng một bộ biến trên local và staging:

```dotenv
# Local: bật profile kafka để chạy broker trong Docker.
COMPOSE_PROFILES=kafka
KAFKA_BOOTSTRAP_SERVERS=kafka:9092
KAFKA_SECURITY_PROTOCOL=PLAINTEXT
```

```dotenv
# Staging: thay bằng địa chỉ do nhà cung cấp Kafka cấp.
COMPOSE_PROFILES=
KAFKA_BOOTSTRAP_SERVERS=broker.example.com:9092
```

Nếu nhà cung cấp yêu cầu đăng nhập, điền thêm đúng thông số họ cấp:

```dotenv
KAFKA_SECURITY_PROTOCOL=SASL_SSL
KAFKA_SASL_MECHANISM=PLAIN
KAFKA_SASL_USERNAME=...
KAFKA_SASL_PASSWORD=...
```

`KAFKA_SECURITY_PROTOCOL` chọn kiểu kết nối: `PLAINTEXT` không mã hóa,
`SSL` mã hóa đường truyền, `SASL_PLAINTEXT` đăng nhập không mã hóa,
`SASL_SSL` đăng nhập qua đường truyền mã hóa. `KAFKA_SASL_MECHANISM` là
cách đăng nhập, hỗ trợ `PLAIN`, `SCRAM-SHA-256`, `SCRAM-SHA-512`;
chỉ cần điền theo nhà cung cấp, không tự đoán. Khi không dùng SASL, client
không gửi thông tin đăng nhập. Giá trị không hợp lệ hoặc thiếu tài khoản/mật
khẩu khi dùng SASL khiến client dừng với lỗi cấu hình, không tự hạ kiểu kết nối.

`KAFKA_SSL_CA_LOCATION` để trống để dùng chứng chỉ tin cậy mặc định của client.
Nếu nhà cung cấp cấp chứng chỉ CA riêng (chứng chỉ dùng để xác minh máy chủ),
Compose staging gắn thư mục `infra/env` chỉ đọc vào `/run/kafka-certificates`
cho các container Work/Classroom. Đặt tệp tại `infra/env/ca.pem`, rồi cấu hình:

```dotenv
KAFKA_SSL_CA_LOCATION=/run/kafka-certificates/ca.pem
```

Đây là đường dẫn **trong container**, không phải đường dẫn Windows. Khi không
dùng CA riêng, để biến trống; không bắt buộc có `ca.pem` nếu dùng Kafka Docker.
Tệp CA chỉ dùng với `SSL`/`SASL_SSL`. Chỉ đặt chứng chỉ CA công khai và các
mapping không chứa bí mật trong thư mục này, không đặt khóa riêng hoặc `.env`
chứa thông tin đăng nhập.

Trên VPS cũng cần tệp tại `STAGING_WORKDIR/infra/env/ca.pem`. Tệp PEM đang được
Git bỏ qua; workflow chỉ chuyển các mapping `*.env`, không tự chuyển CA.
Chuẩn bị CA trên VPS trước khi tạo lại container; không đưa khóa riêng vào Git.

Chạy trực tiếp Docker Compose từ repository root. Compose tự đọc `.env`:

```bash
docker compose up --build -d

# Trên VPS, dùng .env của staging cạnh file Compose.
# Workflow deploy vẫn cấp image đã phát hành qua staging-images.json.
docker compose -f docker-compose.staging.yml -f staging-images.json up -d
```

Nếu cần chạy app có profile khi thao tác staging thủ công, thêm
`--profile work-service --profile classroom-service` trước `up`.
Khi truyền `--profile` trên lệnh, Docker Compose ưu tiên danh sách đó thay cho
`COMPOSE_PROFILES`; nếu vẫn dùng broker Docker, thêm cả `--profile kafka`.
Deploy staging tự bật profile các app được phát hành và giữ lựa chọn profile
`kafka` của máy chủ. Để dùng cloud, bỏ `kafka` khỏi `COMPOSE_PROFILES`
(giữ các profile khác nếu có) rồi điền địa chỉ broker.
Không cần file Compose riêng hay script khởi động bổ sung.
Worker chỉ chờ broker Docker khi profile `kafka` được bật; khi tắt, dependency
này không bắt buộc. Docker Compose cần hỗ trợ `depends_on.required` (từ 2.20).
Biến đã export trong shell được Compose ưu tiên hơn giá trị trong `.env`.

Tắt profile `kafka` không tạo topic trên cloud, không chuyển dữ liệu/offset và không tự
xóa container Kafka cũ. Chuẩn bị topic, quyền gửi/nhận, nhóm đọc và thời gian
lưu theo [hướng dẫn Kafka](kafka.md#kafka-bên-ngoài). Giữ nguyên volume nếu
cần quay lại broker Docker. Sau khi sửa cấu hình kết nối, tạo lại các container
liên quan để nhận biến mới; chỉ restart không nạp lại giá trị.

Các biến kết nối đi qua `.env` → `infra/env/work-service.env` hoặc
`infra/env/classroom-service.env` → Compose `env_file` → settings → client
gửi/nhận và gửi thông điệp lỗi. Profile chỉ chọn container cần chạy,
không thay đổi nội dung sự kiện.

AI Service chỉ dùng `infra/env/ai-service.env` cho biến thường/cờ chế độ
và `.env` root cho secret. AI_ENVIRONMENT và MOCK_TEST chọn context mock;
chỉ development/test được bật mock; dữ liệu mẫu được đọc ngay tại adapter,
không cần server/mock microservice hay launcher riêng. SDK nhận key từ Settings, không cần
export secret ra terminal. Compose inject `AI_CREDENTIAL_KEY`, `AI_JWT_PUBLIC_KEY` và `AI_LLM_API_KEY`
vào các process AI; PostgreSQL AI nhận `AI_DB_PASSWORD`. Compose root ghi đè
URL DB sang `ai-postgres` và broker sang Redis DB1, tránh `localhost` trong container.
CI/CD tiếp tục dùng `infra/env/*.env`, không upload `.env` root. Xem
[cấu hình AI](../ai-service/README.md#cấu-hình) và
[mock data](../ai-service/mock-data.md).

Không ghi bí mật thật vào các tệp được theo dõi trong Git. Tạo `.env` cục bộ
theo mẫu repository rồi kiểm tra cấu hình Compose:

```powershell
if (-not (Test-Path -LiteralPath .env)) {
    Copy-Item -LiteralPath .env.example -Destination .env
}
docker compose -p utask config --quiet
```

Điền các giá trị local còn thiếu trước khi khởi động. Với Identity–Classroom–Work,
dùng một nguồn hướng dẫn là [quy trình local](local-development.md#khởi-động-identity-classroom-và-work).
Trong local, `start-postgres.sh` gọi `init-databases.sh` sau khi PostgreSQL sẵn
sàng; script tạo các database còn thiếu kể cả khi volume đã được khởi tạo.
Staging cũng dùng wrapper PostgreSQL này: deploy upload `start-postgres.sh`,
health chỉ sẵn sàng sau preparation, kể cả volume đã có dữ liệu. Script tạo
role Integration và cập nhật mật khẩu từ `INTEGRATION_DB_PASSWORD`; cấu hình
thiếu/trùng hoặc role có đặc quyền gây dừng trước khi app chạy migration.
`start-kafka.sh` khởi động broker rồi tạo các topic còn thiếu theo
`kafka-startup.env`. API chạy migration trong entrypoint trước Gunicorn; worker
bỏ qua migration và đợi API tương ứng healthy. Build không kết nối database.
Staging không dùng wrapper Kafka local; migration chạy tuần tự trước runtime
theo [quy trình CI/CD](ci-cd.md).

Các tệp ánh xạ Compose không phải kho chứa mật khẩu. Không commit `.env`, khóa
Django, token hoặc thông tin xác thực môi trường dùng chung.

## Phân tách theo môi trường

- Local dùng `.env` không commit.
- CI dùng `.env.example` với giá trị kiểm tra an toàn.
- Staging giữ `.env` trên server, cũng dùng mẫu `.env.example`; thay toàn bộ mật khẩu,
  secret, domain, Kafka cluster ID và đường dẫn PEM bằng giá trị dành cho staging.
  Workflow upload mapping dùng chung, không upload `.env` hoặc PEM.
- Production dùng cấu hình của nền tảng và hạ tầng bên ngoài theo baseline; không đặt secret trong repository.

**Một phần:** Integration dùng `INTEGRATION_DB_USER`/`INTEGRATION_DB_PASSWORD`
riêng, không fallback `POSTGRES_USER`/`POSTGRES_PASSWORD`. Container app chỉ
nhận host/port, `DATABASE_NAME`, credential Integration và cấu hình Django.
Script chuẩn bị role không đặc quyền, database/schema riêng và đóng PUBLIC
CONNECT/TEMP ở các database quản lý, `postgres` và `template1`. Custom role cần
được GRANT rõ ràng trước vận hành nếu trước đây dựa PUBLIC CONNECT; database
ngoài danh sách repo phải tự đóng ACL để không cấp lại quyền cho login khác.
Role Integration cũ có đặc quyền, membership hoặc sở hữu DB khác bị từ chối;
không tự hạ quyền role đang dùng chung.

Identity/Work/Classroom còn dùng credential chung `POSTGRES_*`; baseline yêu
cầu tiếp tục tách từng service. Hai biến Integration DB credential là đầu vào
bắt buộc của PostgreSQL startup, kể cả khi profile app Integration đang tắt.
Điền giá trị riêng vào `.env` trước cập nhật local/staging; không dùng mật khẩu mẫu.

AI đã có Celery broker qua Redis; Kafka client và R2 tùy service vẫn là
công nghệ mục tiêu theo baseline; biến môi trường của từng adapter chỉ được liệt kê như đã có sau khi kiểm tra mã
triển khai. Không xem URL service trong file env là bằng chứng client đã gọi
service đó. Xem [job nền](background-jobs.md), [Kafka](kafka.md) và
[lưu trữ file](storage.md).

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

| Giá trị trong `.env` VPS                                       | Container nhận                                                   |
| -------------------------------------------------------------- | ---------------------------------------------------------------- |
| `POSTGRES_*`                                                   | PostgreSQL và các app cần database, qua mapping dùng chung       |
| `IDENTITY_DB_NAME`, `IDENTITY_DJANGO_SECRET_KEY`, `IDENTITY_*` | Identity: `DATABASE_NAME`, `DJANGO_SECRET_KEY` và cấu hình riêng |
| `WORK_DB_NAME`, `WORK_DJANGO_SECRET_KEY`                       | Work khi bật profile của service                                 |
| `CLASSROOM_DB_NAME`, `CLASSROOM_DJANGO_SECRET_KEY`             | Classroom khi bật                                                |
| `INTEGRATION_DB_NAME`, `INTEGRATION_DJANGO_SECRET_KEY`         | Integration khi bật                                              |
| `NOTIFICATION_DB_NAME`, `NOTIFICATION_DJANGO_SECRET_KEY`       | Notification khi bật                                             |

Giá trị thật nằm trong `.env`; `infra/env/<service>.env` chỉ ánh xạ `${TEN_BIEN}`.
Không tạo thêm `.env` trong từng container và không đưa nguyên `.env` chung vào tất cả
app. Hiện chỉ cần điền secret runtime của Identity và PostgreSQL, cùng khóa mail nếu
dùng đăng ký/reset; các app chưa bật chưa cần secret riêng. Giữ các tên database theo
mẫu cho script khởi tạo PostgreSQL. Xem [phạm vi staging và biến cần có](ci-cd.md).

Sau khi sửa `.env`, phải tạo lại container của service để áp dụng biến mới, không chỉ
`restart`. Workflow deploy lần tiếp theo sẽ áp dụng; nếu thao tác thủ công, cấp đúng
hai biến nội suy image prefix/tag và giữ file `staging-images.json` của lần phát hành.
Dùng cả `-f docker-compose.staging.yml -f staging-images.json` khi gọi
`up -d --no-build --force-recreate <service>`; xem lệnh trong [CI/CD](ci-cd.md).

Các service Django hiện dùng chung `POSTGRES_USER` và `POSTGRES_PASSWORD`, nhưng mỗi service vẫn nhận `DATABASE_NAME` riêng. Đây là hiện trạng chưa đáp ứng credential riêng theo baseline đã nêu ở trên.

Work nhận cấu hình qua `.env` → `infra/env/work-service.env` → `env_file` của HTTP,
publisher, Beat và profile consumer → `config/settings/base.py`. Bốn biến
`WORK_R2_ENDPOINT`, `WORK_R2_ACCESS_KEY`, `WORK_R2_SECRET_KEY`, `WORK_R2_BUCKET`
có placeholder trống trong `.env.example`; chỉ điền credentials của môi trường
được phép dùng. `WORK_STORAGE_ADAPTER` mặc định tại mapping là
`infrastructure.storage.R2Storage`. `WORK_AI_ADAPTER` và
`WORK_INTEGRATION_ADAPTER` mặc định vẫn là `UnavailableProposals` và
`UnavailableIntegration`: thêm mapping không tự nối service thật. Giữ
`WORK_CLASSROOM_DEV_ENABLED=false` ở staging; không đưa fixture test vào adapter
runtime. Kiểm propagation với env test riêng không thay nghiệm thu R2/provider.

`env_file` chỉ đưa các biến của file đó vào service được khai báo; không gán một file chung chứa toàn bộ secret cho mọi service.

Classroom nhận cấu hình qua `.env` → `infra/env/classroom-service.env` → API,
publisher, Beat, consumer → `config/settings/base.py`. Cần khóa HMAC
`CLASSROOM_ACCESS_CODE_HMAC_KEY`, khóa caller Identity
`IDENTITY_CLASSROOM_SERVICE_KEY` và khóa Work `CLASSROOM_WORK_SERVICE_KEY`.
Các secret để trống trong mẫu, phải điền riêng từng môi trường. Caller keys
`classroom`/`work` trong `IDENTITY_SERVICE_KEYS` phải khớp; không thay route
Identity để nối Classroom. Work dùng `CLASSROOM_BASE_URL`, adapter
`RemoteClassroom`, cùng khóa Work; staging giữ chế độ Classroom dev tắt.

Classroom Celery dùng Redis DB3 (`CLASSROOM_REDIS_URL`); Work dùng DB2.
`CLASSROOM_KAFKA_TOPIC`, `CLASSROOM_WORK_KAFKA_TOPIC`, nhóm đọc và DLQ có mapping
riêng; phía Work nhận các biến `WORK_CLASSROOM_KAFKA_*`. `KAFKA_LOG_RETENTION_MS`
mặc định 604800000 (7 ngày) là mặc định broker cho topic nghiệp vụ và DLQ
không có override; topic đã tồn tại có cấu hình riêng cần kiểm trực tiếp.
Chi tiết tại [Classroom backend](../classroom-service/README.md).

Mapping Work dùng `CLASSROOM_KAFKA_TOPIC` ở `.env` làm nguồn cho
`WORK_CLASSROOM_KAFKA_TOPIC` trong container để bên gửi Classroom và bên nhận
Work dùng cùng topic. `WORK_KAFKA_TOPIC`, nhóm đọc
`WORK_CLASSROOM_KAFKA_GROUP`, topic lỗi `WORK_CLASSROOM_KAFKA_DLQ_TOPIC` và
giới hạn `WORK_CLASSROOM_CONSUMER_MAX_RETRIES` cũng đi qua mapping này cho
API và mọi worker Work ở cả Compose local lẫn staging. Chỉ khai báo trong
`.env.example` không tự đưa biến vào container; phải có ánh xạ `env_file`.
Consumer Classroom của Work dùng cùng hàm cấu hình kết nối với publisher,
consumer Identity và bên gửi thông điệp lỗi, gồm tài khoản, mật khẩu và CA
khi dùng Kafka cloud. Quy tắc chỉ xác nhận offset sau xử lý hoặc DLQ thành công
được giữ nguyên; kiểm thử cấu hình không thay cho nghiệm thu luồng sự kiện thật.

Image prefix/tag và khóa RSA Identity là các đầu vào của staging Compose.
Workflow cấp image app/worker theo digest qua `staging-images.json`;
deploy thủ công vẫn cần UTASK_IMAGE_PREFIX/UTASK_IMAGE_TAG để nội suy file gốc và
phải dùng kèm file ghi đè image. Khóa phải có trước khi startup và user container
đọc được; workflow không vận chuyển PEM. Nginx hiện chỉ nghe HTTP trong container
trên port 80; port trên host lấy từ `UTASK_HTTP_PORT` (mặc định 8080). Compose hiện
không publish HTTPS 443, mount chứng chỉ hoặc chạy Certbot. TLS trên VPS thực tế
chưa được xác minh; xem [cấu hình staging](ci-cd.md#chuẩn-bị-máy-staging).
Các giá trị OAuth/R2/caller keys nằm trong `.env` của từng máy; file ánh xạ chỉ
chứa `${...}` hoặc hằng cấu hình container không bí mật. Không điền credential hoặc
flags trực tiếp vào `infra/env/identity-service.env`.

Local để `IDENTITY_REDIS_URL` trống theo cấu hình cache hiện tại. Compose staging đặt
mặc định Redis `redis://redis:6379/0` và Integration `http://integration-service:8000`;
giá trị không trống trong `.env` có thể thay các mặc định này. Chỉ bật OAuth/avatar sau
khi có đủ credential và callback theo [tài liệu Identity](../identity-service/README.md).

Nếu đổi tên database, cập nhật giá trị trong `.env` và chuẩn bị database tương ứng có
chủ đích. Local wrapper gọi script bảo đảm database ở mỗi lần khởi động; staging chỉ
chạy script qua cơ chế khởi tạo volume mới. Sửa `.env` không tự đổi tên database hoặc
chuyển dữ liệu. Không xóa volume để áp dụng biến môi trường.

## Cấu hình AI trong Compose root

Local giữ cờ và biến thường trong `infra/env/ai-service.env`. Staging mặc định
`AI_ENVIRONMENT=staging`, `MOCK_TEST=false`; dùng giá trị cấu hình staging trong
`.env` server theo các override được khai báo ở Compose. Không bật mock ở staging.

`AI_DB_PASSWORD` bắt buộc khi khởi động PostgreSQL AI lần đầu. Password phải dùng
được trong URL, hoặc cung cấp `AI_DATABASE_URL` với password percent-encode.
`AI_CREDENTIAL_KEY` phải giống nhau cho các process; JWT chọn public key hoặc
JWKS, cùng issuer/audience đúng từ Identity; LLM cần model/base URL/key và REST
adapter cần URL quyền/context thật. Xem [cấu hình AI](../ai-service/README.md#cấu-hình).
Đừng dùng endpoint proxy development trong staging nếu chưa chủ động cấu hình.

Không truyền toàn bộ `.env` chung vào container. PostgreSQL AI dùng volume
`ai_database` riêng; đổi password `.env` không tự thay password role đã lưu trong
volume. Redis DB1 là broker AI; Redis DB0 dành cấu hình Identity. Đổi file
Compose hoặc chuyển từ stack AI riêng không tự chuyển database/queue cũ.
