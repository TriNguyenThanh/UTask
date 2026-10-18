# ADR-003 — Quyền và hợp đồng nền của Integration

- Ngày: 18/10/2026.
- Trạng thái: **Đã được ADR-004 thay thế một phần** theo yêu cầu người dùng:
  GitHub account/consent thuộc Integration, không yêu cầu đổi code Identity/Work.
  Xem [quyết định hiện hành](004-integration-github-account-ownership.md).
  Nội dung dưới giữ để truy nguyên thiết kế M0 ban đầu; M1 lúc đó chỉ triển khai khung
  chạy và health; các API nghiệp vụ bên dưới thuộc M2 trở đi.
- Phạm vi: GitHub chỉ đọc; giữ quyền sở hữu dữ liệu theo [baseline](../architecture/README.md).

## Bối cảnh

Identity đã sở hữu liên kết OAuth và có client exchange proof. Work đã có
`ConnectionFact`, `ReferenceFact`, guard trước/sau lời gọi adapter. Những điểm
nối này chưa cung cấp credential GitHub theo user hoặc server Integration.
Phải xác định nguồn quyền, consent và cách xử lý hai service commit lệch nhau
trước khi mở chức năng Project.

## Danh tính và credential GitHub

1. Giữ registration OAuth của Identity cho việc liên kết tài khoản, scope
   `read:user`. Chỉ Integration đổi code và gọi `/user`; proof trả Identity giữ
   nguyên binding `operation_id`, `user_id`, provider và expiry hiện có. Token
   của lần xác minh này không dùng liệt kê repository, không lưu lâu dài.
2. GitHub App dùng **registration riêng**, có consent riêng lấy **user access
   token**. Integration sở hữu client secret, private key, user/refresh token
   và installation token. Identity không nhận những token này. Lựa chọn này
   giữ nguyên OAuth client hiện tại và không mở rộng scope của Identity.
3. User phải liên kết GitHub qua Identity trước. Integration đọc mapping qua
   `GET /api/v1/internal/users/{user_id}/oauth/GITHUB`, dùng key caller
   `integration`. Khi hoàn tất consent và trước mỗi lần liệt kê/chọn repo,
   kiểm `/user` với user token, so ID ổn định với `mapping.provider_user_id`.
   Mapping rỗng, khác ID, nguồn lỗi hoặc credential bị thu hồi đều từ chối.
4. Chứng minh quyền bằng `GET /user/installations` và
   `GET /user/installations/{installation_id}/repositories` với **user token**.
   Chỉ chấp nhận repo nằm trong giao quyền user và App ở thời điểm kiểm tra;
   không dùng installation token toàn cục để chứng minh quyền user. Khi chọn
   phải kiểm lại từ GitHub, không tin trường `accessible` hoặc cursor cũ.
5. App chỉ yêu cầu Metadata/Contents/Pull requests đọc; Issues đọc chỉ khi
   triển khai đồng bộ Issue. Chưa yêu cầu quyền ghi, Administration hoặc Actions.
   Mã adapter pin API version `2026-03-10`; thay version cần contract test.

