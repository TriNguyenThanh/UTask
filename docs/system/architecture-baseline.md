# UTask – Architecture & Technology Baseline

**Phiên bản:** 1.0  
**Trạng thái:** Architecture Baseline  
**Phạm vi:** Kiến trúc hệ thống, công nghệ, tổ chức mã nguồn, dữ liệu, giao tiếp service, AI, GitHub Integration, CI/CD, testing và vận hành.

---

## 1. Mục đích tài liệu

Tài liệu này xác định nền tảng kỹ thuật chung cho UTask nhằm bảo đảm các thành viên phát triển cùng một kiến trúc, cùng quy ước và cùng định hướng mở rộng.

UTask là nền tảng hỗ trợ quản lý dự án công nghệ thông tin trong môi trường học tập, kết hợp:

- Quản lý Project, Backlog, Sprint, Task và Kanban theo Scrum/Agile.
- Quản lý thành viên và theo dõi workload.
- Collaboration qua comment, activity history và notification.
- Quản lý lớp học, sinh viên, nhóm, điểm danh và điểm số.
- Tích hợp GitHub để thu thập repository, commit, branch, issue và pull request.
- AI hỗ trợ sinh task, phân rã task, đề xuất priority, phân tích workload, tiến độ và nguy cơ deadline.
- Dashboard phục vụ sinh viên, trưởng nhóm và giảng viên.

`Task & Workflow Management` là core domain của UTask. Kiến trúc phải ưu tiên tính nhất quán của Project, Member, Sprint, Backlog, Task, Comment và Workflow trước khi tối ưu việc tách nhỏ service.

---

## 2. Nguyên tắc kiến trúc

UTask sử dụng các nguyên tắc sau:

1. **Coarse-grained Microservices**  
   Service được chia theo business capability/bounded context, không chia theo từng bảng hoặc từng entity.

2. **Event-driven Architecture**  
   Kafka được sử dụng cho các domain/integration event giữa những service độc lập.

3. **Synchronous API cho thao tác cần phản hồi ngay**  
   REST API được sử dụng cho command/query cần kết quả trực tiếp.

4. **Database ownership**  
   Mỗi service sở hữu dữ liệu của domain mình. Service khác không truy cập trực tiếp bảng của service đó.

5. **Strong consistency trong một service**  
   Các bảng liên quan chặt, cần join/transaction thường xuyên được giữ trong cùng service và cùng database.

6. **Eventual consistency giữa các service**  
   Notification, analytics, GitHub synchronization và AI analysis có thể cập nhật bất đồng bộ thông qua Kafka.

7. **Monorepo**  
   Frontend, backend services, AI và infrastructure được quản lý trong cùng một Git repository, nhưng mỗi service vẫn có dependency và Docker image độc lập.

8. **Không đưa hạ tầng phức tạp vào nếu chưa có nhu cầu thực tế**  
   Kubernetes, Debezium, ClickHouse, service mesh và các hệ thống tương tự chỉ được bổ sung khi workload chứng minh cần thiết.

---

## 3. Kiến trúc tổng thể

```text
                            ┌──────────────────────┐
                            │      React Web       │
                            │ Vite + TypeScript    │
                            └──────────┬───────────┘
                                       │
                                 HTTPS / REST
                                       │
                            ┌──────────▼───────────┐
                            │ Edge / API Routing   │
                            │ Nginx / Reverse Proxy│
                            └──────────┬───────────┘
                                       │
        ┌──────────────────┬───────────┼────────────┬─────────────────┐
        │                  │           │            │                 │
        ▼                  ▼           ▼            ▼                 ▼
┌───────────────┐ ┌───────────────┐ ┌───────────┐ ┌──────────────┐ ┌──────────────┐
│ Identity      │ │ Work          │ │ Classroom │ │ Integration  │ │ Notification │
│ Service       │ │ Service       │ │ Service   │ │ Service      │ │ Service      │
│ Django + DRF  │ │ Django + DRF  │ │ Django    │ │ Django + DRF │ │ Django       │
└───────┬───────┘ └───────┬───────┘ └─────┬─────┘ └──────┬───────┘ └──────┬───────┘
        │                 │               │               │                │
        └─────────────────┴───────────────┼───────────────┴────────────────┘
                                          │
                                    ┌─────▼─────┐
                                    │   Kafka   │
                                    └─────┬─────┘
                                          │
                           ┌──────────────┼──────────────┐
                           │              │              │
                           ▼              ▼              ▼
                    ┌────────────┐ ┌──────────────┐ ┌──────────────┐
                    │ AI Service │ │ Analytics    │ │ Realtime     │
                    │ FastAPI +  │ │ (later)      │ │ (later)      │
                    │ Google ADK │ │              │ │              │
                    └────────────┘ └──────────────┘ └──────────────┘
```

