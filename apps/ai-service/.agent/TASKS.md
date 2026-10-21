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

### 2026-10-22 — Đồng bộ contract test với provider Work đã triển khai

- `tests/test_work_context_contract.py` kiểm cả Bearer và caller key trên ba
  operation nội bộ, trạng thái `implemented` và không còn ngoại lệ key-optional.
  Không đổi permission provider hoặc mặc định cấu hình gửi key của AI.
- Đồng bộ `docs/ai-service/code-map.md`: nối Work phải bật gửi service key;
  source/test mock không thay bằng chứng phân quyền runtime.
- Đã tái hiện assertion cũ thất bại; toàn module contract Work đạt sau sửa.
  Deterministic evaluation đạt **30 ca**, tạo được JSON/JUnit report; Ruff
  lint/format file test đạt. Chưa chạy lại toàn suite AI hoặc provider live.

### 2026-10-22 — Cho phép endpoint LLM HTTP ở mọi môi trường

- Theo yêu cầu người dùng, bỏ riêng điều kiện cấm HTTP ở staging/production
  trong `src/infrastructure/providers.py`; giữ kiểm scheme HTTP/HTTPS, host,
  port, credential/query/fragment, model và API key.
- `tests/test_custom_provider_configuration.py` kiểm HTTP/HTTPS cho cả bốn
  môi trường, HTTP từ Docker host và URL có fragment bị từ chối.
- Cập nhật README về hành vi mới; không thêm cờ hoặc dependency, không đổi
  model, budget, JWT/session hay quyền context.
- Kiểm thử provider/configuration và workflow: **74 passed**, một cảnh báo
  experimental từ ADK; HTTP transport của test là fake, không phải LLM thật.
  Ruff lint toàn AI và format **101 file** đạt. Trên Windows bật UTF-8 khi
  chạy test để đọc contract tiếng Việt, không sửa test khác để bỏ qua lỗi encoding.
- Đã build và recreate bốn process AI trên staging local từ image mới; giữ
  `AI_ENVIRONMENT=staging`, `MOCK_TEST=false`, service key bật. Model dựng được
  với endpoint HTTP đã cấu hình; HTTP `/models` trả 200. Không chạy lại bốn
  workflow LLM trong lượt sửa này, không kết luận đã hết các timeout trước đó.
- GitNexus đã reindex; impact cũ là LOW nhưng sau refresh tool không resolve
  symbol này (UNKNOWN). Đối chiếu source/import và tests là bằng chứng chính.

### 2026-10-22 — JWT theo Work và tạm bỏ caller key AI→Work

- Quyết định hiện tại thay hướng dẫn PEM staging trước đó: verifier luôn GET
  raw JWKS từ `AI_IDENTITY_BASE_URL/.well-known/jwks.json` mỗi lần xác thực,
  không cache/PEM/URL JWKS riêng. Chọn RSA/use/alg/kid và required claims đúng
  Work (`exp`, `iss`, `aud`, `sub`, `token_type`); `iat` không bắt buộc.
  Kiểm UUID, access token, session Identity vẫn giữ; HTTP 401 thêm
  `WWW-Authenticate: Bearer`. Không gọi Identity với JWT sai cấu trúc/thuật toán.
- `AI_WORK_SERVICE_AUTH_ENABLED=false` mặc định tạm bỏ header/key AI→Work,
  vẫn gửi Bearer, action/intent và yêu cầu quyết định quyền đúng target.
  Bật lại flag yêu cầu Work key. Không bỏ key AI→Identity, AI→Integration
  hoặc mã hóa Fernet. Settings, ba Compose và env example đã đồng bộ.
- Cập nhật contract hai endpoint AI theo ngoại lệ tạm thời và ADR-005;
  Integration→Work vẫn bắt buộc key. Provider Work **Chưa triển khai**, không
  tự tạo endpoint giả và chưa xác minh role/quyền với Work runtime.
- `setup_mock.py` giữ public JWKS test tại `.env.mock/jwks.json`, không ghi
  PEM vào `.env`. Test API/worker dùng HTTP Identity giả nhưng JWT ký thật.
- Kiểm tra: full AI suite PostgreSQL/Redis thật **585 passed**; sau bổ sung
  auth challenge header chạy lại auth/API/admission **79 passed**. Toàn bộ
  **170 test script** do agent hạ tầng chạy đạt. Ruff lint/format, Docker build,
  kiểm tra diff và link tài liệu đạt. Identity/domain/LLM trong test là giả;
  staging thật **Chưa xác minh**. Không sửa secret `.env` hoặc deploy.

### 2026-10-21 — Sửa cấu hình xác thực staging và chặn thiếu secret lúc khởi động

- Compose staging lấy issuer/audience mặc định từ Identity, dùng PEM trong
  `AI_JWT_PUBLIC_KEY`, cố định JWKS rỗng và truyền Identity URL/caller key cho
  API/worker/dispatcher/beat. `.env.example` bổ sung key caller AI và hướng dẫn
  thay các giá trị mock khi triển khai.
- `src/config.py` từ chối staging/production khi thiếu issuer/audience, khóa
  xác minh, key AI→Identity hoặc Fernet key không hợp lệ. Không bắt buộc secret
  AI khi chỉ render Compose cho profile khác.
- `tests/test_environment_modes.py` kiểm đủ/thiếu cấu hình và Fernet sai;
  `test_identity_session_auth.py` xác nhận `Bearer x.y.z` trả 401 trước HTTP
  Identity/application. Các fixture production cho context/provider bổ sung
  cấu hình auth để tiếp tục kiểm đúng boundary riêng.
- Full suite AI trong Docker với PostgreSQL/Redis thật: **561 passed**;
  Identity HTTP và LLM giả, không xác nhận integration staging thật.
- Kiểm thử Compose render PEM nhiều dòng, mặc định/override Identity và cấu
  hình dùng chung: 64 test Compose/deployment do agent chính chạy đạt;
  toàn bộ 170 test script do agent hạ tầng chạy đạt. Lint/format, Docker build,
  diff check và kiểm tra link tài liệu cập nhật đạt.
- Tài liệu chuẩn: `docs/infrastructure/environment.md`, `ci-cd.md`, README và
  code map AI. User chọn **chỉ sửa repo**; không đổi secret `.env` hiện có hoặc
  deploy server. PEM/secret/session và luồng Identity staging thật **Chưa xác minh**.

### 2026-10-21 — Xác thực JWT và phiên Identity theo Work Service

