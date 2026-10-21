# Điều kiện phát hành AI Service

**Trạng thái: Một phần.** Source/test của adapter context, tool scope, retention
và wiring phát hành đã có; không đồng nghĩa hệ thống đã chạy E2E với Work,
Integration và LLM production. AI-side Work client có source; Work provider
theo contract dưới đây **Chưa triển khai**.
Smoke LLM local ngày 15/10/2026 dùng context/quyền fixture, xem
[checkpoint](checkpoint.md). Nguồn vị trí source là [code map](code-map.md).

## Boundary domain và quyền

[Work AI context v1](../../contracts/api/work-ai-context-v1.yaml) được
[Work contract](../../contracts/api/work-service.yaml) tham chiếu và đánh dấu
`planned`. Đội Work cần triển khai provider trước khi contract dùng được trên
staging. AI-side client không chứng minh endpoint Work đã tồn tại. Không đọc
database Work hoặc tự tạo endpoint thay thế.
Chi tiết công việc, mapping và kiểm thử dành cho đội Work nằm trong
[hướng dẫn triển khai provider Work](../project-service/ai-service-integration-guide.md).

| Lời gọi | Credential và shape |
| --- | --- |
| Contract AI → Work POST `/api/v1/internal/ai/targets/{target_type}/{target_id}/authorize` (`planned`) | AI client gửi Bearer actor + body `{action: "ai.analyze", intent}`; chỉ gửi `X-Service-Key` khi `AI_WORK_SERVICE_AUTH_ENABLED=true`, khi đó cần `AI_WORK_SERVICE_KEY`; response contract `success/data` có target_type, target_id, action và allowed boolean |
| Contract AI → Work GET `/api/v1/internal/ai/targets/{target_type}/{target_id}/contexts/{domain}` (`planned`) | AI client gửi Bearer actor; key AI → Work chỉ khi cờ bật; `ContextDocument` trực tiếp theo contract. Chưa có Work provider source để xác minh kiểm quyền runtime |
| AI → Integration GET `/api/v1/internal/projects/{project_id}/github/context` | Bearer actor + `AI_INTEGRATION_SERVICE_KEY`; Integration kiểm mapping/consent và gọi Work authorize `github.read` bằng key Integration → Work |

Theo luồng đã chốt, AI gửi authorize request cho target khi nhận request và
khi worker thực thi; Work context được kiểm lại khi fetch. Hiện provider Work
chưa có source nên các bước này **Chưa triển khai** phía Work, không xác nhận
role authorization runtime. `AI_WORK_SERVICE_AUTH_ENABLED=false` tạm thời chỉ
bỏ header Work `X-Service-Key`; Bearer và authorize body vẫn được gửi. Bật cờ
thì cần Work key. Nhánh fetch GitHub không gọi thêm Work từ AI:
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

`AI_AUTHORIZATION_URLS` cần ba key project/task/sprint. `AI_CONTEXT_URLS` cần
project/team/progress cho mỗi target, thêm task:task; task ID không do agent
chọn. Placeholder chỉ `{target_type}`, `{target_id}`. Khi bật GitHub, thêm
project:github_activity URL Integration và key riêng. Staging/production
thiếu mapping hoặc bật mock sẽ bị từ chối lúc nạp Settings. Work key chỉ cần
khi `AI_WORK_SERVICE_AUTH_ENABLED=true`; cờ mặc định `false`. Base URL
provider LLM phải HTTPS ngoài development/test; URL nội bộ domain dùng cấu
hình tĩnh HTTP/HTTPS theo network triển khai hiện có.

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
cho bốn process; secret inject environment, không đặt vào env_file thường.
Compose truyền `AI_WORK_SERVICE_AUTH_ENABLED`; mặc định tắt service key Work.
Khi bật, phải cấp `AI_WORK_SERVICE_KEY` cho mọi process cần gọi Work. Khi tắt,
chỉ header Work `X-Service-Key` bị bỏ; Bearer actor và yêu cầu authorize
target/intent vẫn được gửi. Cờ không ảnh hưởng Identity hoặc Integration key.
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
thường. Không tăng deadline 30 giây để che lỗi provider/model.
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

Work provider (contract còn planned) và fixture staging; JWT Identity/rotation
key; allow/deny theo user/target; partial/stale/missing với Integration thật; gateway AI POST/GET;
ba intent với model pin; quota/deadline/latency; retention trên volume thật và
khôi phục sau lỗi. Test source, mock transport, PostgreSQL/Redis test và smoke
LLM local cần được báo riêng. Chưa có bằng chứng cho phép kết luận production
hoàn chỉnh hoặc chất lượng model đạt yêu cầu chỉ từ các thay đổi này.
