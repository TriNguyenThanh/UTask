# Integration Service

**Trạng thái: Một phần.** API account, consent GitHub App, credential mã hóa,
refresh có fencing, GitHub App installation, webhook bền vững và worker có
trong source. Cấu hình M4 mặc định tắt; GitHub thật và triển khai chưa được
xác minh. Chi tiết tại [foundation](foundation.md), [API](api.md) và
[checkpoint 20/10/2026](checkpoint-2026-10-20.md).

## Nguồn chuẩn

- [Phạm vi và quyền](scope-access.md): ownership và ranh giới Identity/Work.
- [API](api.md): route, request, response và trạng thái.
- [Foundation](foundation.md): bằng chứng source, cấu hình và kiểm thử.
- [Sơ đồ](diagram/README.md): mô hình khái niệm và luồng mục tiêu.

## Ranh giới service

Integration là service duy nhất gọi trực tiếp GitHub API. Service sở hữu
mapping UTask–GitHub, consent, credential và metadata installation. `user_id`
là UUID tham chiếu logic Identity, không có khóa ngoại hoặc truy cập database
Identity. Identity xác thực Bearer qua `GET /users/me`.

Work sở hữu Project, Task, ProjectMember và quyền nghiệp vụ; Integration không
đọc database Work. Liên kết account/installation không cấp quyền Project hay
repository cho Work hoặc AI. Không có thay đổi Work Identity, AI, UI, Kafka,
hay GitHub App private key trong M4.

## Hiện trạng đã đối chiếu

| Hạng mục | Trạng thái | Bằng chứng |
| --- | --- | --- |
| Account và xác thực Identity | Đã triển khai trong source | API account, Identity Bearer adapter và kiểm thử; tích hợp runtime chưa xác minh |
| Consent GitHub App và credential | Đã triển khai trong source | OAuth authorization hiện có đổi sang user token có hạn, mã hóa riêng; kiểm thử mock |
| Refresh fencing và revoke | Đã triển khai trong source | version/generation/claim, job thu hồi token và management command |
| Installation và repository live list | Đã triển khai trong source | setup start/complete, kiểm tra quyền live và phân trang |
| Webhook, job durable và worker/Beat | Đã triển khai trong source | HMAC, inbox PostgreSQL, Celery/Redis, migration gate trong Compose |
| GitHub thật/production | Chưa xác minh | Cần cấu hình và xác minh môi trường thật |
| Project/Task mutation, AI context, Kafka | Chưa triển khai | Ngoài phạm vi M4; Work vẫn sở hữu quyền nghiệp vụ |

## Mốc triển khai

- M0–M2: ownership và xác minh actor qua Identity API.
- M3: OAuth consent PKCE và mapping account, trước đây không lưu token.
- M4: chuyển consent sang GitHub App user authorization, lưu credential mã
  hóa có hạn, installation, webhook và jobs. Mốc triển khai thực tế chưa xác
  minh; xem [checkpoint](checkpoint-2026-10-20.md).

Các kế hoạch trong `plans/` là snapshot, không phải hợp đồng hiện hành.

Phiên tiếp theo theo [kế hoạch nghiệm thu GitHub thật](plans/2026-10-20-github-live-acceptance.md):
hoàn tất installation/repository, kiểm tra refresh, uninstall/revoke và kết nối lại.