- **Đã triển khai** trong `src/infrastructure/security.py`: chỉ nhận RS256,
  kiểm chữ ký/issuer/audience/hạn/claim bắt buộc, `token_type=access`, UUID
  `sub`; JWKS chọn khóa RSA theo alg/use/kid và từ chối khóa mơ hồ.
- API và worker dùng chung verifier; mỗi lần xác minh đều POST Identity
  `/api/v1/internal/auth/session-status` bằng Bearer và caller key AI.
  Phiên bị thu hồi trả 401; thiếu key, timeout, redirect, lỗi HTTP/schema
  đều từ chối. Giữ mapping lỗi công khai v1 cho `AUTH_UNAVAILABLE`.
- `src/config.py` bổ sung `AI_IDENTITY_BASE_URL` và secret
  `AI_IDENTITY_SERVICE_KEY`; Compose riêng truyền cả hai vào API/worker.
  `scripts/setup_mock.py` và fixture đổi sang UUID ổn định, access-token claim;
  test dùng HTTP Identity giả, không có bypass xác thực ở chế độ mock.
- Test: `tests/test_identity_session_auth.py` bao phủ JWT/JWKS, active/revoked,
  lỗi Identity, API và worker từ chối trước application/executor; cập nhật
  `test_security.py`, `test_environment_modes.py`, `test_mock_context.py` và
  `test_mock_pipeline.py`. Full suite trong Docker với PostgreSQL/Redis thật:
  **532 passed**; sau đó thêm hai case worker revoked/unavailable và chạy lại
  file auth: **46 passed**. Identity HTTP và LLM đều giả trong kiểm thử.
- Ruff check/format, Docker build và `git diff --check` đạt; liên kết file nội
  bộ của 5 tài liệu AI cập nhật không có đích thiếu. GitNexus impact/check
  đã chạy; index chậm HEAD 2 commit nên đối chiếu source trực tiếp.
- **Chưa xác minh** Identity runtime/staging/production. Cần inject
  `AI_IDENTITY_SERVICE_KEY` vào Compose root local/staging, cấu hình key khớp
  `IDENTITY_SERVICE_KEYS.ai` của Identity, issuer/audience và public key/JWKS
  thật. Không sửa Compose root hoặc `.env.example` ngoài phạm vi AGENTS AI.

### 2026-10-21 — Context boundary, retention và gate phát hành phase 1

- Trạng thái: Đã triển khai và kiểm thử local; **chưa nghiệm thu domain/LLM
  staging/production**. Không sửa business implementation Work, không deploy.
- Work contract mục tiêu ở `contracts/api/work-ai-context-v1.yaml`, được
  `work-service.yaml` tham chiếu. AI consumer gọi POST authorize với Bearer và
  key AI→Work, đọc typed project/task/team/progress ContextDocument; Work
  provider vẫn do đội Work triển khai. GitHub chỉ gọi Integration với key
  riêng, không gọi Work thêm cho github.read; Integration sở hữu bước quyền đó.
- GitHub tool chỉ cấp risk Project theo flag/focus; mặc định flag tắt. Sprint
  và Project khi tắt GitHub nhận limitation deterministic sau schema validation.
  Required context chỉ nhận available/partial. Domain schemas lọc PII/field
  ngoài allowlist, kiểm giới hạn 20/100 item và 64 KiB. Log JSON metadata có
  correlation ID; không log credential hoặc context thô.
- Migration `0004` thêm terminal_at/check/partial index; backfill từ updated_at,
  completed_at rồi created_at, abort khi timestamp legacy sai. Cleanup giữ
  30 ngày, một batch tối đa 500 mỗi giờ, SKIP LOCKED và cascade. Mọi terminal
  path gán timestamp; retry không đổi mốc. API/worker/dispatcher/beat dùng chung
  secret/config, staging/production fail startup nếu thiếu cấu hình domain.
- Nginx giữ nguyên `/api/ai/v1/...`, chặn internal Work. Thêm beat ở ba Compose,
  deterministic CI gate và live gate staging; JSON/JUnit persist theo release
  và được workflow upload artifact, kể cả khi gate lỗi. Live gate chạy sau
  rollout, không tự rollback.
- Golden dataset 30 case, 10 mỗi intent; fake model vẫn đi qua ADK và adapter
  thật. Live dùng fixture manifest có scenario/từ khóa/evidence IDs, preflight
  quyền/context thật, kiểm full response/request binding, pacing quota và hard
  timeout. Case chỉ mock ép được có live override riêng; quality chỉ chấm case
  kỳ vọng success. Rubric theo tham chiếu không thay đánh giá ngữ nghĩa của người.
- File chính: `src/config.py`, `src/models/context.py`, `src/context/tools.py`,
  `src/infrastructure/context_http.py`, `observability.py`, `repositories.py`,
  `db/tables.py`, `src/jobs/**`, `src/evaluation/**`, `tests/test_*context*`,
  `test_retention_*`, `test_evaluation.py`, Compose/CI/scripts và docs liên quan.
- Kiểm tra thực tế: **485 AI tests passed, 0 skipped** trong Python 3.12 với
  PostgreSQL 16/Redis 7 cô lập; gồm migration/backfill/cascade/concurrency,
  beat scheduler → Redis/Celery worker thật, API/completion và mock domain/LLM. **135 script
  tests passed**, gồm Nginx container và Compose/deploy failure boundaries.
  Ruff check/format (100 Python file), `git diff --check` và Docker build
  `utask/ai-service:production-readiness` đạt. Evaluation CLI trong image build
  đạt **30/30 deterministic cases**; không gọi model/domain production.
  Image từ chối startup production thiếu Work config và chặn live gate thiếu
  fixture/pin; cả hai được kiểm tra bằng process container thực tế.
- GitNexus: refresh incremental ban đầu thất bại; force rebuild với PDG và
  2 worker đã đạt tại HEAD `40bb330`, runner 1.6.12 current, incompleteReasons
  rỗng. `detect_changes(all)` báo HIGH, 9 flow AI/evaluation bị ảnh hưởng như
  dự kiến. Công cụ diff chỉ nhận file tracked, nên các file mới untracked
  được đọc/kiểm thử riêng; không coi graph là bằng chứng bao phủ toàn bộ diff.
  Analyzer còn cảnh báo giới hạn chọn execution flow; không suy ra flow vắng
  mặt là không bị ảnh hưởng. Không commit/push.
