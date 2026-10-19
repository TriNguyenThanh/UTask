# Checkpoint Integration Service — 19/10/2026

**Trạng thái: Một phần.** Runtime Django/DRF, database riêng, mapping
`GitHubAccount` và API GET/DELETE account đã có trong source. Xác thực actor
qua Identity đã có adapter và test, nhưng tích hợp xuyên service thực tế chưa
được xác minh. OAuth consent, GitHub provider, repository access, webhook và
Work adapter vẫn chưa triển khai.

## Bước tiếp theo

Kế hoạch chính cho milestone tiếp theo nằm tại
[plan OAuth liên kết danh tính GitHub](plans/2026-10-19-github-identity-oauth.md).

Phạm vi M3 đã chốt:

- dùng GitHub OAuth App cho consent cá nhân;
- xác minh GitHub user rồi lưu mapping tại Integration;
- state một lần, TTL 10 phút, actor/session/browser binding và PKCE S256;
- không lưu access token/refresh token;
- chưa liệt kê repository và chưa mở luồng Work.

Trước callback OAuth phải xử lý race giữa pending consent, first-link và
DELETE. Sau khi M3 đạt test, milestone kế tiếp mới xem xét credential có vòng
đời đầy đủ, GitHub App installation, repository connection và webhook.

## Ranh giới dữ liệu

Integration sở hữu mapping `user_id`–GitHub và consent. Work sở hữu Project,
Task, quyền nghiệp vụ, `TaskGitHubLink` và tiến độ. Hai service không dùng
foreign key xuyên database; Work không nhận GitHub token.

## Bằng chứng hiện trạng

- [Foundation](foundation.md) ghi source/test đã đối chiếu.
- [API hiện hành](api.md) ghi route account đã triển khai và OAuth là thiết kế
  mục tiêu.
- [Scope và quyền](scope-access.md) ghi ownership và giới hạn Integration.
- [Checkpoint 18/10/2026](checkpoint-2026-10-18.md) giữ snapshot lịch sử trước
  kế hoạch M3 này.
