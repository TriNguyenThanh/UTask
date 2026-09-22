# CI/CD

UTask dùng một workflow điều phối và hai workflow dùng lại trong GitHub Actions:

1. `ci.yml` chạy khi có pull request vào `main` hoặc khi đẩy mã lên `main`. Workflow lọc theo đường dẫn, kiểm tra đúng service bị ảnh hưởng và kiểm tra Compose. Pytest của AI bao gồm regression evaluation. Pull Request dựng image để kiểm tra Dockerfile; lần đẩy lên `main` chỉ gọi phát hành sau khi mọi kiểm tra liên quan thành công.
2. `python-service.yml` không tự khởi động. Đây là workflow dùng lại được `ci.yml` gọi cho từng service Python để tránh lặp các bước cài dependency, lint, format, test và kiểm tra image.
3. `release-staging.yml` là workflow dùng lại do `ci.yml` gọi. Workflow chỉ dựng và đẩy image của service có mã nguồn thay đổi. Với service không đổi, workflow gắn thẻ SHA mới cho manifest `main` hiện có mà không dựng lại image. Sau khi đủ sáu image của cùng bản phát hành, workflow triển khai staging bằng Docker Compose qua SSH.

## Kiểm tra CI local trước khi đẩy mã

Chạy từ thư mục gốc repository:

```powershell
python scripts/ci_local.py
```

Lệnh này kiểm tra Compose, Nginx, script PostgreSQL, lint/format/test của sáu service Python, lint/typecheck/test/build của Web và dựng Docker image. Dùng `python scripts/ci_local.py --skip-images` để bỏ qua bước dựng image khi cần vòng lặp nhanh hơn. GitHub Actions vẫn là bước kiểm tra bắt buộc trên remote; script local không đẩy image hoặc triển khai staging.

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

Máy staging cần có Docker Engine, Docker Compose plugin và tệp `.env` tại `STAGING_WORKDIR`. Workflow tự đồng bộ `docker-compose.yml`, các tệp ánh xạ `infra/env/*.env`, cấu hình Nginx, script PostgreSQL và datasets.

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
```

`UTASK_HTTP_PORT` là tùy chọn và mặc định là `8080`. Workflow đặt `UTASK_IMAGE_PREFIX` và `UTASK_IMAGE_TAG=sha-<commit>` tại lúc triển khai, vì vậy hai biến này không bắt buộc trong `.env` staging. Các tệp `infra/env/*.env` chỉ là ánh xạ không bí mật; workflow không sao chép hoặc ghi đè `.env`.

## Luồng phát hành

```text
Pull Request → CI theo đường dẫn → merge vào main
                                  ↓
             build image đổi + gắn thẻ lại image không đổi
                                  ↓
                    Environment staging gate (nếu cấu hình)
                                  ↓
                 SSH → compose pull → compose up --wait
```

Mỗi service vẫn có image độc lập. Image thay đổi được gắn hai thẻ: `main` và `sha-<commit>`. Image không đổi giữ nguyên manifest và chỉ nhận thêm thẻ `sha-<commit>`, nhờ đó Compose vẫn triển khai một bộ sáu image đồng nhất theo cùng SHA mà không dựng lại service không liên quan. Thẻ `main` là nguồn hiện hành để tái sử dụng; nếu image này chưa tồn tại, phát hành dừng thay vì tạo kết quả giả.

Nếu chưa cấu hình Environment hoặc secrets, bước triển khai sẽ dừng với thông báo thiếu cấu hình; không có triển khai giả hoặc tự động bỏ qua lỗi.

## Production

Baseline chỉ cho phép triển khai production từ release/tag hoặc workflow được kiểm soát, đồng thời yêu cầu PostgreSQL, Redis và Kafka bên ngoài. Repository chỉ giữ một `docker-compose.yml` cho local và staging; không tạo thêm một Compose production khi chưa có nền tảng, mạng và cơ chế secrets được baseline chỉ định. Không dùng workflow staging cho production; khi có hạ tầng, cần tạo Environment production riêng và triển khai image theo thẻ SHA bất biến.
