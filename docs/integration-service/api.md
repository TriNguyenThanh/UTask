# API Integration Service

**Trạng thái: Thiết kế mục tiêu, bản đề xuất ngày 15/10/2026.** Chưa có server
Integration, OpenAPI hoặc endpoint được nghiệm thu. Tài liệu này mô tả API
cần xây dựng; riêng OAuth exchange đã có client Identity làm bằng chứng kỳ vọng.
Các URL, status và payload còn lại là đề xuất để review trước triển khai,
không phải hợp đồng máy đọc được đã chốt trong `contracts/`.

Nguồn: [phạm vi service](README.md), [sơ đồ](../diagram/integration-service/README.md),
[giao tiếp hệ thống](../system/communication.md),
[client OAuth Identity](../../apps/identity-service/authentication/adapters/github_identity_proof.py),
[adapter Work](../../apps/work-service/infrastructure/integration.py).

[Phạm vi và quyền truy cập](scope-access.md) là nguồn chuẩn cho ma trận
caller/action/target, quyền GitHub và thu hồi quyền. API dưới đây diễn giải
chính sách đó; tất cả vẫn là thiết kế mục tiêu.

## 1. URL, xác thực và quyền

Các path bên dưới tính từ **root server Integration**, phân biệt ba nhóm:

| Nhóm | Cách gọi mục tiêu | Kiểm tra quyền |
| --- | --- | --- |
| Người dùng `/api/v1/github/*` | JWT do Identity cấp; callback dùng state gắn phiên | Leader ACTIVE được Work cho phép cấu hình Project; chỉ cài App, xem danh sách theo quyền GitHub của user và đọc job có scope; không trực tiếp đổi kết nối Project |
| Nội bộ `/api/v1/internal/*` | Service credential theo caller allowlist; Work/AI có thêm ngữ cảnh user đã xác thực | Service key không thay quyền của user; xác minh phạm vi với Work qua REST khi cần |
| GitHub `/api/v1/webhooks/github` và callback installation | Webhook dùng chữ ký; callback dùng state ràng buộc phiên | Webhook không dùng JWT; installation ID trên callback không đủ chứng minh quyền |

**Hiện trạng gateway:** [Nginx](../../infra/nginx/nginx.conf) bỏ prefix
`/api/integrations/`. Ví dụ URL công khai đề xuất
`/api/integrations/api/v1/github/repositories` được chuyển thành
`/api/v1/github/repositories`. Internal API chỉ dành mạng backend: cần chặn
`/api/integrations/api/v1/internal` và toàn bộ route con tại gateway trước
khi triển khai; cấu hình hiện chưa có chặn riêng Integration. Tài liệu này
không thay cấu hình Nginx.

Chỉ `X-Service-Key` của OAuth exchange có bằng chứng phía client. Tên header,
quy tắc xoay key và cách chuyển ngữ cảnh user cho các API nội bộ khác cần chốt;
không tin `user_id` hoặc `project_id` chỉ vì caller gửi lên. Không nhận URL
GitHub tùy ý để server truy cập; nhận định danh repository/ref và dùng adapter.

Work là caller duy nhất được chọn/đổi/ngắt kết nối Project, theo yêu cầu leader
ACTIVE và Project có thể ghi. AI chỉ đọc context; Identity chỉ exchange OAuth.
Mỗi service có allowlist riêng. Quyền đọc project có thể chia sẻ metadata cho
member/giảng viên đúng phạm vi Work cho phép, không cấp quyền liệt kê mọi repo
của App. SYSTEM_ADMIN không mặc nhiên bỏ qua quyền tài nguyên. Integration
chưa được allowlist gọi session-status Identity; cần chốt kiểm JWT/phiên và
quyền Work trước khi mở public API.

## 2. Quy ước đề xuất

- JSON UTF-8; ID GitHub là chuỗi, ID UTask là UUID, thời gian có múi giờ theo
  RFC 3339. Không trả installation token, OAuth code, verifier hoặc secret.
- Response thành công dùng `{ "success": true, "data": ... }`. OAuth exchange
  phải giữ envelope này để tương thích client Identity hiện tại.
- Các API lệnh dùng `operation_id` để chống lặp: cùng caller, loại lệnh,
  project và operation với cùng payload trả lại kết quả; khác payload trả
  `409 OPERATION_CONFLICT`. Không dùng mỗi operation ID làm khóa toàn cục.
  Thời hạn giữ kết quả chống lặp cần chốt trước triển khai.