- Rủi ro vận hành: migration backfill/index thường cần cửa sổ bảo trì với bảng
  lớn; cleanup tối đa 500/giờ cần theo dõi backlog. Work API, JWT/rotation,
  fixture staging và model thật phải nghiệm thu trước khi bật GitHub production.

### 2026-10-18 — Migration trước API trong container entrypoint

- Trạng thái: Đã triển khai source và kiểm tra local; không commit/push/deploy
  hoặc chạy migration production. Giữ nguyên schema và migration Alembic hiện có.
- `docker-entrypoint.sh` chạy `alembic upgrade head` trước `uvicorn` hoặc đường
  dẫn tuyệt đối tới Uvicorn, dùng Alembic cùng thư mục executable. Migration
  lỗi dừng API; `exec` giữ tham số, PID và mã thoát của lệnh. Worker, dispatcher
  và lệnh quản trị bỏ qua migration tự động. Dockerfile copy executable và
  gắn ENTRYPOINT, giữ CMD API.
- Compose riêng bỏ `migrate`: API chờ DB/broker healthy; worker/dispatcher chờ
  API/broker healthy. Giữ PostgreSQL 17 riêng của stack AI; Compose root dùng
  PostgreSQL 16 chung do agent chính cập nhật. Không thêm khóa migration giữa
  replica; cần migration qua một API trước khi scale đồng thời.
- Files: `Dockerfile`, `docker-entrypoint.sh`, `compose.yaml`,
  `tests/test_container_startup.py`; docs AI `README.md`, `mock-data.md`,
  `architecture.md`, `erd.md`, `code-map.md` đồng bộ startup container với
  application lifespan không tự tạo schema; chạy bằng uv vẫn migrate thủ công.
- Tests mới dùng shell/lệnh giả, không gọi LLM hoặc DB nghiệp vụ: thành công,
  lỗi migration, restart ở head, tuyệt đối/sibling executable, args rỗng/có
  khoảng trắng, PID, mã thoát, worker/dispatcher/manual-command skip.
- Kiểm tra: `uv run ruff check .`, `uv run ruff format --check .` pass (87 file),
  compileall test mới pass; 72 link nội bộ docs và `git diff --check` pass.
  Compose riêng `config --quiet` pass với password giả chỉ trong process
  kiểm tra (root `.env` không đặt password của PostgreSQL riêng).
  `uv run pytest` trên Windows gặp lỗi encoding cp1252 trong test contract cũ.
  Chạy lại với Python `-X utf8` và WindowsSelector policy trong bộ nhớ:
  233 passed, 59 skipped, 1 failed ở test cũ đòi chmod POSIX 0600 trên Windows.
  Loại đúng test đó: **233 passed, 59 skipped, 1 deselected**. 10 ca shell mới
  skip trên Windows. Agent chính chạy lại toàn bộ bằng image Linux với
  PostgreSQL 16 và Redis 7 thử nghiệm riêng: **293 passed**, gồm 10 ca shell
  và test quyền POSIX; một cảnh báo experimental của Google ADK.
  Build image đạt. Docker smoke thực tế đạt ba tình huống: database sạch tự
  migrate rồi HTTP healthy, restart khi schema ở head vẫn healthy, migration
  lỗi không khởi động API. Container/network thử nghiệm đã được dọn; chưa
  deploy VPS hoặc xác minh provider production.
- GitNexus impact Dockerfile trả UNKNOWN (file không được graph index), không
  xác định callers/processes. Đã đối chiếu source compose/Dockerfile và startup
  tests để xác định gate API/worker/dispatcher; không coi UNKNOWN là LOW.

### 2026-10-15 — Chạy pipeline với LLM thật qua CLIProxyAPI

- Trạng thái: Đã triển khai và xác minh local. API/dispatcher/worker, AI
  PostgreSQL và Redis đang chạy bằng Compose riêng AI tại port 8000.
  Domain quyền/context vẫn dùng fixture MOCK_TEST=true; chưa xác minh production.
- Reuse adapter LiteLLM/ADK hiện có, không thêm provider/framework/service.
  Provider bật JSON mode, tắt retry cả LiteLLM và SDK OpenAI. Workflow bắt
  lỗi OpenAI/LiteLLM 429/5xx/kết nối/timeout để retry trong budget/deadline.
  Output usage completion đã gồm reasoning nên không cộng thoughts lần nữa.
- Proxy vẫn có thể bọc Markdown dù yêu cầu JSON mode. Workflow chỉ gỡ một
  JSON fence bao trọn output trước typed validation; không trích JSON từ
  văn bản tùy ý. Prose, JSON lỗi, field thừa và sai intent vẫn bị từ chối.
  Text `thought=True` không được ghép vào JSON proposal; HTTP reasoning case
  có regression test. Fixture HTTP đặt LITELLM_MODE=PROD trước import để SDK
  không tự nạp `.env` developer, dùng model cost map local và đóng logging worker.
- Files: `src/infrastructure/providers.py`, `src/workflow/bounded.py`,
  `compose.yaml`, tests `test_custom_provider_configuration.py`,
  `test_workflow.py`, `test_provider_http.py`; docs AI README/code-map/checkpoint.
  Compose truyền model/base URL đã resolve và hỗ trợ override qua process.
  JWT local refresh bằng utility hiện có, giữ DB/Fernet/LLM key; không ghi secret.
- Kiểm tra: **281 passed, 0 skipped** với PostgreSQL 17/Redis 7 test riêng;
  Ruff check/format **86 files pass**, Docker build/Compose health pass,
  config override model/base cùng giá trị ở API/worker/dispatcher/migrate.
  HTTP boundary tests dùng LiteLlm/LiteLLM/OpenAI thật, chỉ thay HTTPX transport:
  tool roundtrip/call ID/JSON mode, 503 retry, 401 không retry, timeout retry.
  Logging worker test được flush/stop; chỉ còn warning experimental ADK sẵn có.
  Review độc lập phát hiện hai vấn đề dotenv/reasoning đã sửa; ba module liên
  quan trên host **51 passed**, xác nhận không nạp credential developer.
- Inference thật với `gemini-3.5-flash-lite`: task decomposition 3 subtasks
  (14,1s, request `3e0eaa68-9f96-4890-8de7-fd7a96e364c7`), backlog 2 items
  (5,1s, `b3d8eaf3-b057-457e-b04e-f99931bedb7f`), risk 2 risks
  (5,2s, `10e0d18e-c352-411a-87ae-008138cb3386`); schema và required context
  pass qua API → dispatcher → Redis/Celery → ADK → completion/API.
  Model high cũ vượt hard deadline 30s; giữ hợp đồng deadline hiện có.
  Smoke lại bản cuối: task 3 subtasks/13,1s (`368fdcc8-c80d-4349-b889-76cf514698f5`),
  backlog 2 items/5,3s (`8e0c1d2c-a40a-4364-a49c-07ddd4fb737b`),
  risk 1 risk/4,9s (`cde35f26-5126-467e-92d8-825aaadcf922`), đều succeeded.
