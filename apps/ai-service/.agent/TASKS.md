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

- Tích hợp provider adapter và ADK Workflow sau khi chọn provider/model.
- Thêm Context Layer/domain tools và internal API adapter theo baseline;
  chốt hợp đồng quyền, timeout và giới hạn context trước khi triển khai.
- Triển khai Celery/Redis cho job nội bộ sau khi chốt hành vi xử lý nền.
- Thay repository in-memory bằng `ai_context_db` và migration.
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