- Danh sách dùng `limit` (đề xuất mặc định 20, tối đa 100), `cursor` mờ;
  trả `data.items` và `data.next_cursor`. Cursor phải gắn với bộ lọc/phạm vi
  quyền, không dùng cursor để vượt quyền hoặc đọc project khác.
- Chỉ trả `202` khi yêu cầu đã lưu bền vững và có cơ chế hoàn tất/phục hồi.
  Redis không thay bản ghi job; đọc job qua API trạng thái khi có `202`.
- `generation` phân biệt mỗi lần thay kết nối; `source_version` tăng trong
  một generation. Không áp dụng dữ liệu cũ lên generation mới. Đây là quy tắc
  đề xuất để adapter Work ánh xạ, chưa phải schema event cuối cùng.

Ví dụ lỗi đề xuất; mã lỗi này thuộc Integration, không mặc nhiên trùng Work:

```json
{
  "success": false,
  "error": {"code": "REPOSITORY_ACCESS_DENIED", "message": "Không có quyền truy cập repository."}
}
```

| HTTP | Ý nghĩa mục tiêu |
| --- | --- |
| 400 | Payload, bộ lọc, state hoặc định danh không hợp lệ |
| 401 / 403 | Thiếu/sai credential hoặc không đủ quyền |
| 404 | Tài nguyên không tồn tại trong phạm vi caller được phép đọc |
| 409 | Xung đột operation, generation hoặc kết quả cùng phiên bản |
| 413 | Body vượt giới hạn cấu hình |
| 429 | Giới hạn request của Integration; có `Retry-After` khi xác định được |
| 503 | GitHub, nguồn phân quyền hoặc DB không khả dụng; không trả kết quả xác minh giả |

Giới hạn body, rate limit, timeout và chính sách che sự tồn tại tài nguyên
cần thống nhất theo từng API. OAuth client hiện coi lỗi HTTP hoặc proof không
hợp lệ là `OAUTH_PROVIDER_UNAVAILABLE` phía Identity.

## 3. Danh mục endpoint đề xuất

| Method và path tại Integration | Caller | Mục đích | Thành công |
| --- | --- | --- | --- |
| POST `/api/v1/github/installations/start` | Leader ACTIVE, được Work cho phép | Tạo phiên cài App gắn user/project và state | 200: URL cài đặt |
| GET `/api/v1/github/installations/callback` | Browser sau GitHub | Kiểm tra state và quyền, ghi nhận installation | 303 về trang cấu hình cho phép |
| GET `/api/v1/github/installations` | Leader ACTIVE trong phiên cấu hình | Installation của chính GitHub user đã xác minh | 200: danh sách |
| GET `/api/v1/github/repositories` | Leader ACTIVE trong phiên cấu hình | Repository giao giữa quyền user và App | 200: danh sách |
| GET `/api/v1/github/sync-jobs/{job_id}` | Leader còn quyền Project | Đọc job; kiểm lại quyền lúc đọc | 200: job |
| GET `/api/v1/internal/sync-jobs/{job_id}` | Work có actor/scope phù hợp | Đọc trạng thái job cho luồng cấu hình Project | 200: job |
| POST `/api/v1/internal/projects/{project_id}/repository-selection` | Work | Chọn repository hoặc xác nhận trạng thái kết nối | 200 hoặc 202: connection + job khi chờ |
| GET `/api/v1/internal/projects/{project_id}/connection` | Work | Đọc kết nối hiện tại để reconcile/poll sau 202 | 200: connection |
| POST `/api/v1/internal/projects/{project_id}/repository-disconnection` | Work | Ngắt liên kết project, không gỡ App khỏi GitHub | 200: connection |
| POST `/api/v1/internal/projects/{project_id}/references/verify` | Work | Xác minh branch/commit/PR | 200: reference |
| POST `/api/v1/internal/repositories/{repo_id}/sync-jobs` | Work, theo yêu cầu leader ACTIVE | Lưu yêu cầu đồng bộ nền | 202: job |
| POST `/api/v1/internal/oauth/github/exchange` | Identity | Đổi OAuth code và trả proof danh tính | 200: proof; có kỳ vọng client |
| GET `/api/v1/internal/context/projects/{project_id}/github-activity` | AI | Hoạt động chuẩn hóa theo project và khoảng thời gian | 200: context |
| POST `/api/v1/webhooks/github` | GitHub | Nhận delivery có chữ ký, lưu để xử lý | 202 hoặc 200 khi trùng/không cần xử lý |

