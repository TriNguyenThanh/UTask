# AI Service Task Log

## Quy tắc cập nhật

File này ghi lại tiến độ công việc của AI Service. Sau mỗi prompt có thay đổi
code trong `apps/ai-service/**`, agent phải cập nhật file này trong cùng thay
đổi.

- Ghi task đã hoàn thành kèm file, kiểm thử và trạng thái kiểm tra.
- Giữ lịch sử đã hoàn thành; không xóa task cũ để làm log ngắn hơn.
- Ghi rõ task đang làm hoặc task kế tiếp ở các mục tương ứng.
- Không đánh dấu hoàn thành khi chưa có bằng chứng từ code và kiểm thử.
- Prompt chỉ đọc, giải thích hoặc chỉ sửa tài liệu không bắt buộc ghi log.

## Đã hoàn thành

### 2026-10-08 — Chia commit theo từng phần AI Service

- Trạng thái: Đã hoàn thành.
- Phạm vi: Chia refactor thành năm commit theo định dạng
  `<task>(<feature>): message`: dependencies, models/contract, runtime kèm
  kiểm thử, Docker/Compose và tài liệu. Giữ API/application/persistence/auth/
  ADK cùng commit runtime vì thay hợp đồng phụ thuộc trực tiếp; không tạo
  commit trung gian lỗi import. Không thay đổi source khi chia commit.
- Kiểm tra: Snapshot staged của hai commit đầu lần lượt **66 passed** và
  **72 passed**; snapshot runtime **141 passed, 0 skipped** với PostgreSQL/
  Redis test riêng. Snapshot deployment pass `docker compose config --quiet`
  và Docker build. Ruff check/format pass trên source cuối cùng.
- GitNexus: Cập nhật index sau mỗi commit và chạy `detect_changes(all)` cùng
  `detect_changes(staged)` trước commit; không partial/truncated. Runtime
  ảnh hưởng 39 flow, risk critical, đã đối chiếu với integration tests.
  Dependencies/Compose không có symbol code để graph mô hình hóa; kiểm tra
  manifest/lock/config/build bổ sung, không dùng zero symbol để kết luận
  không có tác động. Tài liệu được kiểm tra link và whitespace trước commit.
- Kết quả: Commit local trên `feat/ai-service`; không push remote.

### 2026-10-08 — Refactor AI Service theo pipeline ADR-002

- Trạng thái: Đã hoàn thành phạm vi source và stack local; integration
  domain/LLM production chưa xác minh.
- Mục tiêu: Thay luồng gọi provider trong HTTP và repository in-memory bằng
  API → PostgreSQL → dispatcher → Redis/Celery → ADK, API đọc persistence
  để trả 200/202 và polling. Hoàn thiện bộ thay đổi pipeline có sẵn trong
  workspace, không reset các thay đổi trước đó.
- File đã thay đổi: `src/{api,application,workflow,context,infrastructure,
  jobs,models}/`, `src/{main,config,errors}.py`, `migrations/`, `alembic.ini`,
  `pyproject.toml`, `uv.lock`, `Dockerfile`, `.dockerignore`, `.env.example`,
  `compose.yaml`, `tests/`, `AGENTS.md`, `.agent/PIPELINE_PLAN.md` và
  `docs/ai-service/{README,api,workflow,architecture,code-map,erd,tech-stack}.md`.
  Thay đổi YAML contract có sẵn trước lượt làm việc này được giữ nguyên;
  không sửa service, gateway hoặc hạ tầng root.
- Boundary: Application có executor/repository/auth/budget protocols; không
  import SDK/I/O. Prompt và schema theo intent thuộc workflow, adapter chỉ
  lắp ghép provider. Agent tự chọn tool; workflow kiểm tra context thiết yếu
  cho từng intent trước proposal. Worker kiểm tra result đúng request,
  intent và version. AI không apply thay đổi hoặc đọc DB service khác.
- Persistence/job: Transaction request + delivery, unique user/key,
  idempotency đồng thời, delivery lease/redelivery/backoff, claim/fencing,
  budget/deadline bền vững, dead-letter và xóa credential terminal. Worker
  xác minh lại JWT và quyền trước khi chạy; task chỉ chứa request UUID.