- GitNexus: impact provider LOW, workflow UNKNOWN được đối chiếu source/ADK
  tests. Reindex incremental và detect_changes(all) đã chạy; báo CRITICAL trên
  toàn worktree gồm thay đổi hạ tầng có sẵn. Mapping gán build_litellm_model
  cho nhiều flow frontend không liên quan, nên chưa có verdict graph đáng tin
  cho phạm vi cuối; không coi kiểm tra này là sạch. Không commit/push.
- Lệnh tái khởi động local có override model được ghi trong docs README;
  config model mặc định tại infra/env không đổi. Không benchmark chất lượng
  hoặc triển khai staging/production. Không tự áp dụng proposal vào nghiệp vụ.

### 2026-10-14 — Giới hạn chống spam tối thiểu cho request AI

- Trạng thái: Đã hoàn thành trong source và kiểm thử local; không deploy hoặc
  chạy migration trên database nghiệp vụ.
- Phạm vi: tối đa 5 request mới/user trong cửa sổ trượt 60 giây và 2 request
  queued/running/user. Cấu hình `AI_REQUESTS_PER_MINUTE` và
  `AI_MAX_ACTIVE_REQUESTS_PER_USER`, không chấp nhận giá trị nhỏ hơn 1.
- Enqueue dùng advisory transaction lock theo user trong PostgreSQL hiện có;
  kiểm tra replay/conflict trước giới hạn. Không tạo request/delivery khi
  từ chối; completion chưa được API tiếp nhận vẫn giữ slot. Đổi key/target
  không vượt giới hạn. Không thêm bảng bộ đếm hoặc hạ tầng mới.
- API trả `429 RATE_LIMITED`, reason `REQUEST_RATE_LIMIT` hoặc
  `ACTIVE_REQUEST_LIMIT`, `retryable=true`, `Retry-After` và số giây trong
  details. Lỗi budget giữ mapping/envelope cũ, không có header admission.
- Files: `src/config.py`, `src/infrastructure/{bootstrap,repositories}.py`,
  `src/infrastructure/db/tables.py`, `src/api/exception_handlers.py`,
  migration `0003_request_admission.py`, tests `test_admission.py`,
  `test_admission_transport.py` và quota riêng test completion 8 job pending.
  Cập nhật env thường, contract API v1 và docs AI README/API/architecture/ERD/code-map.
- Tests: toàn suite **257 passed, 0 skipped**, PostgreSQL 17 và Redis 7 test
  riêng; ADK thật với model fake. Bao phủ cửa sổ đúng 60 giây, replay/conflict,
  user isolation, queued/running/completion, terminal release, rollback và
  tranh chấp qua 6 engine độc lập. Migration upgrade/downgrade và ORM parity pass.
  Hai regression test HTTP thất bại đúng tại expected 429 khi thay enqueue
  bằng implementation HEAD cũ, pass trên implementation mới.
- Validation: Ruff check/format **85 file pass**, Docker build
  `utask/ai-service:admission-check` pass. Smoke image mới với JWT ký thật và
  PostgreSQL test: health, POST 202, 429/Retry-After, replay và polling pass,
  không gọi LLM. Kiểm tra 66 link file nội bộ không hỏng; `git diff --check` pass.
  Host thiếu uv/Python 3.12 nên suite chạy trong container, mount source hiện tại.
- Review/GitNexus: review độc lập không có finding cần sửa. Reindex source và
  detect_changes(all) nhận diện 28 symbol/5 flow/14 file tracked, risk MEDIUM,
  response không partial/truncated. Pre-edit HTTP error helper HIGH với 4
  caller đã cảnh báo và kiểm thử. Constructor/enqueue UNKNOWN được đối chiếu
  source/tests; graph diff không bao phủ file untracked, inventory và suite
  kiểm tra migration/hai file test mới. Flow enumeration có giới hạn và chưa
  có PDG, không kết luận mọi flow hoặc taint đều đã được graph kiểm chứng.
- Giới hạn: đây là giới hạn tạo job, không chặn mọi HTTP flood/polling. Budget,
  reauthorization, tool scope và proposal boundary hiện có được giữ nguyên.
  Chatbot, lịch 06:00/22:00 chống trùng và chống lặp thông báo chỉ ghi rõ
  thiết kế tối thiểu; chưa tạo runtime hoặc tuyên bố đã triển khai.

### 2026-10-09 — Chọn rõ Gemini Developer API và bỏ model fallback

- Trạng thái: Đã hoàn thành; user xác nhận Gemini Developer API, model chỉ
  định trong AI_MODEL. Không đổi API/context/queue/ADK workflow hoặc CI/CD.
- Source: Settings.model không có giá trị mặc định; kiểm tra tên rỗng/space.
  build_gemini_model yêu cầu model và key, lắp Gemini với API v1beta và
  enterprise=False, không tự dùng Cloud/Vertex/ADC. Model dạng projects/...
  bị từ chối. Thiếu model/key có reason rõ trước khi gọi SDK/trừ budget;
  model fake vẫn được inject cho unit tests như trước.
- Cấu hình: AI_MODEL=gemini-3.8-flash trong infra/env/ai-service.env, model
  cụ thể được Google công bố; GOOGLE_API_KEY tiếp tục nằm .env root, không
  đổi hoặc in secret. Không tạo thêm env hoặc thay kiểu context mock.
- File: src/config.py, src/infrastructure/providers.py,
  tests/test_gemini_api_configuration.py, test_workflow.py, ai-service.env,
  docs/ai-service/{README,code-map,mock-data}.md.
- Tests: **177 passed, 38 skipped** vì không đặt PostgreSQL/Redis test;
  targeted provider/workflow **22 passed**. Kiểm tra backend API khi các cờ
  Cloud bật, key/model/env không fallback, input model lỗi, key không export,
  thiếu cấu hình không gọi SDK/budget, deadline/retry/schema/tool flow cũ.
- Validation: Ruff check/format pass (82 file), Docker build
  utask/ai-service:gemini-api-explicit pass, Compose config --quiet pass;
  36 link nội bộ và fence được kiểm tra, git diff --check pass.
