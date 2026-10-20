# Nghiệm thu Integration với GitHub thật

**Trạng thái: Đã triển khai quy trình.** Các ca GitHub dev đã nghiệm thu
ngày 20/10/2026; bằng chứng tại [checkpoint](checkpoint-2026-10-20.md).
Tài liệu này là checklist tái sử dụng theo
[kế hoạch 20/10/2026](plans/2026-10-20-github-live-acceptance.md), không phải
biên bản đã đạt. Ghi kết quả thực tế vào checkpoint của phiên thực hiện.
[API](api.md) và [OpenAPI](../../contracts/api/integration-service-v1.yaml)
giữ hợp đồng; [foundation](foundation.md) giữ hiện trạng source/kiểm thử.

## Chuẩn bị phiên

- Dùng GitHub App dev hiện tại, một actor UTask thử và repository thử riêng.
  Ghi nhận App ID, actor UUID, installation ID, repository ID bằng nhãn thử
  nghiệm trong bằng chứng; không chọn bản ghi đầu tiên trong database.
- Kiểm tra API, gateway, worker, Beat, Redis và database Integration. Kiểm tra
  cấu hình App enabled, App ID/slug, OAuth client, redirect/setup URI,
  credential key ring và webhook bằng kết quả đúng/sai, không in giá trị bí mật.
  App ID khác Client ID; slug chỉ là tên cuối URL App. Cách nạp cấu hình ở
  [foundation](foundation.md).
- Xác nhận URL HTTPS công khai hiện tại, ngrok đang hoạt động và webhook
  trỏ tới `/api/integrations/api/v1/github/webhooks` qua gateway. Đối chiếu
  Recent deliveries của đúng App; không suy ra webhook chạy từ health 200.
- Người dùng thao tác GitHub/Reqable; operator kiểm tra backend và metadata
  Integration. Không đọc/sửa database Identity hoặc Work. Không xóa repo thử,
  sửa quyền repo nghiệp vụ hay thay khóa mã hóa trong phép thử này.
- Reqable giữ cookie theo đúng host/path và gửi Bearer tới đúng API. Không
  tự theo redirect có Bearer sang GitHub. Mở URL GitHub từ response trên
  trình duyệt riêng; chỉ đưa các tham số callback cần thiết về Reqable.
- Dùng cùng origin HTTPS ở start/complete. Cookie consent mặc định `Secure`,
  `HttpOnly`, `SameSite=Lax`, path `/`; cookie Secure không được gửi qua HTTP.
  Không tắt kiểm tra cookie để vượt lỗi. Cookie Identity `refresh_token`
  không thay cookie nonce Integration.

## Checklist Reqable

Ví dụ qua gateway: `ORIGIN` là origin HTTPS đang dùng, không chứa path;
`IDENTITY = ORIGIN/api/auth`, `GITHUB = ORIGIN/api/integrations/api/v1/github`.
Các tên này chỉ là ký hiệu tài liệu. Gửi JSON với
`Content-Type: application/json` ở request có body. Request start/account
không có query và **không có body**, kể cả `{}`. Dùng
`Authorization: Bearer <access UTask>` cho mọi request Integration bên dưới.

