# Hướng dẫn bàn giao & Phối hợp hợp đồng cho Team AI, Team Integration và Team Notification

> **Mục đích tài liệu:** Kênh bàn giao kỹ thuật chính thức từ **Team Core Backend (`apps/core-service`, hợp nhất Identity, Classroom và Work theo [ADR-006](adr/006-consolidate-core-monolith.md))** sang **Team AI (`apps/ai-service`)**, **Team Integration (`apps/integration-service`)** và **Team Notification (`apps/notification-service`)** nhằm khớp nối trọn vẹn **Đợt 5**, **Đợt 6** và **Đợt 7** theo [Kế hoạch triển khai Backend](backend-web-gap-implementation-plan.md).  
> **Cập nhật kiến trúc (ADR-006 — Không phá vỡ tích hợp cho 3 đội):** Ba dịch vụ lõi cũ đã hợp nhất vào `apps/core-service` trên `core_db`, nhưng **không yêu cầu sửa bất kỳ dòng mã hay biến môi trường nào** phía Team AI, Team Integration hay Team Notification: container `core-service` đăng ký đầy đủ Docker network aliases (`identity-service`, `classroom-service`, `work-service`), giữ nguyên toàn bộ internal routes (`/.well-known/jwks.json`, `/users/me`, `/api/v1/internal/*`), và outbox Kafka tiếp tục phát đúng `producer: "identity-service"` trên `utask.identity.events` cùng `producer: "work-service"` trên `utask.work.events`.  
> **Trạng thái tài liệu:** Phần phía **miền Work trong `apps/core-service` (Team Core Backend)** của Đợt 5 đã ở trạng thái `Đã triển khai (local)` và qua kiểm thử hợp đồng/kiến trúc trên PostgreSQL 16 (deploy staging `Chưa xác minh`). Các endpoint và event mới phía **`ai-service` (Team AI)** và **`integration-service` (Team Integration)** vẫn ở trạng thái `Chưa triển khai` (`Thiết kế mục tiêu`) cho tới khi từng đội xác nhận bằng code + contract + kiểm thử.  
> **Phân tách trách nhiệm:** Team Core Backend **không chỉnh sửa** mã nguồn thuộc `apps/ai-service/**`, `apps/integration-service/**`, `apps/notification-service/**` và `apps/web/**`. Tài liệu này chốt hợp đồng wire (REST nội bộ, Kafka event, mã lỗi, biến môi trường và điều kiện nghiệm thu) để hai phía phát triển song song và ghép nối an toàn.

---

## 1. Bảng phân tách quyền sở hữu theo đợt

