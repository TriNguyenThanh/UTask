# Điều kiện phát hành AI Service

**Trạng thái: Một phần.** Source/config/test của AI context adapter, Work
provider, Integration provider, tool scope, retention và wiring phát hành đã
có. Mức nghiệm thu runtime giữa các service và LLM production chưa đầy đủ;
không suy ra E2E hoàn chỉnh từ source/test hoặc healthcheck.
Smoke LLM local ngày 15/10/2026 dùng context/quyền fixture, xem
[checkpoint](checkpoint.md). Nguồn vị trí source là [code map](code-map.md).

## Boundary domain và quyền

[Work AI context v1](../../contracts/api/work-ai-context-v1.yaml) được
[Work contract](../../contracts/api/work-service.yaml) tham chiếu. Work
authorize/context provider đã có source/config/test; kiểm thử và smoke staging
đã xác minh một phần. Mức runtime và giới hạn kiểm chứng nằm trong
[hướng dẫn Work–AI](../project-service/ai-service-integration-guide.md).
Không đọc database Work hoặc tự tạo endpoint thay thế. Cấu hình đầy đủ các
service nằm trong [hướng dẫn triển khai AI](deployment-and-service-integration.md).

| Lời gọi | Credential và shape |
| --- | --- |
| AI → Work POST `/api/v1/internal/ai/targets/{target_type}/{target_id}/authorize` | Work provider đã có source; Bearer actor + `X-Service-Key` caller `ai`; body `{action: "ai.analyze", intent}`; response envelope có target/action/allowed |
| AI → Work GET `/api/v1/internal/ai/targets/{target_type}/{target_id}/contexts/{domain}` | Work provider đã có source; Bearer actor + `X-Service-Key` caller `ai`; trả `ContextDocument` trực tiếp theo contract |
| AI → Integration GET `/api/v1/internal/projects/{project_id}/github/context` | Provider có source; Bearer actor + `AI_INTEGRATION_SERVICE_KEY`; Integration kiểm mapping/consent và gọi Work authorize `github.read` bằng key Integration → Work |

Theo luồng hiện tại, AI gửi authorize request cho target khi nhận request và
khi worker thực thi; Work context được kiểm lại khi fetch. Work bắt buộc cả
Bearer và service key, nên khi dùng provider Work thật phải đặt
`AI_WORK_SERVICE_AUTH_ENABLED=true` và cấu hình key khớp
`WORK_SERVICE_KEYS.ai`. Nếu cờ `false`, AI không gửi service key và Work từ
chối request. Nhánh fetch GitHub không gọi thêm Work từ AI:
Integration sở hữu quyết định quyền GitHub hiện hành. Đó không phải bỏ bước
authorize request AI. Work phải từ chối dùng AI key cho caller Integration.

## Xác thực Identity

Mỗi lần xác thực Bearer, AI tải JWKS trực tiếp từ
`{AI_IDENTITY_BASE_URL}/.well-known/jwks.json`; không dùng PEM, URL JWKS riêng
hoặc cache khóa. AI lọc khóa RSA theo `kty`, `use` mặc định `sig`, `alg` mặc
định `RS256`, lọc `kid` nếu JWT có, rồi yêu cầu đúng một khóa. Claim bắt buộc
là `exp`, `iss`, `aud`, `sub`, `token_type`; `iat` tùy chọn. AI yêu cầu
`sub` là UUID và `token_type=access`, sau đó gọi session-status bằng Bearer và
`AI_IDENTITY_SERVICE_KEY`. Phiên bị thu hồi trả 401; dependency lỗi phát sinh
`503 AUTH_UNAVAILABLE` nội bộ, được error envelope v1 ánh xạ thành
`500 INTERNAL_ERROR` công khai. Source và HTTP fake tests có sẵn; xác minh
runtime Identity/staging/production **Chưa xác minh**. Token/JWKS do
`setup_mock` tạo chỉ dành cho test, không dùng trong runtime.