| Bước | Request | Kiểm tra trước khi đi tiếp |
| --- | --- | --- |
| 1. Login | POST `IDENTITY/login`; JSON `{"email":"<email thử>","password":"<mật khẩu>"}`; có thể dùng `username` thay `email`, không gửi cả hai | 200, `success=true`; lấy access từ **`data.access`**, không phải `access_token` hoặc `data.refresh`. Giữ token trong vùng bí mật Reqable. |
| 2. Xác minh actor | GET `IDENTITY/users/me` bằng access vừa nhận | 200; lấy `data.id` làm actor UUID để đối chiếu `user_id` Integration. Không gửi `user_id` vào API Integration. |
| 3. Account ban đầu | GET `GITHUB/account` | `data.user_id` khớp actor; ghi `status`, `authorization_status`, `source_version`. Chưa kết nối có thể `UNLINKED/NOT_AUTHORIZED`. |
| 4. Authorization start | POST `GITHUB/authorizations/start` | 200; lưu riêng `data.authorization_url`, `data.expires_at` và cookie **`utask_github_consent`** từ Set-Cookie. |
| 5. Consent GitHub | Mở nguyên `authorization_url`; cấp quyền bằng đúng GitHub account thử | Lấy `code` và `state` từ query callback. URL-decode từng giá trị đúng một lần; không dùng cả URL, không giữ `%xx` đã mã hóa, không decode hai lần. Không lưu URL callback vào bằng chứng. |
| 6. Authorization complete | POST `GITHUB/authorizations/complete`; JSON đúng hai trường `{"code":"<code callback>","state":"<state callback>"}` | Cùng Bearer ở bước 4, cookie consent của bước 4; còn hạn 600 giây. 200, account `LINKED`, `authorization_status=ACTIVE`, actor đúng. Cookie consent được xóa khi thành công. |
| 7. Installation start | POST `GITHUB/installations/start` | 200; lưu riêng `data.installation_url`, `data.expires_at`, cookie **`utask_github_installation`** mới. Không dùng cookie consent ở bước 4. |
| 8. Cài App | Mở nguyên `installation_url`; chọn đúng account và repo thử | Lấy `state`, `installation_id`, `setup_action` từ query callback, URL-decode một lần. `installation_id` là chuỗi ID số dương, không phải App ID/repository ID. |
| 9. Installation complete | POST `GITHUB/installations/complete`; JSON đúng `{"state":"<state callback>","installation_id":"<ID>","setup_action":"install"}` | Dùng `setup_action` thực nhận (`install`, `update` hoặc `request`), cùng Bearer/cookie/state của bước 7, trong 600 giây. `install/update` cần 200 và `data.status=ACTIVE`. `request` trả `PENDING_APPROVAL`, chưa đạt ca ACTIVE. |
| 10. Đọc live | GET `GITHUB/installations?page=1&per_page=100`, rồi GET `GITHUB/installations/<ID>/repositories?page=1&per_page=100` | 200, `{items,next_page}`; theo các trang tới hết, thấy đúng installation/repository ID thử. Metadata local không thay bằng chứng quyền live. |