`Analytics` và `Realtime` được xác định boundary từ đầu nhưng chưa bắt buộc triển khai ở giai đoạn MVP.

---

## 4. Service boundaries

### 4.1 Identity Service

**Công nghệ:** Python + Django + Django REST Framework

Chịu trách nhiệm:

- User account.
- Đăng ký, đăng nhập, đăng xuất.
- Password reset.
- Profile.
- Global role.
- Token issuance/refresh.
- Google OAuth trong giai đoạn mở rộng.
- GitHub OAuth cho đăng nhập nếu cần.

Dữ liệu chính:

```text
users
user_profiles
roles
refresh_tokens / sessions metadata
oauth_accounts
```

Identity Service là nguồn dữ liệu chính của thông tin người dùng.

### 4.2 Work Service

**Công nghệ:** Python + Django + Django REST Framework

Đây là **core service** của UTask.

Chịu trách nhiệm:

```text
Project
Project Member
Product Backlog
Epic
User Story
Sprint
Task
Task Assignment
Label
Comment
Workflow
Activity History
Task Progress
Project Progress
```

Các entity này được giữ chung vì có quan hệ nghiệp vụ và transaction chặt.

```text
Project
 ├── ProjectMember
 ├── Sprint
 │    └── Task
 ├── Backlog
 │    ├── Epic
 │    ├── UserStory
 │    └── Task
 └── Task
      ├── Assignee
      ├── Comment
      ├── Label
      └── Activity
```

Không tạo riêng `Task Service`, `Sprint Service`, `Comment Service` hoặc `Project Service` trong giai đoạn đầu.

### 4.3 Classroom Service

**Công nghệ:** Python + Django + Django REST Framework

Chịu trách nhiệm:

```text
Course / Subject
Class
Teacher
Student
Group
Attendance
Grade
Group - Project association
```

Classroom được tách khỏi Work vì vòng đời lớp học, sinh viên, điểm danh và điểm số khác với vòng đời Project/Sprint/Task.

### 4.4 Integration Service

**Công nghệ:** Python + Django + Django REST Framework

Giai đoạn đầu tập trung vào GitHub.

Chịu trách nhiệm:

```text
GitHub App installation
Repository connection
Repository metadata
Commit
Branch
Issue
Pull Request
Webhook
GitHub contribution
Task ↔ GitHub Issue/PR mapping
```

GitHub nên được tích hợp bằng `GitHub App + Webhooks`, không sử dụng Personal Access Token làm kiến trúc chính.

Luồng webhook:

```text
GitHub
   │
   │ Webhook
   ▼
Integration Service
   │
   ├── verify signature
   ├── kiểm tra idempotency
   ├── normalize event
   ├── lưu dữ liệu cần thiết
   └── publish Kafka event
```

Ví dụ event:

```text
github.commit.received
github.pull_request.opened
github.pull_request.merged
github.issue.updated
```

### 4.5 Notification Service

**Công nghệ:** Python + Django

Subscribe các event liên quan:

```text
task.assigned
task.deadline.approaching
task.comment.created
task.status.changed
github.pull_request.merged
ai.project.risk.detected
```

Các channel dự kiến:

```text
In-app notification
Email
Web Push – giai đoạn sau
Mobile Push – nếu có mobile app
```