`config.py` mặc định khai báo đủ ba authorize URL project/task/sprint và 10
context URL Work qua `work-service:8000`. `AI_AUTHORIZATION_URLS` và
`AI_CONTEXT_URLS` chỉ là override tùy chọn, thay toàn bộ map; biến rỗng dùng
mặc định, `{}` là map rỗng tường minh. Task ID không do agent chọn.
Placeholder chỉ `{target_type}`, `{target_id}`. Khi bật GitHub, thêm
project:github_activity URL Integration và key riêng. Staging/production
thiếu mapping hoặc bật mock sẽ bị từ chối lúc nạp Settings. AI mặc định
`AI_WORK_SERVICE_AUTH_ENABLED=false`; khi tích hợp Work thật, phải bật cờ và
cấp key khớp Work vì provider luôn yêu cầu header này. Base URL provider LLM
chấp nhận HTTP hoặc HTTPS ở mọi môi trường; việc endpoint/model cụ thể có hoạt
động và an toàn trong triển khai đích vẫn chưa được xác minh. URL nội bộ domain
dùng cấu hình tĩnh HTTP/HTTPS theo network triển khai hiện có.

HTTP adapter không redirect, có timeout, đọc streaming tối đa 65536 byte,
kiểm tra domain/thời điểm/status và shape lồng nhau theo domain. Project gồm
task/sprint summary; Task gồm dependency UUID; Team chỉ user_id/capacity/workload;
Progress gồm metric/count đã tính theo quy tắc Work. Trường ngoài allowlist
Work bị loại; tên/email/token và URL tùy ý không đi vào prompt. Điều này không
thay thế trách nhiệm provider làm sạch nội dung text. GitHub strict theo
contract Integration, tối đa 20 commit/PR/issue mỗi loại, URL HTTPS GitHub
không query/fragment; malformed/extra field bị từ chối. Xem
[hướng dẫn GitHub](../integration-service/ai-service-integration-guide.md).

Context available/partial phải đúng typed shape; Work partial phải có warning,
Integration partial giữ warning theo contract provider.
Missing không biến thành dữ liệu đầy đủ; stale/unavailable không dùng để
khẳng định trạng thái hiện tại. Context thiết yếu: backlog có target cần
project; decomposition cần task; risk cần progress. Không có target thì không
cấp tool. GitHub tool chỉ cấp cho risk Project khi flag bật và focus rỗng
hoặc có github_activity. Risk Sprint không fetch GitHub; runtime thêm limitation
xác định khi focus cần GitHub. Cờ tắt cũng thêm limitation tương ứng.

## Retention và runtime

