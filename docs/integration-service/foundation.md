# Integration: hiện trạng và cách kiểm tra

**Trạng thái: Một phần.** Đối chiếu source, cấu hình và test trong worktree
ngày 18/10/2026. Chưa xác minh deploy Identity/Integration, GitHub OAuth App,
GitHub API hoặc môi trường VPS.

## Các phần đã có

| Phần | Trạng thái | Bằng chứng và giới hạn |
| --- | --- | --- |
| Runtime Django/DRF, health và cấu hình | Đã triển khai | `apps/integration-service/`, Compose profile, Nginx và test khung; xem README service |
| PostgreSQL Integration riêng | Đã triển khai một phần | Role/database riêng trong bootstrap; migration account hiện có. Không suy ra đã tách toàn PostgreSQL cluster |
| GitHub account mapping | Đã triển khai một phần | `GitHubAccount` migration, validation và service link/unlink; model giữ UUID `user_id` logic, status `LINKED`/`REVOKED`, metadata thời gian/version |
| API account | Đã triển khai trong source | GET/DELETE `/api/v1/github/account`; auth dùng Identity `GET /users/me`; API-level PostgreSQL tests trong `tests/integration/test_github_account_api.py` |
| Xác thực Bearer qua Identity | Đã triển khai một phần | Adapter gửi Bearer tới `http://identity-service:8000/users/me`, timeout 2/3 giây và parse `data.id`; chưa xác minh chạy xuyên service |
| OAuth consent, provider và token adapter | Chưa triển khai | Chưa có callback/start/complete, gọi GitHub, token lưu trữ hoặc token revoke |
| Work/AI, GitHub App, webhook, sync, Kafka | Chưa triển khai | Work integration adapter mặc định `UnavailableIntegration`; chưa có runtime Integration tương ứng |

## Mốc và quyết định hiện hành

- **M0 — Đã chốt:** Integration sở hữu mapping GitHub cá nhân, consent và
  credential. Identity xác thực UTask user qua API hiện có. Quyết định hiện
  hành ghi trong [ADR-004](../adr/004-integration-github-account-ownership.md);
  phần mapping/proof và API Identity/Work cũ trong ADR-003 đã bị thay thế.
- **M1 — Đã triển khai một phần:** bảng `GitHubAccount`, migration,
  persistence/service layer và GET/DELETE account.
- **M2 — Đã triển khai một phần:** adapter Bearer → Identity `/users/me` có
  source. Tích hợp thật giữa service chưa được xác minh.
- **M3 — Thiết kế mục tiêu:** personal OAuth consent, GitHub provider/token
  adapter, xác minh/refresh/revoke credential và hoàn tất link account.
- GitHub App installation, webhook, sync và mutation/project workflow chưa
  nằm trong phần đã triển khai.

Các kế hoạch trong `plans/` là snapshot thiết kế cũ, không phải nguồn chuẩn
cho ownership/contract hiện hành. Không tự động migrate hoặc nhập mapping
Identity/Work legacy.

## Kiểm thử đã có

Unit tests tại `apps/integration-service/tests/unit/test_github_accounts.py`
bao phủ validation, link/unlink, account switch, verification cũ, conflict,
idempotency và version behavior. Integration tests tại
`apps/integration-service/tests/integration/test_github_accounts.py` cần
PostgreSQL test riêng và bao phủ DB constraints, unique active mapping,
concurrency và persistence. API tests tại
`apps/integration-service/tests/integration/test_github_account_api.py` bao phủ
đọc/thu hồi account actor hiện tại, query/body giả mạo, thiếu Bearer, Identity
không khả dụng và method chưa hỗ trợ. Ngày 18/10/2026, bộ kiểm thử Integration
đã chạy với PostgreSQL 16 tạm riêng: **242 passed**. Ruff, Django system check
và kiểm tra migration drift đều đạt.

Image Docker đã build và khởi động với PostgreSQL tạm: migration và bảng
thuộc role Integration không có superuser/CREATEDB/CREATEROLE hoặc quyền
CONNECT database Identity. Smoke HTTP qua Identity stub cục bộ đạt health,
401, GET/DELETE account, DELETE lặp lại và 503 khi upstream không khả dụng.
Kết quả này không chứng minh tích hợp Identity hoặc GitHub thật.

Identity client có unit tests cho Bearer forward, URL/response validation,
timeout, lỗi 401/403 và upstream unavailable. Các test đó không chứng minh
deployment hoặc OAuth GitHub thật.

## Cách kiểm tra

Lệnh local khung được mô tả tại
[hướng dẫn service](README.md). Khi cần chạy kiểm thử account, dùng PostgreSQL
test riêng theo cấu hình trong `apps/integration-service/config/settings/test.py`;
không dùng database runtime hay database thật của dự án.

Trước khi nối callback M3, phải thêm cơ chế hủy pending consent hoặc generation
riêng. Hiện DELETE khi chưa có account không tạo bản ghi/watermark: kết quả
xác minh đầu tiên đến muộn vẫn có thể được helper lưu. Chưa có public route
gọi helper link; kiểm thử M3 phải bổ sung late first-link sau DELETE và
first-link/DELETE đồng thời trước khi mở callback.

## Giới hạn tích hợp Work

Work sở hữu Project/Task và quyền nghiệp vụ. Integration chỉ có thể dùng các
API GET Work hiện hành cho snapshot `/projects/{id}/`, `/tasks/{id}/` và
`/projects/{id}/members/`; các API đọc không bảo đảm quyền ghi hoặc CAS. Không
mở luồng mutation/prepare-confirm nếu contract Work chưa có; adapter hiện
`UnavailableIntegration`. Không có yêu cầu sửa Work trong phạm vi tài liệu
Integration này.
