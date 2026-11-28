# ADR-006 — Hợp nhất Identity, Classroom và Work thành Core Modular Monolith

- Ngày: 28/11/2026.
- Trạng thái: **Đã triển khai (local)** cho mã nguồn `apps/core-service`, cấu hình Docker Compose, Nginx, CI/CD discovery và kiểm thử cục bộ; **Chưa xác minh** trên VPS staging và các provider ngoài (AI, Integration, Notification, SMTP/R2 production).
- Phạm vi: Toàn bộ miền nghiệp vụ lõi **Identity**, **Classroom**, **Work**, hạ tầng Compose/Nginx/env/CI liên quan và cam kết giữ nguyên hợp đồng giao tiếp với 4 đội bên ngoài (`web`, `ai-service`, `integration-service`, `notification-service`).

## Bối cảnh

Trước quyết định này, phần backend nghiệp vụ lõi của UTask được tách thành ba Django microservice độc lập (`apps/identity-service`, `apps/classroom-service`, `apps/work-service`), kéo theo:

1. **Chi phí container và vận hành cao:** Riêng ba service lõi chiếm tới **10 container runtime** (3 API, các Celery worker/publisher, Celery Beat, và các Kafka consumer nội bộ), ba cơ sở dữ liệu PostgreSQL riêng (`identity_db`, `classroom_db`, `work_db`), ba tệp lockfile và nhiều kênh đồng bộ vòng lặp (HTTP nội bộ + Kafka outbox/consumer + bảng chiếu `UserProjection`).
2. **Độ phức tạp nhất quán dữ liệu giữa các miền gắn chặt:** Identity, Classroom và Work có quan hệ nghiệp vụ trực tiếp (người dùng, vai trò toàn cục, thành viên nhóm học tập, thành viên dự án và quyền giảng viên giám sát). Việc giữ ba dịch vụ riêng buộc phải duy trì nhiều khóa caller nội bộ (`IDENTITY_CLASSROOM_SERVICE_KEY`, `IDENTITY_WORK_SERVICE_KEY`, `CLASSROOM_WORK_SERVICE_KEY`), cơ chế đồng bộ bất đồng bộ `classroom.group.membership.changed` / `work.project.created` và độ trễ đồng bộ hồ sơ người dùng.
3. **Nhu cầu giữ nguyên 100% hợp đồng cho các đội khác:** Bốn nhóm `apps/web`, `apps/ai-service`, `apps/integration-service` và `apps/notification-service` phát triển song song dựa trên các đường dẫn Gateway `/api/auth/*`, `/api/classroom/*`, `/api/work/*`, các route nội bộ (`/.well-known/jwks.json`, `/users/me`, `/api/v1/internal/*`), tên host Docker (`identity-service`, `classroom-service`, `work-service`) và các tệp hợp đồng trong `contracts/api/`.

## Các lựa chọn đã cân nhắc

1. **Lựa chọn A — Giữ nguyên 3 microservice lõi riêng biệt:** Không thay đổi cấu trúc nhưng giữ nguyên chi phí 10 container, 3 DB và toàn bộ vòng lặp đồng bộ HTTP/Kafka nội bộ.
2. **Lựa chọn B — Modular Monolith đa cơ sở dữ liệu (M1, dùng `DATABASE_ROUTERS`):** Gom mã nguồn vào một project Django nhưng vẫn giữ 3 database riêng. Tăng rủi ro lỗi transaction đa-DB, phức tạp hóa migration/test và vẫn không giải quyết triệt để đồng bộ dữ liệu giữa ba miền.
3. **Lựa chọn C — Modular Monolith thống nhất trên một cơ sở dữ liệu `core_db` (M2 — ĐƯỢC CHỌN):** Hợp nhất ba miền vào một project Django duy nhất (`apps/core-service`) dùng một database PostgreSQL 16 (`core_db`), giao tiếp giữa các miền trong tiến trình qua module giao diện rõ ràng (`interface.py`) với giao dịch ACID, và giữ ranh giới tuyệt đối với các service ngoài (`ai-service`, `integration-service`, `notification-service`).

