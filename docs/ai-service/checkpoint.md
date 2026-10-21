# Checkpoint AI Service — 21/10/2026

Đây là bản bàn giao theo source, cấu hình và kiểm thử tại thời điểm checkpoint.
Tài liệu kiến trúc chuẩn vẫn là [architecture](architecture.md), hợp đồng
hành vi là [API v1](api.md), vị trí mã nguồn là [code map](code-map.md).

## Quyết định bổ sung — 22/10/2026

**Sẽ làm:** gỡ cơ chế mã hóa Fernet của token giữa API và worker để đơn giản
hóa luồng xử lý, theo yêu cầu người dùng. Khi thực hiện, bỏ
`FernetCredentialVault` và yêu cầu `AI_CREDENTIAL_KEY`, cập nhật cấu hình,
kiểm thử và cách xử lý job cũ đang chứa token mã hóa.

Checkpoint này chỉ ghi nhận việc cần làm; runtime vẫn dùng Fernet hiện tại.
Việc gỡ Fernet không đồng nghĩa bỏ xác thực JWT/session hoặc quyền người dùng.

## Kết luận tại checkpoint

**Trạng thái tổng thể: Một phần; chưa sẵn sàng phát hành production.** Phần
AI consumer, retention và wiring/gate đã có source và kiểm thử local. Blocker
chính là provider Work chưa triển khai và chưa có nghiệm thu liên service
với quyền/context thật. Không thay đổi business implementation Work, không
deploy, không bật GitHub hoặc sửa secret trong lần ghi checkpoint này.

API công khai POST/GET `/api/ai/v1/requests` và schema kết quả v1 giữ nguyên.
AI chỉ tạo proposal; không ghi dữ liệu Work, không đọc database service khác.
Không mở rộng thêm intent, Kafka projection hoặc specialist trong milestone này.

## Tiến độ M1–M4

| Phần việc | Trạng thái | Phạm vi bằng chứng |
| --- | --- | --- |
| Work boundary | Thiết kế mục tiêu đã chốt | `work-ai-context-v1.yaml` được `work-service.yaml` tham chiếu; provider Work **Chưa triển khai** |
| M1 — Adapter AI / least privilege | Đã triển khai source/test; tích hợp thật Một phần | POST authorize envelope, key theo provider, typed domain data/allowlist; GitHub risk Project theo flag/focus, Sprint limitation từ runtime; chưa nối Work thật |
| M2 — Retention terminal | Đã triển khai source/test | Migration 0004, terminal_at, batch/cascade/SKIP LOCKED; mặc định tối đa 500 request terminal quá 30 ngày mỗi giờ; volume production Chưa xác minh |
| M3 — Runtime/gateway | Một phần | Bốn process root/standalone; URI AI giữ nguyên, internal bị chặn; đã test wiring, chưa nghiệm thu gateway → Work/Integration thật |
| M4 — Evaluation gate | Một phần | Dataset 30 case và deterministic gate đã chạy; live runner/release wiring đã có; fixture staging/model pin và gate thật Chưa xác minh |
| Bàn giao cho đội Work | Đã viết và kiểm tra tài liệu | Ba API, quyền, mapping, key/URL và checklist trong guide Work; không đồng nghĩa provider đã có |

Quy trình và phần chưa nghiệm thu tại
[điều kiện phát hành](production-readiness.md). Source/test cụ thể tại
[code map](code-map.md) và [task log](../../apps/ai-service/.agent/TASKS.md).

## Bằng chứng kiểm tra mới nhất

Các kết quả source/build sau đã chạy trong đợt triển khai ngày 21/10, được
ghi tại task log; không phải vừa chạy lại toàn bộ khi sửa checkpoint:

- **485 AI tests passed, 0 skipped**, Python 3.12, PostgreSQL 16/Redis 7 thử
  nghiệm cô lập. Gồm migration/backfill/cascade/concurrent cleanup và beat →
  broker → worker thật; domain HTTP và LLM vẫn dùng mock/fake trong suite.
- **135 infrastructure script tests passed**, gồm Compose/deploy boundaries
  và Nginx container. Ruff check/format 100 Python file và Docker build image
  `utask/ai-service:production-readiness` đạt.
- Evaluation CLI đạt **30/30 deterministic cases**. Khi ghi checkpoint đã
  đọc lại JSON trong `/tmp/utask-ai-evaluation.8dbh55/`: report passed và toàn
  bộ check đạt. Đây là artifact local tạm thời, không phải artifact release
  staging hoặc bằng chứng chất lượng/latency model production.
- Guide Work đã kiểm tra 35 link nội bộ trên bốn tài liệu liên quan, năm ví
  dụ request/response theo OpenAPI và hai URL map qua AI production Settings.
