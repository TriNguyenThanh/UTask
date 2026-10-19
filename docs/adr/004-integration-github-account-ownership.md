# ADR-004 — Integration sở hữu liên kết tài khoản GitHub

- Ngày quyết định ban đầu: 18/10/2026.
- Trạng thái: **Đã chốt; M4 có source, vận hành thật chưa xác minh.**
- Thay thế phần mapping/OAuth proof và yêu cầu sửa Identity/Work trong
  [ADR-003](003-integration-auth-and-contracts.md). Quy tắc ranh giới dữ liệu,
  chống lặp và bảo vệ secret tiếp tục áp dụng.

## Quyết định

Integration sở hữu mapping `user_id ↔ github_user_id`, login, consent và
credential GitHub. `user_id` là UUID tham chiếu logic Identity, không phải FK
hay bản sao user. Identity sở hữu tài khoản UTask, JWT và session; Integration
xác minh Bearer qua `GET {IDENTITY_BASE}/users/me`. Work sở hữu Project/Task,
ProjectMember và quyền nghiệp vụ. Không đọc database service khác, không nhập
mapping legacy và không chuyển token GitHub sang Work/AI.

Liên kết account không đòi Project hoặc quyền leader. Nó chỉ xác minh danh
tính GitHub và không cấp quyền Project/repository cho service khác. Thao tác
Project/Task cần quyền do Work kiểm tra.

## Hiện trạng triển khai

**Đã triển khai trong source:** `GitHubAccount`, API account, GitHub App user
authorization qua route consent hiện hữu, state/PKCE/nonce binding, GitHub
`/user` identity verification, credential access/refresh có hạn, mã hóa
Fernet key ring riêng, refresh fencing theo version/generation/claim, unlink
và revoke job. `github_app_authorization` revoke webhook thu hồi credential
local và hủy pending consent. Xem [API](../integration-service/api.md) và
[foundation](../integration-service/foundation.md).

M4 cũng có GitHub App installation start/complete, live installation và
repository listing, HMAC webhook durable inbox, Celery/Redis jobs, Beat,
cleanup và lệnh xoay khóa/replay. Đây là bằng chứng source/cấu hình. GitHub
thật, Identity deployment, credentials deployment và staging/production
**Chưa xác minh**. M4 bật theo opt-in, `INTEGRATION_GITHUB_APP_ENABLED` mặc
định `false`.

## Cơ chế và giới hạn

Credential chỉ được lưu trong Integration dưới dạng mã hóa xác thực. Phần tử
đầu tiên của `INTEGRATION_CREDENTIAL_KEYS` mã hóa mới; các key sau giải mã
credential cũ. Key ring phải khác khóa consent. Lệnh
`manage.py rotate_github_credentials` mã hóa lại credential và token revoke
job bằng khóa đầu ring.

Refresh HTTP không giữ khóa DB. Claim/version/generation ngăn response refresh
cũ ghi đè unlink hoặc consent mới. Nếu không biết GitHub đã xoay token hay
chưa, credential chuyển sang yêu cầu consent lại. DELETE vô hiệu local access
ngay và tạo durable revoke job; revoke phía provider hoàn tất bất đồng bộ.

Installation metadata chỉ là cache gợi ý. Quyền repository được đọc live bằng
user token, không cache hoặc coi installation là quyền Project. Setup callback
`installation_id`/`setup_action` khác OAuth callback `code`/`state`; action
`request` trả pending approval.

Không có GitHub App private key, Work mutation, AI context, Kafka hay GitHub
domain synchronization trong phạm vi hiện hành. Đây là **Chưa triển khai**;
không được mô tả là đã vận hành. Xem [checkpoint](../integration-service/checkpoint-2026-10-19.md).

## Tương thích

OAuth GitHub legacy, `SocialAccount` và proof client của Identity không bị
thay đổi hoặc dùng làm nguồn quyền/mapping mới. Không migrate dữ liệu legacy.
Kế hoạch lịch sử trước ownership hiện hành không được triển khai máy móc.
