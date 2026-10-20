# API Integration Service

**Trạng thái: Đã triển khai trong source.** Các ca GitHub dev theo kế hoạch
đã nghiệm thu local; bằng chứng tại [checkpoint 20/10/2026](checkpoint-2026-10-20.md).
Runtime production chưa xác minh. Contract máy đọc được ở
[OpenAPI 1.4.0](../../contracts/api/integration-service-v1.yaml). Path tính từ root server,
chưa gồm prefix gateway. Response thành công dùng `{success:true,data:...}`;
riêng AI context trả trực tiếp `ContextDocument` để tương thích AI adapter.

## Account và consent

| Method và path | Trạng thái | Hành vi |
| --- | --- | --- |
| GET/HEAD `/healthz` | Đã triển khai | Health database |
| GET `/api/v1/github/account` | Đã triển khai trong source | Account actor hiện tại; không query/body |
| DELETE `/api/v1/github/account` | Đã triển khai trong source | Thu hồi mapping/credential, hủy consent; giao revoke token thành job |
| POST `/api/v1/github/authorizations/start` | Đã triển khai trong source | Mở consent GitHub App hiện hành, trả `authorization_url`, `expires_at`, đặt nonce cookie |
| POST `/api/v1/github/authorizations/complete` | Đã triển khai trong source | Nhận đúng `code`, `state`; xác minh và lưu credential mã hóa |

Account trả `user_id`, `status`, `authorization_status`, `github_user_id`,
`github_username`, `verified_at`, `linked_at`, `revoked_at`, `source_version`.
Trạng thái authorization: `NOT_AUTHORIZED`, `ACTIVE`, `REAUTH_REQUIRED`,
`REVOKED`. Khi account chưa link, các trường GitHub và thời điểm xác minh là
null; `status=UNLINKED`, `source_version=0`. Khi account bị thu hồi, ID/login
không được trả như account đang link. Response riêng tư có
`Cache-Control: private, no-store`.

Consent giữ state một lần, PKCE S256, cookie `utask_github_consent` HttpOnly,
SameSite=Lax, path `/`, TTL 600 giây và Secure mặc định. Complete cần cùng
Bearer UTask và nonce browser. Provider exchange lấy user ID/login từ GitHub;
credential access và refresh được mã hóa trong Integration. Token không xuất
hiện trong response hoặc log. Lỗi refresh mơ hồ yêu cầu consent lại.

## Installation và repository

| Method và path | Trạng thái | Request / kết quả |
| --- | --- | --- |
| POST `/api/v1/github/installations/start` | Đã triển khai trong source | Không query/body; trả `installation_url`, `expires_at`, đặt cookie nonce |
| POST `/api/v1/github/installations/complete` | Đã triển khai trong source | JSON đúng `state`, `installation_id` (chuỗi ID số dương), `setup_action` (`install`, `update`, `request`) |
| GET `/api/v1/github/installations` | Đã triển khai trong source | Query tùy chọn `page` (mặc định 1) và `per_page` (mặc định 30, tối đa 100); trả `{items,next_page}` |
| GET `/api/v1/github/installations/{installation_id}/repositories` | Đã triển khai trong source | Cùng phân trang; trả `{items,next_page}` với item `repository_id`, `name`, `full_name`, `private` |

Complete ràng buộc actor, Bearer, nonce, state, generation và credential
version. Với `setup_action=request`, kết quả là
`{status:"PENDING_APPROVAL",installation_id}`; không khẳng định installation
đã hoạt động. Với install/update, Integration kiểm tra installation và
repository access qua GitHub ngay lúc gọi, rồi trả `status:"ACTIVE"` cùng
metadata installation: `installation_id`, `app_id`, `account` (`id`, `login`,
`type`), `repository_selection`, `suspended_at`. Cache metadata chỉ là gợi ý;
không cấp quyền truy cập. Danh sách installation/repository được lấy live,
không cache quyền. Khi xác minh installation trong complete, scan tối đa 10
trang × 100; quá giới hạn trả lỗi khả dụng thay vì kết luận không tìm thấy.

