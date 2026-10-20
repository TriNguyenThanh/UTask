# Integration: hiện trạng và cách kiểm tra

**Trạng thái: Một phần.** Đã đối chiếu source và cấu hình M4 trong worktree
ngày 19/10/2026. Bộ kiểm thử và smoke Docker local đã chạy; ngày 20/10/2026
đã nghiệm thu các ca GitHub dev theo kế hoạch. Staging/production **Chưa xác minh**.

Cập nhật cấu hình và chẩn đoán Docker local ngày 20/10/2026 tại
[checkpoint mới](checkpoint-2026-10-20.md), gồm bằng chứng consent, đọc repo,
refresh thật, vòng đời quyền và trạng thái kết nối lại cuối phiên.

## Bằng chứng source

| Phần | Trạng thái | Bằng chứng |
| --- | --- | --- |
| Account, API, xác thực actor | Đã triển khai trong source | `github_accounts/{models,api,services}.py`, `config/urls.py`; Identity adapter |
| GitHub App user consent | Đã triển khai trong source | `consent.py` dùng exchange qua `GitHubAppClient`, lưu mapping và credential trong transaction |
| Credential bảo vệ | Đã triển khai trong source | `GitHubCredential`; Fernet `MultiFernet`, access/refresh expiration, `rotate_github_credentials` |
| Refresh fencing | Đã triển khai trong source | claim/version/generation; lock được nhả trước HTTP; response cũ bị từ chối/revoke |
| Account unlink | Đã triển khai trong source | revoke local ngay, tăng version, tạo `REVOKE_TOKEN` durable job |
| Installation/repository | Đã triển khai trong source | start/complete, actor/Bearer/nonce/state binding, live provider checks, pagination |
| Webhook | Đã triển khai trong source | raw-body HMAC-SHA256, giới hạn 25 MiB, delivery ID/fingerprint durable; authorization revoke thu hồi local credential đồng bộ |
| Jobs | Đã triển khai trong source | PostgreSQL `GitHubJob`, claim/lease/version, Celery task payload chỉ ID; retry hữu hạn; replay command |
| Runtime/deployment | Một phần | API/worker/Beat local healthy; webhook/job đã xử lý sự kiện GitHub thật; staging/production chưa xác minh |
| GitHub/Identity thật trong phạm vi dev | Đã triển khai, đã nghiệm thu local | Actor qua Identity/gateway, smoke có Bearer và các ca live có bằng chứng riêng trong checkpoint 20/10; không suy ra từ test mock |

## Hành vi và cấu hình

M4 chuyển luồng account consent hiện hành sang GitHub App user authorization:
code exchange trả access/refresh token có hạn, `/user` xác minh identity, cả
cặp token được mã hóa riêng và lưu cùng mapping. `INTEGRATION_GITHUB_APP_ENABLED`
mặc định `false`; các biến M4 là `INTEGRATION_GITHUB_APP_ID`,
`INTEGRATION_GITHUB_APP_SLUG`, `INTEGRATION_GITHUB_WEBHOOK_SECRET`,
`INTEGRATION_CREDENTIAL_KEYS` và các OAuth client/redirect hiện hữu.
Điền giá trị thật trong `.env` root ở local hoặc `.env` server ở staging;
[mẫu cấu hình](../../.env.example) liệt kê các biến cần thiết.
`INTEGRATION_GITHUB_APP_ID` là App ID, `INTEGRATION_GITHUB_APP_SLUG` là phần
cuối URL `https://github.com/apps/<slug>`, còn `INTEGRATION_GITHUB_CLIENT_ID`
và `INTEGRATION_GITHUB_CLIENT_SECRET` lấy từ phần Client ID/client secret
của chính GitHub App đó. App ID khác Client ID. Không ghi secret thật vào source.
Mapping [Integration env](../../infra/env/integration-service.env) truyền
nguyên tên biến `INTEGRATION_GITHUB_*` cho API, migration, worker và Beat ở
cả Compose local/staging. Sau khi đổi `.env`, tạo lại các container liên quan
để nạp cấu hình; chỉ restart không cập nhật biến môi trường.
`INTEGRATION_GITHUB_SETUP_URI` được kiểm tra khi mở luồng cài App: HTTPS hoặc
HTTP loopback, không query/fragment/credential; URL cài App tạo từ slug. Key ring credential là JSON array Fernet; phần
tử đầu tiên mã hóa mới, các phần tử sau giải mã cũ. Key ring phải khác
`INTEGRATION_CONSENT_KEY`. Thứ tự đổi khóa: thêm khóa mới đầu danh sách, chạy
`manage.py rotate_github_credentials`, giữ khóa cũ trong ring cho đến khi
hoàn tất.

Refresh chỉ bắt đầu khi access sắp hết hạn; fencing gồm actor generation,
credential version và claim. Nếu response refresh thất lạc, credential yêu
cầu consent lại vì GitHub có thể đã xoay cặp token. DELETE account xóa token
khỏi credential row và giao token cũ cho revoke job. Webhook
`github_app_authorization` action `revoked` tăng generation, hủy consent chờ
và thu hồi credential local ngay trong lúc lưu delivery.

Webhook khác được xử lý qua inbox bền vững. Beat dispatch mỗi 5 giây; job có
lease 60 giây, tối đa 5 lần thử, backoff; cleanup hằng ngày dọn payload
delivery đã hoàn tất/ignored sau 30 ngày và token revoke quá hạn. Dedupe
fingerprint được giữ. Khi tắt feature, job REVOKE_TOKEN vẫn được xử lý; phải
giữ OAuth client và credential key ring cho tới khi giao việc thu hồi xong. Replay thủ công:
`python manage.py replay_github_job <id>`; chỉ nhận ID, không nhận secret.

