# Checkpoint Integration Service — 18/10/2026

**Trạng thái: Một phần.** Đây là bản chụp tiến độ và điểm tiếp tục công việc
ngày 18/10/2026. Quyết định kiến trúc hiện hành nằm tại
[ADR-004](../adr/004-integration-github-account-ownership.md); bằng chứng và
cách kiểm tra nằm tại [foundation](foundation.md). Các kết quả bên dưới được
ghi nhận từ lượt triển khai trước khi lưu checkpoint, không phải lượt chạy mới.

## Phạm vi đã chốt

- Code nghiệp vụ chỉ thay đổi trong `apps/integration-service/`; không sửa
  code Identity hoặc Work. Tài liệu và hợp đồng tiếp tục cập nhật trong
  `docs/` và `contracts/`.
- Integration sở hữu GitHub user ID/login, liên kết tài khoản, consent và
  credential. Identity sở hữu tài khoản UTask, JWT và session.
- `user_id` trong Integration là UUID tham chiếu logic, không có khóa ngoại
  xuyên service hoặc truy cập database Identity/Work.
- ADR-004 thay thế phần ownership và yêu cầu sửa Identity/Work trong ADR-003.
  Các kế hoạch milestone cũ là snapshot; cần đọc cùng quyết định hiện hành.

## Tiến độ

| Mốc | Trạng thái | Phần đã có và giới hạn |
| --- | --- | --- |
| M0 | Đã chốt nền | Ownership và hướng xác thực bằng API Identity `GET /users/me` hiện có |
| M1 | Một phần | Runtime Django/DRF, health, database/role riêng, migration `GitHubAccount`, persistence và API GET/DELETE account; chưa có link qua HTTP |
| M2 | Một phần | Adapter xác thực Bearer qua Identity đã có; chưa xác minh chạy xuyên service thật |
| M3 | Chưa triển khai | OAuth consent/callback, GitHub provider, lưu mã hóa và refresh/revoke token |

Work adapter vẫn là `UnavailableIntegration`. Chưa mở mutation, webhook,
sync hoặc Kafka. Liên kết GitHub cá nhân không yêu cầu Project hoặc vai trò
leader và không tự cấp quyền thao tác Project/Task.

API và trạng thái route được ghi tại [tài liệu API](api.md) và
[hợp đồng OpenAPI](../../contracts/api/integration-service-v1.yaml).

## Kết quả kiểm tra đã ghi nhận

- **242 test Integration và 18 test Compose đạt.**
- Lint/format, Django system check, migration drift và 119 link tài liệu đạt.
- Image Docker đã build và khởi động; migration và bảng thuộc role Integration
  riêng. Role không có superuser/CREATEDB/CREATEROLE hoặc quyền CONNECT
  database Identity.
- Smoke HTTP với **Identity stub cục bộ** đạt health, từ chối Bearer sai,
  GET/DELETE account, DELETE lặp lại và 503 khi Identity không khả dụng.
- GitNexus đã cập nhật ở lượt kiểm tra triển khai; phân tích thay đổi có mức
  ảnh hưởng **MEDIUM**. Kết quả là phân tích tĩnh, không chứng minh runtime.

**Chưa xác minh:** tích hợp Identity/GitHub App thật hoặc triển khai VPS.
Không tự động chuyển hay nhập dữ liệu GitHub legacy từ Identity.

## Bước kế tiếp

1. Trước khi nối callback M3, bổ sung cơ chế hủy pending consent hoặc generation
   riêng. Hiện DELETE khi chưa có account không tạo watermark; kết quả xác minh
   first-link đến muộn vẫn có thể được helper lưu.
2. Bổ sung test kết quả xác minh đến sau DELETE và first-link/DELETE đồng thời
   trước khi mở callback.
3. Triển khai OAuth consent, GitHub provider và quản lý token trong Integration;
   danh tính phải lấy từ GitHub sau exchange, không nhận ID/login tự khai báo
   từ client.
4. Xác minh luồng với Identity và GitHub App thực tế, rồi cập nhật hiện trạng
   và kết quả kiểm tra tại nguồn chuẩn.

Mọi bước tiếp tục giữ giới hạn code trong Integration. Luồng cần hợp đồng
ghi của Work chưa có phải tiếp tục đóng.