## Webhook và lỗi

POST `/api/v1/github/webhooks` không nhận Bearer/query, chỉ nhận
`application/json` và header `X-Hub-Signature-256`, `X-GitHub-Delivery`,
`X-GitHub-Event`. Payload tối đa 25 MiB. Chữ ký HMAC-SHA256 được kiểm trên raw
body trước khi parse; delivery được lưu bền vững trước khi trả 202 với
`{delivery_id}`. Hỗ trợ `ping`, `installation`, `installation_repositories`,
`github_app_authorization`; event không hỗ trợ được đánh dấu bỏ qua sau khi
xác thực và lưu.

Các API user được xác thực qua Identity `GET /users/me`; không nhận `user_id`
từ caller. Errors dùng envelope `success:false,error:{code,message}`. Cấu hình
GitHub App mặc định tắt; khi tắt hoặc thiếu cấu hình, provider route đóng với
503. Thông tin cấu hình và giới hạn xem [foundation](foundation.md).

## Ngoài phạm vi đã triển khai

Integration không sửa Project/Task của Work. Đồng bộ hoạt động GitHub bằng
webhook/event riêng chưa có; context hiện đọc live theo request. Work/AI thật
chưa nghiệm thu nối runtime, dù provider nội bộ dưới đây đã có trong source.

## Internal API M5/M6

**Trạng thái: Đã triển khai phía provider; flags mặc định tắt.** OpenAPI 1.4.0
có sáu capability nội bộ, kiểm thử PostgreSQL và HTTP stub; Work/AI thật chưa
nghiệm thu. Tất cả dùng `X-Service-Key` theo caller và bị chặn tại gateway:

| Method và path | Caller | Mục đích |
| --- | --- | --- |
| POST `/api/v1/internal/projects/{project_id}/github/connection/prepare` | Work + Bearer | Chuẩn bị connect/disconnect theo idempotency và generation |
| POST `.../connection/confirm` | Work | Xác minh receipt Work rồi finalize connection |
| POST `.../connection/abort` | Work | Hủy operation chưa được Work áp dụng |
| GET `.../connection/operations/{operation_id}` | Work | Phục hồi sau timeout/mất response |
| POST `.../github/references/verify` | Work + Bearer | Xác minh branch/commit/Pull Request |
| GET `.../github/context` | AI + Bearer | Trả `ContextDocument` GitHub đã lọc sau Work authorize |

Schema request/response và error là nguồn chuẩn trong OpenAPI. Quy trình phía
caller xem [guide Work](work-service-integration-guide.md) và
[guide AI](ai-service-integration-guide.md); quyết định kiến trúc ở
[ADR-005](../adr/005-integration-work-ai-contracts.md).

Prepare trả snapshot PENDING bất biến cả khi retry sau confirm; status phản
ánh state operation hiện tại, confirm replay trả kết quả cuối cũ. Operation ID
không nhận `.`/`..`. Một Project chỉ có một operation PREPARED; operation
khác đang chờ trả 409. TTL 24 giờ, tombstone ít nhất 30 ngày sau expiry;
receipt đang đại diện connection cuối được giữ lâu hơn. Abort/expire không
tái sử dụng generation đã dành.

Lỗi thêm: `OPERATION_CONFLICT`/`VERSION_CONFLICT` (409), `OPERATION_EXPIRED`
(410), `WORK_UNAVAILABLE`/`CONNECTIONS_UNAVAILABLE` (503), Work không cho đọc
context (403). Thiếu/sai key hoặc sai caller trả 403 trước khi gọi Identity.
GitHub 401 yêu cầu cấp quyền lại; không coi dữ liệu rỗng là context hợp lệ.
Xem [cấu hình, retry và rollout](runtime-connections.md).