## Quyết định

### 1. Kiến trúc mã nguồn chuẩn Django Modular Monolith (`apps/core-service`)

- **Tầng dùng chung thuần túy (`common/`, 0 Django model):** Tập trung xác thực JWT RS256 (`common/authentication.py`), phân quyền (`common/permissions.py`), envelope phản hồi 5 khóa (`common/responses.py`, `common/renderers.py`), bộ xử lý lỗi thống nhất (`common/errors.py`, `common/exception_handler.py`), middleware IP proxy tin cậy (`common/middleware.py`), phân trang và chuẩn hóa nội dung (`common/content.py`).
- **Tầng adapter bên ngoài (`infrastructure/`):** Chứa toàn bộ adapter giao tiếp dịch vụ ngoài (`storage.py` cho Cloudflare R2, `kafka.py`, `ai.py`, `integration.py`); không lẫn logic nghiệp vụ domain.
- **11 Django app phẳng 1 cấp trong `apps/` theo DAG (đồ thị có hướng không vòng lặp) 4 tầng:**
  - **Tầng 0 (nền tảng):** `apps.messaging` (outbox, inbox, idempotency dùng chung), `apps.accounts`, `apps.authentication`.
  - **Tầng 1 (thực thể chính):** `apps.courses`, `apps.projects`.
  - **Tầng 2 (nghiệp vụ chi tiết):** `apps.groups`, `apps.sprints`, `apps.tasks`, `apps.collaboration`, `apps.integrations`.
  - **Tầng 3 (lá):** `apps.activities` (`ClassroomActivity`, `WorkActivity`).
- **Cơ sở dữ liệu thống nhất `core_db`:** Toàn bộ tên bảng chuẩn hóa `snake_case` chữ thường, bảo toàn các trigger bảo vệ ghi PostgreSQL và khóa ngoại tổng hợp có thể trì hoãn (deferrable composite FK) của Classroom.
- **Giao tiếp nội bộ trong tiến trình (`interface.py`):** Thay toàn bộ HTTP/Kafka nội bộ giữa Identity, Classroom và Work bằng giao diện công khai `apps.accounts.interface`, `apps.groups.interface`, `apps.projects.interface`. Loại bỏ bảng chiếu `UserProjection` và các consumer nội bộ Classroom/Identity của Work cũ. Ranh giới giữa các app được bảo vệ bằng kiểm thử kiến trúc (`apps/core-service/tests/test_architecture_boundaries.py`).

### 2. Tối ưu hạ tầng Docker Compose & cấu hình môi trường

- Giảm từ **10 container Core cũ** xuống **3 container** dùng chung một Docker image (`utask/core-service`) và một cấu hình ánh xạ `infra/env/core-service.env`:
  1. `core-service`: Gunicorn HTTP API.
  2. `core-worker`: Celery worker tích hợp Beat (`celery -A config worker -B -Q core-worker`) xử lý outbox publishing, quét deadline, dọn attachment, phục hồi kết nối GitHub và dọn dữ liệu retention.
  3. `core-consumer`: chạy `python manage.py consume_integration` tiêu thụ duy nhất kênh Kafka ngoài từ Integration (`utask.integration.events` và DLQ `utask.work.integration.dlq`).
- Hợp nhất Redis nội bộ Core vào một URL (`CORE_REDIS_URL`, mặc định `redis://redis:6379/0` với `KEY_PREFIX="core"`) và hợp nhất cấu hình Cloudflare R2 (`CORE_R2_*`, giữ tương thích ngược fallback sang `WORK_R2_*` và `IDENTITY_R2_*`).
- Loại bỏ mã nguồn và env mapping của ba service cũ (`apps/{identity,classroom,work}-service/`, `infra/env/{identity,classroom,work}-service.env`).