Không cung cấp endpoint sửa Task hoặc tính tiến độ trong Integration.
Hành vi gỡ/suspend installation bắt nguồn từ GitHub; thao tác ngắt project
chỉ thay liên kết do Integration quản lý và phản hồi cho Work.

## 4. Cài App và đọc repository

**Đề xuất:** `POST installations/start` nhận `project_id`. Sau khi Work xác
nhận leader ACTIVE, Project ghi được và phiên user hợp lệ,
server tạo state ngẫu nhiên, có hạn và dùng một lần, gắn user/project; trả
`installation_url` và `expires_at`. Không nhận redirect URL tùy ý từ client.

Callback nhận `installation_id`, `state` và tham số hành động do GitHub gửi;
kiểm state/phiên và quyền Work còn hiệu lực, xác minh installation/quyền
repository qua GitHub. Chỉ ghi nhận installation và kết quả phiên cài đặt;
không tạo/đổi ProjectConnection. State sai/hết hạn trả 400, quyền bị từ chối trả
403. Redirect chỉ đến allowlist frontend và không đưa token lên query string. Callback này
khác callback OAuth do Identity sở hữu. Theo
[GitHub setup URL](https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/about-the-setup-url),
GitHub gửi installation ID trong redirect; Integration vẫn phải xác minh quyền.

`GET installations` và `GET repositories` cần phiên cấu hình gắn Project,
actor và quyền Work; tên tham số phiên cần chốt cùng contract.
`GET repositories` nhận thêm `installation_id`, `cursor`, `limit`. Mỗi item đề xuất
có `github_repo_id`, `owner`, `name`, `default_branch`, `installation_id` và
`accessible`. Chỉ liệt kê giao giữa quyền App và chính GitHub user đã được
Identity xác minh. Mapping danh tính không thay credential chứng minh quyền
GitHub; chưa có cơ chế này thì đóng API, không dùng App token toàn cục.
Phân trang này không thay API phân trang của GitHub.

## 5. Kết nối project và xác minh reference

### Chọn repository

Đề xuất body `POST repository-selection`:

```json
{
  "github_repo_id": "123456",
  "operation_id": "select-repository-01",
  "expected_connection_generation": 0
}
```

Browser gửi yêu cầu chọn repo tới Work. Work kiểm leader ACTIVE trước/sau
lời gọi adapter; Integration nhận danh tính Work cùng actor đã xác thực, kiểm
action/project qua Work và quyền GitHub hiện hành của user/App độc lập.
Không giữ transaction/lock xuyên lời gọi HTTP tới Work/GitHub.
Xung đột generation trả 409; repository không được cấp quyền trả 403/404 theo
chính sách che dữ liệu. Response `data.connection` đề xuất:

```json
{
  "project_id": "11111111-1111-4111-8111-111111111111",
  "operation_id": "select-repository-01",
  "generation": 1,
  "source_version": 1,
  "status": "CONNECTED",
  "repo_id": "123456",
  "repo_owner": "utask-team",
  "repo_name": "demo",
  "default_branch": "main",
  "synced_at": "2026-10-15T03:00:00Z"
}
```

Adapter Work cần ánh xạ `data.connection` sang `ConnectionFact`; không truyền
thẳng JSON thành dữ liệu tin cậy. Khi `PENDING`, trả thêm `data.job_id`;
Work có thể đọc connection để reconcile. `GET connection` trả cùng cấu trúc;
chưa từng kết nối trả 404. `DISCONNECTED` giữ generation/version để loại dữ liệu
cũ; metadata repository có thể null.

Ngắt kết nối chỉ nhận Work command của leader có quyền; không bắt buộc còn
quyền GitHub để xóa liên kết kỹ thuật đã tồn tại. Nhận
`operation_id`, `expected_connection_generation`, trả
connection với `DISCONNECTED`; tăng generation khi thay thế/ngắt kết nối.
Job cũ không được khôi phục kết nối đã ngắt. Work chịu trách nhiệm vô hiệu
hóa/đối chiếu các liên kết Task theo kết quả này. Work chưa có route ngắt kết
nối riêng; cần bổ sung contract/implementation Work trước khi mở luồng này.