- Kiểm thử/kiểm tra: `uv sync --all-groups --locked`, Ruff format/check và
  Pytest đều pass: **141 passed, 0 skipped**, coverage source **98%**.
  Dùng PostgreSQL 17 và Redis 7 test riêng; ADK Runner thật với model fake.
  Migration upgrade/downgrade và ORM schema drift, enqueue/claim đồng thời,
  Celery/Redis thật và các nhánh lỗi/biên đều pass. Cảnh báo duy nhất là
  ADK đánh dấu JSON schema tool declaration experimental.
- Unit test: Application/worker có doubles không cần DB, kiểm tra ownership,
  failed replay, queued/running, wrong request/intent/version/result, budget,
  auth/quyền. Domain tools/prompt/ADK có success và failure theo ba intent;
  lifecycle kiểm tra cleanup cả khi app/client lỗi. Protocol, re-export và
  composition wiring được kiểm tra bằng architecture/API/integration tests,
  không viết test mock từng khai báo framework.
- Build/smoke: Docker image `utask/ai-service:local` build pass. Compose local
  khởi động migration/API/dispatcher/worker/DB/broker, API healthy. HTTP qua
  container thật kiểm tra JWT, POST 202, GET terminal failed khi không có LLM
  credential, replay 502, conflict 409 và missing 404. DB giữ đúng một request,
  một model attempt, một dead-letter, không delivery hoặc credential còn lại.
  Đường thành công dùng model fake đã kiểm tra qua ADK/Celery/PostgreSQL thật;
  không gọi LLM trả phí.
- GitNexus: Lập lại index; impact báo LOW/MEDIUM cho phần lớn symbol,
  **CRITICAL** cho `_fetch` dùng chung năm tool, đã cảnh báo và kiểm thử các
  đường gọi. UNKNOWN/dynamic framework calls được đối chiếu source/test.
  `detect_changes(all)` nhận diện 243 symbol và 37 flow, risk **critical**,
  không partial/truncated; phạm vi lớn phù hợp thay toàn bộ pipeline.
  `check --cycles --json` trả enumeration complete, 0 vòng import.
  Graph diff không bao phủ file untracked; inventory, architecture tests và
  integration/build bổ sung kiểm chứng cho file mới. Không coi zero caller
  hoặc diff thiếu file mới là bằng chứng không có tác động.
- Tài liệu: Kiểm tra 64 link nội bộ trong 14 file, không link hỏng hoặc file
  rỗng ngoài package initializer có chủ ý. Không còn tham chiếu implementation
  cũ trong source/tài liệu chuẩn; `git diff --check` pass.
- Giới hạn: Identity issuer/key và hợp đồng REST quyền/context của Work/
  Integration cần công bố/cấu hình. Adapter dùng schema nội bộ, không tuyên
  bố service nguồn đã cung cấp endpoint đó. Gateway/Compose root, LLM quality,
  quota, secret rotation và retention production chưa xác minh. Kafka/
  specialist/SSE chưa có use case/contract runtime và không thêm vào MVP.

### 2026-10-07 — Đặt source trực tiếp trong src

- Trạng thái: Đã hoàn thành
- Mục tiêu: Theo yêu cầu người dùng, bỏ package bao ngoài và đặt các module,
  layer trực tiếp trong `src/`.
- File đã thay đổi: di chuyển toàn bộ source thành `src/{main,config,errors}.py`
  và `src/{api,application,workflow,infrastructure,models}/`; cập nhật import
  giữa layer và trong `tests/`. Cập nhật `Dockerfile`, architecture test,
  `.agent/STRUCTURE_PLAN.md`, `docs/ai-service/{README,architecture,code-map}.md`.
- Entry point: `uv run uvicorn main:app --app-dir src --reload`; Docker CMD
  chạy `main:app --app-dir src`. Pytest tiếp tục dùng `pythonpath = ["src"]`.