[ERD](erd.md#retention-terminal) mô tả migration `0004`, terminal_at và cascade
chỉ trong AI DB. Mặc định xóa terminal cũ hơn 30 ngày, một batch tối đa 500
mỗi giờ; không xóa queued/running. Backfill ưu tiên updated_at, completed_at,
created_at; timestamp JSON sai làm abort. Index tạo thông thường có thể giữ
lock khi bảng lớn, cần maintenance window và kiểm tra dữ liệu/backup trước
phát hành. Chưa nghiệm thu hiệu năng migration hoặc nhịp cleanup production.

Compose root local/staging có `ai-service`, `ai-worker`, `ai-dispatcher`,
`ai-beat`; Compose standalone có api/worker/dispatcher/beat. Một image/cấu hình
cho bốn process. Root `.env` giữ giá trị runtime và secret; mapping chung
`infra/env/ai-service.env` đưa biến thường và placeholder secret vào environment
của mọi process AI qua `env_file`. PostgreSQL standalone dùng riêng
`infra/env/database.env`; mapping không chứa giá trị secret thật.
Mapping AI yêu cầu `AI_DATABASE_URL` và `AI_BROKER_URL` trong `.env` root hoặc
environment process, không tự dựng URL theo stack. `AI_ENVIRONMENT` mặc định
`staging`, `MOCK_TEST` mặc định `false`; `.env` local phải đặt rõ
`AI_ENVIRONMENT=development`; chỉ bật `MOCK_TEST=true` khi dùng fixture.
Khi chạy staging, đặt rõ
`AI_ENVIRONMENT=staging`, `MOCK_TEST=false` cùng URL database/broker staging.
Root local dùng URL trong `.env.example`. `AI_DB_NAME` bootstrap phải khớp tên
database trong `AI_DATABASE_URL`; đổi tên thì cập nhật cả hai. Standalone cần
`POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` cho PostgreSQL riêng; URL
database ứng dụng phải khớp các giá trị này và password cần percent-encode.
Nếu dùng volume cũ, giữ các giá trị đã khởi tạo. Runtime staging chưa được
xác minh.
`AI_WORK_SERVICE_AUTH_ENABLED` được cấp qua mapping chung. Giá trị mặc định code là
`false`, nhưng tích hợp Work thật cần đặt `true` và cấp `AI_WORK_SERVICE_KEY`
cho mọi process AI gọi Work. Khi tắt, AI bỏ header `X-Service-Key`; Work sẽ
từ chối request. Cờ không ảnh hưởng Identity hoặc Integration key.
Beat chỉ lập lịch, worker thực hiện cleanup. Chạy một scheduler cho lịch này
là cấu hình Compose hiện tại, không phải quy tắc singleton worker của baseline.
Nginx giữ URI `/api/ai/v1/...`, chặn internal Identity/Work/Integration;
health/PID/Celery ping không thay thế smoke request thật qua gateway.

## Evaluation và gate phát hành

Từ `apps/ai-service/`, CLI được wiring theo hai chế độ:

```sh
PYTHONPATH=src uv run python -m evaluation --mode deterministic --report-dir evaluation-reports
PYTHONPATH=src uv run python -m evaluation --mode live --report-dir evaluation-reports
```

CI chạy pytest rồi deterministic evaluation cho riêng AI và upload báo cáo.
Golden dataset `phase1-2026-10-21.v1` gồm 30 case (10 mỗi intent) và các nhánh biên/lỗi;
rubric là quy tắc tự động, không phải human judge hoặc bằng chứng chất lượng
trong mọi tình huống. Báo cáo JSON/JUnit ghi phiên bản dataset, prompt SHA-256,
model pin, kết quả rule và thời gian; không lưu Bearer, service key hay context
thô. Deterministic dùng doubles/fake; chỉ live mới gọi gateway/runtime đã cấu
hình. Phải kiểm tra kết quả CLI, không suy ra đã pass từ workflow YAML.

Evaluation đạt khi toàn bộ case đúng schema/context policy/safety, case lỗi có
outcome đúng kỳ vọng 100%; tỷ lệ
case kỳ vọng thành công đạt ít nhất 95%; quality trung bình ít nhất 85/100,
mỗi intent ít nhất 80/100; p95 tối đa 25 giây và mọi case tối đa 30 giây.
Rubric quality chấm nội dung có title/description hoặc reason (20 điểm),
acceptance criteria/evidence (20), căn cứ/rationale/action (30), và độ bao phủ
các từ khóa tham chiếu do đội sản phẩm chốt trong fixture (30). Risk evidence
phải tham chiếu ID có thật trong context staging. Error case chỉ chấm outcome,
không tham gia điểm quality. Đây là kiểm tra tự động theo tham chiếu, không
đo đầy đủ tính đúng đắn/ngữ nghĩa do chuyên gia đánh giá. Model trong báo cáo
là pin cấu hình của runner; cần nghiệm thu riêng model thực tế trên provider.

Live là kiểm tra thủ công tùy chọn. Chạy runner từ `apps/ai-service/` trong
môi trường có thể truy cập gateway staging và đã nhận các biến cần thiết; không
cần lưu chúng trong `.env` trên VPS hoặc thêm vào deploy workflow. Lệnh ghi
báo cáo vào thư mục đã chọn:

```sh
PYTHONPATH=src uv run python -m evaluation --mode live --report-dir evaluation-reports/live
```

Các biến `EVAL_AI_*` và `EVAL_EXPECTED_MODEL` chỉ cần cho lần chạy live này.
`AI_MODEL` là cấu hình model của service và phải khớp giá trị expected:

| Biến | Mục đích |
| --- | --- |
| `EVAL_AI_BASE_URL` | URL gateway staging mà runner truy cập được; không trỏ API AI trực tiếp |
| `EVAL_AI_BEARER` | Token tài khoản kiểm thử có quyền trên target staging; giữ ngoài log/diff |
| `EVAL_AI_PROJECT_ID`, `EVAL_AI_TASK_ID`, `EVAL_AI_SPRINT_ID` | Target fixture staging theo intent |
| `AI_MODEL`, `EVAL_EXPECTED_MODEL` | Model pin của service và giá trị đối chiếu trong live; expected phải bằng AI_MODEL |
| `EVAL_AI_CASE_TARGETS` | JSON map case ID → UUID; bắt buộc ghi đè riêng cho các scenario partial/missing/stale/denied/large/injection và GitHub partial/missing/stale |
| `EVAL_AI_CASE_EXPECTATIONS` | JSON map đủ 30 case → `{scenario, required_terms, evidence_ids}`; case thành công cần ≥2 từ khóa và risk cần ID evidence thật |

Case lỗi không được coi là đã kiểm chứng nếu các fixture quyền/target tương
ứng chưa được provision. Không dùng target sản xuất của người dùng để tạo
fixture lỗi; tài khoản, dữ liệu và credential test tách khỏi runtime thông
thường. Runtime cho phép tối đa 300 giây; gate evaluation riêng vẫn giới hạn
30 giây, không dùng việc tăng deadline runtime để thay bằng chứng provider/model đạt gate.
Ví dụ cấu trúc ghi đè là `{"backlog-denied":"<UUID fixture không có quyền>"}`;
thay placeholder bằng UUID hợp lệ trên staging, không phải giá trị chạy ngay.
Ví dụ expectation một case: `{"risk-project":{"scenario":"available",
"required_terms":["bị chặn","deadline"],"evidence_ids":["<UUID task>"]}}`.
Manifest phải đủ case và khớp `live_overrides` trong dataset. Các lỗi chỉ mock
ép được (`omit_required`, `invalid`, flag GitHub tắt) vẫn chạy deterministic;
bộ live thay chúng bằng available/dependencies để giữ 10 case mỗi intent.
Trước mỗi live case, runner đọc authorization/context thật để xác minh fixture,
status và evidence ID. Không gửi request nếu fixture sai. Candidate staging cần
`AI_GITHUB_CONTEXT_ENABLED=true` để nghiệm thu GitHub; quyết định bật trên
production cần được nghiệm thu riêng. Runner pacing theo `AI_REQUESTS_PER_MINUTE`, thời gian chờ pacing
không tính latency. Mỗi case bị chặn cứng ở 30 giây cả POST và polling.

Nếu evaluation thủ công thất bại, kiểm tra báo cáo JSON/JUnit trong thư mục
được truyền qua `--report-dir`; runner không ghi response/context thô vào báo
cáo. Kết quả này không tự thay đổi trạng thái deploy hoặc rollback. Staging
deploy tiếp tục kiểm tra migration và health gateway theo CI/CD; không yêu cầu
`EVAL_AI_*` và không tải báo cáo live thành artifact phát hành.

## Những phần còn phải nghiệm thu

Nghiệm thu runtime Identity/JWT/key rotation; allow/deny theo user/target với
Work thật; partial/stale/missing với Integration thật; gateway AI POST/GET;
ba intent với model pin; quota/deadline/latency; retention trên volume thật và
khôi phục sau lỗi. Test source, mock transport, PostgreSQL/Redis test và smoke
LLM local cần được báo riêng. Chưa có bằng chứng cho phép kết luận production
hoàn chỉnh hoặc chất lượng model đạt yêu cầu chỉ từ các thay đổi này.