Installation setup URL được tạo từ App slug và state. Callback của GitHub App
frontend chuyển `state`, `installation_id`, `setup_action` về POST
`/api/v1/github/installations/complete`; đây không phải OAuth callback
`code/state`. `setup_action=request` lưu phản hồi pending approval, không coi
là installation active. Installation/repository list gọi GitHub live. Kiểm
tra installation khi complete scan tối đa 10 trang × 100, vượt giới hạn thì
trả lỗi khả dụng.

## Bằng chứng kiểm tra

Source tests tồn tại tại `tests/unit/test_github_credentials.py`,
`test_github_app.py`, `test_github_installation_api.py` và
`tests/integration/test_github_credentials.py`,
`test_github_installations.py`, `test_github_consent.py`; chúng dùng mock hoặc
PostgreSQL test, không xác minh GitHub thật. Kết quả M4 ngày 19/10/2026 trên PostgreSQL 16 tạm riêng: **524 passed**,
bao gồm unit, API/contract, persistence và race. Ruff lint/format, Django
system check, migration drift và `git diff --check` đạt. Mười một test hạ tầng
Integration và smoke script đạt.

Image `utask/integration-service:github-app-m4-check` build thành công. Smoke
local bằng image trên database riêng `integration_m4_smoke` và Redis tạm đã
áp dụng migration, kiểm health/401, nhận webhook có chữ ký với 202, Beat giao
job qua Redis, worker đổi metadata thành DELETED/version 2 và delivery lặp
không ghi lại. Smoke không gọi GitHub hoặc Identity thật.

Lượt CI đầu tiên của M4 dừng tại 5 lỗi cấu hình AI có sẵn ở HEAD `27181d7`.
Lượt sửa CI tiếp theo đã khôi phục profile AI local và tách giá trị local khỏi
fixture staging: **107 test hạ tầng đạt**, kiểm tra Compose local/staging,
script PostgreSQL và Nginx đạt. Cổng PostgreSQL test Integration được khai
báo rõ là `5432` trong metadata CI, không dùng mặc định local `55443`.
Lượt CI local tiếp theo dùng virtualenv ngoài repo và PostgreSQL/Redis tạm:
AI **293**, Classroom **455**, Identity **304**, Integration **524**, Work
**737** test đạt; lint/format và Django check/migration drift đều đạt.
Frontend lint/typecheck đạt; build chạy riêng đạt. CI toàn repo chưa xanh:
lượt test frontend có 3 ca thất bại ở KanbanBoard/TeacherSetup/TeacherWorkspace;
chạy lại 3 file thì 2 file đạt, TeacherWorkspace còn lỗi điều hướng/Breadcrumb.
Chạy riêng TeacherWorkspace tiếp theo: **28 passed**. Các ca frontend đều có
lượt retry đạt, nhưng suite chung chưa ổn định; chưa kết luận nguyên nhân.
Không có thay đổi source frontend trong đợt sửa CI này. Không dùng kết quả
lịch sử M3 làm bằng chứng M4.

Compose root/staging có `integration-migrate` làm dependency thành công trước
API, worker và Beat; worker và Beat phụ thuộc PostgreSQL/Redis healthy. Đây là
cấu hình source, chưa chứng minh staging đã chạy. Hướng dẫn khung tại
[README Integration](README.md); không dùng database runtime khi chạy test.

## Giới hạn

Không có thay đổi Work, Identity, AI, UI, Kafka, GitHub App private key hoặc
domain sync trong M4. Provider Work/AI được bổ sung sau M4 trong cùng nhánh;
chi tiết source, cấu hình và phạm vi kiểm thử ở
[vận hành provider](runtime-connections.md). Phía Work/AI vẫn cần triển khai
adapter/dispatcher/consumer theo guide và nghiệm thu tích hợp thật.


## Smoke GitHub thật (chạy riêng)

[Runbook nghiệm thu](live-acceptance.md) là nguồn chuẩn cho Reqable, biến môi
trường/cách chạy smoke, kiểm repo kỳ vọng qua phân trang, refresh có kiểm
soát và các ca uninstall/revoke/phục hồi. Script chỉ GET, không theo redirect
mang Bearer và không ép refresh/revoke/uninstall; GET có thể refresh tự nhiên
theo backend. Kết quả GitHub dev ngày 20/10/2026 nằm tại
[checkpoint](checkpoint-2026-10-20.md); không suy ra từ test mock hoặc smoke
Docker local ở trên, không khẳng định staging/production đã đạt.


## Phân tích ảnh hưởng cuối thay đổi

GitNexus đã rebuild toàn graph. `detect_changes --scope all --limit 1000`
chạy với index Git tạm để bao gồm file mới, không stage vào index của người
dùng: 59 file; risk **CRITICAL**. Lượt rebuild ghi nhận 381 symbol/46 flow;
lượt incremental sau đó trả 224 symbol/561 flow, nên không coi số liệu graph
là bằng chứng nhất quán hoặc xác nhận thay đổi an toàn. Các luồng
ảnh hưởng gồm consent, credential refresh, account unlink, installation và
provider. Đã review source và kiểm thử hồi quy cho các luồng này; graph vẫn
có giới hạn phân giải và cắt bớt luồng trong quá trình index, không phải bằng
chứng bao phủ toàn hệ thống. Không commit hoặc deploy trong thay đổi này.