- Local apply: Rebuild/recreate API/worker theo xác nhận user; migration head
  chạy lại không thay schema, giữ database/broker và volume. API healthy.
  Worker dùng model cấu hình và client vertexai=False, API v1beta; metadata
  model đọc qua SDK được kiểm tra mà không gọi inference. Không deploy remote.
- GitNexus: Bound UTask đúng workspace, Settings MEDIUM, runtime LOW nhưng
  receiver gaps được đối chiếu source/tests; index và graph diff cập nhật.
  Không commit/push. Quyền Google project/inference vẫn là giới hạn riêng,
  không tuyên bố cấu hình đã giải quyết lỗi 403 trước đó.

### 2026-10-09 — Mock data trực tiếp tại adapter, giữ luồng request chuẩn

- Trạng thái: Đã hoàn thành theo yêu cầu làm rõ của user.
- Luồng: Client vẫn gọi API AI, lưu PostgreSQL, dispatcher giao Redis/Celery,
  worker chạy ADK, bàn giao completion cho API và client GET/replay kết quả.
  Chỉ nguồn quyền/context của microservice chưa có được thay bằng fixture.
  LLM runtime vẫn thật; không mock workflow hoặc kết quả trong source runtime.
- Factory: API/worker cùng dùng `build_context_adapter`. MOCK_TEST=true chọn
  FixtureContextAdapter đọc JSON tại package, kiểm tra allowed_users/target,
  lọc allowlist/giới hạn và trả ContextDocument; false chọn REST adapter cũ.
  JWT tại API/worker giữ nguyên. Config giữ ai-service.env + .env root; bỏ
  mock URL và cơ chế chuyển URL sang server giả. Cấm mock ngoài dev/test.
- Dọn: Xóa dev/, server mock_domain.py, launcher run_local.py và
  compose.mock.yaml. JSON chuyển tới src/infrastructure/fixtures/domain.json;
  request mẫu tới examples/requests/. Helper JWT chuyển scripts/setup_mock.py,
  chỉ dùng khi cần credential local, không nằm trong pipeline/startup.
  Secret/JWT hiện có giữ nguyên; không sửa CI/CD hoặc reset DB user.
- Files: `src/infrastructure/context_{factory,fixtures}.py`, fixture JSON,
  wiring main.py/jobs/tasks.py, config.py, compose.yaml, ai-service.env,
  scripts/setup_mock.py, examples/requests/, tests config/mock/pipeline và
  docs README/code-map/architecture/mock-data AI, environment infra.
- Unit tests: Chọn fixture/REST, không có HTTP trong mock mode, all domain
  tools/ba intent, ADK thật với model fake, quyền bị từ chối, unknown target,
  context thiếu/domain sai, draft, fixture/schema lỗi và cách ly document.
  API/worker composition chọn cùng adapter; wiring kiểm tra qua unit/integration.
  Hai adapter mới/factory đạt **100%** coverage qua 33 targeted tests.
- Integration: **203 passed, 0 skipped** với PostgreSQL 17 và Redis 7 test
  riêng. Test pipeline ba intent qua API/JWT ký thật, repository/claim/budget,
  Celery, ADK, listener completion/polling, replay và ownership. Fake đúng LLM
  bên ngoài, không gọi service mock hoặc LLM trả phí. Container test/credential
  tạm đã dọn; không dừng hay restart stack user.
- Validation: Ruff check/format pass (81 file); Docker build
  utask/ai-service:fixture-context pass. Trong image, adapter đọc fixture thành
  công không cần dev/server. Compose chỉ có API/worker/dispatcher/migrate/
  DB/broker, MOCK_TEST lấy từ ai-service.env; config --format json pass.
  60 link/anchor trong năm docs đúng, fence cân bằng, git diff --check pass.
- GitNexus: Bound UTask đúng workspace. Impact create_app/execute_request LOW;
  decorators/fetch/dataset UNKNOWN được đối chiếu source/tests. Giữ tên symbol
  khi chuyển module, không find-replace tên hàm. Index/graph diff cập nhật;
  diff tổng có completion/env/mock trước đó và không bao phủ đầy đủ untracked/
  enumeration flow, nên dùng inventory/full tests bổ sung. Không commit/push.
- Giới hạn: REST Work/Integration và LLM production chưa xác minh. Google
  project 403 trước đó là vấn đề external, không được giải quyết bằng fixture.

### 2026-10-09 — Một ai-service.env cho cấu hình và .env root cho secret

- Trạng thái: Đã hoàn thành theo yêu cầu thống nhất cấu hình mới.
- Nguồn chuẩn: `infra/env/ai-service.env` giữ biến thường/cờ chế độ;
  `.env` root giữ GOOGLE_API_KEY, AI_CREDENTIAL_KEY, AI_DB_PASSWORD và bộ
  credential xác minh AI_JWT_PUBLIC_KEY. Xóa các env/template riêng của AI;
  chuyển JWT sang `.env.mock/` root, không phải dotenv thứ ba. Giữ nguyên
  credential hiện có, không in secret, không restart stack đang chạy của user.
- Settings: Đọc config → secret, biến process ưu tiên cao nhất. Thêm
  AI_ENVIRONMENT, MOCK_TEST (alias chính xác), AI_MOCK_DOMAIN_URL và LLM
  SecretStr. Mock chỉ development/test; tạo URL domain REST theo flag và
  chặn URL không hợp lệ. Validation error không in giá trị input/secret.
- Runtime/Compose: Provider truyền key từ Settings qua Gemini client_kwargs,
  không export vào process. Compose inject riêng secret AI, DB local nhận
  password; không đưa toàn bộ `.env` root vào container. Launcher local chọn
  override theo cờ, truyền hai env_file để interpolation/cờ process nhất quán.
  Factory mock cũng từ chối khi flag tắt hoặc ngoài môi trường local.
- Setup: Ghi biến thường vào file chuẩn và secret vào root; --refresh thay
  JWT/public key, giữ DB/Fernet/LLM key và secret khác. Credential directory
  0700, secret/token 0600; chưa chỉ định refresh thì từ chối thay JWT đã có.
- File: `src/config.py`, `src/infrastructure/providers.py`, `dev/{setup_mock,
  run_local,mock_domain}.py`, Compose AI/mock/root, `infra/env/ai-service.env`,
  `.env.example`, `.agent/ENV_PLAN.md`, tests config/mock/workflow/conftest và
  tài liệu README/code-map/mock-data AI, environment infra. Không sửa schema
  DB, API/event contract hoặc CI/CD; git diff .github/workflows bằng không.
