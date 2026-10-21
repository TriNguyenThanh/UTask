# Integration Service

**Trạng thái: Một phần.** API account, consent GitHub App, credential mã hóa,
refresh có fencing, GitHub App installation, webhook bền vững và worker có
trong source. Các ca GitHub dev trong kế hoạch nghiệm thu đã đạt ngày
20/10/2026; staging/production chưa xác minh. Cấu hình M4 mặc định tắt.
Chi tiết tại [foundation](foundation.md), [API](api.md) và
[checkpoint 20/10/2026](checkpoint-2026-10-20.md).

## Nguồn chuẩn

- [Checkpoint mới nhất](checkpoint-2026-10-20.md): trạng thái bàn giao, bản sửa
  timeout publisher và bước tiếp tục; [review provider](review-2026-10-20.md).
- [Phạm vi và quyền](scope-access.md): ownership và ranh giới Identity/Work.
- [API](api.md): route, request, response và trạng thái.
- [Cách liên kết repository GitHub](github-repository-linking.md): luồng cấp
  quyền, cài App, đọc repository live, chọn repo chính cho Project và liên kết
  hoạt động GitHub vào Task.
- [Hướng dẫn tích hợp Work](work-service-integration-guide.md): adapter REST,
  prepare/confirm/abort, Kafka consumer và rollout phía Work (**Đã triển khai
  trong source; HTTP/Kafka test riêng đạt, GitHub live/staging chưa xác minh**).
- [Hướng dẫn tích hợp AI](ai-service-integration-guide.md): REST context
  `github_activity`, service key và mapping lỗi phía AI (**Thiết kế mục tiêu**).
- [Foundation](foundation.md): bằng chứng source, cấu hình và kiểm thử.
- [Nghiệm thu GitHub thật](live-acceptance.md): checklist Reqable, smoke,
  refresh có kiểm soát và vòng đời quyền; kết quả từng phiên ở checkpoint.
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
| Account và xác thực Identity | Đã triển khai | API account, Identity Bearer adapter, kiểm thử và actor thật qua gateway ở local |
| Consent GitHub App và credential | Đã triển khai trong source | OAuth authorization hiện có đổi sang user token có hạn, mã hóa riêng; kiểm thử mock |
| Refresh fencing và revoke | Đã triển khai trong source | version/generation/claim, job thu hồi token và management command |
| Installation và repository live list | Đã triển khai trong source | setup start/complete, kiểm tra quyền live và phân trang |
| Webhook, job durable và worker/Beat | Đã triển khai trong source | HMAC, inbox PostgreSQL, Celery/Redis, migration gate trong Compose |
| GitHub dev theo kế hoạch nghiệm thu | Đã triển khai, đã nghiệm thu local | Consent, đọc repo, refresh thật, đổi quyền repo, uninstall/reinstall, revoke, DELETE và reconnect; xem checkpoint |
| Staging/production | Chưa xác minh | Không deploy trong phiên nghiệm thu local |
| Provider connection/reference/context/outbox | Đã triển khai trong source | Kiểm thử PostgreSQL và HTTP stub; flags mặc định tắt |
| Kết nối Project và Task reference phía Work | Đã triển khai trong source | Hai backend qua HTTP/PostgreSQL/Kafka test riêng; GitHub/Identity stub, xem [Work](../project-service/github-integration.md) |
| AI authorize/context và GitHub live cho Project | Chưa xác minh | Không nằm trong lượt triển khai Work này |

Provider M5/M6 hiện có connection theo Project, prepare/confirm/abort/status,
reference, REST context và Kafka outbox. Xem
[vận hành provider Work/AI](runtime-connections.md). Phía Work đã có task phục
hồi/consumer; adapter AI và nghiệm thu GitHub live cho Project là phạm vi riêng.

## Mốc triển khai

- M0–M2: ownership và xác minh actor qua Identity API.
- M3: OAuth consent PKCE và mapping account, trước đây không lưu token.
- M4: chuyển consent sang GitHub App user authorization, lưu credential mã
  hóa có hạn, installation, webhook và jobs. GitHub dev đã nghiệm thu local;
  staging/production chưa xác minh. Xem [checkpoint](checkpoint-2026-10-20.md).

Các kế hoạch trong `plans/` là snapshot, không phải hợp đồng hiện hành.

Thực hiện [runbook nghiệm thu GitHub thật](live-acceptance.md) để hoàn tất
installation/repository, refresh, uninstall/revoke và kết nối lại. Kết quả
thực tế được ghi tại checkpoint của phiên, không suy ra từ checklist.

## Mở rộng thông báo

Notification hiện chỉ nhận nguồn Identity/Work; sự kiện GitHub chưa có
consumer Notification trong phạm vi đã bàn giao. Trước khi mở rộng, đọc
[hướng dẫn thêm nguồn/event](../notification-service/implementation.md#thêm-service-hoặc-event-mới)
và [checkpoint](../notification-service/checkpoint-2026-10-22.md).
Integration tiếp tục là service duy nhất gọi GitHub API.
