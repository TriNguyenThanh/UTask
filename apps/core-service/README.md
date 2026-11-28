# UTask Core Service

`apps/core-service` là Django Modular Monolith (kiến trúc nguyên khối phân tách mô-đun) hợp nhất ba miền nghiệp vụ lõi của UTask gồm **Identity**, **Classroom** và **Work** trên một cơ sở dữ liệu PostgreSQL thống nhất (`core_db`).

## Tài liệu chuẩn

- Quyết định kiến trúc: [ADR-006 — Hợp nhất Identity, Classroom và Work thành Core Modular Monolith](../../docs/system/adr/006-consolidate-core-monolith.md)
- Kiến trúc tổng thể và ranh giới: [Kiến trúc UTask](../../docs/system/architecture.md) · [Quyền sở hữu dữ liệu](../../docs/system/data-ownership.md) · [Giao tiếp REST và Kafka](../../docs/system/communication.md)
- Tài liệu theo miền nghiệp vụ: [Identity](../../docs/identity-service/README.md) · [Classroom](../../docs/classroom-service/README.md) · [Work](../../docs/project-service/README.md)
- Vận hành và cấu hình: [Biến môi trường](../../docs/system/infrastructure/environment.md) · [Chạy local](../../docs/system/infrastructure/local-development.md) · [CI/CD](../../docs/system/infrastructure/ci-cd.md)

## Cấu trúc mã nguồn

- `config/`: cấu hình Django (`settings/{base,local,staging,test}.py`), routing công khai/nội bộ (`urls.py`, `urls_internal.py`, `urls_domains/`), Celery (`celery.py`) và OpenAPI (`api_documentation.py`).
- `common/`: tiện ích dùng chung thuần túy (0 Django model) — xác thực JWT (`authentication.py`), phân quyền (`permissions.py`), envelope phản hồi (`responses.py`, `renderers.py`), xử lý lỗi thống nhất (`errors.py`, `exception_handler.py`), middleware IP proxy tin cậy (`middleware.py`) và làm sạch nội dung (`content.py`).
- `infrastructure/`: adapter tích hợp dịch vụ bên ngoài (`storage.py` cho Cloudflare R2, `kafka.py`, `ai.py`, `integration.py`).
- `apps/`: 11 Django app phẳng xếp theo đồ thị phụ thuộc 4 tầng không vòng lặp:
  - Tầng 0: `messaging`, `accounts`, `authentication`
  - Tầng 1: `courses`, `projects`
  - Tầng 2: `groups`, `sprints`, `tasks`, `collaboration`, `integrations`
  - Tầng 3 (lá): `activities`

## Kiểm tra cục bộ nhanh

Chạy từ thư mục `apps/core-service` (cần PostgreSQL 16 test theo `config.settings.test`):

```bash
uv run ruff check .
uv run ruff format --check .
uv run python manage.py check --settings=config.settings.test
uv run python manage.py makemigrations --check --dry-run --settings=config.settings.test
uv run pytest -v
```