- Tests: **190 passed, 35 skipped** do chưa đặt PostgreSQL/Redis test. Thêm
  coverage flag true/false, staging/production, URL, precedence, giữ secret khi
  refresh, CLI success/error/exit, factory guard và key provider không cần
  export. Test không tự đọc env developer; fixture isolation là wiring được
  kiểm chứng bởi toàn bộ tests và test dotenv dùng checkout/file tạm riêng.
  Targeted config/dev tests đạt 98% coverage trước test hide-input bổ sung;
  entrypoint CLI được kiểm tra bằng module launcher thật.
- Validation: Ruff check/format pass (80 file), build
  `utask/ai-service:unified-env` pass. Launcher/Compose mode true/false kiểm
  chứng cờ runtime và lựa chọn service khớp; config root với .env.example pass.
  HTTP qua image mới trên project smoke riêng xác minh health/context owner
  và outsider 403; stack smoke đã dọn. Không gọi LLM thật trong lượt này.
- Tài liệu: 41 link/anchor đúng, fence cân bằng; không còn tham chiếu env
  riêng cũ trong source/tài liệu hiện hành, git diff --check pass. Secret
  Google/root và JWT được Git bỏ qua, file cấu hình thường không chứa secret.
- GitNexus: Bound repo UTask, impact Settings MEDIUM, provider/CLI LOW;
  factory/decorator UNKNOWN và receiver gaps đối chiếu source/tests. Index
  cập nhật và detect_changes(all) không partial/truncated, risk HIGH vì gồm
  completion/mock có sẵn; không suy ra an toàn từ diff bỏ qua file untracked
  hoặc giới hạn enumeration flow. Không commit/push/deploy remote.
- Giới hạn: Domain/LLM production chưa xác minh. Google project đã trả 403
  trước đó; thay cấu hình không chứng minh project đã được cấp quyền.

### 2026-10-09 — Gom env vào infra/env và giữ nguyên CI/CD

- Trạng thái: Đã hoàn thành theo yêu cầu điều chỉnh phạm vi của user.
- Vị trí cuối: `infra/env/ai-service.env` giữ ánh xạ deployment; mẫu runtime
  ở `infra/env/ai-service.env.example`; config local mặc định ở
  `infra/env/.env.ai-service`; bộ mock đã chuyển vào
  `infra/env/.env.ai-service.mock/`. Không có local runtime env để di chuyển;
  chỉ cập nhật đường dẫn mặc định. Giữ nguyên credential đã sinh và quyền file.
- CI/CD: Hoàn nguyên đúng các dòng đã sửa ở `ci.yml`/`release-staging.yml` và
  đường dẫn Compose root. `git diff --exit-code -- .github/workflows
  docker-compose.yml docs/infrastructure/ci-cd.md` pass. Không thay glob,
  upload script hoặc cấu trúc staging; không chạy deploy/commit/push.
- Source: Cập nhật ENV_DIR/default dotenv của Settings, output mặc định script
  mock và Compose AI/mock. Cập nhật unit tests vị trí env/CLI; giữ success,
  error/missing file, precedence, cwd khác và chống ghi đè. Không sửa hàm
  runtime xử lý AI hoặc schema database trong lượt này.
- Validation: Ruff check/format pass (77 file); **164 passed, 35 skipped**
  do chưa cấu hình PostgreSQL/Redis test. Docker build
  `utask/ai-service:env-central` pass; Compose root, AI sample và AI/mock
  config --quiet pass. Credential đã chuyển vẫn xác minh owner 200/outsider
  403 qua mock ASGI HTTP thật; không gọi LLM. Git bỏ qua config/JWT local;
  chỉ mapping `.env` khớp glob CI, sample/mock không bị upload bởi glob đó.
- Tài liệu: README/code-map/mock-data AI và environment infra cập nhật vị trí
  cuối; CI-CD doc hoàn nguyên. 42 link/anchor pass, code fence cân bằng,
  git diff --check pass. Mục lịch sử phía dưới giữ đường dẫn ở thời điểm làm.
- GitNexus: Impact Settings MEDIUM, CLI LOW; test UNKNOWN được kiểm chứng
  bằng source/Pytest. Cập nhật index và graph diff; diff tổng workspace vẫn
  gồm completion/mock có sẵn, không dùng zero/untracked làm kết luận an toàn.

### 2026-10-09 — Gom file môi trường AI vào infra/env/ai-service

- Trạng thái: Đã hoàn thành di chuyển và cập nhật tham chiếu local/CI.
- File: Chuyển `apps/ai-service/.env.example` và bộ `.env.mock/` sang
  `infra/env/ai-service/`; giữ `ai-service.env` đã được user chuyển sẵn.
  Không có `.env` runtime trong service để di chuyển; default mới trỏ tới
  `infra/env/ai-service/.env`. Giữ nguyên nội dung credential và quyền file.
- Source/config: `src/config.py` tính ENV_DIR theo vị trí source, không theo
  cwd; `dev/setup_mock.py` mặc định sinh config/JWT trong ENV_DIR/.env.mock.
  Cập nhật Compose AI/mock/root, CI path filter cho env lồng thư mục và
  staging mkdir/scp chỉ file ánh xạ không bí mật. Phạm vi infra/workflow được
  user cho phép trực tiếp trong yêu cầu di chuyển, không sửa service khác.
- Tests: Thêm `tests/test_env_location.py` kiểm tra checkout/cwd khác, đọc
  dotenv, env precedence, cấu hình sai và file thiếu; thêm unit test CLI
  mock mặc định chọn thư mục central và từ chối ghi đè. Toàn bộ **164 passed,
  35 skipped** vì không đặt DB/Redis test trong lượt này. Không suy ra kết
  quả integration từ test skip; không chạy lại migration/pipeline DB.
- Validation: Ruff check/format pass (77 file); Docker build
  `utask/ai-service:env-location` pass. Compose root, Compose riêng AI với
  sample và AI/mock với credential đã chuyển đều config --quiet pass.
  YAML và 14 script shell workflow parse pass; không chạy deployment remote.
  Container import Settings thành công khi không có dotenv checkout.
- Smoke: Uvicorn dùng env/JWT tại vị trí mới; HTTP health, quyền/context owner
  và outsider 403 pass. Process smoke đã dừng. Git tiếp tục bỏ qua env/JWT
  thật; sample và file ánh xạ là nguồn theo dõi trong repo.