GitHub quy định user token chỉ truy cập phần giao quyền user/App, có API
liệt kê theo user và hỗ trợ PKCE S256. Xem [user access token](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-a-user-access-token-for-a-github-app)
và [installation API](https://docs.github.com/en/rest/apps/installations#list-repositories-accessible-to-the-user-access-token).

## Consent, callback và vòng đời bí mật

- Consent bắt đầu bằng `POST /api/v1/github/authorizations/start` với JWT user
  và `project_id`, sau khi Work cho phép `github.configure`. State ngẫu nhiên
  tối thiểu 32 byte, dùng một lần, hết hạn sau 10 phút; binding gồm user,
  session, project, registration và redirect URI allowlist chính xác.
- Dùng PKCE S256. GitHub chuyển về callback **frontend** nằm trong allowlist;
  frontend gửi code/state tới `POST /api/v1/github/authorizations/complete`
  cùng JWT hiện hành và cookie nonce HttpOnly, SameSite=Lax, Secure ở staging.
  Callback frontend xóa code/state khỏi URL ngay và không nạp script ngoài
  trước bước này. Integration kiểm session, binding và quyền Work lại rồi
  mới đổi code. Sai GitHub ID không thay mapping Identity; phải hủy và consent lại.
- Installation setup callback là luồng khác. GET callback chỉ giữ kết quả
  tạm gắn state/cookie và redirect về frontend. Việc xác nhận installation dùng
  `POST /api/v1/github/installations/confirm` có JWT và kiểm Work/GitHub lại.
  Callback không tạo ProjectConnection hoặc tự cấp quyền.
- Bật expiring user token; dùng expiry provider trả về, refresh trước khi hết
  hạn 60 giây, xoay cặp access/refresh token trong một cập nhật có kiểm phiên
  bản. Chỉ một refresh cho một credential version; không retry refresh mù khi
  mất response vì token cũ có thể đã bị vô hiệu. Khi không xác định được kết
  quả, hết hạn refresh hoặc gặp `401`, chuyển sang yêu cầu consent lại.
- Credential lưu mã hóa xác thực bằng Fernet với key ID và key ring ngoài DB,
  active key dùng ghi, old keys chỉ đọc trong thời gian rotation. Không lưu
  khóa cùng ciphertext. M3 phải kiểm round trip, sai key, rotation và kiểm tra
  log; M1 chưa có bảng token hoặc key giả. State/code/verifier tạm xóa ngay
  sau sử dụng hoặc hết hạn; không đưa token/code/verifier vào Kafka/log/AI.
- `github_app_authorization` revoked, Identity unlink/mapping đổi hoặc provider
  từ chối làm credential user không còn dùng được. Không giả định event đến
  kịp: kiểm mapping và quyền provider trực tiếp ở các thao tác cấu hình.
  Installation suspend/uninstall/repo removed hủy job và chặn dữ liệu mới của
  scope đó. Không tự gỡ installation dùng chung khi một user unlink.
- Dữ liệu lịch sử bị thu hồi không được phục vụ qua API/context; giữ tối đa
  30 ngày để điều tra rồi xóa/anonymize. Delivery metadata không chứa raw secret
  giữ 30 ngày; raw webhook không giữ mặc định. Thay retention cần cập nhật hợp đồng.

Thời gian token và việc refresh vô hiệu token cũ được mô tả tại
[GitHub: refreshing user access tokens](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/refreshing-user-access-tokens).

## Quyền UTask và giao tiếp nội bộ

- Mỗi cặp caller/callee dùng key ngẫu nhiên riêng tối thiểu 32 byte trong
  `X-Service-Key`, allowlist theo endpoint. Chấp nhận tối đa current/previous
  key khi rotation, overlap tối đa 24 giờ. Không suy caller từ header user gửi.
- Public API Integration xác thực JWT RS256 theo JWKS/issuer/audience Identity,
  sau đó gọi `POST /api/v1/internal/auth/session-status` với key `integration`
  và `Authorization: Bearer <user-token>`; `data.active` phải đúng `true`.
  **M2 phải thêm caller này tại Identity; hiện chưa có**. Không cache kết quả
  cho phép. JWT hoặc service key riêng lẻ không cấp quyền Project.
- Work/AI gọi Integration bằng key của mình và forward nguyên Bearer actor.
  Integration lấy actor từ JWT đã kiểm chứng, hỏi Work
  `POST /api/v1/internal/integration/authorize` với key riêng Integration→Work,
  Bearer đó, `action` và `target`. Không nhận actor do JSON/header tự khai báo.
  Work tự kiểm JWT/phiên và quyền domain, không gọi ngược Integration.
- Kết quả Work phải khớp actor, action, target, project; hết hạn sau 5 giây,
  chỉ dùng cho lần gọi hiện tại. Timeout kết nối 2 giây/đọc 3 giây, không
  retry/cache positive cho mutation. Nguồn lỗi trả 503, không fallback allow.
  Work vẫn kiểm quyền/generation lại trong transaction áp dụng kết quả.
- `github.configure`, `github.sync`, `github.disconnect`: target Project,
  leader ACTIVE, Project ghi được. `github.link`: target Task, member ACTIVE,
  Task/Project ghi được. `github.read`: target Project/Task, member ACTIVE hoặc
  teacher scope do Work/Classroom xác minh. Global role không bỏ qua quyền.
- OAuth proof chỉ key Identity; không cần JWT actor vì Identity đã tiêu thụ
  OAuth context của chính phiên và gửi binding. AI chỉ đọc context đã lọc,
  không được exchange/list/command. Worker dùng danh tính hệ thống và job scope,
  không lưu JWT user để giả danh lúc chạy nền.
- Internal Integration exact path và route con bị chặn tại gateway. M1 chỉ
  mở `/healthz` GET/HEAD, có kiểm DB và không trả chi tiết lỗi.

Wire contract hiện hành ở [Integration API](../../contracts/api/integration-service-v1.yaml).
Work access API của bản thiết kế này đã được thu hồi theo ADR-004.
Các API phân quyền/consent thuộc M2–M4; schema không phải bằng chứng đã chạy.

## Chống lặp, generation và phục hồi

- OAuth exchange: giữ nguyên payload client Identity; expiry tối đa 10 phút,
  `verified_at <= now + 30s` và không sớm hơn `expires_at - 600s`. Chống lặp
  theo `(caller, operation_id)` và digest payload; cùng operation/payload trả
  proof cũ chỉ khi proof còn hạn. Operation khác dùng lại code bị từ chối;
  chỉ giữ HMAC fingerprint code tới hết hạn, không giữ code/verifier raw.
  Mất response trong exchange provider: đánh dấu kết quả chưa xác định,
  yêu cầu OAuth flow mới, không đổi lại code hoặc tự tạo operation mới để retry.
- Lệnh connection dùng `(caller, command, project_id, operation_id)`; giữ
  result/digest 24 giờ, tombstone tới 30 ngày. Payload khác cùng key trả 409;
  key quá hạn trả `OPERATION_EXPIRED`, không thực thi như mới.
- Selection/disconnection CAS trên `expected_connection_generation`; lệnh
  mới thành công tăng generation một lần; retry không tăng. Source version
  tăng trong generation, không dùng timestamp để sắp thứ tự.
- M5 dùng **prepare/confirm** qua REST: selection tạo technical connection
  `PENDING`, không cho sync/context. Work áp dụng kết quả sau guard lần hai,
  lưu receipt và ý định confirm cùng transaction Work. Dispatcher thuộc Work
  gửi confirm idempotent; Integration xác minh receipt Work qua REST và chỉ
  kích hoạt khi operation/project/generation khớp bản ghi Work đã áp dụng.
  Đây là hoàn tất lệnh đã được Work chấp nhận, không giả danh JWT user cũ.
- Work từ chối sau prepare: abort reservation theo operation/generation;
  timeout/mất response: đọc trạng thái rồi retry cùng operation. Pending quá
  24 giờ không có receipt Work được hủy. Confirm/abort muộn không tác động
  generation mới. Đọc reconcile/event không tự chấp nhận operation mà Work
  chưa lưu; giữ guard hiện có. M5 phải bổ sung cả confirm/abort/status API và
  durable dispatcher trước khi bật HTTP adapter, không chỉ thay hai port.
- Event đầu tiên: `integration.project.connection.changed`, version 1,
  topic `utask.integration.events`, key `project_id`, envelope `payload` theo
  baseline, outbox cùng transaction Integration. Work là consumer đầu tiên
  ở M6, chống lặp `event_id`, kiểm generation/version và operation đã chấp nhận;
  không dùng event để cấp quyền hoặc tự xác nhận Task link. Không có subscriber
  AI/Notification mặc định. Schema ở [event v1](../../contracts/events/integration.project.connection.changed.v1.json).
  Broker giữ 7 ngày, outbox đã phát giữ 30 ngày; retry có giới hạn, lỗi cuối
  cần vận hành xử lý. ACL chỉ Integration produce, Work consume topic này.

## Gate triển khai

M0 đóng khi các quyết định trên, schema và ví dụ được kiểm tra. M1 cần CI
discovery, image không kết nối DB lúc build, settings thiếu cấu hình bị từ
chối, migration/health sạch và credential PostgreSQL riêng. M2 trở đi kiểm
caller, session và Work permission với ca allow/deny thực tế. M3 kiểm contract
proof với client Identity; M4 chứng minh quyền user bằng provider fake và repo
test; M5 kiểm prepare/confirm/abort và race. M6 mới bật publisher/consumer.
Không đánh dấu service hoàn tất từ bootstrap hoặc schema.
