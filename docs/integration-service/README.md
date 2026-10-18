# Integration Service

**Trạng thái: Một phần.** Khung Django/DRF, bảng `GitHubAccount` và API đọc/
thu hồi liên kết cá nhân đã có trong source. Chưa có OAuth consent, GitHub
provider/token adapter, GitHub App, webhook hay đồng bộ. Hiện trạng chi tiết và
cách kiểm tra tại [foundation](foundation.md).

Điểm tiếp tục công việc: [checkpoint ngày 18/10/2026](checkpoint-2026-10-18.md)
là bản chụp tiến độ, giới hạn xác minh và các bước kế tiếp tại thời điểm ghi nhận.

## Nguồn chuẩn

- [Phạm vi và quyền](scope-access.md): quyền sở hữu tài khoản GitHub, xác thực
  user và ranh giới với Work/Identity.
- [API](api.md): route hiện có và các API consent mục tiêu.
- [Sơ đồ](diagram/README.md): mô hình khái niệm và luồng mục tiêu.
- [Foundation](foundation.md): bằng chứng source, cấu hình và kiểm thử.

## Ranh giới service

Integration là service duy nhất gọi trực tiếp GitHub API. Integration sở hữu
mapping tài khoản UTask–GitHub, consent GitHub cá nhân, credential/provider
liên quan và dữ liệu GitHub. `user_id` là UUID tham chiếu logic tới Identity;
không có khóa ngoại hoặc truy cập database Identity.

Identity vẫn sở hữu tài khoản UTask, JWT và phiên đăng nhập. Integration gửi
Bearer tới endpoint Identity hiện có `GET /users/me`; Identity tự xác minh JWT
và trạng thái phiên, Integration dùng `data.id` làm actor. Không dựa vào
Identity SocialAccount, `profile.github_username`, API mapping nội bộ hoặc
OAuth proof exchange giữa service.

Work sở hữu Project, Task, ProjectMember và quyền nghiệp vụ. Integration
không đọc database Work. Các API GET Work hiện có có thể dùng làm snapshot
đọc, nhưng không đủ bảo đảm quyền ghi hoặc compare-and-set (CAS). Nếu một luồng
Project cần mutation/prepare-confirm mà chưa có contract Work tương ứng, luồng
đó vẫn đóng cho tới khi contract được chốt; phạm vi này không yêu cầu sửa Work.
Adapter Work hiện mặc định là `UnavailableIntegration`.

Liên kết GitHub cá nhân không cần `project_id`, vai trò leader hoặc quyền
Project. Nó cũng không tự cấp quyền đọc repository hay sửa Project/Task.
Project/repository và Task/GitHub vẫn cần các quyết định quyền riêng của Work.

## Hiện trạng đã đối chiếu

| Hạng mục | Trạng thái | Bằng chứng |
| --- | --- | --- |
| Runtime và cấu hình | Đã triển khai một phần | Django/DRF, settings, health, Compose, Nginx và role PostgreSQL riêng; xem [foundation](foundation.md) |
| Mapping tài khoản GitHub | Đã triển khai một phần | `GitHubAccount`, migration và dịch vụ link/unlink có kiểm thử PostgreSQL; chưa có luồng OAuth/provider tạo xác minh từ GitHub |
| Đọc/thu hồi account hiện hành | Đã triển khai trong source | `GET` và `DELETE /api/v1/github/account`, xác thực actor qua Identity `/users/me`; có API-level PostgreSQL tests trong source |
| OAuth consent cá nhân và credential | Chưa triển khai | Mục tiêu M3; chưa có provider/token adapter hoặc endpoint start/complete |
| Work/AI GitHub adapter, GitHub App, webhook, sync, Kafka | Chưa triển khai | Work adapter mặc định `UnavailableIntegration`; không có provider/runtime tương ứng trong Integration |

`integration_db` là database logic riêng. Không migrate hay tự import mapping
legacy từ Identity/Work; không đọc database của hai service đó. Các tài liệu
trong thư mục này là nguồn chuẩn của Integration; tài liệu app chỉ nên trỏ về
đây.

## Mốc triển khai

- **M0 — Đã chốt nền** ([ADR-004](../adr/004-integration-github-account-ownership.md)):
  Integration sở hữu mapping GitHub cá nhân; Identity
  xác minh user UTask qua endpoint hiện có; consent và credential GitHub thuộc
  Integration. Luồng Project/Work tách biệt.
- **M1 — Đã triển khai một phần:** `GitHubAccount`, migration, persistence và
  API GET/DELETE account có trong source. Chưa có thao tác link qua HTTP.
- **M2 — Đã triển khai một phần:** xác thực Bearer gọi Identity `GET /users/me`
  đã có. Chưa xác minh triển khai thực tế giữa hai service.
- **M3 — Thiết kế mục tiêu:** OAuth consent cá nhân, provider/token adapter và
  luồng tạo/cập nhật mapping. Chưa có schema API bổ sung ngoài hợp đồng đã
  được chốt.

Tài liệu nằm dưới `docs/integration-service/diagram/`; các kế hoạch milestone
cũ trong `plans/` là snapshot, không phải nguồn hợp đồng hiện hành.