- Tài liệu: Cập nhật README/code-map/mock-data AI và environment/CI-CD infra;
  43 link/anchor pass, code fence cân bằng, git diff --check pass. Không còn
  env ở apps/ai-service hoặc tham chiếu đường dẫn cũ trong tài liệu hiện hành;
  các mục lịch sử task log giữ nguyên để truy nguyên.
- GitNexus: Bound UTask đúng workspace, impact Settings MEDIUM và CLI LOW;
  test UNKNOWN được đối chiếu Pytest/source. Index và graph diff được cập
  nhật; phạm vi diff còn gồm các thay đổi completion/mock có sẵn. Không
  dùng graph zero hoặc file untracked làm bằng chứng không có tác động.
  Không commit/push.

### 2026-10-09 — Mock API quyền/context của Work và Integration

- Trạng thái: Đã hoàn thành mock local; domain/LLM production chưa xác minh.
- Phạm vi theo yêu cầu: Chỉ mock quyền/context, không mock LLM. Thêm process
  FastAPI local trong `dev/`, reuse JWT verifier/dependency, error envelope và
  REST adapter/tool pool hiện có; không sửa hàm runtime AI, service khác,
  schema DB hoặc contract API/event. Giữ các thay đổi completion có sẵn.
- Dữ liệu: Project/Task/Sprint, bốn task có trạng thái/dependency, team/
  workload/capacity, progress cố định và GitHub activity giả. Các document
  có source_version/warning mock; as_of sinh khi trả response. Fixture kiểm
  tra UUID, target type và reference/domain; provider Work/Integration và
  scope target được kiểm tra trên từng endpoint.
- File: `dev/{__init__,mock_domain,setup_mock}.py`, `dev/fixtures/domain.json`,
  `dev/requests/{backlog,task-decomposition,risk-analysis}.json`,
  `compose.mock.yaml`, `tests/test_mock_domain.py`, `pyproject.toml` (thêm
  root vào pytest pythonpath), `docs/ai-service/mock-data.md` và link/entry
  point trong README/code-map AI. Không thêm dependency.
- Credential: Sinh RSA/Fernet/password riêng, JWT owner và outsider ký thật,
  thời hạn 1–24 giờ; không lưu private key, không in secret, không ghi đè
  thư mục đã tồn tại. Config/token trong `.env.mock/` được Git/Docker bỏ qua,
  quyền directory/file 0700/0600. Image production không copy `dev/`.
- Unit tests: **32 passed**, coverage `dev/` **99%**; dòng entry point CLI
  còn lại được kiểm tra qua lần chạy module thật. Kiểm tra JWT, denied user,
  missing target/context, provider/domain sai, validation fixture/config,
  chống ghi đè và cả ba intent lấy context qua ASGI HTTP + adapter/tool pool.
- Validation: Ruff check/format toàn service pass; **197 passed, 0 skipped**
  với PostgreSQL 17/Redis 7 test riêng, database `ai_test` và Redis DB 15.
  Docker build `utask/ai-service:mock-check` và Compose config pass. Host
  không có `uv`, dùng `.venv/bin/python`/Ruff; Docker build sync dependency
  frozen thành công. Cảnh báo ADK JSON schema experimental có sẵn.
- Smoke: Compose riêng `ai-mock-verify` chạy migration/API/dispatcher/worker/
  mock/DB/broker. HTTP thật kiểm tra 13 scope context, quyền owner/outsider;
  cả ba payload có outsider 403, owner 202, GET terminal failed khi thiếu
  LLM credential và GET khác owner 404. Không gọi LLM trả phí. Stack và
  volume test do lượt này tạo đã được dọn; giữ config/token local cho user.
- GitNexus: Bound repo/worktree UTask hiện tại, cập nhật index. Adapter risk
  LOW; Depends/factory/new symbol UNKNOWN được xác minh bằng source, Compose,
  tests và HTTP smoke, không coi zero caller là an toàn. detect_changes(all)
  không partial/truncated, risk HIGH do gồm cả refactor completion có sẵn;
  graph diff không bao phủ file mới untracked. Analyzer cũng báo giới hạn
  enumeration flow, nên inventory/tests bổ sung kiểm chứng phần mock.
  Không commit/push.
- Tài liệu: Hướng dẫn Compose/local, JWT/token expiry, payload/polling,
  mock contract và giới hạn tích hợp; 37 link/anchor trong ba tài liệu đã
  kiểm tra, fence cân bằng, không có file mới rỗng, git diff --check pass.

### 2026-10-08 — Worker thông báo kết quả để API cập nhật DB

- Trạng thái: Đã hoàn thành source và kiểm thử local; production chưa xác minh.
- Quyết định: Process API của AI nhận completion và ghi trạng thái/kết quả cuối.
  Worker lưu `ai_completion` và phát PostgreSQL NOTIFY cùng transaction; API
  LISTEN, tiếp nhận qua application, kiểm tra token/schema/intent/version,
  ghi response/dead-letter và xóa inbox cùng transaction. Redis vẫn là broker;
  không thêm Kafka, HTTP callback hoặc lưu nội dung context.
- Tin cậy: Inbox phục hồi sau restart/mất tín hiệu; listener reconnect và đọc
  lại định kỳ. SKIP LOCKED cho nhiều API consumer; thông báo trùng hoặc token
  cũ không ghi đè kết quả. Success bàn giao trước deadline không bị dispatcher
  timeout khi API tạm dừng. Credential xóa khi bàn giao hoặc terminal failure.
- File: `src/application/{ports,execution,service}.py`, `src/config.py`,
  `src/infrastructure/{repositories,completions}.py`, `src/infrastructure/db/tables.py`,
  `src/main.py`, migration `0002_completion_handoff.py`, `.env.example`,
  `tests/test_completion_{unit,postgres}.py`, các test application/worker/job/
  repository/lifecycle liên quan, `AGENTS.md`, `.agent/COMPLETION_PLAN.md` và
  `docs/ai-service/{README,architecture,api,workflow,erd,code-map,tech-stack}.md`.
- Unit tests: application tiếp nhận không chạy executor; worker bàn giao
  success/failure; listener LISTEN trước read, drain, mất tín hiệu, reconnect
  khi connect/LISTEN/accept/notify lỗi, cancellation và cleanup. Protocol,
  ORM/migration và composition wiring kiểm tra bằng architecture/lifecycle/
  integration tests. Transaction, khóa hàng và NOTIFY dùng PostgreSQL thật
  vì mock không xác minh được rollback, commit hoặc tranh chấp giữa consumer.