Notification không được nhúng trực tiếp vào Work Service.

### 4.6 AI Service

**Công nghệ:** Python + FastAPI + Google ADK

Chịu trách nhiệm:

```text
AI Task Generation
AI Task Decomposition
AI Priority Suggestion
AI Task Description
Workload Analysis
Project/Sprint Progress Analysis
Deadline Risk Detection
Task Reallocation Suggestion
Reasoning / Explanation
```

Cấu trúc logic:

```text
AI Orchestrator
├── Task Generation
├── Task Decomposition
├── Priority Analysis
├── Workload Analysis
└── Project Risk Analysis
```

Không cho AI truy cập trực tiếp database của Work Service.

```text
AI Service
    │
    ├── gọi internal API để lấy Project/Task context
    ├── chạy Google ADK agent/tools
    └── trả suggestion / publish event
```

Mọi hành động làm thay đổi Project/Task phải đi qua Work Service.

Nguyên tắc ban đầu:

```text
AI đề xuất
    ↓
User xem / xác nhận
    ↓
Work Service thực hiện thay đổi
```

### 4.7 Analytics Service – giai đoạn sau

Không cần triển khai đầy đủ ở MVP.

Nguồn dữ liệu chủ yếu từ Kafka:

```text
task.created
task.assigned
task.status.changed
task.completed
sprint.started
sprint.completed
github.commit.received
github.pull_request.merged
```

Phục vụ workload analytics, sprint velocity, contribution analytics, deadline analytics, member activity, project health và teacher dashboard.

PostgreSQL có thể được sử dụng ban đầu. ClickHouse hoặc data warehouse chỉ được bổ sung khi volume phân tích đủ lớn.

### 4.8 Realtime Service – giai đoạn sau

Không cần tách service riêng nếu UTask chỉ cần notification, refresh Kanban và task update cơ bản.

Có thể bắt đầu bằng SSE hoặc WebSocket trong service hiện tại. Service realtime riêng chỉ cần khi xuất hiện workload như live collaboration, presence, live cursor hoặc rich-text collaborative editing.

---

## 5. Backend stack

### 5.1 Ngôn ngữ

```text
Python
```

Lý do:

- Django phù hợp với hệ thống CRUD/domain-heavy.
- Django ORM hỗ trợ tốt PostgreSQL và transaction.
- Django REST Framework ổn định cho REST API.
- Cùng ngôn ngữ với AI/Google ADK.
- Giảm chi phí duy trì nhiều ngôn ngữ ở backend.

### 5.2 Framework

Business services:

```text
Django
Django REST Framework
```

AI:

```text
FastAPI
Google ADK
```

API documentation:

```text
OpenAPI
drf-spectacular
```

### 5.3 Python dependency management

Mỗi Python service có:

```text
pyproject.toml
uv.lock
```

Sử dụng `uv` để quản lý dependency và virtual environment. Mỗi microservice được phép có dependency riêng và build Docker image độc lập.

---

## 6. Frontend stack

```text
React
Vite
TypeScript
React Router
TanStack Query
Zustand
Tailwind CSS
shadcn/ui
```

Phân chia state:

```text
Server State → TanStack Query
UI / Client State → Zustand
```

Kanban drag-and-drop ưu tiên `@atlaskit/pragmatic-drag-and-drop` hoặc thư viện tương đương sau khi benchmark UI.

Frontend tổ chức theo feature:

```text
src/
├── app/
├── features/
│   ├── auth/
│   ├── project/
│   ├── backlog/
│   ├── sprint/
│   ├── task/
│   ├── kanban/
│   ├── classroom/
│   ├── github/
│   ├── ai/
│   └── notification/
├── components/
├── hooks/
├── lib/
├── stores/
└── types/
```

---

## 7. Authentication và Authorization

### 7.1 Authentication

Không sử dụng Keycloak ở giai đoạn hiện tại.

Identity Service sử dụng:

```text
Django Authentication
+
Django REST Framework
+
JWT Access Token
+
Refresh Token
```