### Xác minh reference

Đề xuất request `POST references/verify`:

```json
{
  "repo_id": "123456",
  "generation": 1,
  "link_type": "PULL_REQUEST",
  "github_ref_id": "24"
}
```

Chỉ nhận `BRANCH`, `COMMIT`, `PULL_REQUEST` để phù hợp adapter Work hiện tại;
Issue cần mở rộng adapter/contract trước. Trả `data.reference` gồm
`project_id`, `repo_id`, `generation`, `source_version`, `link_type`, `ref_id`,
`title`, `status`, `url`, `is_verified`, `synced_at` để adapter tạo
`ReferenceFact`. PR dùng số nguyên dương dạng chuỗi chuẩn; branch/commit trả
ref đã chuẩn hóa. `status` của PR là `OPEN`, `MERGED`, `CLOSED`; loại khác null.
URL khi có phải là HTTPS GitHub hợp lệ. Chỉ trả `is_verified: true` sau xác minh;
lỗi quyền, ref không tồn tại hoặc nguồn lỗi phải trả lỗi tương ứng.

API không nhận `task_id` để tạo link; Work sở hữu xác nhận và lưu `TaskGitHubLink`.

## 6. Đồng bộ nền

Đề xuất request `POST .../sync-jobs`: `operation_id`, `project_id`, `generation`
và `resources` trong `repository`, `branches`, `commits`, `issues`, `pull_requests`.
Chỉ Work được gọi sau kiểm quyền leader; AI/Identity không được tạo job.
Kiểm repository thuộc kết nối/generation đang được cấp quyền. Transaction lưu
job và ý định giao job trước khi trả `202` với `job_id`, `status`, `created_at`.

`GET sync-jobs/{job_id}` trả `job_id`, `repo_id`, `project_id`, `generation`,
`status`, `created_at`, `updated_at`, `finished_at`, `error_code`,
`next_retry_at`. Trạng thái đề xuất: `QUEUED`, `RUNNING`, `RETRY_WAIT`,
`SUCCEEDED`, `FAILED`, `CANCELLED`; API public chỉ leader còn quyền Project,
API backend chỉ Work có scope được đọc. Caller tạo job không giữ quyền đọc
vĩnh viễn khi actor rời Project hoặc quyền đã bị thu hồi.
Không trả payload thô hoặc credential trong thông tin lỗi. Retry không làm
nhân đôi dữ liệu/outbox; job generation cũ bị hủy hoặc bỏ kết quả. Job theo
lịch/webhook do worker Integration tạo nội bộ, không dùng user giả; kiểm lại
quyền installation và generation khi chạy.

## 7. OAuth exchange: kỳ vọng đã có ở Identity

`POST /api/v1/internal/oauth/github/exchange`, header
`X-Service-Key: <Identity caller key>`, timeout phía client hiện là 5 giây.
Body đã được [client Identity](../../apps/identity-service/authentication/adapters/github_identity_proof.py)
tạo:

```json
{
  "operation_id": "22222222-2222-4222-8222-222222222222",
  "user_id": "11111111-1111-4111-8111-111111111111",
  "provider": "GITHUB",
  "code": "<authorization-code>",
  "code_verifier": "<pkce-verifier>",
  "redirect_uri": "https://utask.example/oauth/github/callback",
  "expires_at": "2026-10-15T03:10:00Z"
}
```

Response thành công phải tương thích kỳ vọng client:

```json
{
  "success": true,
  "data": {
    "operation_id": "22222222-2222-4222-8222-222222222222",
    "user_id": "11111111-1111-4111-8111-111111111111",
    "provider": "GITHUB",
    "github_user_id": "12345",
    "github_username": "student-dev",
    "verified_at": "2026-10-15T03:00:00Z",
    "expires_at": "2026-10-15T03:10:00Z"
  }
}
```

Client kiểm operation/user/provider và `expires_at` khớp chính xác request;
expiry còn hiệu lực; `verified_at` không quá hiện tại 30 giây và không sớm hơn
expiry 600 giây; GitHub user ID là chuỗi số ASCII tối đa 100 ký tự, username
phù hợp regex GitHub trong client. Đây là kiểm tra client, server vẫn phải
kiểm credential, hạn request, allowlist redirect URI và trao đổi code với GitHub.
Không trả proof chỉ dựa trên user ID do request cung cấp.

