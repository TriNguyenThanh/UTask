# Plan: OAuth liên kết danh tính GitHub cho Integration Service (M3)

**Trạng thái: Đã triển khai trong source và kiểm thử local ngày 19/10/2026;
chưa xác minh OAuth với GitHub thật.**

## Kết quả triển khai

- Hai route start/complete, provider identity-only, pending consent mã hóa và
  generation chống callback sau DELETE đã có; xem [API hiện hành](../api.md).
- Migration `0002_githubconsentgeneration_githubpendingconsent` bổ sung hai
  bảng nội bộ Integration, không có FK xuyên service.
- **362 test đạt** trên PostgreSQL 16 tạm riêng; gồm unit, API, contract và
  concurrency. Ruff lint/format, Django check, migration drift và Docker build
  đạt. Migration trong image đã áp dụng trên database tạm riêng.
- `python scripts/ci_local.py --skip-images` đã chạy nhưng dừng tại discovery:
  `docker-compose.staging.yml` thiếu `x-deploy.gateway_health_path` cho
  Integration, có sẵn tại HEAD trước thay đổi M3. Chưa xác minh các bước CI
  toàn repo sau điểm này. Chi tiết tại [foundation](../foundation.md).
- Session binding dùng HMAC của chính access Bearer đã được Identity xác
  minh; Identity `/users/me` không trả session ID. Nếu refresh Bearer giữa
  luồng, cần bắt đầu consent mới. Không thay đổi contract Identity.

Các mục dưới giữ phạm vi và tiêu chí của kế hoạch đã triển khai.

## Tóm tắt

Triển khai M3 cho Integration Service theo mô hình GitHub OAuth App: người dùng
UTask đăng nhập bằng Bearer, thực hiện consent GitHub, Integration xác minh
GitHub user và lưu mapping `user_id`–GitHub account. M3 **không lưu
access token/refresh token**, không liệt kê repository và chưa mở Work
repository flow.

M3 sử dụng hai route đã có trong contract mục tiêu:

- `POST /api/v1/github/authorizations/start`
- `POST /api/v1/github/authorizations/complete`

## Thay đổi cần triển khai

### Pending consent và callback

- Tạo state dùng một lần với TTL 10 phút, ràng buộc actor, session và browser
  nonce.
- Dùng PKCE S256; Integration giữ verifier tạm thời trong consent record.
- Bảo vệ verifier tạm thời bằng khóa consent riêng của Integration; không lưu
  credential GitHub.
- Callback phải kiểm tra lại Bearer, state, nonce và thời hạn trước khi exchange.
- State sai, hết hạn, replay hoặc khác actor phải bị từ chối.

### GitHub OAuth provider

- Tạo adapter exchange authorization code với GitHub OAuth App.
- Gọi GitHub `/user` sau exchange và lấy `github_user_id` cùng
  `github_username` từ provider; không nhận các giá trị này từ client.
- Không trả hoặc ghi log code, verifier hay token; discard token sau bước xác
  minh danh tính.
- Mapping account được tạo/cập nhật qua service hiện có, giữ nguyên constraint
  active account và `source_version`.
- Khi account đang `LINKED`, yêu cầu unlink hoặc consent mới theo quy tắc đã
  chốt; không âm thầm đổi GitHub identity.

### Race và thu hồi mapping

- Bổ sung generation hoặc tombstone cho pending consent để DELETE trước khi
  first-link hoàn tất không bị kết quả đến muộn ghi đè.
- Xử lý first-link và DELETE đồng thời theo thứ tự version/generation.
- DELETE vẫn chỉ thu hồi mapping local; không revoke token GitHub vì M3 không
  lưu token.

### Contract và tài liệu

- Cập nhật `contracts/api/integration-service-v1.yaml` từ trạng thái
  `design-not-implemented-m3` sang trạng thái phản ánh source sau khi code và
  test đạt.
- Cập nhật `docs/integration-service/api.md` để ghi rõ OAuth App cá nhân,
  state/PKCE, response không chứa credential và giới hạn identity-only của M3.
- Cập nhật `docs/integration-service/scope-access.md` về ownership consent,
  actor binding và việc chưa có repository access.
- Không thêm API Project/repository hoặc event Kafka placeholder.

## Kiểm thử và nghiệm thu

- Unit test tạo state/PKCE thành công; state sai, hết hạn, replay; nonce/session/
  actor không khớp; provider timeout, HTTP lỗi và response thiếu ID/login.
- Unit/API test bảo đảm token không xuất hiện trong response, log hoặc database.
- PostgreSQL integration test cho callback thành công, callback thất bại không
  ghi mapping, account conflict, đổi account, DELETE lặp lại và version.
- Concurrency test cho callback đến sau DELETE và first-link/DELETE đồng thời.
- Contract test kiểm tra response và mã lỗi `400/401/409/503`; authorization URL
  không chứa token.
- Chạy kiểm tra service:

  ```bash
  uv run ruff check .
  uv run ruff format --check .
  uv run python manage.py check
  uv run python manage.py makemigrations --check --dry-run
  uv run pytest
  python scripts/ci_local.py --skip-images
  ```

## Ngoài phạm vi M3

- Lưu, refresh hoặc revoke GitHub token.
- Liệt kê repository hoặc xác minh branch/commit/pull request.
- GitHub App installation, webhook, sync worker và Kafka.
- API chọn repository của Project và `TaskGitHubLink`.
- Thay đổi Work, Identity hoặc AI ngoài contract xác minh actor cần thiết.

## Quyết định và giả định

- M3 dùng GitHub OAuth App cá nhân; GitHub App installation/webhook để M4.
- M3 chỉ liên kết danh tính GitHub; chưa có repository access.
- Credential GitHub không được lưu trong milestone này.
- Integration sở hữu mapping GitHub; `user_id` là UUID tham chiếu logic, không
  có foreign key xuyên service.
- Work adapter tiếp tục là `UnavailableIntegration` cho đến khi có contract
  repository riêng ở milestone sau.