JWT phù hợp hơn Django Session khi UTask có nhiều backend service độc lập.

```text
User
  │
  ▼
Identity Service
  │
  ├── kiểm tra credentials
  ├── issue access token
  └── issue refresh token
```

Các service khác xác thực token nhưng không truy cập database Identity.

OAuth mở rộng:

```text
Google OAuth
GitHub OAuth
```

Có thể sử dụng `django-allauth` thay vì tự viết toàn bộ OAuth flow.

### 7.2 Authorization

UTask kết hợp:

```text
Global RBAC
+
Resource / Project membership permission
```

Global roles:

```text
System Admin
Teacher
User
```

Project roles:

```text
Leader / Project Owner
Member
```

Một user có thể có quyền khác nhau ở các project khác nhau. Permission phải được kiểm tra ở backend, không dựa vào frontend.

---

## 8. Database

### 8.1 Database engine

```text
PostgreSQL
```

### 8.2 Database ownership

Giai đoạn đầu có thể chạy trên một PostgreSQL Server/Cluster:

```text
PostgreSQL
│
├── identity_db
├── work_db
├── classroom_db
├── integration_db
└── notification_db
```

Mỗi service:

- Có database riêng.
- Có database user/credential riêng.
- Không đọc bảng của service khác.

Không cần nhiều máy PostgreSQL vật lý ngay từ đầu.

### 8.3 Quan hệ xuyên service

Không tạo foreign key xuyên database/service.

Ví dụ:

```text
identity_db.users
id = user_123
```

Work Service lưu:

```text
project_members
----------------
project_id
user_id = user_123
role
```

`user_id` là logical reference.

Nếu Work cần tên/avatar user thường xuyên, có thể giữ local projection:

```text
user_projection
---------------
user_id
display_name
avatar_url
```

và cập nhật projection bằng event.

---

## 9. Kafka và Event-driven Architecture

### 9.1 Vai trò Kafka

Kafka được sử dụng cho cross-service domain events.

Ví dụ:

```text
user.created
project.created
member.joined
sprint.started
task.created
task.assigned
task.status.changed
task.completed
comment.created
github.commit.received
github.pull_request.merged
ai.analysis.completed
ai.project.risk.detected
```

Không sử dụng Kafka để thay thế REST API cho mọi request.

```text
Command / Query cần response ngay → REST API
Event thông báo sự kiện đã xảy ra → Kafka
```

### 9.2 Kafka client

Python services ưu tiên client ổn định như:

```text
confluent-kafka
```

Client cụ thể có thể được thay đổi mà không ảnh hưởng event contract.

---

## 10. Transactional Outbox

### 10.1 Vấn đề

Ví dụ Work Service cập nhật task thành `DONE`, sau đó publish `task.completed`. Nếu database update thành công nhưng Kafka lỗi, các service khác sẽ không nhận được event.

### 10.2 Outbox Pattern

Work Service thực hiện:

```text
BEGIN TRANSACTION

UPDATE tasks ...

INSERT INTO outbox_events ...

COMMIT
```

Task và event được lưu trong cùng transaction.

Cấu trúc ví dụ:

```text
outbox_events
-------------
id
aggregate_type
aggregate_id
event_type
event_version
payload
created_at
published_at
```

Worker sau đó:

```text
outbox_events
     ↓
publisher worker
     ↓
Kafka
```

### 10.3 Giai đoạn đầu

Sử dụng:

```text
Django transaction.atomic()
+
Outbox table
+
Celery publisher worker
```

### 10.4 Giai đoạn mở rộng

Khi event throughput và reliability requirement tăng:

```text
PostgreSQL
    ↓
Debezium CDC
    ↓
Kafka
```

Debezium chưa phải dependency bắt buộc của MVP.

---

## 11. Celery và Redis

Celery và Kafka có trách nhiệm khác nhau.

### Celery + Redis

Dùng cho background jobs nội bộ:

```text
deadline scan
email sending
retry
outbox publishing
periodic task
data cleanup
scheduled synchronization
```

