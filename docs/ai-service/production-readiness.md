# Điều kiện phát hành AI Service

**Trạng thái: Một phần.** Source/test của adapter context, tool scope, retention
và wiring phát hành đã có; không đồng nghĩa hệ thống đã chạy E2E với Work,
Integration và LLM production. Provider Work dưới đây **Chưa triển khai**.
Smoke LLM local ngày 15/10/2026 dùng context/quyền fixture, xem
[checkpoint](checkpoint.md). Nguồn vị trí source là [code map](code-map.md).

## Boundary domain và quyền

[Work AI context v1](../../contracts/api/work-ai-context-v1.yaml) được
[Work contract](../../contracts/api/work-service.yaml) tham chiếu và đánh dấu
`planned`. Đội Work cần triển khai provider trước khi cấu hình đó dùng được
trên staging. Không đọc database Work hoặc tự tạo endpoint thay thế.
Chi tiết công việc, mapping và kiểm thử dành cho đội Work nằm trong
[hướng dẫn triển khai provider Work](../project-service/ai-service-integration-guide.md).

| Lời gọi | Credential và shape |
| --- | --- |
| AI → Work POST `/api/v1/internal/ai/targets/{target_type}/{target_id}/authorize` | Bearer actor + `AI_WORK_SERVICE_KEY` trong `X-Service-Key`; body `{action: "ai.analyze", intent}`; response envelope `success/data` chứa đúng target_type, target_id, action và allowed boolean |
| AI → Work GET `/api/v1/internal/ai/targets/{target_type}/{target_id}/contexts/{domain}` | Bearer actor + key AI → Work; `ContextDocument` trực tiếp, không envelope Work; Work tự resolve Project và tự kiểm quyền tại mỗi lần đọc |
| AI → Integration GET `/api/v1/internal/projects/{project_id}/github/context` | Bearer actor + `AI_INTEGRATION_SERVICE_KEY`; Integration kiểm mapping/consent và gọi Work authorize `github.read` bằng key Integration → Work |

AI kiểm quyền target lúc nhận request và khi worker thực thi; Work context
được kiểm lại khi fetch. Nhánh fetch GitHub không gọi thêm Work từ AI:
Integration sở hữu quyết định quyền GitHub hiện hành. Đó không phải bỏ bước
authorize request AI. Work phải từ chối dùng AI key cho caller Integration.

`AI_AUTHORIZATION_URLS` cần ba key project/task/sprint. `AI_CONTEXT_URLS` cần
project/team/progress cho mỗi target, thêm task:task; task ID không do agent
chọn. Placeholder chỉ `{target_type}`, `{target_id}`. Khi bật GitHub, thêm
project:github_activity URL Integration và key riêng. Staging/production
thiếu Work key/mapping hoặc bật mock sẽ bị từ chối lúc nạp Settings. Base URL
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

Gate yêu cầu toàn bộ case đúng schema/context policy/safety, case lỗi có
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

Live cần cấu hình trong `.env` server staging:

| Biến | Mục đích |
| --- | --- |
| `EVAL_AI_BASE_URL` | Gateway mà runner truy cập, ví dụ `http://nginx`; không trỏ API AI trực tiếp |
| `EVAL_AI_BEARER` | Token tài khoản kiểm thử có quyền trên target staging; giữ ngoài log/diff |
| `EVAL_AI_PROJECT_ID`, `EVAL_AI_TASK_ID`, `EVAL_AI_SPRINT_ID` | Target fixture staging theo intent |
| `AI_MODEL`, `EVAL_EXPECTED_MODEL` | Model pin bắt buộc trong live; expected phải bằng AI_MODEL |
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
`AI_GITHUB_CONTEXT_ENABLED=true` để nghiệm thu GitHub; production chỉ bật sau
khi gate đạt. Runner pacing theo `AI_REQUESTS_PER_MINUTE`, thời gian chờ pacing
không tính latency. Mỗi case bị chặn cứng ở 30 giây cả POST và polling.

Khi service được chọn phát hành có AI, script deploy chạy gate live sau
rollout/migration/gateway checks bằng one-shot AI image qua Compose. Credential
đọc whitelist từ `.env` server, truyền tên biến environment, không nằm trong
tham số giá trị của SSH/Docker. Thiếu cấu hình hoặc gate lỗi làm release lỗi;
không có bỏ qua gate cho release bật AI. Service không bật AI giữ luồng cũ.
Báo cáo persist ở `ai-evaluation-reports/<image_tag>` trên host staging và
workflow tải JSON/JUnit thành artifact `ai-evaluation-live-<source_sha>`, kể
cả khi gate thất bại. Báo cáo không chứa response/context thô.
Gate hiện sau rollout và không tự rollback; lỗi gate cần xử lý vận hành theo
quy trình phát hành hiện hành, không tự suy ra quyền deploy/rollback.

## Những phần còn phải nghiệm thu

Work provider và fixture staging; JWT Identity/rotation key; allow/deny theo
user/target; partial/stale/missing với Integration thật; gateway AI POST/GET;
ba intent với model pin; quota/deadline/latency; retention trên volume thật và
khôi phục sau lỗi. Test source, mock transport, PostgreSQL/Redis test và smoke
LLM local cần được báo riêng. Chưa có bằng chứng cho phép kết luận production
hoàn chỉnh hoặc chất lượng model đạt yêu cầu chỉ từ các thay đổi này.