- Validation: Ruff format/check pass; **165 passed, 0 skipped**, coverage source
  **98%**. PostgreSQL 17 và Redis 7 trong container test riêng; DB chỉ tên
  `ai_test`, không dùng dữ liệu nghiệp vụ. Migration upgrade/downgrade và ORM
  schema drift pass. Celery/Redis thật + ADK fake model → completion listener
  → API application → terminal result pass; không gọi LLM trả phí.
- Docker build `utask/ai-service:completion-local` pass. Kiểm tra 74 link nội
  bộ trong 9 tài liệu, anchor, code fence, file rỗng và tham chiếu luồng cũ
  trong tài liệu AI; `git diff --check` pass.
- GitNexus: impact trước sửa chủ yếu LOW/MEDIUM; UNKNOWN ở test/lifecycle và
  dynamic repository dispatch được đối chiếu source/config/Pytest. Lập lại
  index; detect-changes(all) nhận diện 83 symbol, 9 flow, risk HIGH, bao gồm
  README root đã thay đổi sẵn. Graph diff không thay thế inventory/test cho
  file mới untracked; không coi zero là không ảnh hưởng. Không commit/push.
- Vận hành: Alembic upgrade head tới `0002` trước restart API/worker. Listener
  cần connection trực tiếp/session pooling; chưa xác minh production và
  tích hợp Identity/Work/Integration/LLM. Hợp đồng POST/GET v1 được giữ nguyên,
  client vẫn GET polling. Chính sách mới nằm trong architecture AI; ADR-002
  là quyết định ban đầu về worker ghi terminal trực tiếp.

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

### 2026-10-09 — Chuyển ADK sang custom provider qua LiteLLM

- Trạng thái: Đã hoàn thành phần cấu hình và adapter; chưa xác minh endpoint/key
  nhà cung cấp cụ thể vì chưa có giá trị cấu hình.
- Mục tiêu: Cho ADK gọi endpoint tùy chọn tương thích OpenAI qua LiteLLM, giữ
  nguyên API request, mock context, workflow, budget và completion.
- Thay đổi: `AI_LLM_PROVIDER=litellm`, `AI_MODEL=openai/<model-id>` và
  `AI_LLM_API_BASE` ở `infra/env/ai-service.env`; `AI_LLM_API_KEY` ở `.env`
  root. Endpoint production yêu cầu HTTPS; HTTP chỉ chấp nhận loopback trong
  development/test. Thời hạn lấy từ deadline request và không retry.
- File: `src/config.py`, `src/infrastructure/providers.py`, `pyproject.toml`,
  `uv.lock`, test provider/workflow/config, `compose.yaml`, root `docker-compose.yml`,
  `scripts/setup_mock.py`, `.env.example`, docs AI Service và cấu hình env.
- Kiểm tra: uv lock/sync pass; Ruff check/format pass; full suite
  **180 passed, 38 skipped**; root và AI Compose config pass; Docker build và
  image smoke `LiteLlm` pass; `git diff --check` pass.
- GitNexus: Re-index source mới và chạy `detect_changes` đầy đủ; risk MEDIUM,
  ba execution flows `Execute → Metadata`, `Execute → Tools`, `Execute → Failure`
  được đánh dấu do thay đổi runtime; diff nhận diện đủ 18 file, không bị partial.
- Tài liệu: Kiểm tra 8 file docs/ai-service, không có link nội bộ hỏng.
- Giới hạn: Chưa có model ID, base URL hoặc API key nhà cung cấp để chạy inference.
  Yêu cầu cũ Gemini Developer API được thay bằng custom OpenAI-compatible provider.

### 2026-10-09 — Cấu hình local CLIProxyAPI làm custom provider

- Trạng thái: AI Service đã cấu hình và stack local healthy; inference chờ
  người dùng thay api-keys mẫu trong CLIProxyAPI Management.
- Cấu hình: `AI_MODEL=gemini-3.8-flash-high`; endpoint host được ánh xạ thành
  `http://host.docker.internal:8317/v1` cho container Linux. LiteLLM tự thêm
  prefix `openai/`. Tạo `AI_LLM_API_KEY` ngẫu nhiên trong root `.env` mode 0600;
  giữ các secret hiện có.
- Compose: Thêm host-gateway mapping cho AI Service ở local và root Compose;
  áp dụng bằng build/recreate `ai-mock` API/worker/dispatcher/migrate. Database
  và broker giữ nguyên, API healthcheck pass.
- Kiểm tra: **182 passed, 38 skipped**; Compose config, Ruff và Docker build
  pass. Từ container truy cập được host port 8317, nhưng `/v1/models` trả 403
  `unsafe_example_api_key`, CLIProxyAPI thông báo `api-keys` còn giá trị mẫu.
- GitNexus: impact `build_litellm_model` LOW trước sửa; re-index và
  `detect_changes` sau sửa báo MEDIUM, ba luồng Execute bị ảnh hưởng như dự kiến.
- Việc còn lại: Trong `http://127.0.0.1:8317/management.html?safe-mode=configure`,
  thay key mẫu bằng giá trị `AI_LLM_API_KEY` trong root `.env`; sau đó kiểm tra
  `/v1/models` và gửi request AI. Không ghi giá trị key vào log.

## Đang thực hiện

Chưa có.

## Sẽ làm

- Gỡ Fernet/token vault và yêu cầu `AI_CREDENTIAL_KEY` để đơn giản hóa API →
  worker, theo [checkpoint 22/10/2026](../../../docs/ai-service/checkpoint.md).
- Xác minh issuer và JWKS của Identity production.
- Nghiệm thu REST quyền/context với Work provider triển khai theo contract
  đã chốt và Integration thật; consumer/mock test không thay E2E.
- Chạy evaluation LLM/model thật, quota/concurrency và cost budget production.
- Nghiệm thu retention 30 ngày trên volume thật, theo dõi backlog cleanup và
  vận hành dead-letter trước production.
- Nếu cần projection Kafka, đối chiếu/version hoặc mapping contract context
  cũ với Work trước khi thêm consumer; không mặc định dùng schema cũ.
- Kiểm tra auth/gateway bằng fixture staging và chạy live release gate/model pin.

## Mẫu mục log

```text
### YYYY-MM-DD — Tên task

- Trạng thái: Đã hoàn thành | Đang thực hiện | Sẽ làm
- Mục tiêu:
- File đã thay đổi:
- Kiểm thử/kiểm tra:
- Ghi chú hoặc blocker:
```