### Kafka

Dùng cho event giữa service:

```text
Work → Notification
Work → Analytics
GitHub → Work
Work → AI
AI → Notification
```

Stack:

```text
Celery + Redis
```

---

## 12. Cloudflare R2

Object storage production:

```text
Cloudflare R2
```

UTask sử dụng R2 cho:

```text
Avatar
Task attachment
Project attachment
Classroom files
AI input files nếu được hỗ trợ
Export files
```

Backend tích hợp thông qua S3-compatible API:

```text
django-storages
+
boto3
+
Cloudflare R2 endpoint
```

Local development dùng filesystem local. MinIO chỉ cần khi muốn test hành vi tương thích S3 ở local.

---

## 13. API Routing

Không cần xây application-level Gateway phức tạp ngay từ đầu.

Sử dụng reverse proxy:

```text
/api/auth/*          → Identity Service
/api/work/*          → Work Service
/api/classroom/*     → Classroom Service
/api/integrations/*  → Integration Service
/api/notifications/* → Notification Service
/api/ai/*            → AI Service
```

Local dùng `Nginx + Docker Compose`. Production có thể đặt Cloudflare/load balancer phía trước.

---

## 14. API Contract

REST API:

```text
JSON
HTTPS
OpenAPI
```

Backend Django sử dụng:

```text
DRF
drf-spectacular
```

Nguyên tắc URL:

```text
/api/v1/...
```

Ví dụ:

```text
POST   /api/v1/auth/login
POST   /api/v1/auth/refresh
GET    /api/v1/projects
POST   /api/v1/projects
GET    /api/v1/projects/{id}/tasks
POST   /api/v1/projects/{id}/tasks
PATCH  /api/v1/tasks/{id}
POST   /api/v1/projects/{id}/sprints
POST   /api/v1/integrations/github/installations
POST   /api/v1/ai/generate-tasks
POST   /api/v1/ai/decompose-task
```

Không thay đổi API breaking mà không version.

---

## 15. Event Contract

Event không được publish dưới dạng JSON tùy ý.

Envelope chuẩn:

```json
{
  "event_id": "uuid",
  "event_type": "task.assigned",
  "event_version": 1,
  "aggregate_id": "task_uuid",
  "occurred_at": "ISO-8601",
  "trace_id": "uuid",
  "payload": {}
}
```

Event schema được quản lý trong:

```text
contracts/events/
```

Giai đoạn đầu dùng JSON Schema. Khi hệ thống lớn hơn có thể bổ sung AsyncAPI, Schema Registry, Avro/Protobuf nếu có nhu cầu rõ ràng.

---

## 16. Monorepo

UTask được quản lý trong một Git repository.

```text
UTask/
│
├── apps/
│   ├── web/
│   ├── identity-service/
│   ├── work-service/
│   ├── classroom-service/
│   ├── integration-service/
│   ├── notification-service/
│   └── ai-service/
│
├── contracts/
│   ├── api/
│   └── events/
│
├── infra/
│   ├── nginx/
│   ├── kafka/
│   ├── postgres/
│   ├── redis/
│   └── docker/
│
├── docs/
│   ├── architecture/
│   ├── adr/
│   └── api/
│
├── .github/
│   └── workflows/
│
├── docker-compose.yml
└── README.md
```

Frontend dùng `pnpm`. Turborepo không phải dependency bắt buộc.

Mỗi Python service dùng:

```text
pyproject.toml
uv.lock
```

và quản lý bằng `uv`.

---

## 17. Cấu trúc Django service

Ví dụ `work-service`:

```text
apps/work-service/
│
├── manage.py
├── pyproject.toml
├── uv.lock
├── Dockerfile
│
├── config/
│   ├── settings/
│   ├── urls.py
│   ├── celery.py
│   └── wsgi.py / asgi.py
│
├── apps/
│   ├── projects/
│   ├── memberships/
│   ├── backlogs/
│   ├── sprints/
│   ├── tasks/
│   ├── comments/
│   └── workflows/
│
├── infrastructure/
│   ├── kafka/
│   ├── outbox/
│   └── storage/
│
└── tests/
```