- Kiểm thử/kiểm tra: locked dependency sync pass; Ruff format/check pass;
  Pytest **66 passed**. Giữ bộ 60 ca cũ, thêm 6 ca cho import sai layer và
  source layer thiếu. API tests kiểm tra wiring/import mới; schema OpenAPI,
  request/response và thân tất cả hàm xử lý giống snapshot trước di chuyển.
- Build: `docker build --tag utask/ai-service:flat-src .` pass. Container chạy
  bằng CMD mặc định mới pass healthcheck, auth, provider lỗi, trace ID, GET,
  replay, conflict, ownership và request validation.
- Phân tích tác động: GitNexus impact trước sửa báo LOW/MEDIUM. Các file
  UNKNOWN (app entry point, test, initializer) được đối chiếu import, cấu hình
  Uvicorn và Pytest collection; không coi zero callers là an toàn. Source
  vẫn untracked nên graph diff không thay thế snapshot và kiểm thử.
- Kiểm tra cuối: index đã lập lại; GitNexus `check` hoàn chỉnh, 0 vòng import.
  `detect_changes(scope=all)` trả LOW, không partial/truncated, chỉ bao phủ
  diff tracked. 41 link nội bộ trong 13 file đều đúng; không còn import/đường
  dẫn source cũ hoặc file rỗng; `git diff --check` pass.
- Giới hạn hiện trạng: không thay đổi contract/API hay thêm runtime AI.
  Tích hợp qua gateway và provider/context/worker production chưa xác minh.

### 2026-10-07 — Refactor cấu trúc theo layer

- Trạng thái: Đã hoàn thành
- Mục tiêu: Tách application/workflow khỏi adapter, để app factory lắp ghép
  implementation cụ thể; giữ hành vi bootstrap và contract hiện tại.
- File đã thay đổi: chuyển module phẳng sang `application/{service,ports,
  responses}.py`, `workflow/{bounded,ports}.py`, `infrastructure/{providers,
  repositories}.py`; cập nhật `main.py` và import test. Giữ public exports của
  application/workflow/models. Thêm `tests/test_{architecture,repository,
  response_builders,application_helpers}.py`, `.agent/STRUCTURE_PLAN.md`; cập
  nhật `docs/ai-service/{code-map,architecture}.md`.
- Kiểm thử/kiểm tra: locked dependency sync pass; Ruff format/check pass;
  Pytest **60 passed** (39 ca cũ và 21 ca mới). OpenAPI, request schema và
  response schema giống hệt snapshot trước refactor. So sánh AST xác nhận
  thân các hàm hiện có không đổi; annotation workflow của application chuyển
  sang protocol và thêm khai báo `RequestWorkflow.run`.
- Build: `docker build --tag utask/ai-service:structure .` pass. Container
  smoke pass healthcheck, auth thiếu identity, provider mặc định, trace ID,
  GET trạng thái, replay, conflict, ownership và request validation.
- Tài liệu: kiểm tra 41 link nội bộ trong 13 file, không có link hỏng, tham
  chiếu module cũ hoặc file source/test/tài liệu rỗng; `git diff --check` pass.
- Phạm vi test: unit test application/workflow và các helper kiểm tra đường
  thành công, lỗi và biên; repository kiểm tra lookup thiếu, user/key scope,
  cập nhật record và cách ly instance. AST test giữ hướng import giữa layer.
  App factory/dependency/HTTP registration là wiring, kiểm tra qua API test
  và container smoke; protocol/re-export không có logic độc lập.
- GitNexus: impact trước sửa báo LOW; lập lại index thành công. `check` trả
  enumeration complete, 0 vòng import. `detect_changes(scope=all)` trả LOW,
  không partial/truncated nhưng chỉ nhận diện diff tracked (tài liệu); source
  vẫn untracked nên không dùng zero affected processes để kết luận source
  không ảnh hưởng. Snapshot, schema, AST và test kiểm chứng phần refactor.
- Giới hạn hiện trạng: provider thật, ADK, Celery, context adapter, Kafka và
  persistence production chưa triển khai. Auth/prefix gateway vẫn cần task
  riêng; không thay đổi các phần này bằng refactor cấu trúc.

