# ADR-004 — Integration sở hữu tài khoản GitHub đã liên kết

- Ngày: 18/10/2026.
- Trạng thái: **Quyết định theo yêu cầu người dùng**: code chỉ thay đổi trong
  `apps/integration-service/`; tài liệu và contract cập nhật tại nguồn chuẩn.
- Thay thế phần mapping/OAuth proof, hai registration và yêu cầu thêm endpoint/
  allowlist ở service khác của [ADR-003](003-integration-auth-and-contracts.md).
  Các quy tắc ranh giới dữ liệu, chống lặp và bảo vệ secret tiếp tục áp dụng.

## Quyền sở hữu

Integration sở hữu liên kết `user_id ↔ github_user_id`, GitHub login, trạng
thái liên kết/thu hồi, phiên bản, thời điểm xác minh, consent và credential
GitHub. Các bản ghi nằm trong `integration_db`. `user_id` là UUID logic của
tài khoản UTask, không phải FK hoặc bản sao User của Identity.

Identity tiếp tục sở hữu tài khoản UTask, đăng nhập, JWT và session. Work tiếp
tục sở hữu Project/Task, ProjectMember và liên kết nghiệp vụ Task–GitHub.
Không chuyển quyền Project hoặc dữ liệu gốc Work sang Integration.

## Xác thực bằng API hiện có

Integration chuyển Bearer actor tới `GET {IDENTITY_BASE}/users/me`. Identity
hiện có kiểm JWT, trạng thái tài khoản và session tại endpoint này; response
thành công phải có `success: true` và `data.id` là UUID khác nil. Integration
dùng ID đó để giới hạn bản ghi của actor, không nhận `user_id` từ JSON/query.

Không cần sửa code Identity, thêm Integration vào session-status allowlist,
cấp key giả danh Work/AI, hoặc tạo User table cục bộ. Không cache kết quả xác
thực cho phép; Identity 401/403 bị từ chối, timeout/lỗi/response sai thành 503.
Adapter không theo redirect, giới hạn body 64 KiB, timeout kết nối/đọc 2/3 giây.

JWT được Identity xác thực, không tự coi decode payload chưa kiểm là bằng
chứng. Scope Project vẫn do Work; API đọc Work hiện có chỉ là snapshot và
không thay authorize/CAS tại transaction ghi.

## Phần đã triển khai trong Integration

- `GitHubAccount`: một row cho mỗi user UUID, GitHub ID ổn định dạng chuỗi số
  ASCII dương tối đa 100 ký tự, login tối đa 39 ký tự và giữ casing provider.
  Login không unique vì có thể đổi; GitHub ID unique giữa các row `LINKED`.
- Trạng thái `LINKED`/`REVOKED`, `verified_at`, `linked_at`, `revoked_at`,
  `source_version` và `updated_at`. Constraint PostgreSQL giữ trạng thái nhất
  quán; không FK tới database khác. Bản ghi thu hồi giữ watermark/version để
  chặn kết quả xác minh cũ và giải phóng GitHub ID cho liên kết mới hợp lệ.
- Service lưu danh tính **đã được adapter xác minh**; bản thân hàm persistence
  không đổi OAuth code hoặc xác minh GitHub. Trùng hoàn toàn là idempotent,
  proof cũ bị từ chối, đổi GitHub ID đang liên kết phải unlink trước. Transaction
  và row lock bảo vệ version; unique constraint bảo vệ hai user tranh cùng ID.
- `GET/DELETE /api/v1/github/account` đọc/thu hồi bản ghi của actor sau xác
  thực Identity hiện có. Không body/query actor; không POST/PATCH nhận GitHub
  identity tự khai báo. Thu hồi lặp lại không tăng version hoặc ảnh hưởng user khác.
- Chưa có OAuth/provider/token adapter. DELETE hiện thu hồi mapping local;
  chưa thể gọi GitHub để revoke token. Không lưu token/code giả để lấp schema.

Xem [code và cấu hình](../../apps/integration-service/),
[API](../integration-service/api.md) và [OpenAPI](../../contracts/api/integration-service-v1.yaml).

## Consent GitHub mục tiêu

Một GitHub App registration do Integration quản lý cung cấp user authorization
và installation. Liên kết tài khoản cá nhân không cần Project hoặc quyền
leader, không cần liên kết GitHub qua Identity trước.

M3 dùng state ngẫu nhiên dùng một lần, TTL 10 phút, PKCE S256, redirect URI
allowlist chính xác và nonce cookie HttpOnly/SameSite=Lax/Secure. Integration
sở hữu state/verifier và đổi code; callback/frontend hoàn tất bằng Bearer
hiện hành. Binding gồm actor, browser nonce và session đã được Identity xác
thực. Claim session nếu đọc từ token chỉ dùng sau Identity chấp nhận token.
Không nhận `github_user_id`, login hoặc verifier tự khai báo để tạo mapping.

Sau exchange, Integration dùng token gọi GitHub `/user` và lưu ID/login đã xác
minh. User token chứng minh tập repo được truy cập qua `/user/installations`
và `/user/installations/{installation_id}/repositories`, giữ giao quyền user/
App. Installation token riêng không chứng minh quyền của user.

Credential tương lai chỉ nằm trong Integration, mã hóa xác thực với key ring
ngoài DB; không trả qua API/event/log/AI. Bật token có hạn, refresh có version
và kiểm soát đồng thời; mất response refresh phải yêu cầu consent lại khi không
biết cặp token nào còn dùng được. Unlink/GitHub revoke phải vô hiệu credential
và job liên quan trước khi mở luồng provider. Những bước này là **Thiết kế mục
tiêu**, chưa triển khai bằng bảng mapping hiện tại. DELETE khi account chưa
tồn tại hiện không giữ watermark. Trước khi nối callback, M3 phải hủy pending
consent hoặc lưu generation riêng để kết quả first-link đến muộn không khôi
phục liên kết sau DELETE; cần kiểm thử cả thứ tự này và cạnh tranh đồng thời.
Tham chiếu
[GitHub user authorization](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-a-user-access-token-for-a-github-app).

## Tương thích và giới hạn

Source Identity legacy vẫn có OAuth GitHub, `SocialAccount` và proof client;
giữ nguyên theo giới hạn user đặt ra. Integration không gọi mapping/proof API
đó, không lấy `profile.github_username` làm bằng chứng, không nhập hoặc đọc
DB Identity. Dữ liệu legacy nếu có vẫn là lịch sử của luồng cũ; không tự di
chuyển hoặc hợp nhất khi triển khai luồng Integration mới.

Contract Work authorize mới trong ADR-003 được thu hồi khỏi kế hoạch hiện
hành vì cần sửa Work. Không giả định Work đã có API đó hoặc receipt/dispatcher
confirm. Adapter Work hiện vẫn unavailable; những thao tác cần hợp đồng chưa
có tiếp tục đóng. Không dùng GET snapshots hay service key khác để vượt gate.

Trong phạm vi quyết định này không sửa code Identity/Work, không bật consumer/
publisher mới và không phát event thay cho nguồn quyền. [Kế hoạch gốc](../integration-service/plans/2026-10-15-gitnexus-plan-integration-staged-implementation.md)
là snapshot trước quyết định này; milestone phụ thuộc ownership cũ cần đọc cùng
ADR-004, không triển khai máy móc.