Mỗi Django app theo feature/domain, không tổ chức toàn bộ service theo kiểu `controllers/`, `services/`, `models/` ở root.

---

## 18. Cấu trúc AI Service

```text
apps/ai-service/
│
├── pyproject.toml
├── uv.lock
├── Dockerfile
│
├── app/
│   ├── main.py
│   ├── agents/
│   │   ├── task_generator/
│   │   ├── task_decomposer/
│   │   ├── priority_analyzer/
│   │   ├── workload_analyzer/
│   │   └── project_risk_analyzer/
│   ├── tools/
│   ├── prompts/
│   ├── schemas/
│   ├── services/
│   └── core/
│
├── evaluations/
└── tests/
```

Prompt không được hard-code rải rác trong business code.

---

## 19. Observability

### Giai đoạn đầu

Bắt buộc:

```text
Structured JSON logs
Request ID
Trace ID propagation
Error logging
Health check endpoint
```

Ví dụ:

```json
{
  "timestamp": "...",
  "level": "ERROR",
  "service": "work-service",
  "request_id": "...",
  "trace_id": "...",
  "message": "..."
}
```

### Giai đoạn nhiều service

Bổ sung OpenTelemetry để thu thập trace, metrics và liên kết logs theo `trace_id`.

Không bắt buộc dựng toàn bộ Grafana/Tempo/Prometheus trong MVP.

---

## 20. Git workflow

Branch chính:

```text
main
```

Không sử dụng `develop` ở giai đoạn hiện tại.

Branch naming:

```text
feat/UT-123-create-task
fix/UT-135-github-webhook
refactor/UT-140-task-service
test/UT-145-project-api
docs/UT-150-api-contract
chore/UT-160-docker
ci/UT-170-workflow
```

Workflow:

```text
Issue
  ↓
Short-lived branch
  ↓
Commit
  ↓
Pull Request
  ↓
CI
  ↓
Code Review
  ↓
Squash Merge
  ↓
main
```

`main` phải luôn build được, test pass và deploy được.

---

## 21. Commit convention

Sử dụng Conventional Commits:

```text
feat:
fix:
refactor:
test:
docs:
chore:
ci:
perf:
```

Ví dụ:

```text
feat(task): add task assignment
feat(ai): add task decomposition agent
fix(github): verify webhook signature
refactor(project): extract permission policy
test(task): add task API tests
ci(work): add work-service pipeline
```

---

## 22. Pull Request rules

Bảo vệ `main`:

- Không direct push.
- Không force push.
- Bắt buộc Pull Request.
- Bắt buộc CI pass.
- Tối thiểu 1 approval.
- Squash merge.
- PR tập trung vào một phạm vi thay đổi chính.

Có thể bổ sung `CODEOWNERS` khi trách nhiệm module rõ ràng.

---

## 23. CI/CD

Sử dụng GitHub Actions.

Monorepo pipeline sử dụng path filtering để chỉ build/test service bị ảnh hưởng.

Python service:

```text
uv sync
ruff check
ruff format --check
pytest
build Docker image
```

Frontend:

```text
pnpm install
lint
typecheck
test
build
```

AI:

```text
uv sync
ruff
pytest
AI evaluation
```

Main branch:

```text
CI
→ Build image
→ Push registry
→ Deploy staging
```

Production deployment chỉ thực hiện từ release/tag hoặc workflow được kiểm soát.

---

## 24. Testing strategy

### Backend

```text
pytest
pytest-django
```

Các lớp test:

```text
Unit Test
Integration Test
API Test
Contract Test
```

Ưu tiên cao:

```text
Authentication
Authorization
Project membership
Task lifecycle
Sprint lifecycle
GitHub webhook validation
Webhook idempotency
Outbox publishing
Kafka consumer idempotency
```

### Frontend

```text
Vitest
React Testing Library
Playwright
```

E2E ưu tiên:

