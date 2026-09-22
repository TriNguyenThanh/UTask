# UTask

> Nền tảng quản lý dự án Agile có AI hỗ trợ cho đội nhóm công nghệ trong môi trường đào tạo.

<p align="center">
  <a href="https://github.com/TriNguyenThanh/UTask/actions/workflows/ci.yml"><img src="https://github.com/TriNguyenThanh/UTask/actions/workflows/ci.yml/badge.svg?branch=main" alt="CI" /></a>
  <a href="https://react.dev/"><img src="https://img.shields.io/badge/React-Frontend-61DAFB?logo=react&logoColor=20232A" alt="React" /></a>
  <a href="https://www.typescriptlang.org/"><img src="https://img.shields.io/badge/TypeScript-Web-3178C6?logo=typescript&logoColor=white" alt="TypeScript" /></a>
  <a href="https://www.django-rest-framework.org/"><img src="https://img.shields.io/badge/Django-REST_Framework-092E20?logo=django&logoColor=white" alt="Django REST Framework" /></a>
  <a href="https://fastapi.tiangolo.com/"><img src="https://img.shields.io/badge/FastAPI-AI_API-009688?logo=fastapi&logoColor=white" alt="FastAPI" /></a>
  <a href="https://google.github.io/adk-docs/"><img src="https://img.shields.io/badge/Google-ADK-4285F4?logo=google&logoColor=white" alt="Google ADK" /></a>
  <a href="https://www.postgresql.org/"><img src="https://img.shields.io/badge/PostgreSQL-Data-4169E1?logo=postgresql&logoColor=white" alt="PostgreSQL" /></a>
  <a href="https://kafka.apache.org/"><img src="https://img.shields.io/badge/Apache-Kafka-231F20?logo=apachekafka&logoColor=white" alt="Apache Kafka" /></a>
  <a href="https://redis.io/"><img src="https://img.shields.io/badge/Redis-Background_Jobs-DC382D?logo=redis&logoColor=white" alt="Redis" /></a>
  <a href="https://docs.docker.com/compose/"><img src="https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white" alt="Docker Compose" /></a>
  <a href="https://docs.github.com/actions"><img src="https://img.shields.io/badge/GitHub-Actions-2088FF?logo=githubactions&logoColor=white" alt="GitHub Actions" /></a>
</p>

<p align="center"><em>Technology baseline; implementation status is summarized below.</em></p>

**UTask giúp đội nhóm biến tín hiệu vận hành thành quyết định rõ ràng hơn:** công việc nào cần ưu tiên, ai đang quá tải, Sprint nào có nguy cơ và hoạt động GitHub có đang phản ánh tiến độ thực tế hay không.

**Trạng thái:** AI-first foundation · Chưa sẵn sàng cho production