| Hạng mục | Team Core Backend (`identity`, `classroom`, `work`) | Team AI (`ai-service`) | Team Integration (`integration-service`) | Team Notification (`notification-service`) |
| --- | --- | --- | --- | --- |
| **Đợt 5.1 — AI `bulk-apply-ai` (DG5)** | Triển khai `RemoteProposals` trong `work-service`, cập nhật cấu hình env Work, kiểm chứng wire + áp dụng nguyên tử `bulk-apply-ai` (`AI_BACKLOG`, `AI_DECOMPOSED`). | Gắn `local_id`, `ai_revision`, `context_version` ở hậu xử lý; mở `POST /api/ai/v1/internal/requests/{request_id}/verify-proposal`; thêm `AI_INBOUND_SERVICE_KEYS`; rà JWT staging (`B32`). | Không liên quan. | Không liên quan. |
| **Đợt 5.2 — Đồng bộ tài khoản GitHub (DG1 / ADR-004)** | Mở rộng `integration_consumer.py` phía `work-service` nhận `integration.github.account.changed` v1 → gọi `apply_account_fact()`. | Không liên quan. | Phát outbox `integration.github.account.changed` v1 khi link/đổi login/unlink/revoke webhook; xuất schema JSON. | Không liên quan. |
| **Đợt 5.3 — GitHub Activity 2 tầng (DG6 / ADR-005)** | Mở rộng `RemoteIntegration` + public `GET /projects/{id}/github/activity/` (cache Redis + gộp `linked_task_ids`); nhận `integration.github.reference.detected` v1 → giải mã `task_code` → `ingest_reference()`. | Không thay đổi (đã có `github_activity` context riêng). | Mở internal `GET /api/v1/internal/projects/{project_id}/github/activity` cho caller `work`; xử lý webhook `push`/`pull_request` → phát `integration.github.reference.detected` v1. | Không liên quan. |
| **Đợt 6 — Kích hoạt email (DG8 / `B3`)** | Đưa bypass kích hoạt về cờ `IDENTITY_REQUIRE_EMAIL_ACTIVATION` phía `identity-service`. | Không liên quan. | Không liên quan. | Xác minh consumer nhận `identity.activation.requested` & `identity.student.imported` + gửi mail SMTP thật trước khi bật cờ trên staging/production. |
| **Đợt 7.2 — Thông báo lớp P2** | Thiết kế & triển khai bảng `ClassAnnouncement` + outbox phía `classroom-service` (sau khi chốt spec P2). | Không liên quan. | Không liên quan. | Mở consumer nguồn Classroom theo [hướng dẫn Notification](../notification-service/implementation.md#thêm-service-hoặc-event-mới). |

---

## 2. Hướng dẫn cho Team AI (`apps/ai-service`) — Đợt 5.1 (`bulk-apply-ai`, DG5)

### 2.1. Hiện trạng đã xác minh trên mã nguồn hai bên
- **Phía `apps/core-service` — miền Work (`Đã triển khai (local)`):**
  - Đã hoàn thiện cả 2 endpoint áp dụng nguyên tử (`POST /projects/{project_id}/tasks/bulk-apply-ai/` với `source="AI_BACKLOG"` và `POST /tasks/{task_id}/subtasks/bulk-apply-ai/` với `source="AI_DECOMPOSED"`) và adapter HTTP thật `RemoteProposals` ([infrastructure/ai.py](../../apps/core-service/infrastructure/ai.py)), ánh xạ env `WORK_AI_BASE_URL` / `WORK_AI_SERVICE_KEY` (giữ `WORK_AI_ADAPTER=infrastructure.ai.UnavailableProposals` làm mặc định an toàn), chuyển tiếp actor Bearer + `X-Service-Key` và hoãn `ACTION` sang AI v2 theo DG5.
- **Phía `apps/ai-service` (`Một phần`):**
  - Hiện có 3 route (`/healthz`, `POST /api/ai/v1/requests`, `GET /api/ai/v1/requests/{request_id}`) tại [routes.py](../../apps/ai-service/src/api/routes.py#L18-L50).
  - Schema kết quả `BacklogItem` và `Subtask` tại [results.py](../../apps/ai-service/src/models/results.py#L11-L38) **chưa có** `local_id`, `ai_revision` và kết quả lưu chưa chuẩn hóa `context_version` cho bước xác thực ngược.
  - Nginx Gateway **đã chặn** `/api/ai/v1/internal` (`404`) từ Đợt 1 (`1d02eb1`).

### 2.2. Yêu cầu triển khai cho Team AI (`Thiết kế mục tiêu`)

#### A. Gắn `local_id`, `ai_revision` và `context_version` ở tầng hậu xử lý
1. Cập nhật [results.py](../../apps/ai-service/src/models/results.py) và [ai-service-v1.yaml](../../contracts/api/ai-service-v1.yaml) (giữ tương thích ngược cho các bản ghi lịch sử cũ):
   - Với `backlog_generation.v1` (`BacklogItem`) và `task_decomposition.v1` (`Subtask`), bổ sung 2 trường được **sinh hoàn toàn bằng mã Python ở tầng hậu xử lý sau khi nhận đầu ra LLM** (không phụ thuộc LLM tự bịa):
     - `local_id`: chuỗi định danh ổn định trong phạm vi một `request_id` (`"item-1"`, `"item-2"`, ... cho backlog; `"subtask-1"`, `"subtask-2"`, ... cho subtask; độ dài `1..100` ký tự, duy nhất trong danh sách).
     - `ai_revision`: chuỗi băm SHA-256 rút gọn (`16..64` ký tự hex, tối đa `100` ký tự) tính từ JSON chuẩn hóa của chính item đó (sau khi chuẩn hóa nội dung).
   - Chuẩn hóa `dependencies` của từng item chỉ chứa các `local_id` hợp lệ khác chính nó trong cùng kết quả (loại bỏ tham chiếu mồ côi hoặc tự tham chiếu để Work kiểm đồ thị `BLOCKS` không bị lỗi rác).
   - Lưu `context_version` (số nguyên `int >= 0`) và bản đồ `context_source_versions` (ví dụ `{"project": "42", "task": "7"}`) thu được từ `ContextDocument.source_version` khi AI đọc context từ Work:
     - Với `backlog_generation`: `context_version = int(context_source_versions["project"])` (fallback `0` chỉ khi không đọc được số nguyên hợp lệ — khuyến nghị fail nếu thiếu context chính).
     - Với `task_decomposition`: `context_version = int(context_source_versions["task"])`.
   - Trả kèm `context_version` trên phản hồi `GET /api/ai/v1/requests/{request_id}` (ở khối `result` hoặc metadata cấp đề xuất) để Team Web truyền nguyên vẹn xuống `POST .../bulk-apply-ai/` (khớp `BacklogApplySerializer.context_version` & `SubtaskApplySerializer.context_version` đang yêu cầu `IntegerField(min_value=0)`).

#### B. Mở Internal Endpoint `POST /api/ai/v1/internal/requests/{request_id}/verify-proposal`
- **Mục đích:** Cho phép duy nhất `work-service` xác thực nguồn gốc và tính toàn vẹn của một AI proposal trước khi ghi nguyên tử vào `work_db`.
- **Xác thực bắt buộc (fail-closed):**
  1. Header `X-Service-Key`: so khớp hằng thời gian (`hmac.compare_digest`) với khóa của caller `"work"` trong `AI_INBOUND_SERVICE_KEYS`. Thiếu/sai hoặc chưa cấu hình trả `403`. **Không** dùng chung khóa chiều AI → Work (`AI_WORK_SERVICE_KEY`).
  2. Header `Authorization: Bearer <actor JWT>`: xác minh chữ ký RS256 qua JWKS và trạng thái phiên qua Identity `/api/v1/internal/auth/session-status` như các route AI hiện có.
- **Request body (JSON, `additionalProperties: false`):**
  ```json
  {
    "proposal_type": "BACKLOG",
    "project_id": "11111111-1111-4111-8111-111111111111",
    "parent_task_id": null
  }
  ```
  - `proposal_type`: `"BACKLOG"` hoặc `"SUBTASK"` (`"ACTION"` hoãn sang AI v2 theo DG5).
  - `project_id`: UUID bắt buộc.
  - `parent_task_id`: `null` khi `proposal_type == "BACKLOG"`; bắt buộc là UUID khi `proposal_type == "SUBTASK"`.
- **Quy tắc kiểm tra bắt buộc phía AI:**
  1. `request_id` tồn tại trong `ai_context_db` → không có trả `404`.
  2. Chưa quá hạn retention (`expires_at > now()`, mặc định `created_at + terminal_retention_days=30 ngày`) → quá hạn trả `410`.
  3. Trạng thái yêu cầu là `succeeded` → nếu `queued`/`running`/`failed`/`expired` trả `409`.
  4. Khớp `intent` và đích:
     - `proposal_type == "BACKLOG"` ⇔ `intent == "backlog_generation"`, `target_type == "project"`, `target_id == project_id`, `parent_task_id is None`.
     - `proposal_type == "SUBTASK"` ⇔ `intent == "task_decomposition"`, `target_type == "task"`, `target_id == parent_task_id`, và `project_id` khớp `project_id` ngữ cảnh đã xác thực khi thực thi request.
     - Lệch bất kỳ điều kiện nào → trả `409`.
  5. Kiểm tra actor: actor từ Bearer JWT phải khớp `requester_user_id` của `ai_request` (nếu mở rộng cho Leader khác cùng dự án thì chỉ trả danh sách `actor_ids` đã được xác minh hợp lệ; mặc định `[requester_user_id]`). Không khớp → trả `403`.
- **Response `200 OK` (`Cache-Control: no-store`, JSON phẳng theo quy ước AI Service, không bọc `success/data`):**
  ```json
  {
    "proposal_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    "proposal_type": "BACKLOG",
    "project_id": "11111111-1111-4111-8111-111111111111",
    "parent_task_id": null,
    "context_version": 42,
    "item_revisions": {
      "item-1": "a1b2c3d4e5f607089988776655443322",
      "item-2": "11223344556677889900aabbccddeeff"
    },
    "actor_ids": [
      "22222222-2222-4222-8222-222222222222"
    ],
    "expires_at": "2026-12-24T10:00:00Z"
  }
  ```
  - Lưu ý kiểu dữ liệu bắt buộc khớp `VerifiedProposal` trong [infrastructure/ai.py](../../apps/core-service/infrastructure/ai.py):
    - `proposal_id`: string bằng đúng `str(request_id)`.
    - `proposal_type`: `"BACKLOG"` | `"SUBTASK"`.
    - `context_version`: integer `>= 0`.
    - `item_revisions`: object `dict[str, str]` (ánh xạ `local_id -> ai_revision`).
    - `actor_ids`: mảng UUID khác rỗng.
    - `expires_at`: RFC 3339 bắt buộc có múi giờ (ví dụ `Z` hoặc `+00:00`).
- **Bảng mã HTTP lỗi để Work ánh xạ an toàn sang tiếng Việt:**
  - `401`: Bearer token không hợp lệ hoặc phiên đã bị thu hồi.
  - `403`: Thiếu/sai `X-Service-Key` hoặc actor không thuộc phạm vi đề xuất.
  - `404`: Không tìm thấy `request_id`.
  - `409`: Đề xuất chưa `succeeded`, sai `proposal_type` hoặc sai `project_id`/`parent_task_id`.
  - `410`: Đề xuất đã hết hạn lưu trữ (quá 30 ngày).
  - `503`: Lỗi phụ thuộc (Identity/DB tạm không khả dụng).

#### C. Cấu hình môi trường & Đồng bộ staging (`B32`)
1. Khai báo `AI_INBOUND_SERVICE_KEYS` theo pipeline `.env.example` → `infra/env/ai-service.env` → [src/config.py](../../apps/ai-service/src/config.py) (JSON map `{"work": "<random-secret >= 32 chars>"}`, giá trị phải khớp `WORK_AI_SERVICE_KEY` phía Work; mặc định rỗng để fail-closed khi chưa bật).
2. Rà soát & đồng bộ cấu hình JWT staging (`B32`) giữa `docker-compose.staging.yml` và `infra/env/ai-service.env`: `AI_JWT_ISSUER`, `AI_JWT_AUDIENCE`, `AI_IDENTITY_BASE_URL`, `AI_IDENTITY_SERVICE_KEY`, `AI_WORK_SERVICE_AUTH_ENABLED=true`, `AI_WORK_SERVICE_KEY`.

#### D. Phạm vi hoãn (DG5) & Nghiệm thu phía Team AI
- **Hoãn `POST /projects/{id}/ai-actions/apply/` (`kind="ACTION"`):** Không cần hỗ trợ `proposal_type="ACTION"` ở AI v1 vì `risk_analysis` v1 chỉ trả văn bản `suggested_actions: list[str]`.
- **Điều kiện bàn giao từ Team AI:**
  1. Cập nhật [contracts/api/ai-service-v1.yaml](../../contracts/api/ai-service-v1.yaml) (mô tả `local_id`, `ai_revision`, `context_version` và endpoint internal `verify-proposal`).
  2. Unit + integration tests cho `verify-proposal` đủ các mã `200 / 401 / 403 / 404 / 409 / 410`, kiểm tra `local_id`/`ai_revision` ổn định và không lộ secret/raw stacktrace.
  3. Thông báo cho Team Core Backend khi sẵn sàng để chạy wire test HTTP thật AI ↔ Work.

---

## 3. Hướng dẫn cho Team Integration (`apps/integration-service`) — Đợt 5.2 & 5.3 (DG1, DG6)

### 3.1. Hiện trạng đã xác minh trên mã nguồn hai bên
- **Phía `apps/core-service` — miền Work (`Đã triển khai (local)`):**
  - Đã hoàn thiện [consumer.py](../../apps/core-service/apps/integrations/consumer.py) nhận và định tuyến đủ cả 3 sự kiện trên `utask.integration.events` (`integration.project.connection.changed`, `integration.github.account.changed` → `apply_account_fact()`, `integration.github.reference.detected` → giải mã `task_code` → `ingest_reference()` tạo ứng viên `PENDING`).
  - Đã bổ sung `RemoteIntegration.fetch_project_activity()` ([infrastructure/integration.py](../../apps/core-service/infrastructure/integration.py)) và public BFF `GET /projects/{project_id}/github/activity/` ([services/activity.py](../../apps/core-service/apps/integrations/services/activity.py)) có cache Redis ngắn (`WORK_GITHUB_ACTIVITY_CACHE_TTL_SECONDS=45`) và gộp mới `linked_task_ids` đã `CONFIRMED`, bám đúng hợp đồng [work-service.yaml](../../contracts/api/work-service.yaml).
- **Phía `apps/integration-service` (`Một phần`):**
  - Đã có `link_verified_account` / `unlink_github_account` ([github_accounts/services.py](../../apps/integration-service/apps/github_accounts/services.py#L13-L93)) và `revoke_authorization` ([github_jobs/webhooks.py](../../apps/integration-service/apps/github_jobs/webhooks.py#L88-L123)) nhưng **chưa phát** event tài khoản GitHub lên outbox/Kafka.
  - Đã có `GitHubProjectClient.activity()` ([github_project.py](../../apps/integration-service/infrastructure/github_project.py#L295-L335)) đọc commits/PRs/issues nhưng **chưa có** internal endpoint cho caller `work` và chưa đọc `branches`.
  - Webhook [webhooks.py](../../apps/integration-service/apps/github_jobs/webhooks.py#L62-L63) hiện đánh dấu `IGNORED` cho mọi event ngoài `ping`, `github_app_authorization`, `installation`, `installation_repositories` (chưa xử lý `push` và `pull_request`).

### 3.2. Yêu cầu 1 — Event `integration.github.account.changed` v1 (Đợt 5.2, DG1 / ADR-004)
- **Mục tiêu:** Tự động đồng bộ trạng thái xác minh tài khoản GitHub (`is_github_verified`, `github_user_id`, `github_username`) sang `work-service` mà không đọc chéo DB và không dùng legacy `/oauth/github*` của Identity.
- **Điểm ghi Outbox (trong CÙNG DB transaction với thay đổi `GitHubAccount`):**
  1. `link_verified_account()` ([github_accounts/services.py](../../apps/integration-service/apps/github_accounts/services.py#L13-L69)): khi liên kết mới hoặc cập nhật đổi `github_username`/khôi phục `REVOKED → LINKED` → phát với `verified: true`.
  2. `unlink_github_account()` ([github_accounts/services.py](../../apps/integration-service/apps/github_accounts/services.py#L72-L93)): khi chuyển `LINKED → REVOKED` → phát với `verified: false`.
  3. `revoke_authorization()` ([github_jobs/webhooks.py](../../apps/integration-service/apps/github_jobs/webhooks.py#L88-L123)): khi nhận webhook `github_app_authorization` (`action="revoked"`), kiểm tra cập nhật đồng bộ `GitHubAccount.status = "REVOKED"`, tăng `source_version` và ghi outbox với `verified: false` (tránh trường hợp chỉ thu hồi credential mà `GitHubAccount` vẫn giữ `LINKED` hoặc Work không hay biết).
- **Topic & Khóa phân vùng:** Topic `utask.integration.events`, Kafka key = `payload.user_id`.
- **Hợp đồng Envelope (cùng quy ước `additionalProperties: false` với [integration.project.connection.changed.v1.json](../../contracts/events/integration.project.connection.changed.v1.json)):**
  ```json
  {
    "event_id": "33333333-3333-4333-8333-333333333333",
    "event_type": "integration.github.account.changed",
    "event_version": 1,
    "aggregate_id": "22222222-2222-4222-8222-222222222222",
    "occurred_at": "2026-11-24T12:00:00Z",
    "trace_id": "44444444-4444-4444-8444-444444444444",
    "producer": "integration-service",
    "payload": {
      "user_id": "22222222-2222-4222-8222-222222222222",
      "github_user_id": "12345678",
      "github_username": "student-dev",
      "source_version": 2,
      "verified": true,
      "synced_at": "2026-11-24T12:00:00Z"
    }
  }
  ```
  - **Ràng buộc khớp 1:1 với `AccountFact` của Work:**
    - `aggregate_id == payload.user_id` (UUID).
    - `github_user_id`: chuỗi chữ số không rỗng (`1..100` ký tự), kể cả khi `verified=false`.
    - `github_username`: chuỗi không rỗng (`1..100` ký tự, lấy login đã lưu trước khi thu hồi khi `verified=false`).
    - `source_version`: số nguyên tăng đơn điệu `>= 1` của `GitHubAccount`.
    - `verified`: boolean (`true` khi `LINKED`, `false` khi `REVOKED`).
    - `synced_at`: RFC 3339 UTC.
- **Đầu ra hợp đồng:** Tạo và kiểm thử schema tại `contracts/events/integration.github.account.changed.v1.json`.

### 3.3. Yêu cầu 2 — Internal API Live GitHub Activity cho Work BFF (Đợt 5.3 Tầng 1, DG6 / ADR-005)
- **Mục tiêu:** Cung cấp dữ liệu cho Tab Code (`/projects/:id/code`) qua Work BFF (`GET /api/work/projects/{project_id}/github/activity/`) theo nguyên tắc **duy nhất Integration gọi GitHub API**.
- **Route nội bộ mới:** `GET /api/v1/internal/projects/{project_id}/github/activity` tại [github_connections/api.py](../../apps/integration-service/apps/github_connections/api.py).
  - Kế thừa `ActorConnectionView` với `allowed_callers = ("work",)` và `http_method_names = ["get"]`.
  - Bắt buộc `X-Service-Key` (khóa Work → Integration) + `Authorization: Bearer <actor JWT>` (xác minh actor qua Identity); từ chối query params và request body.
  - **Không** cần gọi ngược `POST /api/v1/internal/integration/projects/{project_id}/authorize` của Work vì chính Work là caller đã kiểm quyền đọc `readable_project` trước khi gọi (cơ chế `github.read` giữ nguyên cho caller `ai`).
- **Mở rộng `GitHubProjectClient.activity()` ([github_project.py](../../apps/integration-service/infrastructure/github_project.py#L295-L335)):**
  - Giữ các danh sách `commits`, `pull_requests`, `issues` (tối đa 20 mục mỗi loại).
  - Bổ sung `branches` (`GET repos/{owner}/{name}/branches?per_page=20&page=1`), mỗi phần tử gồm `{name, sha, url}` (URL đã chuẩn hóa `https://github.com/{owner}/{name}/tree/{branch}`).
  - Bổ sung `open_pull_requests_count` (`int >= 0`, số PR đang `OPEN`).
- **Response `200 OK` (envelope chuẩn Integration `{success: true, data: {...}}`, `Cache-Control: no-store`):**
  ```json
  {
    "success": true,
    "data": {
      "project_id": "11111111-1111-4111-8111-111111111111",
      "repo_id": "12345",
      "repo_owner": "student-dev",
      "repo_name": "utask-demo",
      "default_branch": "main",
      "generation": 1,
      "status": "CONNECTED",
      "open_pull_requests_count": 2,
      "branches": [
        {
          "name": "main",
          "sha": "0123456789abcdef0123456789abcdef01234567",
          "url": "https://github.com/student-dev/utask-demo/tree/main"
        }
      ],
      "commits": [
        {
          "id": "0123456789abcdef0123456789abcdef01234567",
          "title": "feat: add UTASK-12 endpoint",
          "url": "https://github.com/student-dev/utask-demo/commit/0123456789abcdef0123456789abcdef01234567",
          "occurred_at": "2026-11-24T11:30:00Z"
        }
      ],
      "pull_requests": [
        {
          "id": "42",
          "title": "Fix UTASK-12 auth middleware",
          "status": "OPEN",
          "url": "https://github.com/student-dev/utask-demo/pull/42",
          "occurred_at": "2026-11-24T11:45:00Z"
        }
      ],
      "issues": [
        {
          "id": "15",
          "title": "Improve error handling",
          "status": "OPEN",
          "url": "https://github.com/student-dev/utask-demo/issues/15",
          "occurred_at": "2026-11-24T11:00:00Z"
        }
      ],
      "synced_at": "2026-11-24T12:00:00Z"
    }
  }
  ```
  - **Các giá trị `status` hợp lệ:**
    - `"CONNECTED"`: đọc đủ các mục từ GitHub.
    - `"PARTIAL"`: một phần quyền (ví dụ Issues hoặc một endpoint phụ) bị `403`, các mục còn lại đọc bình thường.
    - `"STALE"`: kết nối tồn tại nhưng dữ liệu cần đối soát lại (ví dụ GitHub tạm rate-limit hoặc lỗi mạng ngắn khi đọc).
    - `"REAUTH_REQUIRED"`: credential sở hữu kết nối bị thu hồi hoặc hết hiệu lực (`401`), cần người dùng ủy quyền lại tại `/settings/integrations`.
  - **Giới hạn an toàn:** Tuyệt đối không trả token, raw GitHub payload hay metadata nhạy cảm; giữ kích thước JSON gọn `<= 64 KiB` (trùng giới hạn `65536` byte hiện tại trong `RemoteIntegration._request` — nếu vượt ngưỡng vì tiêu đề dài cần cắt tiêu đề `<= 300` ký tự như `GitHubProjectClient` đang làm). Nếu dự án chưa có `ProjectConnection(status="CONNECTED")`, trả `404`.
  - **Đầu ra hợp đồng:** Cập nhật [contracts/api/integration-service-v1.yaml](../../contracts/api/integration-service-v1.yaml) lên `v1.5.0`.

### 3.4. Yêu cầu 3 — Webhook `push` & `pull_request` → Event `integration.github.reference.detected` v1 (Đợt 5.3 Tầng 2, DG6)
- **Mục tiêu:** Khi sinh viên push commit/nhánh hoặc mở/cập nhật/merge Pull Request có nhắc mã công việc (ví dụ `UTASK-12`), Integration trích xuất tham chiếu đã xác thực từ webhook GitHub và gửi sang Work để tạo ứng viên `TaskGitHubLink(confirmation_status="PENDING")` chờ người dùng xác nhận.
- **Xử lý trong [github_jobs/webhooks.py](../../apps/integration-service/apps/github_jobs/webhooks.py#L50-L85) & Celery worker:**
  1. Giữ nguyên xác thực HMAC `X-Hub-Signature-256`, chống lặp theo `X-GitHub-Delivery` (`GitHubJob`), và kiểm `installation.app_id == INTEGRATION_GITHUB_APP_ID`.
  2. Thay vì đánh dấu `IGNORED` ở dòng `62-63`, nhận `event in {"push", "pull_request"}`, chuẩn hóa payload tối giản allowlist (không lưu toàn bộ raw webhook khổng lồ vào DB) với trạng thái `PENDING` để worker xử lý bất đồng bộ.
  3. Worker tìm tất cả `ProjectConnection(status="CONNECTED", repo_id=str(repository.id))`:
     - Regex tách mã công việc: `\b([A-Z0-9]{2,10}-[1-9][0-9]*)\b` (chuẩn hóa chữ hoa, khớp ràng buộc `Project.identifier` `^[A-Z0-9]{2,10}$` và `sequence_id >= 1` của Work).
     - Với **`push`**:
       - Tách tên nhánh từ `ref` (bỏ tiền tố `refs/heads/`): nếu tên nhánh chứa mã task → ứng viên `link_type="BRANCH"`, `ref_id=<branch>`, `title=<branch>`, `status=null`, `url="https://github.com/{owner}/{name}/tree/{branch}"`.
       - Duyệt tối đa 20 commit trong `commits[]`: nếu `message` chứa mã task → ứng viên `link_type="COMMIT"`, `ref_id=<40-char sha>`, `title=<dòng đầu message <= 300 ký tự>`, `status=null`, `url="https://github.com/{owner}/{name}/commit/{sha}"`.
     - Với **`pull_request`** (`action in {"opened", "edited", "reopened", "closed", "synchronize"}`):
       - Tìm mã task trong `pull_request.title`, `pull_request.body`, và `pull_request.head.ref`.
       - Mỗi mã task tạo ứng viên `link_type="PULL_REQUEST"`, `ref_id=str(pull_request.number)` (chuỗi số nguyên dương), `title=<title <= 300 ký tự>`, `status="MERGED"` nếu `merged_at` khác `null` ngược lại `"OPEN"` / `"CLOSED"`, `url="https://github.com/{owner}/{name}/pull/{number}"`.
  4. Ghi outbox cho từng `(project_id, task_code, link_type, ref_id)` duy nhất lên topic `utask.integration.events` (Kafka key = `payload.project_id`):
     ```json
     {
       "event_id": "55555555-5555-4555-8555-555555555555",
       "event_type": "integration.github.reference.detected",
       "event_version": 1,
       "aggregate_id": "11111111-1111-4111-8111-111111111111",
       "occurred_at": "2026-11-24T12:05:00Z",
       "trace_id": "66666666-6666-4666-8666-666666666666",
       "producer": "integration-service",
       "payload": {
         "project_id": "11111111-1111-4111-8111-111111111111",
         "repo_id": "12345",
         "generation": 1,
         "source_version": 3,
         "task_code": "UTASK-12",
         "link_type": "PULL_REQUEST",
         "ref_id": "42",
         "title": "Fix UTASK-12 auth middleware",
         "status": "OPEN",
         "url": "https://github.com/student-dev/utask-demo/pull/42",
         "is_verified": true,
         "synced_at": "2026-11-24T12:05:00Z"
       }
     }
     ```
  - **Ràng buộc khớp 1:1 với `ReferenceFact` của Work ([infrastructure/integration.py](../../apps/core-service/infrastructure/integration.py)):**
    - `is_verified` phải là `true` (đã xác thực chữ ký webhook GitHub thuộc đúng `repo_id` và `generation` hiện hành).
    - `status` chỉ có giá trị `"OPEN" | "MERGED" | "CLOSED"` khi `link_type == "PULL_REQUEST"`, còn lại bắt buộc `null`.
    - `url` chỉ chấp nhận `https://github.com/...` không chứa query/fragment/credentials.
    - **Integration chỉ gửi `task_code`**, không truy vấn `work_db` tìm `task_id`. Work tự đối chiếu `project.identifier` + `sequence_id` để gọi `ingest_reference()` (nếu `task_code` không thuộc dự án hoặc không tồn tại, Work bỏ qua an toàn, không đẩy DLQ vòng lặp vô hạn).
- **Đầu ra hợp đồng:** Tạo và kiểm thử schema tại `contracts/events/integration.github.reference.detected.v1.json`.

### 3.5. Điều kiện nghiệm thu phía Team Integration
1. Xuất đầy đủ 2 event schema JSON (`integration.github.account.changed.v1.json`, `integration.github.reference.detected.v1.json`) và cập nhật `contracts/api/integration-service-v1.yaml` lên `v1.5.0`.
2. Unit + integration + contract tests chứng minh:
   - Outbox ghi nguyên tử trong cùng transaction cho link/unlink/revoke và webhook `push`/`pull_request`.
   - `GET /api/v1/internal/projects/{project_id}/github/activity` chỉ nhận caller `work` + Bearer hợp lệ, phản ánh đủ 4 trạng thái `CONNECTED/PARTIAL/STALE/REAUTH_REQUIRED`, không lộ token.
   - Webhook `push`/`pull_request` chống replay `delivery_id`, kiểm chữ ký HMAC, bỏ qua repo chưa `CONNECTED`.

---

## 4. Ghi chú phối hợp cho Team Notification (`apps/notification-service`) & Hạ tầng Cloudflare R2 (`B30`)

- **Đợt 6 — Kích hoạt tài khoản qua email (DG8 / `B3`):**
  - Team Core Backend (`identity-service`) đã đưa cơ chế bỏ qua kích hoạt vào cờ cấu hình `IDENTITY_REQUIRE_EMAIL_ACTIVATION` (mặc định `false` ở local/dev).
  - Trước khi bật `IDENTITY_REQUIRE_EMAIL_ACTIVATION=true` trên staging/production, Team Notification cần nghiệm thu consumer nhận `identity.activation.requested` và `identity.student.imported` cùng gửi email SMTP thật (chấm dứt chính sách tạm đặt mật khẩu ban đầu bằng email).
- **Đợt 6.2.4 — Sự kiện đổi email mới (`identity.email_change.requested` v1):**
  - `identity-service` phát sự kiện `identity.email_change.requested` (topic `utask.identity.events`, khóa phân vùng `user_id`, envelope v1 và cơ chế mã hóa AES-256-GCM giống hệt `identity.activation.requested` / `identity.password_reset.requested`):
    ```json
    {
      "event_id": "uuid",
      "event_type": "identity.email_change.requested",
      "event_version": 1,
      "aggregate_type": "user",
      "aggregate_id": "<user_id>",
      "occurred_at": "2026-11-24T12:00:00Z",
      "trace_id": "uuid",
      "producer": "identity-service",
      "data": {
        "user_id": "<user_id>",
        "email": "<new_email>",
        "expires_at": "2026-11-24T12:15:00Z",
        "secret": {
          "key_id": "<IDENTITY_MAIL_KEY_ID>",
          "expires_at": "2026-11-24T12:15:00Z",
          "nonce": "<base64-12-bytes>",
          "ciphertext": "<base64-aes-256-gcm>"
        }
      }
    }
    ```
  - **Giải mã `secret`:** AAD là `["<event_id>","identity.email_change.requested","<user_id>","<expires_at>"]` (UTF-8 không khoảng trắng); plaintext là `{"token":"<raw-token>","new_email":"<new_email>"}` (hạn 15 phút). Team Notification cần thêm handler & template gửi liên kết xác minh tới `data.email` (`new_email`), dẫn về trang xác nhận trên Web (gọi `POST /api/auth/users/me/email-change/confirm` với `{"token": "..."}`); nếu `secret == null` (đã hết hạn bị `cleanup_identity` redaction) thì bỏ qua an toàn.
  - Phía `work-service` đã bổ sung `identity.email_change.requested` vào `NON_PROFILE_EVENT_TYPES` nên không đẩy nhầm sang DLQ.
- **Hạ tầng Cloudflare R2 CORS (`B30`, dùng chung cho Avatar Identity & Attachment Work):**
  - Token S3 R2 ứng dụng không có quyền sửa bucket CORS (`AccessDenied`); người quản trị hạ tầng Cloudflare cần cập nhật CORS Policy trên bucket R2 tại Cloudflare Dashboard (giữ nguyên các origin production như `https://utask.u-code.dev`, bổ sung origin Web local/staging nếu cần):
    ```json
    [
      {
        "AllowedOrigins": ["https://utask.u-code.dev", "http://localhost:8080"],
        "AllowedMethods": ["PUT", "GET", "HEAD"],
        "AllowedHeaders": ["Content-Type"],
        "ExposeHeaders": ["ETag"],
        "MaxAgeSeconds": 3600
      }
    ]
    ```
- **Đợt 7.2 — Thông báo lớp học P2 (`ClassAnnouncement`):**
  - Hiện Notification chưa đăng ký consumer nguồn Classroom. Sau khi chốt đặc tả P2, hai đội sẽ chốt hợp đồng sự kiện theo [hướng dẫn Notification](../notification-service/implementation.md#thêm-service-hoặc-event-mới).

---

## 5. Phần Team Core Backend (`apps/core-service` — miền Work) đã triển khai ở Đợt 5 (`Đã triển khai (local)`)

Team Core Backend đã hoàn tất trọn phần thuộc quyền sở hữu của miền Work trong `apps/core-service` (hợp nhất theo [ADR-006](adr/006-consolidate-core-monolith.md)) bám đúng hợp đồng ở Mục 2 & Mục 3 trên (không sửa mã nguồn của Team AI hay Team Integration):
1. **`RemoteProposals` (`apps/core-service/infrastructure/ai.py`):** gọi `POST {WORK_AI_BASE_URL}/api/ai/v1/internal/requests/{proposal_id}/verify-proposal` ngoài DB transaction, truyền `X-Service-Key: WORK_AI_SERVICE_KEY` + forwarded actor Bearer, chấp nhận `context_version` dạng số nguyên hoặc chuỗi số nguyên dương, ánh xạ lỗi `401/403/404/409/410/503` sang `CoreAPIError` tiếng Việt; giữ `WORK_AI_ADAPTER=infrastructure.ai.UnavailableProposals` làm mặc định an toàn.
2. **Consumer `utask.integration.events` (`apps/core-service/apps/integrations/consumer.py`):** định tuyến theo `event_type` cho cả 3 sự kiện (`integration.project.connection.changed`, `integration.github.account.changed` → `apply_account_fact()`, `integration.github.reference.detected` → phân giải `task_code` → `ingest_reference()`).
3. **Public BFF `GET /projects/{project_id}/github/activity/` (`apps/core-service/infrastructure/integration.py`, `apps/core-service/apps/integrations/`):** kiểm quyền `visible_project`, trả ngay `DISCONNECTED`/`PENDING` từ `core_db` nếu chưa kết nối; khi `CONNECTED` gọi `RemoteIntegration.fetch_project_activity()` có cache Redis (`WORK_GITHUB_ACTIVITY_CACHE_TTL_SECONDS`, mặc định 45 giây) theo `(project_id, connection_generation)` (chỉ cache `CONNECTED`/`PARTIAL`, kiểm tra khớp `repo_id`/`generation`) và luôn gộp mới `linked_task_ids` từ `TaskGitHubLink(confirmation_status="CONFIRMED")`.
4. **Kiểm thử hiện hành trên `apps/core-service` (local):** Đạt bộ kiểm thử hợp nhất PostgreSQL 16 (71/71 pytest bao gồm `test_architecture_boundaries.py`, `test_external_team_contracts.py` và integration xuyên miền), `export_api_contracts --validate` (0 lỗi/cảnh báo; khớp đầy đủ tuyến công khai với `contracts/api/{identity,classroom,work}-service.yaml`). Sẵn sàng chạy kiểm thử ghép thật khi Team AI và Team Integration hoàn tất provider.