### 3. Cam kết không phá vỡ hợp đồng (Zero Breaking Change) với 4 đội bên ngoài

- **Không sửa bất kỳ tệp nào** trong `apps/web/**`, `apps/ai-service/**`, `apps/integration-service/**`, `apps/notification-service/**`, và **giữ nguyên hoàn toàn 3 tệp hợp đồng** `contracts/api/{identity,classroom,work}-service.yaml`.
- **Đối với Team Web:**
  - `config/urls.py` gắn trực tiếp các tiền tố `/api/auth/`, `/api/classroom/`, `/api/work/` (cùng `/api/{auth,classroom,work}/{healthz,openapi/,docs/}` và OpenAPI tổng `/openapi/`, `/docs/`); Nginx chuyển tiếp trực tiếp tới `core-service:8000` mà không cần `rewrite`.
  - Giữ nguyên `@ensure_csrf_cookie` trên `/api/auth/docs/`, giữ `refresh_token` cookie với `path=/api/auth`, và giữ nguyên envelope 5 khóa `{success, message, data, meta, error}`.
  - **Đồng nhất hóa nhẹ mã lỗi hệ thống ở `common/exception_handler.py`:** thống nhất bộ mã `401` (`AUTHENTICATION_REQUIRED`, `INVALID_TOKEN`, `TOKEN_EXPIRED`, `TOKEN_REVOKED`), thống nhất `429 -> RATE_LIMIT_EXCEEDED`, và chuẩn hóa danh sách `error.details[]` tiếng Việt tự nhiên cho cả ba miền.
- **Đối với Team AI, Team Integration và Team Notification:**
  - `core-service` khai báo Docker network aliases `identity-service`, `classroom-service`, `work-service` trong cả `docker-compose.yml` và `docker-compose.staging.yml`.
  - `config/urls_internal.py` phục vụ đúng các đường dẫn nội bộ ở root (`/.well-known/jwks.json`, `/users/me`, `/api/v1/internal/*`), đồng thời Nginx tiếp tục chặn mọi đường dẫn `/internal` từ bên ngoài bằng `404`.
  - Outbox Kafka tiếp tục phát đúng 2 topic đối ngoại `utask.identity.events` (giữ nguyên `"producer": "identity-service"`) và `utask.work.events` (giữ nguyên `"producer": "work-service"`).

## Hệ quả

- **Tích cực:** Giảm mạnh tài nguyên RAM/CPU và số container (10 → 3); bỏ hoàn toàn lỗi lệch dữ liệu/độ trễ đồng bộ giữa Identity, Classroom và Work; đơn giản hóa biến môi trường (bỏ các khóa caller nội bộ giữa ba miền lõi); rút gọn vòng lặp kiểm thử và build CI xuống một image lõi.
- **Ràng buộc cần lưu ý:**
  - `core_db` là cơ sở dữ liệu hợp nhất mới; không có kịch bản di chuyển dữ liệu tự động từ ba cơ sở dữ liệu cũ `identity_db`/`classroom_db`/`work_db` (phù hợp với quyết định chấp nhận khởi tạo DB mới).
  - Các ranh giới kiến trúc trong `apps/core-service` là ranh giới cấp mô-đun Python được kiểm bằng test (`test_architecture_boundaries.py`), không còn cách ly vật lý ở mức database giữa Identity, Classroom và Work; mọi tính năng mới phải đi qua `interface.py` thay vì truy vấn chéo model trực tiếp.
  - Ranh giới vật lý (database riêng, REST nội bộ, Kafka outbox/consumer) với `ai-service`, `integration-service` và `notification-service` được bảo toàn nguyên vẹn.
  - Môi trường staging VPS thực tế vẫn ở trạng thái **Chưa xác minh** cho tới khi chạy release workflow và smoke thực tế trên server.