[Bắt đầu nhanh](#bắt-đầu-nhanh) · [Trạng thái sản phẩm](#trạng-thái-sản-phẩm) · [Tài liệu kỹ thuật](#tài-liệu) · [Quy tắc phát triển](AGENTS.md)

## Vấn đề UTask giải quyết

Nhóm dự án học thuật thường phân tán thông tin giữa bảng việc, trao đổi nhóm và GitHub. Điều này khiến người điều phối khó nhìn thấy tải công việc thực, tiến độ Sprint và rủi ro trễ hạn trước khi chúng trở thành vấn đề.

UTask được định hướng để kết nối ba lớp thông tin đó:

| Đối tượng | Giá trị mong đợi |
| --- | --- |
| **Sinh viên** | Biết việc cần làm, mức ưu tiên và bối cảnh của Sprint. |
| **Trưởng nhóm** | Nhận diện quá tải, phân bổ chưa cân bằng và rủi ro delivery sớm hơn. |
| **Giảng viên** | Có nền tảng cho việc theo dõi nhóm, tiến độ và đóng góp dựa trên dữ liệu. |

AI đóng vai trò **đề xuất có giải thích**, không thay thế quyết định của người dùng và không tự thay đổi dữ liệu nghiệp vụ.

## Trạng thái sản phẩm

Repository đang ở giai đoạn xây dựng nền tảng theo chiến lược AI-first: ưu tiên luồng dữ liệu thật cho AI, nhưng chưa tuyên bố một sản phẩm hoàn chỉnh.

| Thành phần | Trạng thái | Giá trị hiện có |
| --- | --- | --- |
| [AI Service](apps/ai-service/README.md) | PARTIAL | Structured suggestion, phân tích workload, priority và project risk trên fixture hoặc API context. |
| [Work Service](apps/work-service/README.md) | PARTIAL | Project, member, sprint, task, assignment và API context cho AI. |
| [Integration Service](apps/integration-service/README.md) | PARTIAL | Dữ liệu GitHub đã chuẩn hoá: repository, commit và pull request. |
| [Identity Service](apps/identity-service/README.md) | SKELETON | Service độc lập, health check và test setup. |
| [Classroom Service](apps/classroom-service/README.md) | SKELETON | Service độc lập, health check và test setup. |
| [Notification Service](apps/notification-service/README.md) | SKELETON | Service độc lập, health check và consumer boundary. |
| [Web Application](apps/web/README.md) | SKELETON | React application shell, feature layout và component test. |

`PARTIAL` chỉ xác nhận các khả năng được nêu trong bảng đã có implementation và test liên quan. Phạm vi, dữ liệu sở hữu, API/event và TODO của từng service được ghi trong README của service đó.

## Nền tảng công nghệ

Bảng trạng thái dưới đây phân biệt công nghệ theo baseline với phần đã có trong source, đã cấu hình cho local development, hoặc còn trong lộ trình.

| Lớp | Công nghệ theo baseline | Tình trạng trong repository |
| --- | --- | --- |
| Web | React, Vite, TypeScript, React Router, TanStack Query, Zustand, Tailwind CSS, shadcn/ui | React/Vite/TypeScript shell và build đã có. Router, state management và UI system chưa được tích hợp vào luồng sản phẩm; Tailwind/shadcn/ui chưa được thêm. |
| Business services | Python, Django, Django REST Framework, OpenAPI, drf-spectacular | Work và Integration có API/model/migration; Identity, Classroom và Notification đang là skeleton. |
| AI | Python, FastAPI, Pydantic, Google ADK | FastAPI, schema và các phân tích workload/priority/risk đã có. ADK model runtime và sinh task thật chưa cấu hình. |
| Dữ liệu | PostgreSQL, database ownership theo service | Docker Compose cấu hình PostgreSQL 16 với database riêng cho từng service và một tài khoản kết nối chung. Test độc lập mặc định dùng SQLite. |
| Event và background jobs | Apache Kafka, Celery, Redis | Kafka và Redis đã có trong Compose. Producer/consumer, transactional outbox và Celery job chưa triển khai. |
| GitHub và object storage | GitHub App, Webhooks, Cloudflare R2 qua S3 API | Integration Service lưu và cung cấp dữ liệu GitHub đã chuẩn hoá; GitHub App, webhook sync và R2 còn trong lộ trình. |
| Delivery và chất lượng | Docker Compose, Nginx, GitHub Actions, Ruff, Pytest, Vitest, React Testing Library, Playwright | CI theo đường dẫn, đánh giá AI, build/đẩy image và workflow staging đã cấu hình. Chạy GitHub thật cần Environment/secrets; Playwright E2E chưa được thêm. |

Technology matrix đầy đủ và các lựa chọn thuộc giai đoạn sau nằm trong [Architecture Baseline](docs/architecture/UTask_Architecture_Technology_Baseline.md#28-technology-matrix).

## Điều có thể kiểm chứng ngay

- AI nhận context qua tool/API contract, không đọc trực tiếp database của Work hoặc Integration Service.
- Kết quả AI có Pydantic schema và là suggestion-only; mutation phải đi qua service sở hữu dữ liệu.
- Bộ fixture/evaluation phát hiện workload quá tải, kiểm tra priority theo deadline và risk dựa trên task/GitHub context.
- Work và Integration Service có API, model, migration và test độc lập.

## Bắt đầu nhanh

### Chạy toàn bộ môi trường local

Yêu cầu: Docker Desktop có Docker Compose.

```powershell
Copy-Item .env.example .env
docker compose up --build
```

`.env` chỉ dùng cho máy cá nhân và không được commit. Các giá trị `change-me-*` trong `.env.example` chỉ là giá trị mẫu; thay chúng bằng giá trị riêng của môi trường trước khi dùng môi trường dùng chung.

Compose nạp biến chạy của từng service qua `env_file`. Tệp `.env` cung cấp giá trị theo môi trường; xem [cách tổ chức môi trường](infra/env/README.md) để thiết lập local và staging.

Nginx lắng nghe tại `http://localhost:8080`. Kiểm tra health endpoint:

```powershell
Invoke-RestMethod http://localhost:8080/api/work/healthz
Invoke-RestMethod http://localhost:8080/api/ai/healthz
```

Lần chạy đầu cần tải image infrastructure, gồm Kafka, nên có thể mất thời gian. Dừng môi trường bằng `docker compose down`.

### Phát triển một Python service

Yêu cầu: Python 3.11+ và [uv](https://docs.astral.sh/uv/).

```powershell
Set-Location apps/work-service
uv sync --all-groups
uv run pytest
uv run python manage.py runserver
```

### Phát triển web application

Yêu cầu: Node.js 22+ và pnpm; Corepack được hỗ trợ.

```powershell
Set-Location apps/web
corepack pnpm install --frozen-lockfile
corepack pnpm dev
```

## Cấu trúc repository

```text
apps/          web application và các service build độc lập
contracts/     API và Kafka event schema có version
datasets/      fixture và regression evaluation cho AI
infra/         asset Docker, Nginx, PostgreSQL, Redis và Kafka
docs/          tài liệu kiến trúc, API và ADR
scripts/       công cụ kiểm tra CI local trước khi đẩy mã
.github/       CI workflow
```

Mỗi service giữ dependency lockfile và Dockerfile riêng. Database được tách theo service; giao tiếp liên service dùng API hoặc event contract, không đọc chéo database.

## Quality gate

Chạy các kiểm tra trong application vừa thay đổi:

```powershell
# Python services
uv run ruff check .
uv run ruff format --check .
uv run pytest

# Web
corepack pnpm lint
corepack pnpm typecheck
corepack pnpm test
corepack pnpm build
```

Trước khi đẩy mã lên remote, chạy bộ kiểm tra CI local:

```powershell
python scripts/ci_local.py
```

Lệnh trên kiểm tra Compose, Nginx, script PostgreSQL, sáu service Python, Web và dựng Docker image. Nếu chỉ cần kiểm tra mã nguồn nhanh, bỏ qua bước dựng image:

```powershell
python scripts/ci_local.py --skip-images
```

GitHub Actions chạy các check tương đương theo đường dẫn thay đổi; bộ Pytest của AI bao gồm regression evaluation. Pull Request dựng image của service bị ảnh hưởng để kiểm tra Dockerfile. Khi CI trên `main` thành công, workflow phát hành dựng và đẩy sáu image lên GHCR đúng một lần, sau đó tự động triển khai staging theo [tài liệu CI/CD](docs/ci-cd.md). Có thể kiểm tra cấu hình bằng `docker compose config`; build image local dùng `docker compose build`.

### Cấu hình GitHub Environment `staging`

Tạo Environment tên `staging` trong phần cài đặt GitHub của repository. Workflow tự chạy sau CI thành công trên `main`; phê duyệt triển khai là tùy chọn do người quản trị Environment quyết định.

| Tên | Loại | Bắt buộc | Mục đích |
| --- | --- | --- | --- |
| `STAGING_WORKDIR` | Variable | Có | Thư mục chứa Compose trên máy staging, ví dụ `/opt/utask`. |
| `STAGING_URL` | Variable | Không | Đường dẫn hiển thị trong GitHub Deployment. |
| `STAGING_HOST` | Secret | Có | Tên máy hoặc địa chỉ máy staging. |
| `STAGING_USER` | Secret | Có | Tài khoản triển khai. |
| `STAGING_SSH_PRIVATE_KEY` | Secret | Có | Khóa riêng dùng để kết nối tới staging. |
| `STAGING_KNOWN_HOSTS` | Secret | Có | Khóa máy chủ đã xác minh, dùng để chống kết nối nhầm máy. |
| `STAGING_REGISTRY_USERNAME` | Secret | Có | Tài khoản có quyền đọc image từ GHCR. |
| `STAGING_REGISTRY_TOKEN` | Secret | Có | Token chỉ có quyền đọc image từ GHCR. |

`GITHUB_TOKEN`, địa chỉ registry, tiền tố image và thẻ `sha-<commit>` được workflow tạo hoặc cung cấp tự động, không cần khai báo. Tệp `.env` của staging nằm ngoài repository và phải có các biến trong [.env.example](.env.example); workflow không ghi đè tệp này.

Các giá trị runtime bắt buộc trong `.env` staging:

| Nhóm | Biến |
| --- | --- |
| PostgreSQL dùng chung | `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `POSTGRES_HOST`, `POSTGRES_PORT` |
| Identity | `IDENTITY_DB_NAME`, `IDENTITY_DJANGO_SECRET_KEY` |
| Work | `WORK_DB_NAME`, `WORK_DJANGO_SECRET_KEY` |
| Classroom | `CLASSROOM_DB_NAME`, `CLASSROOM_DJANGO_SECRET_KEY` |
| Integration | `INTEGRATION_DB_NAME`, `INTEGRATION_DJANGO_SECRET_KEY` |
| Notification | `NOTIFICATION_DB_NAME`, `NOTIFICATION_DJANGO_SECRET_KEY` |
| Django dùng chung | `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS` |
| Kafka | `KAFKA_CLUSTER_ID` |

`UTASK_HTTP_PORT` là tùy chọn và mặc định là `8080`. `UTASK_IMAGE_PREFIX` cùng `UTASK_IMAGE_TAG` được workflow đặt khi triển khai nên không bắt buộc trong `.env` staging.

## Lộ trình gần

1. Hoàn thiện Google ADK runtime, task generation và task decomposition có evaluation.
2. Kết nối GitHub App, webhook signature verification, synchronization và idempotency.
3. Hoàn thiện JWT, Classroom, Notification, outbox/Kafka consumer và luồng duyệt đề xuất AI trên web.

Analytics và realtime riêng là boundary giai đoạn sau, không phải ứng dụng MVP hiện tại.

## Tài liệu

- [Architecture & Technology Baseline](docs/architecture/UTask_Architecture_Technology_Baseline.md) — source of truth về kiến trúc và công nghệ.
- [AGENTS.md](AGENTS.md) — quy tắc bắt buộc khi thay đổi repository.
- [Contracts](contracts/) — API/event contract hiện có.
- [CI/CD](docs/ci-cd.md) — cấu hình registry và triển khai staging.
- [Environment files](infra/env/README.md) — cách phân tách biến theo service và môi trường.
- [Architecture decisions](docs/adr/) — ADR cho thay đổi hoặc làm rõ baseline.

## Đóng góp

Đọc [AGENTS.md](AGENTS.md) trước khi thay đổi service boundary. Giữ thay đổi tập trung, cập nhật test/contract/README tương ứng và không đánh dấu một khả năng là `IMPLEMENTED` khi nó chưa hoạt động.