Proof truyền qua kênh backend đã xác thực, chưa có thiết kế proof ký để dùng
ngoài kênh này. Chính sách retry/replay phải chốt với Identity: client hiện tạo
operation ID mới mỗi lần gọi, OAuth code không được đổi lại tùy ý. Không log
hoặc lưu raw code/verifier trong webhook, outbox hay bảng nghiệp vụ.

## 8. Context GitHub cho AI

**Đề xuất:** chỉ caller AI được allowlist đọc context, có actor và quyết định
quyền Project/use case AI từ Work. GET nhận `from`, `to` (RFC 3339), `cursor`, `limit`;
phạm vi project đã được cấp quyền, không chỉ kiểm service key. Giai đoạn đầu
chỉ target project; task/sprint cần Work phân giải phạm vi trước, không tự
suy ra từ ID và không đọc DB Work.

Response `data` đề xuất: `domain: "github_activity"`, `as_of`, `status`,
`source_version`, `warning`, `data: {project_id, items, next_cursor}`. Mỗi item
chỉ có metadata GitHub cần cho phân tích (repo, loại ref, định danh, thời gian,
trạng thái và actor khi được phép). Adapter AI phải ánh xạ sang
[ContextDocument](../../apps/ai-service/src/models/context.py); response này
chưa có server để cung cấp.

Không đủ quyền trả 403. Chưa đồng bộ/nguồn cũ trả trạng thái
`missing`, `partial` hoặc `stale` với `as_of`/warning trung thực, không biến
thiếu dữ liệu thành kết luận không có đóng góp. Cửa sổ tối đa, ngưỡng freshness,
quy tắc actor và cách client đi hết các trang cần chốt trước tích hợp AI.

## 9. Webhook GitHub

**Đề xuất:** POST `/api/v1/webhooks/github` nhận raw body và các header
`X-Hub-Signature-256`, `X-GitHub-Delivery`, `X-GitHub-Event`. Xác minh HMAC-SHA256
trên đúng raw body bằng webhook secret, so sánh constant-time trước xử lý;
không tính chữ ký trên JSON đã serialize lại. Tham chiếu
[GitHub xác minh delivery](https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries).

- Sai/thiếu chữ ký trả 401; body lỗi trả 400/413, không tạo thay đổi nghiệp vụ.
- Delivery hợp lệ được ghi nhận bền vững, chống lặp theo App + delivery ID và
  kiểm nội dung khi ID trùng; trả 202 với `delivery_id`, `status: "ACCEPTED"`.
- Delivery trùng đã nhận trả 200, không sinh job/event lặp; cùng ID khác body
  hợp lệ trả 409 và ghi nhận lỗi vận hành. Worker có retry riêng nếu xử lý lỗi.
- Event hợp lệ chưa hỗ trợ trả 200 với `status: "IGNORED"`; không phát event
  nghiệp vụ giả. DB lỗi trước khi lưu bền vững trả 503.
- Worker xử lý installation/repository, push, issues và pull request theo
  bộ event sẽ chốt; lưu dữ liệu chuẩn hóa + outbox trong transaction rồi
  publisher phát Kafka. Không chờ Kafka để trả webhook thành công.

Mục tiêu phản hồi sớm theo
[GitHub webhook best practices](https://docs.github.com/en/webhooks/using-webhooks/best-practices-for-using-webhooks),
không giữ request để chạy full sync. Payload thô nếu cần lưu phải có retention
và lọc dữ liệu nhạy cảm; hash body phục vụ chống lặp không thay chữ ký.

## 10. Điều kiện trước triển khai

Chốt URL/payload/auth và ánh xạ adapter cùng Identity/Work/AI; quy tắc installation
và repository access; trạng thái kết nối/job, idempotency/retention, pagination,
timeout/rate limit; event contract và version. Sau đó mới xuất OpenAPI từ API
đã thống nhất và thêm vào `contracts/api/`, không dùng tài liệu đề xuất này làm
bằng chứng endpoint đang chạy.

Kiểm thử tối thiểu: thành công và lỗi quyền từng API; generation/operation xung
đột; proof binding/expiry/replay; webhook signature/duplicate/rollback; retry
job/publisher; context stale/missing và phân trang không rò dữ liệu; kiểm thử
xuyên service trước khi nghiệm thu. Xem [tiêu chí chung](README.md#tiêu-chí-kiểm-thử-khi-triển-khai).
