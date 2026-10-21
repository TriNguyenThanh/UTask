# Kiểm chứng deploy và HTTP staging local — 21/10/2026

## Kết luận cập nhật sau sửa — 22/10/2026

**Đã triển khai và kiểm lại các lỗi đã chứng minh trong phạm vi này.** Tên
đăng ký đã có trong event và projection Work; cập nhật hồ sơ đã đi hết Kafka
và hiển thị đúng qua HTTP Work. COMMIT sai định dạng trả 400; branch/commit
hợp lệ, replay và connect/disconnect vẫn chạy với GitHub thật. Script deploy
staging chạy lại thành công trên máy local với image mới và `.env.staging`.

Đây là kết quả trên các ca đã chạy, không phải chứng nhận toàn bộ nghiệp vụ
hoặc độ ổn định dài hạn. Chi tiết bản sửa, kiểm thử và giới hạn nằm ở
[phần kiểm lại ngày 22/10](#kiem-lai-20261022). Các mục phía dưới trước phần đó
giữ bằng chứng của **snapshot trước sửa ngày 21/10**, không mô tả source hiện tại.

## Kết luận snapshot trước sửa — 21/10/2026

**Một phần.** Đã chạy nguyên script deploy staging trên máy local và kiểm HTTP
thật cho Work–Identity cùng luồng GitHub connect/confirm, branch/commit,
receipt/replay, disconnect và recovery sau khi worker dừng. Consent/cài App
đã hoàn tất với GitHub thật. Chưa nghiệm thu PR thành công vì repo thử không có
PR, hoặc mọi tình huống crash/race/thu hồi quyền trên provider.

Deploy bằng volume mới thành công, nhưng nâng cấp trên volume local cũ dừng
do credential PostgreSQL không khớp. Phân quyền và thu hồi phiên hoạt động
đúng trong các ca đã chạy. Đồng bộ hồ sơ chưa đạt: sự kiện đăng ký mang tên
rỗng, còn sự kiện cập nhật đang retry trên broker cloud thật.

Đây là kiểm chứng runtime của bốn backend đã chọn, không phải chứng nhận
toàn bộ hệ thống, GitHub Actions hosted, VPS hoặc toàn bộ nghiệp vụ Work.

## Cách deploy và những khác biệt đã khai báo

- Đã đọc [workflow release](../../.github/workflows/release-staging.yml),
  [script deploy](../../scripts/deploy_staging.sh), Compose staging, mapping
  môi trường và source đường gọi trực tiếp.
- Dọn 27 container UTask cũ, 13 tag image UTask và cache build. Giữ volume dữ
  liệu cũ, image ngoài UTask; không reset database hoặc credential cũ.
- Build source worktree hiện tại của Identity, Classroom, Work, Integration;
  push registry local và pin digest cho 14 tiến trình app/worker/migration.
  Không push GHCR, không SSH hoặc triển khai VPS. Registry local chỉ phục vụ
  kiểm chứng thao tác login/push/pull và image theo digest.
- Sao chép bộ file release như workflow vào thư mục server tạm ngoài repo.
  Script deploy dùng bản `.env` là bản sao của `.env.staging` thật, không dùng
  fixture adapter. Đã chạy nguyên `scripts/deploy_staging.sh`: resolve/pull,
  kiểm Nginx, chờ hạ tầng, migration, runtime, reload Nginx, kiểm migration và
  health qua gateway.
- Theo xác nhận của người dùng, hoàn thiện tám biến kết nối trong chính
  `.env.staging`: adapter/cờ Work, khóa Work→Integration, danh sách khóa nhận
  của Work, cờ connection/Kafka Integration và khóa Integration→Work. Hai
  chiều dùng khóa khác nhau, giữ credential khác; không in giá trị bí mật.
- Cổng 80 bị Windows sử dụng; runtime ghi đè `UTASK_HTTP_PORT` thành
  `127.0.0.1:18080`. Không thay Compose. Bốn profile được chọn là Identity,
  Classroom, Work, Integration; AI không thuộc lượt này và không chạy live gate AI.
- Dùng đúng Aiven staging, topic/group thật. Đã phát hiện consumer của
  deployment khác trong hai group Work–Classroom; người dùng yêu cầu tiếp tục
  dùng trực tiếp. Không đổi/reset offset, không ép consumer khác rời group.
  Vì vậy kiểm Kafka không có tính độc lập giữa hai deployment.
- Tạo đúng hai topic Integration còn thiếu bằng mặc định broker:
  `utask.integration.events`, `utask.work.integration.dlq`. Không sửa ACL,
  credential, retention hoặc các topic đã có.

## Kết quả deploy

1. Project `utask`, volume cũ: script exit 1 ở migration Identity;
   `password authentication failed for user "utask"`. PostgreSQL vẫn healthy
   vì healthcheck dùng `pg_isready`, không kiểm đăng nhập TCP với credential
   của ứng dụng. Đây là lệch trạng thái môi trường local, chưa phải bằng chứng
   migration/schema bị lỗi. Xem [healthcheck](../../docker-compose.staging.yml:70)
   và [migration gate](../../scripts/deploy_staging.sh:71).
2. Project `utask-staging-local-20261021`, volume mới riêng, cùng file staging
   và credential: script exit 0. Bốn health URL gateway trả 200. Snapshot sau
   deploy có 16 runtime healthy và migration Integration exited 0.
3. Đã thử tạm dừng riêng API Identity trong stack local: Work/Integration trả
   503 `IDENTITY_UNAVAILABLE`; sau khởi động lại, Work nhận token hợp lệ và
   trả 200. Không dừng dịch vụ trên VPS.

Không gọi lượt dùng volume mới là nâng cấp thành công trên dữ liệu cũ. Không
thay mật khẩu role hoặc xóa volume để làm lượt nâng cấp báo xanh.

## HTTP và dữ liệu thật đã kiểm

Ghi nhận 124 quan sát: **113 đúng kỳ vọng, 3 kết quả runtime chưa đạt, 8 lỗi đầu
vào hoặc kỳ vọng của probe**. Tám quan sát không tính thành lỗi backend: thiếu
Idempotency-Key; hai request identifier quá dài; poll dùng thứ tự tên khác
trigger; reference chưa có connection trả 404; probe dùng token outsider đã
thu hồi; receipt đổi payload dùng 422; tạo link khi disconnected dùng 400.
Đã gọi lại với input/session đúng hoặc đối chiếu source. Ba kết quả chưa đạt
là hồ sơ Work khác Identity, commit sai định dạng trả 503 và một lần timeout
tra PR (lần gọi lại trả 404). Không cộng với số pytest của lượt trước.

| Nhóm | Kết quả đã kiểm bằng HTTP thật |
| --- | --- |
| Identity → Work | Đăng ký/đăng nhập, JWT thật qua JWKS/session-status; thiếu hoặc sai Bearer bị 401; token hợp lệ đọc được Project theo quyền |
| Quyền Project | Leader tạo 201 và replay cùng key; Member tạo bị 403; Leader/Member/Teacher đọc 200; outsider/Admin không có quyền tài nguyên nhận 404 |
| Phiên và tài khoản | Logout, logout-all, refresh rotation/reuse, đổi mật khẩu, suspend đều làm Work từ chối access cũ; restore không phục hồi phiên; Integration cũng từ chối phiên logout |
| Vai trò Teacher | Thu hồi role làm token cũ bị 401; đăng nhập lại vẫn không đọc được Project theo quyền Teacher đã mất, trả 404; đã khôi phục role cho tài khoản thử |
| Identity ngừng | Work và Integration trả 503, không bỏ qua xác thực; Work hoạt động lại sau khi Identity khởi động |
| Hồ sơ Kafka | GET thành viên Work không khớp tên authoritative từ Identity; đã đối chiếu outbox Identity và projection/receipt Work bằng shell chỉ đọc của từng service |
| Avatar R2 | Presign → PUT → confirm đều 200; người khác confirm cùng key bị 400; file thuộc tài khoản thử, không dùng mock storage |
| Work → Integration | Member/Teacher bị 403, outsider 404; repo ID sai bị 400; Leader chưa cấp GitHub consent nhận 409; không tạo kết nối giả |
| Internal trust boundary | Prepare sai key 403, key đúng nhưng thiếu actor 401; status/confirm/abort operation không tồn tại trả 404; receipt sai/thiếu key 403 và đúng key nhưng chưa có acceptance trả 404 |
| Gateway | Receipt nội bộ bị chặn 404 qua public prefix |
| GitHub consent/installation | Hai callback do người dùng xác nhận qua trình duyệt; complete trả 200, account LINKED/ACTIVE, installation ACTIVE; danh sách repository thật trả 200 |
| Kết nối GitHub thành công | Work 202 PENDING → CONNECTED sau khoảng 2 giây; replay cùng operation trả đúng acceptance; generation cũ bị 409, payload đổi bị 422 |
| Task reference thật | Branch/commit 201 CONFIRMED, is_verified=true; replay không tạo link trùng; Member tạo/gỡ branch, confirm/replay 200; Task không tự đổi state; không có PR để kiểm ca thành công |
| Disconnect và recovery | Dừng Work publisher local, DELETE vẫn commit 202 PENDING, chặn lệnh/link mới 409; start worker thì DISCONNECTED; replay khớp, receipt connect/disconnect vẫn bất biến PENDING/no-store |
| Kafka Integration | Hai event connect/disconnect đầu PUBLISHED trong outbox Integration, có đúng hai receipt tiêu thụ tương ứng trong Work; xác minh theo event_id, không suy từ health |

Tạo một admin bằng command bootstrap sẵn có trong database mới; đăng ký bốn
tài khoản thử, gán role Teacher, tạo Course/Class/Group/Project bằng HTTP.
Các thay đổi session/password/status chỉ tác động tài khoản thử. Không chèn
Project/member/connection hoặc credential GitHub bằng SQL, không monkeypatch
dịch vụ, không tạo file test, không dùng pytest fixture làm provider thật.

## Các vấn đề có bằng chứng ở snapshot trước sửa

### P1 — Event đăng ký mang tên hiển thị rỗng

**Đã tái hiện:** bốn tài khoản đăng ký qua HTTP có tên trong Identity nhưng
bốn outbox `identity.user.created` có `data.display_name=""`, đã được publish.
Projection của bốn user tương ứng trong Work cũng rỗng; GET members trả tên rỗng.

[RegistrationService](../../apps/identity-service/accounts/services/registration.py:33)
tạo `UserProfile` với tên rỗng rồi gọi `emit_user` ở dòng 44.
[Trigger PostgreSQL](../../apps/identity-service/accounts/migrations/0001_initial.py:12)
sinh tên nhưng instance Python được cache chưa được đọc lại;
[emit_user](../../apps/identity-service/messaging/outbox.py:30) đọc `user.profile`.
Work chỉ [chiếu tên từ projection](../../apps/work-service/apps/projects/queries/projects.py:104),
không tự bịa tên thay sự kiện.

**Ảnh hưởng:** thành viên mới có thể hiện tên trống cho tới khi có event cập nhật
đúng được xử lý. **Hướng sửa nhỏ nhất:** đọc lại hồ sơ sau trigger trước khi tạo
event đăng ký; giữ transaction hiện có, kiểm cả payload outbox. Luồng PATCH đã
[refresh hồ sơ](../../apps/identity-service/accounts/services/profiles.py:25).
Chưa sửa source trong lượt kiểm chứng ngày 21/10; không sửa migration lịch sử.

### P1 — Đồng bộ hồ sơ chưa hoàn tất trên broker staging

**Đã tái hiện:** PATCH hồ sơ trả 200 và Identity giữ đúng tên, nhưng event
`6ff0edeb-5796-43b7-8091-f2dbef0678e7` còn pending ở snapshot, retry 8 lần,
`last_error=RuntimeError`. Snapshot cập nhật sau kiểm GitHub ghi retry 13;
event avatar tiếp theo của cùng user chưa được gửi.
Publisher có log không lấy được idempotence PID từ broker; một số event khác
sau nhiều retry đã ACK. Container publisher/consumer healthy, restart 0.

[Producer](../../apps/identity-service/messaging/kafka.py:15) hiện đặt delivery
timeout 5 giây và flush 6 giây.
[Dispatcher](../../apps/identity-service/messaging/publisher.py:54) tạo producer
trong mỗi lần drain; lỗi giữ outbox và tăng backoff. Đây là cơ chế không mất dữ
liệu, nhưng chưa chứng minh được thời gian đồng bộ chấp nhận được trên môi trường này.

**Giới hạn kết luận:** chưa tách được latency/broker/client lifecycle thành
nguyên nhân duy nhất; không kết luận mật khẩu SASL sai hoặc consumer Work sai.
Không nới timeout tùy tiện để báo đạt. Cần đo thời gian kết nối/ACK với đúng
client và cấu hình hiện hành trước khi chọn sửa producer lifecycle/budget.
Group dùng chung cũng làm việc nhận event giữa các database không độc lập.

### P2 — Volume cũ không dùng được credential staging hiện tại

**Đã tái hiện:** PostgreSQL healthy nhưng migration đăng nhập TCP thất bại.
Biến `POSTGRES_PASSWORD` lúc recreate không đổi mật khẩu role đã tồn tại trong
volume. Script dừng trước khi rollout ứng dụng; không công bố deploy thành công.

**Hướng xử lý:** xác minh credential của đúng volume/role và đồng bộ có chủ ý;
không xóa volume hoặc tự reset mật khẩu. Fresh-volume pass chỉ chứng minh
đường cài mới với credential staging, không giải quyết dữ liệu cũ.

### P2 — Commit sai định dạng bị báo thành provider không khả dụng

**Đã tái hiện:** khi đang CONNECTED, POST Task GitHub link với
`link_type=COMMIT`, `github_ref_id=not-a-sha` trả 503
`INTEGRATION_UNAVAILABLE`. Không tạo link.

[Serializer Work](../../apps/work-service/apps/integrations/serializers/links.py:36)
chỉ kiểm ref PR, còn [validator Integration](../../apps/integration-service/apps/github_connections/validation.py:76)
chấp nhận chuỗi ref commit chưa đúng SHA. Sau khi kiểm connection live,
[GitHubProjectClient](../../apps/integration-service/infrastructure/github_project.py:213)
nhận commit không khớp 7–40 ký tự hex và ném `GitHubOAuthUnavailable` tại dòng
223. Đây là input sai xác định được, không phải bằng chứng provider tạm hỏng.

**Hướng sửa nhỏ nhất:** chặn định dạng commit ở validation có sẵn trước khi gọi
provider; giữ response validation tiếng Việt và không ghi link. Không cần thêm
service, cache hay cơ chế retry cho input này. Chưa sửa source trong lượt ngày 21/10.

### P2 — Budget chờ Work ngắn hơn thời gian xử lý provider hợp lệ

**Đã tái hiện:** tra PR không tồn tại qua Work có một lần trả 503. Log Work
ghi `ReadTimeout`; cùng request ở Integration hoàn tất 404 sau 3,195555 giây.
Gọi lại cùng ref qua Work trả 404 đúng. Không tạo link ở cả hai lần.

[RemoteIntegration](../../apps/work-service/infrastructure/integration.py:259)
đặt read timeout 3 giây. [Provider reference](../../apps/integration-service/apps/github_connections/services.py:514)
kiểm credential/connection, tìm repository live rồi xác minh ref bằng các
lượt HTTP GitHub tuần tự. Mỗi request GitHub có budget riêng, nên tổng thời
gian có thể vượt budget Work dù từng request vẫn hợp lệ.

**Hướng sửa nhỏ nhất:** thống nhất budget end-to-end tại adapter/config hiện
có dựa trên số lần gọi và thời gian đã đo; không mở timeout vô hạn, không bỏ
kiểm quyền hoặc dùng metadata cũ để báo thành công. Lượt này chứng minh budget
lệch ở một request thật, chưa đo phân bố latency/load dài hạn; chưa sửa source.

## Giới hạn của lượt kiểm ngày 21/10

- Đã hoàn tất OAuth/cài App, connect/confirm, receipt 200, event cuối,
  branch/commit, replay và disconnect với GitHub thật. Recovery đã kiểm khi
  Work publisher dừng rồi chạy lại, không phải mô phỏng mất phản hồi prepare.
  Repo thử không có PR: chỉ kiểm PR không tồn tại, chưa có ca PR thành công.
  Chưa thử uninstall/revoke repo thật, refresh token GitHub đến hạn, crash ở
  mọi ranh giới hoặc các race của operation đang được ghi trong review trước.
- Reference metadata được khám phá bằng client GitHub thật trong shell của
  Integration; các mutation/link kiểm qua HTTP Work thật. Không có lời gọi
  GitHub từ Work hoặc script HTTP host. Không tạo commit/PR hay sửa repo thử.
- Không chuyển credential/account của deployment khác vào database mới để
  vượt consent. File URL cấp quyền và callback phục vụ operator nằm trong thư
  mục tạm riêng; không đưa token, code, state hoặc URL ký vào báo cáo/repo.
- Chưa nghiệm thu mail/Notification, AI, frontend, TLS/Cloudflare, SSH và GHCR,
  hoặc hosted CI. Không lấy health/JUnit của lượt trước thay bằng chứng lần này.
- Stack local vẫn chạy ở `http://127.0.0.1:18080`; snapshot cuối có 16 runtime
  healthy, migration Integration exited 0, không restart bất thường. API
  Identity và Work publisher đã được stop/start có chủ đích để kiểm lỗi phụ
  thuộc và recovery. Project thử cuối cùng DISCONNECTED, link thử đã gỡ;
  không uninstall GitHub App hoặc revoke credential người dùng. Volume/project
  cũ vẫn giữ và dừng. Không commit/deploy VPS.

Artifact ngoài repo nằm ở thư mục tạm `utask-staging-deploy-20261021-yymvwmys`:
exit/log deploy, digest image, bảng `http-validation-results.json`, snapshot
container và evidence outbox. File credential riêng không phải artifact chia sẻ.

<a id="kiem-lai-20261022"></a>

## Sửa và kiểm lại — 22/10/2026

### Thay đổi nhỏ nhất đã thực hiện

| Vấn đề | Bản sửa và căn cứ source |
| --- | --- |
| Event đăng ký tên rỗng | [RegistrationService](../../apps/identity-service/accounts/services/registration.py:34) đọc lại `display_name` sau trigger trước `emit_user`; giữ transaction và migration hiện có. |
| Publisher timeout khi mới kết nối | [Command watch](../../apps/identity-service/accounts/management/commands/publish_identity_outbox.py:23) dùng lại một producer, chỉ khởi tạo khi cần gửi. [KafkaPublisher](../../apps/identity-service/messaging/kafka.py:15) chờ delivery 30 giây, flush 31 giây; [drain_outbox](../../apps/identity-service/messaging/publisher.py:21) có budget 35 giây. Chỉ ghi `published_at` khi ACK, giữ thứ tự/retry/backoff. |
| COMMIT sai trả 503 | [Serializer Work](../../apps/work-service/apps/integrations/serializers/links.py:43) và [validator Integration](../../apps/integration-service/apps/github_connections/validation.py:76) chặn mã không đủ 7–40 ký tự hex ASCII, trả 400 trước provider. |
| Work ngắt chờ sau 3 giây | [RemoteIntegration](../../apps/work-service/infrastructure/integration.py:259) dùng timeout kết nối/đọc 2/20 giây. Vẫn giới hạn thời gian và kiểm quyền live; không thêm cache hoặc bỏ kiểm repository/reference. |
| Volume local cũ khác credential staging | Đã xác minh đăng nhập TCP qua IP mạng Docker: `.env` local thành công, `.env.staging` bị từ chối mật khẩu. Giữ volume/project local và staging riêng; không sửa role/password hoặc xóa dữ liệu. Xem [quy tắc môi trường](environment.md#phan-tach-volume-local-staging). |

Đo bằng client và cấu hình thật trong container **Identity publisher**, gửi lại
cùng event đang pending: giới hạn cũ thất bại sau **5,016 giây**; producer mới
với giới hạn 30 giây được ACK sau **6,292 giây**; dùng lại producer được ACK sau
**0,360 giây**. Các số này là mẫu đo tại thời điểm kiểm, không phải phân bố
latency dài hạn. Log startup mới vẫn có một cảnh báo GETPID trước khi ACK;
không kết luận broker hết mọi lỗi hoặc sai mật khẩu SASL từ cảnh báo đó.

Timeout 20 giây là giới hạn chờ đọc của từng request adapter, không phải
deadline tổng cho mọi trang discovery/GitHub. Budget drain được kiểm trước
mỗi event, không phải deadline cưỡng chế cả batch.

### Kiểm tự động đã chạy

| Phạm vi | Kết quả |
| --- | --- |
| Identity, toàn bộ suite mặc định | **384 passed**; hai cảnh báo deprecation từ dj-rest-auth/allauth. |
| Work, suite mặc định | **846 passed, 5 deselected** theo marker external/e2e; không coi năm ca đó là đã chạy. |
| Integration, toàn bộ suite mặc định | **992 passed**. |
| Gate Compose/Kafka profile/Integration/deploy/Work config hiện có | **85 passed trên Linux**, cộng **1 passed trên Windows** cho ca gateway cần bind file và localhost của Docker host. Không sửa hoặc bỏ test để báo đạt. |
| Ruff ba service | Lint đạt; **605 file** đạt format check. |
| Django ba service trên image mới | `check`, `makemigrations --check --dry-run` đều exit 0; deploy cũng kiểm `migrate --check`. |
| Contract/tài liệu | Hai OpenAPI Work/Integration hợp lệ, resolve cả `$ref` tương đối; `LinkInput` khớp schema sinh từ image Work mới và không lệch danh sách path. Kiểm liên kết local, file rỗng liên quan và `git diff --check` đạt. |

Chỉ cập nhật các test hiện có, không tạo file test mới. Các suite dùng database
test riêng; provider giả trong suite không thay bằng chứng runtime bên dưới.
Lần chạy Identity đầu đặt sai tiền tố tên database nên một test migration bị
chặn; đã sửa cấu hình chạy và chạy lại toàn suite, không sửa/skip test đó.
Các lỗi Bash/đường dẫn của lượt gate trên Windows đã được tách khỏi lỗi ứng dụng
và chạy lại trên nền tảng phù hợp như bảng trên.

### Deploy và HTTP/provider thật

- Build tuần tự image Identity/Work/Integration từ source worktree; giữ image
  Classroom của lượt trước. Push registry local, cập nhật digest cho các process
  dùng chung image rồi chạy nguyên script deploy staging. **Exit 0**, migration,
  Nginx và bốn gateway health đạt. Dùng lại volume staging, không cài lại database.
  Snapshot cuối có **16 runtime healthy**, migration Integration exited 0,
  restart count của các container staging đều bằng 0.
- `.env` trong thư mục server tạm là bản sao byte-for-byte của `.env.staging`
  tại thời điểm deploy; root `.env`/`.env.staging` không bị sửa trong lượt fix.
  Chỉ bật bốn profile cũ, không triển khai AI hoặc thay source frontend.
- **29 quan sát HTTP đạt kết quả mong đợi**: ba login; đăng ký 201; PATCH hồ sơ
  200; đọc repository/link; token sai 401, outsider 404, Member connect 403;
  connect 202 và replay; ba COMMIT sai 400; branch/commit hợp lệ 201 và replay;
  ba PR không tồn tại 404; branch không tồn tại 404; gỡ hai link 200;
  disconnect 202; validation nội bộ Integration cho COMMIT sai 400.
- Tài khoản mới có tên đúng ngay trong `identity.user.created`, được ACK và
  projection Work có cùng tên. PATCH tài khoản thành viên có tên đúng qua GET
  members của Work. Năm event của hai tài khoản được chọn đều đã publish;
  kiểm riêng event cũ `6ff0edeb-5796-43b7-8091-f2dbef0678e7` cũng đã ACK.
  Không sửa `published_at`, reset retry hay ép consumer offset bằng SQL.
- Repository thật tiếp tục dùng consent/cài App đã được người dùng cấp.
  Connect generation 5 và disconnect generation 6 hoàn tất; hai event mới
  `PUBLISHED` tại Integration và có hai `ConsumedEvent` tương ứng tại Work,
  đối chiếu bằng `event_id`. Link thử được gỡ, Project cuối DISCONNECTED;
  không sửa repository, tạo PR/commit, uninstall App hoặc revoke consent.
- Ba lần tra PR không tồn tại mất **2,843 / 2,329 / 2,375 giây**, đều trả 404;
  branch/commit thành công mất **2,625 / 2,547 giây**. Lượt này không tái hiện
  một request provider chậm hơn 3 giây; test transport kiểm chính xác timeout
  mới, nhưng các số runtime này không chứng minh mọi latency tương lai đều đạt.

### Giới hạn còn giữ và artifact

Chưa nghiệm thu PR thành công (repo không có PR), mọi race/crash/thu hồi quyền,
tải dài hạn, mail/Notification, AI/frontend, hosted CI, GHCR, SSH, VPS hoặc
Cloudflare. Các consumer vẫn dùng broker/group staging chung theo xác nhận
của người dùng; không suy đây là phép kiểm độc lập giữa các deployment.

Artifact mới ngoài repo: thư mục tạm `utask-runtime-fixes-20261022-3_o4knsj`,
gồm JUnit/log ba suite, build/push/deploy, measurement Kafka,
`http-fix-results.json`, `profile-runtime-checks.json`,
`identity-events-after.json`, `integration-events-after.json` và digest image.
File env/state chứa credential không phải artifact chia sẻ. Không tự commit.
