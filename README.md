# UTask

> Nền tảng quản lý project phần mềm cho nhóm học tập.

<p align="center">
  <a href="https://github.com/TriNguyenThanh/UTask/actions/workflows/ci.yml"><img src="https://github.com/TriNguyenThanh/UTask/actions/workflows/ci.yml/badge.svg?branch=main" alt="CI" /></a>
  <a href="https://react.dev/"><img src="https://img.shields.io/badge/React-Web-61DAFB?logo=react&logoColor=20232A" alt="React" /></a>
  <a href="https://www.typescriptlang.org/"><img src="https://img.shields.io/badge/TypeScript-Web-3178C6?logo=typescript&logoColor=white" alt="TypeScript" /></a>
  <a href="https://www.django-rest-framework.org/"><img src="https://img.shields.io/badge/Django-REST_Framework-092E20?logo=django&logoColor=white" alt="Django REST Framework" /></a>
  <a href="https://fastapi.tiangolo.com/"><img src="https://img.shields.io/badge/FastAPI-AI_API-009688?logo=fastapi&logoColor=white" alt="FastAPI" /></a>
  <a href="https://www.postgresql.org/"><img src="https://img.shields.io/badge/PostgreSQL-Data-4169E1?logo=postgresql&logoColor=white" alt="PostgreSQL" /></a>
  <a href="https://kafka.apache.org/"><img src="https://img.shields.io/badge/Apache-Kafka-231F20?logo=apachekafka&logoColor=white" alt="Apache Kafka" /></a>
  <a href="https://redis.io/"><img src="https://img.shields.io/badge/Redis-Cache-DC382D?logo=redis&logoColor=white" alt="Redis" /></a>
  <a href="https://docs.docker.com/compose/"><img src="https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white" alt="Docker Compose" /></a>
  <a href="https://docs.github.com/actions"><img src="https://img.shields.io/badge/GitHub-Actions-CI%2FCD-2088FF?logo=githubactions&logoColor=white" alt="GitHub Actions" /></a>
</p>

UTask hướng tới việc giúp sinh viên và giảng viên tổ chức project, nhóm, Sprint, task và theo dõi tiến độ. Kiến trúc dự kiến kết nối hoạt động GitHub và dùng phân tích AI để gợi ý ưu tiên, tải công việc hoặc rủi ro. AI chỉ đề xuất; người dùng quyết định và service sở hữu dữ liệu thực hiện thay đổi.

## Công nghệ

| Lớp | Công nghệ nổi bật |
| --- | --- |
| Web | React, TypeScript, Vite; React Router, TanStack Query và Zustand |
| Backend | Python, Django REST Framework, FastAPI |
| Dữ liệu và xử lý bất đồng bộ | PostgreSQL, Apache Kafka, Redis |
| Hạ tầng và triển khai | Docker Compose, Nginx, GitHub Actions, GitHub Container Registry (GHCR) |

Web shell và cấu hình hạ tầng hiện có trong repository. Các công nghệ backend được Compose/CI tham chiếu, nhưng mã nguồn backend chưa có trong checkout hiện tại.

## Cấu trúc project

```text
apps/
  web/                    ứng dụng React
  <service>/              vị trí các backend service
contracts/
  api/                    hợp đồng REST
  events/                 hợp đồng Kafka
datasets/                 fixture JSON cho project, task và workload
docs/
  system/                 kiến trúc và luồng hệ thống
  <service>/              tài liệu theo service
  infrastructure/         cấu hình local và CI/CD
infra/                    Docker, Nginx, PostgreSQL và biến môi trường
scripts/                  script kiểm tra CI local
.github/workflows/        CI và phát hành staging
docker-compose.yml        cấu hình stack
```

Các service dự kiến gồm Identity, Project (`work-service`), Classroom, Integration, Notification và AI. Ranh giới service và quyền sở hữu dữ liệu được mô tả trong [kiến trúc hệ thống](docs/system/architecture.md).

## Cấu hình và chạy

Cần Docker Compose. Tạo cấu hình local từ mẫu:

```powershell
Copy-Item .env.example .env
docker compose config --quiet
```

Không commit `.env`; thay các giá trị `change-me-*` trước khi dùng môi trường chung. Biến môi trường được ánh xạ qua `infra/env/`.

Có thể chạy riêng Web với Node.js 22+ và pnpm 10:

```powershell
Set-Location apps/web
corepack pnpm install --frozen-lockfile
corepack pnpm dev
```

Toàn bộ stack chưa chạy được trong checkout hiện tại vì các backend service chưa có mã nguồn và Dockerfile.

## Triển khai

GitHub Actions kiểm tra thay đổi trên Pull Request vào `main` và khi push lên `main`. Sau CI thành công, thay đổi backend hoặc cấu hình triển khai có thể kích hoạt workflow phát hành: build image, gắn thẻ theo commit và triển khai staging bằng Docker Compose qua SSH.

Staging cần GitHub Environment tên `staging`, thông tin SSH/GHCR trong secrets và tệp `.env` trên máy chủ. Cấu hình chi tiết nằm trong [hướng dẫn CI/CD](docs/infrastructure/ci-cd.md). Workflow đã được cấu hình trong repository; môi trường staging chưa được xác minh.