Xem [Identity hiện hành](../identity-service/README.md#api-để-tích-hợp) và
[đặc tả login](../architecture/Identity_Service_API_Specification.md#313-login-bằng-email-hoặc-username).
Không xuất access/refresh, mật khẩu, cookie, code hoặc state vào log, screenshot
chia sẻ, checkpoint hay lịch sử lệnh.

### Khi complete lỗi

`PARSE_ERROR` chưa chứng minh lỗi backend. Source dùng mã này cho JSON sai,
cookie thiếu/sai, state không khớp, hết hạn, đã dùng hoặc Bearer không khớp.
Lỗi `NOT_AUTHENTICATED` cần kiểm tra Bearer trước. Start mới hủy pending cũ;
complete có thể đã tiêu thụ state trước khi gọi GitHub nên không retry code
hoặc state cũ sau lỗi/timeout.

1. Bắt đầu lại đúng luồng lỗi bằng một lần start mới. Giữ đúng cookie của
   response mới và chỉ hoàn tất callback đó. Nếu access UTask hết hạn/đã
   refresh hoặc login lại giữa start/complete, xác minh `/users/me` rồi start
   mới bằng access mới. Cùng actor nhưng khác chuỗi Bearer vẫn không khớp.
2. Kiểm tra tại Reqable bằng boolean: có đúng header Bearer, cùng Bearer,
   đúng cookie theo host/path, state callback khớp state URL start, còn TTL,
   body đúng tập trường/kiểu, không query thừa. Không in giá trị để so sánh.
3. Operator đối chiếu đúng actor với pending: tồn tại, `consumed_at` rỗng,
   `expires_at` còn hạn, `session_hash` và `nonce_hash` khớp bằng phép so sánh
   trong bộ nhớ. Chỉ ghi kết quả đúng/sai, không log hash hoặc đầu vào bí mật.
   Với installation còn cần `generation` khớp `GitHubConsentGeneration`,
   `installation_generation` khớp `GitHubInstallationGeneration`,
   `credential_version` khớp credential hiện tại và credential `ACTIVE`.
4. Nếu refresh credential hoặc consent mới làm đổi version/generation giữa
   start/complete, start installation mới; không sửa pending để ép khớp.
   Chỉ kết luận lỗi backend sau khi tái hiện với request mới đáp ứng các ràng
   buộc trên; thêm test hồi quy trước khi sửa hành vi.

## Smoke chỉ đọc

Sau khi consent/cài App thành công, đặt biến môi trường qua kênh bí mật:

| Biến | Ý nghĩa |
| --- | --- |
| `INTEGRATION_SMOKE_URL` | Root Integration hoặc gateway kết thúc bằng `/api/integrations`; HTTPS, hoặc HTTP loopback; không query, fragment hay credential trong URL. |
| `INTEGRATION_SMOKE_BEARER` | Access UTask của actor thử, không phải token GitHub. |
| `INTEGRATION_SMOKE_INSTALLATION_ID` | ID installation thử; cần để kiểm repository. |
| `INTEGRATION_SMOKE_EXPECTED_REPOSITORY_ID` | Tùy chọn ID repo số dương dạng chuỗi; khi đặt thì **bắt buộc có installation ID**. Đặt để nghiệm thu chính xác repo thử. |

Từ root repo chạy script hiện có:

```bash
uv run --project apps/integration-service python scripts/smoke_integration_github.py
```

Script chỉ GET account/installation/repository và không theo redirect mang
Bearer. Khi chỉ định repo kỳ vọng, script tìm qua `next_page`, tối đa 100
trang; thiếu repo, ID sai, pagination thiếu/sai hoặc lặp phải thất bại, không
coi trang đầu rỗng là đã đạt. Không in Bearer/response cá nhân. Script không
ép refresh, revoke hay uninstall; GET có thể kích hoạt refresh tự nhiên nếu
credential đã gần hết hạn theo luồng backend hiện có. Kết quả smoke không
thay bằng chứng các ca refresh/vòng đời dưới đây.

## Refresh thật có kiểm soát

Đây là thao tác operator thay đổi **metadata credential thử trong database
Integration**, tách khỏi smoke. Không thêm endpoint force refresh hoặc thay
runtime mặc định. Phần này mô tả các trường và thứ tự khóa; không cung cấp
lệnh sửa database để chạy hàng loạt.

1. Hoàn tất ca đọc live và chọn `GitHubAccount`, `GitHubCredential`,
   `GitHubConsentGeneration` bằng **actor UUID từ `/users/me`**. Đối chiếu
   account `LINKED`, `github_user_id` giữa account/credential khớp và
   credential `app_id` đúng App dev. Giữ yên các request cùng actor, không
   consent/unlink/revoke đồng thời. Ghi snapshot metadata gồm generation,
   credential version/status và các thời hạn, không lấy nội dung token.
2. Trong một transaction ngắn, khóa row `GitHubConsentGeneration` của actor
   trước, rồi khóa `GitHubCredential` bằng `select_for_update`, cùng thứ tự
   `lock_generation` → credential của source. Đọc lại và so với snapshot:
   `generation` và `version` phải chưa đổi, account vẫn khớp;
   `status=ACTIVE`, `refresh_expires_at` còn hạn đủ cho phép thử,
   `refresh_claim` và `refresh_started_at` đều null. Nếu khác hoặc đang
   `REFRESHING`, dừng, không ghi đè claim hay sửa status để tiếp tục.
3. Chỉ đặt **`expires_at` local = thời điểm hiện tại + 30 giây**, rồi commit.
   Giữ nguyên ciphertext access/refresh, `refresh_expires_at`, version,
   generation, status, claim và mọi trường khác. Thao tác này không thay hạn
   token tại GitHub. Không gọi HTTP/GitHub khi còn giữ khóa.
4. Sau khi commit, gửi GET `GITHUB/installations` bằng actor đó để gọi luồng
   refresh hiện có: access còn dưới ngưỡng 60 giây nên backend claim refresh,
   nhả khóa trước HTTP và chỉ lưu kết quả nếu generation/version/claim còn
   khớp. Không bắn nhiều request đồng thời để ép refresh.
5. Đọc lại metadata: generation giữ nguyên; credential `ACTIVE`, version tăng
   đúng một trong phép thử cô lập, `expires_at` mới lớn hơn giá trị 30 giây
   vừa đặt, `refresh_expires_at` cập nhật theo response provider còn hạn,
   `refresh_claim`/`refresh_started_at` trở về null. GET repository thử phải
   tiếp tục 200 và thấy đúng repo qua các trang. Chỉ lưu version, thời hạn,
   trạng thái và boolean; không so/in ciphertext hoặc plaintext token.
6. Nếu refresh timeout/lỗi mơ hồ, source chuyển `REAUTH_REQUIRED` và không
   retry cặp refresh cũ vì GitHub có thể đã xoay token. Giữ trạng thái này,
   cấp quyền lại qua authorization mới rồi installation mới khi cần; không
   khôi phục token cũ hay đổi `ACTIVE` thủ công. `GITHUB_REFRESH_IN_PROGRESS`
   là ca chưa đạt; không xóa claim để thử lại. Nếu generation/version đổi do
   cạnh tranh, ghi ca không kết luận và phục hồi bằng consent mới.

Nguồn đối chiếu:
[model credential](../../apps/integration-service/apps/github_accounts/models.py),
[fencing refresh](../../apps/integration-service/apps/github_accounts/credentials.py)
và [list live](../../apps/integration-service/apps/github_installations/services.py).

## Vòng đời quyền và phục hồi

Chạy tuần tự trên repo thử. Với mỗi thao tác GitHub, ghi thời điểm bắt đầu,
response API, delivery ID/event/action và metadata/job trong cửa sổ quan sát
**60 giây**. Deadline này là tiêu chí quan sát phiên, không phải cam kết mọi
retry phải xong trong 60 giây. Chưa có delivery thì kiểm ngrok, URL webhook,
Recent deliveries và response HTTP trước khi kết luận worker lỗi. Nếu cần,
redeliver delivery của đúng phép thử sau khi đường webhook hoạt động lại;
đối chiếu delivery ID/fingerprint và job, không tạo event giả thay bằng chứng
GitHub thật. Job `FAILED/PENDING/PROCESSING` chưa chứng minh xử lý đã đạt.

| Ca | Thao tác và điều kiện đạt | Phục hồi |
| --- | --- | --- |
| Bỏ quyền repo thử | Ghi lại `repository_selection` và tập repo được chọn trước khi sửa trên GitHub; bỏ riêng repo thử. GET live qua hết trang không còn repo đó; webhook `installation_repositories/removed` có delivery/job và metadata được invalidated (`STALE`, version tăng) nếu row đã lưu. Không dùng cache local để kết luận quyền. | Khôi phục đúng selection/tập repo cũ trên GitHub; xác minh repo xuất hiện lại và delivery tương ứng. Nếu App đang chọn tất cả repo, chỉ đổi selection trên installation thử và ghi đủ để trả lại cấu hình cũ. |
| Uninstall App | Gỡ đúng App dev/installation thử. Webhook `installation/deleted` được nhận 202, job `WEBHOOK` hoàn tất `DONE`; row đã lưu chuyển `DELETED`, `source_version` tăng. GET installation/repository không còn truy cập được installation cũ. | Nếu delivery thiếu, chẩn đoán và redeliver như trên; không tự sửa metadata thành `DELETED` để đánh dấu đạt. |
| Cài lại | Start installation mới, cài lại repo thử, complete `ACTIVE`, đọc lại repo thành công. | Lấy installation ID từ callback mới và đối chiếu bằng API live; không sao chép ID của lần đã uninstall để mặc định dùng lại. Ghi nhận ID thực nhận của lần cài lại. |
| Revoke authorization trên GitHub | Thu hồi quyền của account thử đối với App. Delivery `github_app_authorization/revoked` có status `DONE`; thu hồi local xảy ra đồng bộ khi nhận delivery: generation/version tăng, credential `REVOKED`, cả `encrypted_access_token` và `encrypted_refresh_token` rỗng, claim null. Account API có `authorization_status=REVOKED`; mapping có thể vẫn `LINKED`. GET live đòi cấp quyền lại. | Authorization start/complete mới; nếu cần installation start/complete mới; xác minh account `ACTIVE` và đọc repo lại trước ca DELETE. Không yêu cầu một job async riêng cho revoke authorization vì delivery này hoàn tất đồng bộ. |
| DELETE từ UTask | Sau khi đã cấp quyền lại để có credential `ACTIVE`, DELETE `GITHUB/account` không body/query. Mapping `REVOKED`, credential `REVOKED`, token local rỗng, consent cũ bị hủy; `REVOKE_TOKEN` job mới được tạo và xử lý `DONE` trong cửa sổ quan sát. Không đọc payload job có ciphertext. | Nếu DELETE ngay sau credential đã revoked, có thể không có revoke job mới; thao tác lặp đó không nghiệm thu được đường tạo job. Ghi rõ ca đã dùng credential active. |
| Kết nối lại cuối phiên | Authorization mới, installation mới khi cần; account `LINKED/ACTIVE`, installation complete `ACTIVE`, GET live và smoke thấy repo thử. | Để môi trường ở trạng thái hoạt động, selection repo đã khôi phục; ghi ca chưa đạt và cách phục hồi còn lại nếu bị chặn. |

## Mẫu bằng chứng không chứa credential

Metadata lấy bằng quyền operator của Integration. Chỉ ghi token đã xóa hay
chưa dưới dạng boolean; không dump model/job payload, header, Set-Cookie,
callback URL, token, code, state, nonce, hash hoặc key. Dùng nhãn actor/repo
trong tài liệu chia sẻ; bản ghi đối chiếu ID giữ tại nơi nội bộ phù hợp.

Bảng dưới là mẫu trống để sao chép cho phiên mới, không phải kết quả của
phiên đã ghi trong checkpoint.

| Ca | Thời điểm UTC / nhãn actor–App–installation–repo | API HTTP / trạng thái | Delivery ID, event/action / job status | Metadata trước → sau hoặc boolean | Kết quả / bằng chứng đã làm sạch |
| --- | --- | --- | --- | --- | --- |
| Login → account → installation → repo | Chưa chạy | Chưa xác minh | Không áp dụng | actor_match / cookie_match / state_match / ttl_valid | Chưa xác minh |
| Refresh thật | Chưa chạy | Chưa xác minh | Không áp dụng | generation, version, status, expiry, claims_null | Chưa xác minh |
| Bỏ quyền repo và khôi phục | Chưa chạy | Chưa xác minh | Chưa xác minh | repo_absent → repo_present / selection_restored | Chưa xác minh |
| Uninstall → reinstall | Chưa chạy | Chưa xác minh | Chưa xác minh | DELETED / new_installation_id / repo_present | Chưa xác minh |
| GitHub revoke → cấp quyền lại | Chưa chạy | Chưa xác minh | Chưa xác minh | credential_REVOKED / tokens_cleared / ACTIVE | Chưa xác minh |
| DELETE → reconnect cuối | Chưa chạy | Chưa xác minh | Chưa xác minh | mapping_REVOKED / tokens_cleared / ACTIVE | Chưa xác minh |

Chỉ đánh dấu **Đã xác minh** sau khi điền bằng chứng thật của đúng ca.
Kiểm thử mock, PostgreSQL test và smoke local trong checkpoint cũ không
chứng minh GitHub live đã đạt.
