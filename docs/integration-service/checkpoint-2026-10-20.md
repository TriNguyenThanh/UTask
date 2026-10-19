# Checkpoint Integration Service — 20/10/2026

**Trạng thái: Một phần.** Đã sửa mapping biến GitHub App, đồng bộ mẫu môi
trường và kiểm tra cấu hình trên container local. Luồng thử bằng Reqable đã
đến bước hoàn tất installation nhưng còn lỗi consent; chưa nghiệm thu toàn
bộ kết nối GitHub thật. Đây là snapshot tiếp nối
[checkpoint 19/10/2026](checkpoint-2026-10-19.md), không thay thế hợp đồng
[API](api.md) hoặc hướng dẫn [foundation](foundation.md).

Worktree: nhánh `feat/integration-service`, HEAD `bf402d2`. Các thay đổi trong
phiên chưa commit; checkpoint không khẳng định staging/production đã triển khai.

## Thay đổi đã thực hiện

- **Đã triển khai:** sửa [mapping Integration](../../infra/env/integration-service.env)
  từ `APP_ENABLED`, `APP_ID`, `APP_SLUG` sang đúng tên
  `INTEGRATION_GITHUB_APP_ENABLED`, `INTEGRATION_GITHUB_APP_ID`,
  `INTEGRATION_GITHUB_APP_SLUG` mà Django đọc. Mapping dùng chung cho API,
  migration, worker và Beat ở Compose local/staging.
- **Đã triển khai:** thêm test hồi quy
  `test_github_app_configuration_reaches_every_integration_process` trong
  [test Compose Integration](../../scripts/tests/test_integration_compose.py).
  Test kiểm tra cấu hình bật/tắt, App ID/slug và OAuth client cho cả bốn
  process ở hai file Compose; đã thấy test thất bại trước khi sửa mapping.
- **Đã triển khai:** viết lại [.env.example](../../.env.example) theo nhóm và
  thứ tự biến của `.env` local: bao phủ 101 biến local, giữ thêm 18 biến tùy
  chọn. Đồng bộ URL ngrok, App slug và cấu hình không bí mật; credential thật
  được thay bằng giá trị mẫu hoặc để trống. Mẫu vẫn tắt GitHub App cho đến
  khi điền đủ cấu hình và giữ role database riêng cho Integration.
- **Đã triển khai:** bổ sung hướng dẫn App ID, slug, Client ID/client secret
  và cách nạp cấu hình container trong [foundation](foundation.md).
- `.env` local không nằm trong Git. Khi viết lại mẫu, đã kiểm tra file local
  không bị thay đổi và không đưa secret thật vào mẫu. Các lượt chẩn đoán
  trước đó có sửa riêng slug local và tạo lại container Integration.

## Kết quả chẩn đoán local

| Hiện tượng | Bằng chứng và kết luận |
| --- | --- |
| `GITHUB_UNAVAILABLE` ở authorization start | **Đã xác minh:** slug local chứa cả URL GitHub App. Đã lấy đúng phần tên App, tạo lại API/worker/Beat; kiểm tra provider configuration và tạo authorization/installation URL đều đạt. Bước tạo URL chưa gọi GitHub API. |
| Runtime Integration | **Đã xác minh tại thời điểm kiểm tra:** API, worker và Beat đều healthy; gateway `/api/integrations/healthz` trả 200 và `status=ok`. |
| `NOT_AUTHENTICATED` ở authorization complete | **Một phần:** response cho thấy backend không nhận credential xác thực. Đã hướng dẫn thêm Bearer từ `data.access`; chưa quan sát trực tiếp request Reqable để kết luận cách cấu hình client. |
| `PARSE_ERROR` ở installation complete | **Một phần:** lúc kiểm tra có một pending installation chưa dùng, còn 325 giây; account/installation generation và credential version đều khớp, credential local `ACTIVE`. Chưa xác định chính xác cookie, state hay Bearer nào sai trong request. |
| GitHub thật | **Một phần:** có credential local `ACTIVE` và yêu cầu installation trong database; chưa tự xác minh response hoàn tất installation, danh sách repo, refresh hoặc revoke với GitHub thật. |

Trong phép thử thủ công, Redirect URI và Setup URL dùng
`https://tigerishly-farinose-shaunda.ngrok-free.dev/api/integrations/healthz`.
Health endpoint chỉ nhận chuyển hướng để đọc tham số trên trình duyệt;
người thử gửi POST complete bằng Reqable, không phải callback tự động của UI.

## Kiểm tra đã chạy

Lượt cuối sau khi viết lại mẫu: **76 test đạt** với lệnh:

```bash
python3 -m unittest \
  scripts.tests.test_local_compose \
  scripts.tests.test_integration_compose \
  scripts.tests.test_staging_deployment \
  scripts.tests.test_ai_compose \
  scripts.tests.test_classroom_compose
```

- Ruff lint/format đạt cho file test Integration đã sửa trong phiên.
- Compose local và staging render hợp lệ với `.env.example`, gồm các profile
  Integration, AI và Notification; chỉ kiểm cấu hình, không deploy staging.
- Cú pháp dotenv, tên biến không trùng, độ bao phủ biến local và việc thay
  secret thật bằng mẫu đã được kiểm tra; `git diff --check` đạt.
- Không chạy lại toàn bộ suite backend/frontend hoặc build image trong lượt
  cập nhật mẫu. Kết quả 524 test Integration và các lượt CI trước thuộc
  checkpoint cũ, không phải kết quả chạy mới của phiên này.

## Phần việc tiếp theo

Phạm vi phiên tiếp theo đã chốt tại
[kế hoạch nghiệm thu GitHub thật](plans/2026-10-20-github-live-acceptance.md):
dùng App dev hiện tại và kiểm tra refresh thật ngay trong phiên. Các bước
trong kế hoạch chưa được thực hiện tại thời điểm viết checkpoint này.

1. Hoàn tất phép thử Reqable từ `POST /installations/start`: giữ nguyên Bearer
   UTask giữa start/complete, dùng cookie `utask_github_installation` và state
   của lần start mới nhất, hoàn tất trong 10 phút. Cookie này khác
   `utask_github_consent` của luồng authorization.
2. Xác minh response installation `ACTIVE`, rồi GET danh sách installation
   và repository bằng chính token UTask đó; ghi nhận phân trang/quyền hiệu lực.
3. Thử gỡ App và revoke authorization trên GitHub: đối chiếu delivery, job,
   metadata installation và credential. Source đã có xử lý; hành vi GitHub
   thật trong môi trường này **Chưa xác minh**.
4. Nghiệm thu refresh, revoke và phục hồi lỗi với GitHub thật; theo dõi
   webhook khi ngrok hoặc worker ngừng hoạt động.
5. Tích hợp frontend sau: hiện API auth frontend vẫn dùng prefix cũ
   `/api/auth/api/v1/auth`, mong đợi `access_token` trực tiếp; Identity thật
   dùng `/api/auth/login`, trả `data.access` và refresh cookie HttpOnly.
   Local frontend bật mock tại thời điểm kiểm tra. Chưa sửa frontend trong phiên.

Identity vẫn sở hữu phiên đăng nhập UTask; Work sở hữu Project/Task và quyền
nghiệp vụ. Phiên này không thêm API, migration, bảng, đồng bộ domain, AI
context hoặc Kafka event. Chi tiết ranh giới tại [scope và quyền](scope-access.md).