```text
Login
Create Project
Invite Member
Create Task
Assign Task
Move Task trên Kanban
Connect GitHub
AI Generate Tasks
```

### AI

Cần:

```text
Golden evaluation dataset
Structured output validation
Task generation quality
Task decomposition quality
Priority reasoning
Tool-call correctness
Regression evaluation
```

---

## 25. Local development

Sử dụng Docker Compose cho infrastructure và service orchestration.

```text
docker compose up
```

Thành phần:

```text
nginx
postgres
redis
kafka
identity-service
work-service
classroom-service
integration-service
notification-service
ai-service
```

Frontend có thể chạy ngoài Docker bằng `pnpm dev` để hot reload nhanh hơn.

---

## 26. Production deployment

Mỗi service phải có Dockerfile riêng.

Không yêu cầu Kubernetes ngay.

Yêu cầu nền tảng:

```text
independent Docker images
environment-based configuration
health checks
readiness checks khi platform hỗ trợ
stateless application containers
external PostgreSQL
external Redis
external Kafka
Cloudflare R2
```

Kubernetes chỉ được đưa vào khi có nhu cầu nhiều replicas, autoscaling, high availability, rolling deployment phức tạp hoặc số lượng production service tăng đáng kể.

---

## 27. Security baseline

Bắt buộc:

- HTTPS.
- Không commit `.env`.
- Secrets lưu bằng platform secrets/GitHub Secrets.
- Password dùng Django password hashing.
- Rate-limit login và endpoint nhạy cảm.
- Validate GitHub webhook signature.
- Kiểm tra permission tại backend.
- Validate upload type/size.
- File private không public trực tiếp nếu không cần.
- Dùng signed/presigned URL cho R2 khi phù hợp.
- Kafka consumer phải idempotent.
- Log không chứa password, access token hoặc secret.
- Dependency được cập nhật và kiểm tra security định kỳ.

---

## 28. Technology matrix

| Thành phần | Công nghệ |
|---|---|
| Frontend | React + Vite + TypeScript |
| Routing | React Router |
| Server State | TanStack Query |
| Client State | Zustand |
| UI | Tailwind CSS + shadcn/ui |
| Backend | Python + Django + DRF |
| API Documentation | OpenAPI + drf-spectacular |
| AI | Python + FastAPI + Google ADK |
| Database | PostgreSQL |
| Event Backbone | Apache Kafka |
| Kafka Python Client | confluent-kafka |
| Background Jobs | Celery |
| Celery Broker/Cache | Redis |
| Object Storage | Cloudflare R2 |
| Production Storage API | S3-compatible API |
| Auth | Django Auth + JWT Access/Refresh |
| OAuth | Google/GitHub qua Django integration |
| Python Package Manager | uv |
| Frontend Package Manager | pnpm |
| Local Environment | Docker Compose |
| Reverse Proxy | Nginx |
| CI/CD | GitHub Actions |
| Python Lint/Format | Ruff |
| Backend Test | Pytest |
| Frontend Test | Vitest + React Testing Library |
| E2E | Playwright |
| Observability ban đầu | Structured logs + request/trace ID |
| Observability mở rộng | OpenTelemetry |

---

## 29. Công nghệ chưa đưa vào baseline

Không đưa vào giai đoạn hiện tại nếu chưa có requirement thực tế:

```text
Kubernetes
Debezium
ClickHouse
Elasticsearch / OpenSearch
Service Mesh
GraphQL
Event Sourcing
CQRS toàn hệ thống
Keycloak
API Gateway application phức tạp
Database server riêng cho từng service
Realtime server riêng
```

Các công nghệ này chỉ được bổ sung khi có dữ liệu vận hành hoặc yêu cầu sản phẩm chứng minh cần thiết.

---

## 30. Thứ tự triển khai foundation

### Phase 1 – Repository & Infrastructure

```text
Monorepo
Docker Compose
PostgreSQL
Redis
Kafka
Nginx
GitHub Actions
Coding conventions
```

### Phase 2 – Core

