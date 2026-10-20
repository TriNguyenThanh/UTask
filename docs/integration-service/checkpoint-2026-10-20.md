# Checkpoint Integration Service — 20/10/2026

**Kết quả cuối ngày: các ca GitHub dev trong kế hoạch đã nghiệm thu đạt,
môi trường đã kết nối lại.** Xem [lượt triển khai kế hoạch nghiệm thu](#lượt-triển-khai-kế-hoạch-nghiệm-thu-trong-ngày).
Các mục trước phần đó giữ bằng chứng của lượt chẩn đoán trước.

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

## Lượt triển khai kế hoạch nghiệm thu trong ngày

**Trạng thái: Đã triển khai, đã nghiệm thu luồng GitHub dev theo kế hoạch.**
HEAD đầu lượt `1cc582e`; không deploy. Sau nghiệm thu, người dùng yêu cầu
commit các thay đổi smoke, kiểm thử và tài liệu trong cùng thay đổi.
Không thay đổi `.gitignore` đang có của người dùng. Không sửa API, migration
hoặc code backend chạy trong container nên không cần build lại image.

- **Đã triển khai:** smoke nhận `INTEGRATION_SMOKE_EXPECTED_REPOSITORY_ID`,
  bắt buộc installation ID nếu cấu hình repo kỳ vọng, kiểm ID trước HTTP và
  tìm repo qua tối đa 100 trang. Từ chối pagination thiếu/sai/lặp, thiếu repo
  hoặc vượt giới hạn; không theo redirect và không xuất credential. Giữ
  hành vi đọc trang đầu nếu không cấu hình repo kỳ vọng.
- **Đã triển khai:** [runbook nghiệm thu](live-acceptance.md) là nguồn chuẩn
  cho checklist Reqable, chẩn đoán consent bằng kết quả so khớp, refresh có
  kiểm soát và uninstall/revoke/phục hồi. Quy trình không phải bằng chứng
  rằng các ca GitHub thật đã đạt.
- **Đã xác minh runtime:** API, worker, Beat, Redis và PostgreSQL local
  healthy; gateway và URL ngrok hiện hành trả health 200. Provider
  configuration hợp lệ; feature và các cấu hình bí mật cần thiết có mặt,
  chỉ kiểm tra bằng boolean. Chưa đối chiếu Recent deliveries trên GitHub;
  health không chứng minh webhook đã nhận sự kiện thật.
- **Một phần — actor thử:** đối chiếu đúng UUID người dùng cung cấp từ phiên
  UTask; ban đầu không có mapping account, credential cũ đã hết access hạn,
  pending installation cũ đã hết hạn. Không chọn account khác hoặc sửa
  credential để ép tiếp tục. Người dùng đã cấp quyền lại và gửi response
  authorization complete có cùng actor, `LINKED/ACTIVE` lúc
  `2026-10-20T10:40:30Z`. Chưa tự gọi lại API bằng Bearer của actor.
- **Đã xác minh đọc GitHub live qua service:** với đúng actor thử và
  installation `173352702` do người dùng cung cấp, operator gọi
  `list_repositories` bên trong Integration Service, dùng credential đã lưu.
  Trang 1 (`per_page=100`) trả repo `TriNguyenThanh/kiem_thu_phan_mem`,
  `repository_id=1410043602`, `private=false`, `next_page=null`. Không xuất
  token. Đây là bằng chứng quyền đọc GitHub của service; chưa thay cho
  kiểm tra API có Bearer UTask. Request HTTP qua ngrok không kèm Bearer trả
  `401 NOT_AUTHENTICATED`, đúng ràng buộc xác thực.
- **Đã xác minh API có Bearer:** người dùng cung cấp access UTask để thử;
  nhận qua stdin không echo, không lưu token vào file hoặc command line.
  `GET /api/auth/users/me` qua ngrok trả 200 và actor khớp. Smoke qua gateway
  đạt với installation `173352702`, repo kỳ vọng `1410043602`;
  `installations_on_page=1`, `repositories_on_page=1`. Metadata installation
  local `ACTIVE`, không có pending installation còn hạn chưa dùng. Chưa quan
  sát trực tiếp response POST installation complete từ Reqable.
- **Đã xác minh refresh GitHub thật có kiểm soát:** ngày 20/10/2026, khóa
  generation rồi credential của đúng actor trong transaction; so khớp
  generation 5, version 2, account `LINKED`, credential `ACTIVE`, GitHub
  actor/App khớp, refresh còn hạn và không có claim/pending installation.
  Chỉ cập nhật `expires_at` local thành `2026-10-20T10:50:05.100994Z`, không
  sửa token, version hoặc trường khác. Sau commit chạy lại smoke có Bearer
  qua gateway để GET installations kích hoạt refresh. Smoke tiếp tục đạt và
  vẫn thấy repo kỳ vọng; credential `ACTIVE`, version **2 → 3**, generation
  giữ **5**, claim/started_at null. Access expiry mới
  `2026-10-20T18:50:03.069010Z`, refresh expiry mới
  `2027-04-20T10:50:03.069010Z`. Không phục hồi token cũ.
- **Đã xác minh bỏ quyền repo thử:** người dùng thay repo `1410043602`
  bằng `TriNguyenThanh/annotate-sync` (`1389441701`) trong installation
  `173352702`. List live qua Integration Service trả đúng một repo mới,
  `next_page=null`, repo cũ không còn. Đối chiếu ngrok inspector đúng hai
  delivery GitHub lúc `2026-10-20T10:53:06Z`: action `removed`, delivery
  `6da40bc2-cc74-11f1-8f1b-43b023377b55`, chứa repo cũ; action `added`,
  delivery `6d994570-cc74-11f1-9e41-8cf9cbd4bb6a`, chứa repo mới. Cả hai
  đúng installation, HTTP 202, job WEBHOOK số 5/6 `DONE` ở lần thử đầu sau
  khoảng 4 giây. Metadata `STALE`, source version **1 → 3**. Payload job đã
  được dọn sau xử lý nên đối chiếu action/installation bằng delivery trong
  inspector, không suy ra từ payload job rỗng. Không xuất signature hoặc
  header chứa credential.
- **Đã xác minh khôi phục selection:** lúc `2026-10-20T10:56:10Z`, list
  live chỉ còn repo thử `1410043602`, không còn repo `1389441701`,
  `next_page=null`; installation vẫn `selected`, không suspended. Hai
  delivery lúc `10:55:51Z` đúng installation, HTTP 202: `removed`
  (`d02828d2-cc74-11f1-8cb4-72311413a8d4`) bỏ repo thay thế; `added`
  (`d021e170-cc74-11f1-97f5-68985eceadd6`) thêm lại repo thử. Job 7/8 đều
  `DONE` lần thử đầu, hoàn tất sau khoảng 4 giây. Metadata vẫn `STALE`,
  source version **3 → 5**, đúng cơ chế invalidation; list live không dùng
  cache metadata để cấp quyền.
- **Đã xác minh uninstall:** GitHub gửi `installation/deleted` của
  installation `173352702`, delivery
  `01ded36c-cc75-11f1-8ec5-ebe6106a9ebd`, webhook HTTP 202 lúc
  `2026-10-20T10:57:14Z`. Job 9 `DONE` lần thử đầu sau dưới một giây;
  metadata chuyển `DELETED`, source version **5 → 6**. Kiểm tra live qua
  service trả danh sách installation rỗng, `next_page=null`; đọc repo bằng
  installation cũ bị từ chối với `GITHUB_NOT_FOUND` (status 404 của
  exception). Phép kiểm tra sau uninstall chạy ở domain service bằng
  credential của actor, không phải request gateway có Bearer.
- **Đã xác minh reinstall:** người dùng gửi response installation complete
  `ACTIVE` cho ID mới **173357210**, App `5383972`, selection `selected`,
  không suspended. Delivery `4c5c3fb0-cc75-11f1-9d99-6ed279fece40` là
  `installation/created` của ID mới, chứa repo thử `1410043602`; webhook
  HTTP 202 lúc `2026-10-20T10:59:19Z`, job 10 `DONE` lần thử đầu sau dưới
  một giây. List live qua service chỉ thấy installation mới và đọc được
  repo thử; `next_page=null`. Metadata mới `ACTIVE` version 1; ID cũ vẫn
  `DELETED` version 6 và đọc repo bị từ chối `GITHUB_NOT_FOUND` (404).
- **Đã xác minh revoke authorization:** delivery
  `a793b4b2-cc75-11f1-87cf-ffdfb17485f2`, event
  `github_app_authorization/revoked`, đúng GitHub actor thử, HTTP 202 lúc
  `2026-10-20T11:01:52Z`. Delivery/job 11 `DONE` đồng bộ, attempts 0;
  không chờ worker. So với snapshot trước revoke, generation **5 → 6**,
  credential version **3 → 4**, status `ACTIVE → REVOKED`; cả ciphertext
  access/refresh đã xóa, claim/started_at null. Mapping vẫn `LINKED` nhưng
  `authorization_status=REVOKED`; installation mới vẫn `ACTIVE`, đúng sự
  khác biệt giữa revoke authorization và uninstall. Đọc repo qua domain
  service bị từ chối `GITHUB_REAUTH_REQUIRED` (409). Chưa cấp quyền lại;
  revoke token job gần nhất vẫn là ID 3, dùng làm mốc trước ca DELETE.
- **Đã xác minh cấp quyền lại trước DELETE:** người dùng gửi response
  authorization complete `LINKED/ACTIVE` lúc `2026-10-20T11:03:43Z`, account
  source version 2. Đối chiếu local: generation 7, credential `ACTIVE`
  version 5, hai ciphertext có mặt, claim/started_at null, refresh còn hạn.
  Đọc live qua service với installation `173357210` tiếp tục thấy đúng repo
  thử `1410043602`, `next_page=null`. Mốc revoke job trước DELETE vẫn ID 3;
  chưa thực hiện DELETE.
- **Đã xác minh DELETE từ UTask:** người dùng gửi response account
  `REVOKED/REVOKED` lúc `2026-10-20T11:05:10Z`, GitHub identity trong
  response được ẩn, source version **2 → 3**. Đối chiếu local: mapping và
  credential đều `REVOKED`, credential version **5 → 6**, generation
  **7 → 9**; hai ciphertext đã xóa, claim/started_at null, không còn consent
  chưa dùng hoặc pending installation còn hạn. Có revoke job mới **12**
  (mốc trước DELETE là 3), kind `REVOKE_TOKEN`, `DONE` lần thử đầu lúc
  `11:05:11.445655Z`, khoảng 1,2 giây sau khi nhận job; payload đã dọn.
  Đọc repo qua domain service bị từ chối `GITHUB_REAUTH_REQUIRED` (409).
  Installation `173357210` vẫn `ACTIVE`; DELETE account không uninstall App.
- **Đã xác minh reconnect cuối phiên:** người dùng gửi response API
  repository thành công với đúng repo thử `1410043602`, `next_page=null`.
  Đối chiếu local lúc `2026-10-20T11:08:36Z`: mapping `LINKED`,
  authorization/credential `ACTIVE`, account source version **3 → 4**,
  credential version **6 → 7**, generation **9 → 10**; hai ciphertext có
  mặt, access/refresh còn hạn, claim/started_at null. List live qua service
  chỉ thấy installation `173357210`, `selected`, không suspended, và đúng
  repo thử; không còn trang sau. Installation mới `ACTIVE` version 1; ID
  cũ vẫn `DELETED` version 6. Selection được khôi phục về repo thử duy nhất
  như snapshot trước vòng đời; revoke job 12 vẫn `DONE`.

Các ca live trong kế hoạch đã đạt trong môi trường dev. Nguyên nhân chính
xác của `PARSE_ERROR` installation ở lượt chẩn đoán đầu ngày vẫn **Chưa xác
minh**: không giữ request bí mật để tái hiện. Ở lượt nghiệm thu, pending cũ
đã hết hạn và ban đầu thiếu mapping account; authorization/start mới rồi
installation/start mới đã hoàn tất thành công, không cần sửa backend hoặc
nới kiểm tra consent. Staging/production chưa triển khai hoặc nghiệm thu.

Kiểm tra mới của lượt này, tách khỏi kết quả lịch sử ở trên:

- **524 test Integration đạt** trên PostgreSQL 16 trong container test tạm
  riêng, cổng loopback tự cấp; không dùng database runtime. Đã xóa container
  test sau khi chạy.
- **20 test smoke đạt**, gồm repo xuất hiện/không xuất hiện, trang sau và
  trang giới hạn, cycle, pagination/ID sai, env wiring và lỗi không lộ
  credential. Đã thấy test hồi quy thất bại trước sửa; reviewer chạy lại
  riêng 20 ca và review source.
- **76 test hạ tầng đạt**: local Compose, Integration, staging deployment,
  AI và Classroom. Compose local/staging render hợp lệ với `.env.example`
  và profile Integration/AI/Notification; chỉ validate, không deploy.
- Ruff lint/format check cho hai file smoke/test đạt. Host không có `uv`
  trong PATH; kiểm tra Python/Ruff dùng virtualenv Integration đã có.
- Kiểm tra 44 link/anchor tương đối trong năm tài liệu liên quan, file không
  rỗng và `git diff --check` đạt. Đã sửa anchor Identity trong runbook.

GitNexus đã refresh trước sửa. Symbol `smoke`/`main` có lúc không phân giải,
context theo file không tìm thấy, truy tên đơn lại trả quan hệ đa service
không liên quan và cảnh báo **CRITICAL**. Impact theo file smoke trả LOW;
đã xác minh caller thực tế bằng source/test và review trực tiếp, không dùng
kết quả rỗng hoặc flow vắng mặt làm bằng chứng an toàn. Graph còn giới hạn
phân giải; kết quả kiểm thử không thay nghiệm thu GitHub thật.

Đã refresh lại graph sau thay đổi code và chạy `detect_changes --scope all`:
20 symbol được liệt kê đầy đủ; kết quả vẫn **CRITICAL**, có section tài liệu
bị gắn với flow đa service không liên quan. CLI/MCP còn lệch số process
(557/451); không ghi nhận đây là một gate graph sạch. Reviewer không phát
hiện bug cụ thể qua source/test đã giao.
Review cuối tài liệu sau khi reconnect không phát hiện vấn đề; phân biệt
bằng chứng gateway có Bearer, response Reqable người dùng cung cấp và các
phép kiểm tra domain service/operator. Source/test không đổi sau lượt kiểm
thử nêu trên; không chạy lặp lại suite chỉ để cập nhật checkpoint.

Lượt refresh/chốt cuối tại HEAD `1cc582e` có status `up-to-date`, runner
current, không có incomplete reasons. `detect_changes` trả LOW, 23 symbol,
0 affected, không báo partial/truncated; tuy nhiên danh sách symbol chỉ có
hai tài liệu và file test, thiếu mapping smoke script đã sửa. Kết quả này
khác các lượt CRITICAL trước, nên không dùng số 0 hoặc LOW để khẳng định
graph đã bao phủ thay đổi. Giới hạn GitNexus vẫn chưa giải quyết trong phạm
vi nghiệm thu này; source đã được review, kiểm thử và đối chiếu GitHub live.