### 2026-10-05 — Chuẩn hóa source bootstrap để dễ đọc

- Trạng thái: Đã hoàn thành
- Mục tiêu: Tách trách nhiệm HTTP và schema; làm rõ luồng application mà
  không đổi contract hoặc hành vi bootstrap.
- File đã thay đổi: `src/utask_ai_service/api/**`, `models/**`, `main.py`,
  `application.py`, `workflow.py`, `tests/**`, `.gitignore`, `README.md`,
  `AGENTS.md`, `.agent/READABILITY_PLAN.md`; cập nhật hướng dẫn chạy và code map
  trong `docs/ai-service/`.
- Kiểm thử/kiểm tra: `uv sync --all-groups --locked`, Ruff format/check và
  Pytest (39 passed). Fingerprint OpenAPI, request schema và response schema
  giống hệt trước refactor. Docker build `utask/ai-service:readability` pass;
  container smoke pass healthcheck, lỗi provider, trace ID, GET trạng thái,
  replay, conflict và ownership. Kiểm tra 15 link nội bộ trong 11 file tài liệu,
  không có link hỏng hoặc file rỗng; `git diff --check` pass.
- Phạm vi test: Unit test application/workflow/schema kiểm tra thành công và
  lỗi/biên. App factory, dependency và đăng ký HTTP handler là wiring, được
  kiểm tra qua API test và container smoke thay vì mock chi tiết framework.
- Phân tích tác động: GitNexus impact trước sửa báo LOW/MEDIUM; fixture/test
  UNKNOWN được đối chiếu source. Đã lập lại index và chạy `detect_changes`.
  Diff chỉ nhận diện tài liệu tracked, không bao phủ source untracked; không
  dùng kết quả zero affected flows để khẳng định source không có tác động.
- Ghi chú hoặc blocker: Không bổ sung provider thật, auth gateway, queue,
  Kafka hoặc DB. Chưa xác minh chạy qua gateway; khác biệt rewrite prefix và
  các phần contract chưa triển khai được ghi rõ trong code map.

### 2026-10-05 — Khởi tạo AI Service bootstrap

- Trạng thái: Đã hoàn thành
- Mục tiêu: Tạo service Python chạy được với healthcheck, boundary API phase 1,
  application/workflow/provider seam và repository in-memory phục vụ phát triển.
- File đã thay đổi: `pyproject.toml`, `.python-version`, `Dockerfile`,
  `.dockerignore`, `src/utask_ai_service/**`, `tests/**`.
- Kiểm thử/kiểm tra: `uv sync --all-groups --locked`, `uv run ruff format
  --check .`, `uv run ruff check .`, `uv run pytest` (8 passed), `docker build
  --tag utask/ai-service:local .` và container `GET /healthz` đều pass.
- Ghi chú hoặc blocker: Provider thật, ADK Workflow, Kafka consumer, context
  projection và PostgreSQL persistence chưa triển khai. Provider mặc định fail
  closed với `PROVIDER_UNAVAILABLE`; repository hiện chỉ lưu trong memory.

## Đang thực hiện

Chưa có.

## Sẽ làm

- Xác minh issuer/public key hoặc JWKS của Identity production; quản lý và
  rotation credential key dùng chung API/worker.
- Tích hợp REST quyền/context với endpoint/schema thật của Work/Integration;
  adapter/tool pool đã có nhưng hợp đồng domain cần công bố.
- Chạy evaluation LLM/model thật, quota/concurrency và cost budget production.
- Chốt retention/ẩn danh request/result và vận hành dead-letter trước production.
- Nếu cần projection Kafka, đối chiếu/version hoặc mapping contract context
  cũ với Work trước khi thêm consumer; không mặc định dùng schema cũ.
- Thống nhất auth/prefix gateway với contract rồi kiểm tra tích hợp thực tế.

## Mẫu mục log

```text
### YYYY-MM-DD — Tên task

- Trạng thái: Đã hoàn thành | Đang thực hiện | Sẽ làm
- Mục tiêu:
- File đã thay đổi:
- Kiểm thử/kiểm tra:
- Ghi chú hoặc blocker:
```