```text
Identity Service
Work Service
Frontend
Authentication
Project
Member
Task
Kanban
Comment
Basic Dashboard
```

### Phase 3 – Differentiation

```text
AI Service
AI Generate Tasks
GitHub Integration
GitHub Repository Connection
Notification
Activity History
```

### Phase 4 – Advanced

```text
AI Task Decomposition
AI Priority Suggestion
GitHub PR linking
GitHub task synchronization
Workload Analysis
Project Risk Analysis
Advanced Dashboard
Analytics Service
Realtime nếu có requirement
```

---

## 31. Trách nhiệm của Tech Lead

Tech Lead chịu trách nhiệm duy trì các chuẩn sau:

1. Xác định và bảo vệ service boundary.
2. Không cho service truy cập trực tiếp database của service khác.
3. Duy trì API contract và event contract.
4. Review thay đổi kiến trúc trước implementation.
5. Duy trì coding convention.
6. Duy trì Git/PR rules.
7. Duy trì CI/CD baseline.
8. Đảm bảo critical business rules có automated tests.
9. Kiểm soát dependency và security.
10. Review database migration.
11. Review Kafka event naming/versioning.
12. Giữ architecture documentation và ADR cập nhật.
13. Không đưa công nghệ mới vào chỉ vì xu hướng nếu chưa có use case rõ ràng.

Các quyết định kiến trúc quan trọng được lưu thành ADR trong:

```text
docs/adr/
```

Ví dụ:

```text
ADR-001-use-django.md
ADR-002-use-coarse-grained-microservices.md
ADR-003-use-kafka.md
ADR-004-use-postgresql-database-ownership.md
ADR-005-use-cloudflare-r2.md
ADR-006-use-django-auth-jwt.md
```

---

## 32. Tài liệu tham khảo kỹ thuật

### UTask

- Tài liệu yêu cầu dự án: **UTask - Nền tảng quản lý dự án công nghệ thông tin**.

### Plane

- Repository: https://github.com/makeplane/plane
- Plane sử dụng monorepo, Django backend, PostgreSQL, Redis/Valkey, RabbitMQ/Celery-style worker architecture và tách realtime workload thành service riêng.

### Django / DRF

- Django: https://docs.djangoproject.com/
- Django REST Framework: https://www.django-rest-framework.org/
- DRF Authentication: https://www.django-rest-framework.org/api-guide/authentication/

### Apache Kafka

- https://kafka.apache.org/

### Cloudflare R2

- R2 API: https://developers.cloudflare.com/r2/api/
- S3 compatibility: https://developers.cloudflare.com/r2/api/s3/api/

### Debezium Outbox

- https://debezium.io/documentation/reference/transformations/outbox-event-router.html

### OpenTelemetry

- https://opentelemetry.io/docs/

### Google ADK

- https://google.github.io/adk-docs/

### GitHub Apps & Webhooks

- https://docs.github.com/en/apps
- https://docs.github.com/en/webhooks

---

## 33. Architecture baseline summary

```text
Architecture
→ Coarse-grained Microservices
→ Event-driven Architecture
→ Monorepo

Frontend
→ React + Vite + TypeScript

Backend
→ Python + Django + DRF

AI
→ Python + FastAPI + Google ADK

Core Domain
→ Work Service
→ Project + Member + Backlog + Sprint + Task + Comment + Workflow

Data
→ PostgreSQL
→ database ownership per service

Async
→ Kafka cho cross-service events
→ Celery + Redis cho background jobs
→ Transactional Outbox bảo vệ event reliability

Authentication
→ Django Auth + JWT
→ OAuth Google/GitHub khi cần

Integration
→ GitHub App + Webhooks

Storage
→ Cloudflare R2

Repository
→ Monorepo
→ pnpm cho frontend
→ uv cho Python

Infrastructure
→ Docker Compose
→ Nginx
→ GitHub Actions

Observability
→ Structured logging + request/trace ID
→ OpenTelemetry khi số lượng service tăng

Production evolution
→ Kubernetes / Debezium / ClickHouse chỉ khi workload yêu cầu
```

---