- GitNexus đã force rebuild tại HEAD `40bb330`; change analysis trước đó báo
  **HIGH**, không partial/truncated, có chín flow AI/evaluation bị ảnh hưởng.
  Diff graph chỉ nhận tracked files; source/test mới untracked được kiểm tra
  riêng, không coi các flow vắng mặt là không bị ảnh hưởng. Kết quả này thay
  cho cảnh báo graph chưa xác minh ở lịch sử 15/10, không phải verdict LOW.

Không chạy lại full pytest/build hoặc gọi LLM khi chỉ cập nhật checkpoint.
Worktree còn thay đổi tracked/untracked; chưa commit/push/deploy. Trước khi
merge cần review toàn diff, chạy regression theo phạm vi thay đổi và
`detect_changes` lại, không dùng checkpoint thay kiểm tra mã cuối.

## Blocker local — kiểm tra ngày 21/10/2026

Đây là snapshot môi trường, không phải khẳng định các container luôn dừng:

- `docker ps -a`: AI API/worker/dispatcher, Work, Identity, Classroom, PostgreSQL,
  Redis và Nginx đang dừng. Integration API restart, worker unhealthy; beat và
  CLIProxyAPI còn chạy. Chưa có bằng chứng stack AI hiện tại healthy.
- Kiểm tra trước đó thấy Integration không resolve được PostgreSQL. Khi bật
  lại môi trường cần kiểm tra dependency/network/log hiện hành, không chỉ
  restart Integration. Không ghi raw log chứa credential vào checkpoint.
- `.env` local: `MOCK_TEST=true`, hai map `AI_AUTHORIZATION_URLS` và
  `AI_CONTEXT_URLS` rỗng; key AI→Work, AI→Integration, Integration→Work cùng
  `EVAL_AI_BEARER` chưa có; `INTEGRATION_SERVICE_KEYS` rỗng. Chỉ kiểm tra trạng
  thái có/thiếu, không xuất giá trị secret. `AI_GITHUB_CONTEXT_ENABLED` chưa
  đặt, nên dùng mặc định `false`.
- Lần kiểm tra URL resolver Work trước đó cho cả ba route bàn giao đều
  `NO_ROUTE`. Work có query/quyền/metrics để tái dùng nhưng chưa có REST
  provider tương ứng. Không suy ra đã triển khai từ contract `planned`.
- Token fixture local owner/outsider được kiểm tra trước đó đã hết hạn;
  nghiệm thu thật cần JWT Identity còn hiệu lực, không dùng lại token smoke 15/10.

Vì vậy hiện chưa thể chạy smoke liên service hoặc live gate. Không né blocker
bằng bật mock trên staging, bỏ authorize hoặc đọc DB Work từ AI.

## Việc tiếp theo theo thứ tự ưu tiên

| Ưu tiên / chủ sở hữu | Công việc | Điều kiện hoàn thành |
| --- | --- | --- |
| P0 — Work + AI | Chốt nghĩa/scope/đơn vị `team.capacity/workload`. Capacity hiện giờ/tuần, phép phân bổ estimate hiện có chưa mặc định là workload còn lại; không chia hai đại lượng khác đơn vị. | Quy tắc và test được thống nhất với consumer; nếu đổi shape phải version hóa contract trước. |
| P0 — Work | Triển khai service-key map theo caller, POST `ai.analyze`, GET 10 cặp target/domain và POST `github.read` chỉ cho Integration. | Provider contract test đạt; kiểm quyền mỗi lần đọc, giới hạn 64 KiB/100 mục, partial/warning, PII và deterministic metrics đúng contract. |
| P0 — Infra + AI/Work | Chuẩn bị môi trường test/staging: DB/broker và các service cần thiết healthy; inject URL map/key đúng chiều cho cả bốn AI process; tắt mock; JWT còn hiệu lực. | Preflight quyền/context thật đạt, cấu hình không lộ secret; không chỉ pass health endpoint. |
| P1 — AI + Work | Chạy smoke ba intent qua gateway: enqueue → dispatcher → worker → Work context → terminal result; thử allow/deny và available/partial/missing/stale. | Schema/context policy đúng; required context không dùng missing; không mutation hoặc fallback fixture. |
| P1 — Integration + Work + AI | Hoàn tất prerequisite connection/consent và quyền `github.read`; nghiệm thu GitHub connected/partial/missing/stale/deny trên candidate test/staging. | Project risk gọi Integration đúng scope; Sprint risk không gọi Integration và có limitation. Chỉ bật flag candidate có kiểm soát để test. |
| P1 — AI + QA | Provision manifest đủ 30 case, ghim model/prompt/dataset, chạy live evaluation qua gateway và lưu JSON/JUnit. | Safety/schema/context/tool policy 100%; success ≥95%; rubric ≥85%, từng intent ≥80%; p95 ≤25s, không request vượt 30s. |
| P2 — Infra + AI | Nghiệm thu migration/retention/khôi phục và vận hành release. | Có backup/cửa sổ bảo trì nếu bảng lớn, active request được giữ, cascade/cleanup và backlog được theo dõi; credential rotation/dead-letter được kiểm tra. |

Tài liệu giao trực tiếp cho đội Work:
[hướng dẫn provider Work–AI](../project-service/ai-service-integration-guide.md).
Luồng repository có điều kiện riêng trong
[hướng dẫn Work–Integration](../integration-service/work-service-integration-guide.md).
Chi tiết manifest, runner và release gate ở
[production readiness](production-readiness.md#evaluation-và-gate-phát-hành).

Hai nhánh Work implementation và chuẩn bị hạ tầng có thể làm song song;
smoke thật phải chờ cả hai. Nghiệm thu Work-only trước, giữ GitHub tắt trên
môi trường chưa đạt điều kiện; production chỉ bật sau smoke/gate thật đạt.
Gate hiện chạy sau rollout và không tự rollback, cần phương án vận hành khi
gate thất bại. Chưa tuyên bố production hoàn chỉnh.

## Lịch sử smoke LLM local — 15/10/2026

Các mục bên dưới lưu bằng chứng ngày 15/10, không phải trạng thái runtime
hiện tại hoặc nghiệm thu thay đổi M1–M4 ngày 21/10. GitHub fixture xuất hiện
trong smoke cũ không chứng minh GitHub context thật đã sẵn sàng.

### Kết quả ngày 15/10

**Một phần:** AI Service đã chạy local và tạo proposal bằng LLM thật qua
CLIProxyAPI. Ba intent v1 đã được kiểm chứng qua pipeline đầy đủ. Context và
quyền domain local dùng fixture; tích hợp domain thật và production chưa xác minh.

| Phần việc | Trạng thái | Bằng chứng và phạm vi |
| --- | --- | --- |
| FastAPI và schema v1 | Đã triển khai | Health; POST/GET `/api/ai/v1/requests`; schema riêng cho ba intent |
| Xác thực và phân quyền request | Đã triển khai | JWT bất đối xứng, ownership khi polling; worker xác thực/kiểm tra quyền lại |
| Request và hàng đợi bền vững | Đã triển khai | AI PostgreSQL lưu request/delivery; dispatcher giao Redis/Celery, worker claim chống chạy trùng |
| Trả kết quả worker → API | Đã triển khai | Inbox completion, notification và reconcile; API validate rồi ghi trạng thái cuối |
| Giới hạn tiếp nhận | Đã triển khai | Mặc định 5 request mới/phút/user và 2 request active/user; replay không tạo job mới |
| Bounded ADK workflow | Đã triển khai | Giới hạn model/tool/output, deadline 30s, schema validation và revise/retry hữu hạn |
| LLM thật | Đã triển khai local | LiteLLM → endpoint OpenAI-compatible của CLIProxyAPI; model smoke `gemini-3.5-flash-lite` |
| Context Tool Pool | Đã triển khai | Project/task/team/progress/development tools; giữ scope theo target, lọc dữ liệu và kiểm tra freshness |
| Context domain thật | Một phần | Adapter đã có, Work boundary đã chốt nhưng provider chưa triển khai; E2E chưa xác minh, smoke local dùng fixture |
| Áp dụng proposal | Chưa triển khai | AI chỉ trả đề xuất; service sở hữu nghiệp vụ sẽ kiểm tra quyền và áp dụng sau xác nhận |
| Retention terminal | Đã triển khai source/test | Migration/lịch beat/cleanup đã có; chưa nghiệm thu production |
| Kafka projection, specialist | Chưa triển khai | Không là dependency của pipeline MVP hiện tại |
| Staging/production và chất lượng model | Chưa xác minh | Local smoke chưa chứng minh deployment, quota, chi phí hoặc chất lượng thực tế |

### Pipeline đã chạy ngày 15/10

```text
POST request + JWT
  → application kiểm tra quyền và idempotency
  → AI PostgreSQL: queued + delivery
  → dispatcher → Redis → Celery worker
  → xác thực lại → ADK workflow → LlmAgent → Context Tool Pool
  → LiteLLM → CLIProxyAPI → LLM thật
  → validation → completion inbox + notification
  → API tiếp nhận → succeeded/result hoặc failed/error
  → GET request để polling kết quả
```

POST chờ tối đa 10 giây: trả 200 khi hoàn thành, 202 nếu cần polling. API,
dispatcher và worker là các process của cùng AI Service, cùng AI database.
Agent chỉ được dùng domain tools; không gọi HTTP tùy ý, đọc database service
khác hay tự tạo/sửa dữ liệu nghiệp vụ.

### LLM và xử lý lỗi tại thời điểm smoke

- Model, base URL và API key đi qua config/provider adapter; không hard-code
  credential. Secret giữ trong `.env` root, không đưa vào prompt hoặc task.
- LiteLLM gửi JSON mode; typed schema vẫn kiểm tra output theo intent.
  Proxy có thể bọc Markdown: workflow chỉ gỡ một JSON fence bao trọn output
  rồi validate, không trích JSON từ văn bản tùy ý.
- Text reasoning có `thought=True` được bỏ khỏi JSON proposal. Output token
  của LiteLLM đã gồm reasoning nên chỉ tính completion usage một lần.
- Tắt retry ẩn ở LiteLLM và SDK OpenAI. Workflow retry lỗi 429/5xx/kết nối/
  timeout provider trong cùng budget/deadline; lỗi cấu hình/quyền provider
  được từ chối. Output sai schema chỉ revise trong giới hạn.
- Model `gemini-3.8-flash-high` từng vượt deadline 30s. Stack local hiện dùng
  override `gemini-3.5-flash-lite`; giữ deadline của hợp đồng API v1.

Source: [provider](../../apps/ai-service/src/infrastructure/providers.py),
[workflow](../../apps/ai-service/src/workflow/bounded.py),
[tools](../../apps/ai-service/src/context/tools.py),
[context adapter](../../apps/ai-service/src/infrastructure/context_http.py).

### Bằng chứng inference thật

Smoke chạy qua API/dispatcher/Redis/Celery/ADK/completion với JWT local ký
thật và context fixture. Kết quả với bản runtime cuối cùng:

| Intent | Kết quả | Thời gian quan sát | Request ID |
| --- | --- | --- | --- |
| task_decomposition | succeeded, 3 subtasks; context task | 13,1s | `368fdcc8-c80d-4349-b889-76cf514698f5` |
| backlog_generation | succeeded, 2 items; context project | 5,3s | `8e0c1d2c-a40a-4364-a49c-07ddd4fb737b` |
| risk_analysis | succeeded, 1 risk; context progress/team/project/github_activity | 4,9s | `cde35f26-5126-467e-92d8-825aaadcf922` |

Số lượng và thời gian là quan sát một lần chạy, không là cam kết hay benchmark.
Schema hợp lệ không thay thế đánh giá chất lượng đề xuất.

### Kiểm thử và cách chạy local tại thời điểm 15/10

Unit tests dùng fake provider hoặc HTTP transport fake; HTTP boundary tests
giữ ADK/LiteLLM/OpenAI thật để kiểm tra JSON mode, tool call ID, reasoning,
retry 503, không retry 401 và timeout. Integration tests dùng PostgreSQL/Redis
test riêng, bao phủ pipeline, completion, idempotency, quota và phân quyền.
Lệnh và kết quả kiểm tra mới nhất ghi tại
[task log](../../apps/ai-service/.agent/TASKS.md).

Kiểm tra ngày 15/10: **281 passed, 0 skipped**; Ruff check/format 86 file pass;
Docker build, Compose health và model/base override pass. Ba module liên quan
trên host có credential local: **51 passed**, xác nhận SDK không tự nạp `.env`
vào test process. Kiểm tra link tài liệu và `git diff --check` pass. Còn warning
experimental ADK; không ảnh hưởng kết quả kiểm thử.

GitNexus đã reindex và chạy change analysis trên toàn worktree, nhưng kết quả
mapping symbol/flow cuối còn bất thường và báo CRITICAL; **Chưa xác minh**
verdict graph cho thay đổi cuối. Không dùng kết quả đó để khẳng định blast
radius thấp. Source/tests và review độc lập là bằng chứng trong checkpoint này.

Tại checkpoint 15/10, stack local chạy tại `http://127.0.0.1:8000`; JWT owner/outsider đã refresh
tại `.env.mock/`. Từ `apps/ai-service/`, tái khởi động cùng model đã kiểm chứng:

```sh
AI_MODEL=gemini-3.5-flash-lite docker compose --project-name ai-mock \
  --env-file ../../.env --env-file ../../infra/env/ai-service.env \
  up --build -d --wait --wait-timeout 60
```

Request mẫu và cách polling tại [mock data](mock-data.md); cấu hình và lệnh
test/build tại [README](README.md). `MOCK_TEST=true` chỉ thay context/quyền
domain local; LLM vẫn gọi thật. Tắt mock cần endpoint quyền/context đã cấu hình.

Danh sách hành động hiện tại nằm ở mục **Việc tiếp theo theo thứ tự ưu tiên**
phía trên. Không áp dụng các thông tin token/container lịch sử như trạng thái
local hiện tại; luôn kiểm tra môi trường trước khi tái khởi động.
