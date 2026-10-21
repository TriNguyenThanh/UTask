# Hướng dẫn nối Work Service với Integration Service

**Trạng thái: Hợp đồng giao tiếp đã chốt.** Work đã có adapter HTTP,
operation/receipt, task phục hồi, disconnect và consumer kết nối trong source;
hướng dẫn triển khai/cấu hình và phạm vi kiểm chứng hiện hành nằm tại
[Work GitHub integration](../project-service/github-integration.md).
`WORK_INTEGRATION_ADAPTER` vẫn mặc định unavailable và cờ nghiệp vụ mặc định tắt.
GitHub live cho luồng Project và staging/production chưa được nghiệm thu. Xem
[luồng liên kết repository](github-repository-linking.md),
[ADR-003](../adr/003-integration-auth-and-contracts.md) và
[contract Integration](../../contracts/api/integration-service-v1.yaml).

Phần Work cung cấp context cho AI và kiểm quyền `github.read` cho Integration
được bàn giao riêng tại
[hướng dẫn Work–AI](../project-service/ai-service-integration-guide.md).
Ba API đó không thay thế luồng kết nối repository trong tài liệu này.

## Ranh giới và xác thực

Integration sở hữu credential GitHub và là service duy nhất gọi GitHub API.
Work sở hữu Project, quyền Leader/Member, trạng thái kết nối, Task link và
projection nghiệp vụ. Work không đọc database Integration, không nhận token
GitHub và không xác nhận quyền repository dựa trên dữ liệu do client gửi.

Các lệnh điều khiển kết nối chỉ dành cho Work gọi nội bộ. Mạng/gateway không
công khai các route nội bộ. Mỗi chiều dùng `X-Service-Key` riêng, ngẫu nhiên,
tối thiểu 32 byte, chỉ nhận key hiện tại và key trước trong thời gian xoay
khóa (tối đa 24 giờ). Không dùng key của chiều Work→Integration để gọi
Integration→Work. Thao tác `prepare` và `verify reference` mang cả key dịch vụ
và nguyên Bearer của actor; Integration kiểm tra key để nhận diện caller và
xác minh Bearer/phiên. Work là authority đã kiểm quyền trước khi gọi. Không
nhận `actor_id` do caller tự khai.
`confirm`, `abort`, `status` và callback receipt là giao tiếp giữa hai service,
không dùng JWT người dùng cũ để giả danh actor.

### Cấu hình đích

Tên dưới đây là cấu hình giao tiếp; cấu hình nhận key hiện tại/trước và consumer
thực tế phía Work xem [hướng dẫn Work](../project-service/github-integration.md#cấu-hình-và-khởi-động).

| Biến | Chủ sở hữu | Mục đích |
| --- | --- | --- |
| `WORK_INTEGRATION_BASE_URL` | Work | URL nội bộ Integration, không phải URL gateway công khai. |
| `WORK_INTEGRATION_SERVICE_KEY` | Work | Key riêng Work→Integration. |
| `INTEGRATION_WORK_URL` | Integration | URL nội bộ Work để kiểm quyền và đọc receipt. |
| `INTEGRATION_WORK_SERVICE_KEY` | Integration | Key riêng Integration→Work. |
| `WORK_GITHUB_CONNECTION_ENABLED` | Work | Cờ bật luồng kết nối; mặc định `false`. |

Giữ các key trong secret store của môi trường, không ghi vào repo, log hoặc
response. Adapter Work chờ tối đa 2 giây kết nối và 20 giây đọc, thay vì
ngắt sau 3 giây khi Integration còn kiểm quyền/repository/reference bằng
các lượt GitHub tuần tự. Đây là giới hạn chờ mỗi request, không phải cam kết
mọi trang discovery đều hoàn tất trong 20 giây. Timeout/lỗi nguồn không được
đổi thành kết quả cho phép. Tên biến và
đường dẫn route cụ thể được đối chiếu trong test adapter và test hai backend.

## Giao diện nội bộ

Contract Integration là nguồn chuẩn cho path, schema, mã lỗi và trạng thái
endpoint. Các endpoint dưới đây đã được triển khai phía Integration với trạng
thái `implemented`. Phía Work đã có test hai backend qua HTTP/PostgreSQL/Kafka
riêng; Identity và GitHub được thay thế trong test, chưa xác minh provider live.
Request/response dùng envelope `success` và `data` theo schema được dẫn.

| Operation | Bên gọi → bên nhận | Dữ liệu/hiệu lực |
| --- | --- | --- |
| `prepare` | `POST /api/v1/internal/projects/{project_id}/github/connection/prepare`; Work → Integration | `ConnectionPrepareRequest`: `operation_id`, `action` (`CONNECT`/`DISCONNECT`), `expected_generation`, `github_repo_id` (ID khi connect, `null` khi disconnect); Bearer actor + Work service key. Trả `ConnectionFact` trạng thái `PENDING`. |
| `confirm` | `POST /api/v1/internal/projects/{project_id}/github/connection/confirm`; dispatcher bền vững Work → Integration | `ConnectionOperationRequest`: `operation_id`, `generation`; chỉ service key. Integration đọc receipt Work trước khi finalize. Idempotent, không nhận Bearer actor cũ. |
| `abort` | `POST /api/v1/internal/projects/{project_id}/github/connection/abort`; Work → Integration | Cùng `ConnectionOperationRequest`; chỉ hủy operation `PREPARED` khớp project/operation/generation. Abort trùng cùng payload thành công; lệnh muộn không ảnh hưởng connection/generation mới. |
| `status` | `GET /api/v1/internal/projects/{project_id}/github/connection/operations/{operation_id}`; Work → Integration | Chỉ service key; trả operation state `PREPARED`, `CONFIRMED`, `ABORTED` hoặc `EXPIRED`, cùng snapshot kết quả nếu có. Không tự confirm. |
| `verify reference` | `POST /api/v1/internal/projects/{project_id}/github/references/verify`; Work → Integration | `ReferenceVerifyRequest`: `repo_id`, `generation`, `link_type`, `ref_id`; Bearer actor + Work service key. Trả `ReferenceFact`; không tạo `TaskGitHubLink`. |
| `receipt` | `GET /api/v1/internal/integration/projects/{project_id}/github/operations/{operation_id}`; Integration → Work | Đã triển khai trong Work, chỉ service key Integration→Work. Trả `applied`, `project_id`, `operation_id`, `generation`, `status`, `repo_id`, `source_version`; có trong OpenAPI Work. |

Callback receipt có trong [contract Work](../../contracts/api/work-service.yaml).
Payload khớp operation đã commit, không suy từ projection hiện thời.

Không đưa token GitHub, raw authorization code hoặc secret vào request, fact,
receipt, event hay log. `ConnectionFact`/`ReferenceFact` là biên dữ liệu trong
adapter Work hiện tại, không thay thế schema công khai trong contract.

## Thứ tự ghi và xử lý kết quả

1. Work mở transaction, khóa Project, kiểm tra Leader ACTIVE, Project còn ghi
   được, feature flag bật, receipt/idempotency và generation mong đợi. Commit
   không xảy ra trong lúc gọi Integration; Work không giữ lock/transaction qua
   request mạng.
2. Work gọi `prepare` với cùng `operation_id` khi retry, key chiều Work→Integration
   và Bearer actor. Integration xác minh actor qua Identity và kiểm tra quyền
   repository live qua GitHub, sau đó lưu reservation `PENDING` bền vững trước
   khi trả fact.
3. Work kiểm tra fact đúng project/operation/repository, trạng thái, generation
   và source version. Work mở transaction mới, khóa lại Project, kiểm tra Leader
   và generation lần hai. Nếu một thao tác/event mới đã thắng, không áp dụng
   fact cũ; gửi `abort` theo operation/generation.
4. Khi hợp lệ, Work cập nhật projection, ghi Activity, outbox event nghiệp vụ,
   idempotency receipt và ý định confirm vào cùng transaction. Chỉ commit này
   là bằng chứng Work đã chấp nhận operation. `PENDING` không được chiếu thành
   `CONNECTED` trước receipt confirm.
5. Dispatcher Work đọc ý định confirm bền vững và gửi `confirm` idempotent.
   Integration gọi `GET /api/v1/internal/integration/projects/{project_id}/github/operations/{operation_id}`
   bằng key chiều Integration→Work, xác minh receipt đã commit,
   rồi mới kích hoạt connection nếu project, operation và generation khớp.
   Callback về Work và event Kafka đều được xử lý lặp an toàn.
6. Integration phát `integration.project.connection.changed` qua outbox cùng
   transaction cập nhật connection. Work consume topic
   `utask.integration.events`, chống lặp bằng `event_id`, chỉ áp dụng
   generation/source version mới hơn và chỉ cho operation đã được Work chấp
   nhận. Event không tự cấp quyền hoặc xác nhận Task link.

Ngắt kết nối cũng dùng operation idempotent và CAS trên
`expected_connection_generation`; Work chỉ chuyển projection sau khi kiểm tra
lại quyền/generation. Không gỡ GitHub App dùng chung chỉ vì một Project ngắt
kết nối. Không giả định worker là singleton.

Work đã có `DELETE /projects/{id}/github/repository/`, body
`{operation_id,expected_connection_generation}` và quyền
Leader ACTIVE. HTTP adapter map body này sang prepare `DISCONNECT` với
`github_repo_id:null`; sau khi lưu pending/receipt/intent trả 202; dispatcher
confirm chuyển projection cuối DISCONNECTED. Không gọi uninstall GitHub.
Mặc định adapter vẫn unavailable. Khi tắt nhận lệnh mới ở môi trường đã bật,
giữ adapter HTTP và recovery tới khi xử lý xong các operation đã commit.

## Lỗi, retry và phục hồi

- Cùng operation và cùng payload được phép retry; cùng key nhưng payload khác
  trả conflict. Retry không tăng generation lần nữa.
- Nếu `prepare` timeout hoặc mất response, Work gọi `status` rồi retry cùng
  operation khi cần. Không tạo operation mới cho tới khi kết quả cũ đã rõ.
- Nếu Work từ chối fact sau prepare, gửi `abort`. Nếu abort/confirm bị lỗi,
  dispatcher retry bền vững; lệnh cũ không được tác động generation mới.
- Nếu Work đã commit nhưng confirm chưa tới Integration, dispatcher tiếp tục
  confirm. Integration không kích hoạt chỉ dựa trên callback trình duyệt, event
  Kafka hoặc dữ liệu do actor khai báo.
- Reservation chưa có receipt Work sau 24 giờ bị hủy. Reconcile/status không
  tự chấp nhận operation Work chưa ghi receipt.
- Lỗi xác thực, timeout, GitHub bị thu hồi quyền hoặc contract sai không được
  fallback allow. Work giữ trạng thái cũ và trả lỗi phù hợp; retry có giới hạn
  theo loại lỗi, lỗi cuối cần cảnh báo/vận hành xử lý.
- Consumer Kafka phải chịu được giao ít nhất một lần: lưu/kiểm `event_id`, áp
  dụng generation/source version theo thứ tự logic, bỏ qua event cũ và không
  phát lại thay đổi nghiệp vụ cho event trùng.

Các thời hạn reservation 24 giờ, timeout HTTP và quy tắc generation nêu trên
đã có trong provider và kiểm thử. Hai backend đã được kiểm qua HTTP/Kafka test;
đã kiểm connect/disconnect, receipt/replay và branch/commit với GitHub thật
trên staging local ngày 21–22/10/2026. Chưa nghiệm thu PR thành công hoặc mọi
tình huống crash/race/thu hồi quyền. Xem [bằng chứng và giới hạn](../infrastructure/staging-http-validation-20261021.md#kiem-lai-20261022)
và [cấu hình provider](runtime-connections.md).

### Quyết định wire cho runtime provider

Receipt Work trả HTTP 200 với `{success:true,data:{applied:true,project_id,
operation_id,generation,status:"PENDING",repo_id,source_version}}`, đúng các
trường này. `repo_id` là repo đích của CONNECT hoặc `null` cho DISCONNECT;
`generation` và `source_version` phải bằng fact prepare đã commit. Receipt
là bằng chứng chấp nhận operation bất biến, không phải snapshot projection có
thể đã đổi do event. Integration so khớp toàn bộ trước khi finalize. Work phải
giữ receipt ít nhất 30 ngày; receipt thiếu hoặc từ chối không kích hoạt connection.

Schema máy đọc là `WorkGitHubOperationReceipt` và
`WorkGitHubOperationReceiptEnvelope` trong [Work OpenAPI](../../contracts/api/work-service.yaml).
Không yêu cầu Bearer actor, không nhận query/body; response đặt
`Cache-Control: no-store`, JSON UTF-8 tối đa 65536 byte. `project_id` là UUID
khác nil; `operation_id` là ID opaque 1–100 ký tự, không chứa ký tự điều khiển
U+0000–U+001F, không bằng `.` hoặc `..`; percent-encode khi đặt vào URL.
Hai ID trong data phải khớp path sau giải mã. `generation/source_version`
là integer dương, không phải boolean hoặc chuỗi; repo ID CONNECT là chuỗi số
ASCII dương tối đa 100 ký tự, DISCONNECT là `null`. Không trả status cuối của
connection thay cho `PENDING` trong receipt, kể cả khi connection đã finalize.
Trên wire, hai số version/generation phải dùng token JSON integer (`1`), không
dùng phần thập phân hoặc exponent (`1.0`, `1e0`). JSON Schema kiểm integer theo
giá trị toán học nên không thể phân biệt các token này; consumer hiện kiểm kiểu
sau parse và từ chối float, không ép kiểu để cho phép.

Lỗi `400` cho path/query/body không hợp lệ, `403` cho sai caller/key, `404`
cho receipt chưa commit hoặc không khớp project/operation, `503` cho lỗi đọc
tạm thời; dùng `WorkErrorEnvelope`. Không trả `200` với `applied=false`.
Consumer Integration hiện coi HTTP khác `200` hoặc payload sai là Work
unavailable và không finalize; envelope cho phép metadata Work ngoài `success/data`,
nhưng object data không được có trường thừa.

API quyền Work cho Integration là
`POST /api/v1/internal/integration/projects/{project_id}/authorize`, header
Bearer actor và key chiều Integration→Work, body duy nhất `{"action":"github.read"}`.
HTTP 200 trả `{success:true,data:{project_id,action:"github.read",allowed:true}}`
hoặc `allowed:false`; thiếu/sai schema hoặc timeout phải từ chối đọc context.

Prepare tiêu thụ generation đúng một lần và dành một source version cho fact
PENDING; confirm tăng source version lần nữa, chỉ phát fact cuối. Khi abort/expire,
generation đã dùng không được tái sử dụng. Status trả snapshot operation để
Work biết generation dành trước khi phát command tiếp theo. Connection cũ không
phục vụ reference/context khi còn operation PREPARED. Sau invalidation, chỉ
operation CONNECT mới cùng receipt mới có thể khôi phục quyền đọc.

Work phải lưu operation đang chờ riêng với connection đã confirm gần nhất.
Abort/expire phục hồi con trỏ về connection được chấp nhận, nhưng không giảm
generation đã dành. Event thu hồi quyền dùng operation/generation của binding
đã confirm cùng source version mới. Consumer ghi nhận việc thu hồi binding đó
cả khi một operation mới đang PENDING; không để pending che mất revocation.
Dispatcher xử lý ABORTED/EXPIRED bằng reconcile projection, không giả định
connection cũ còn quyền. Receipt CONNECT đang đại diện binding phải giữ tới
khi binding mới được confirm; retention 30 ngày không xóa receipt đang dùng.

Cursor cho command tiếp theo lấy từ generation của operation status mới nhất;
generation để verify reference lấy từ binding đã CONFIRMED. Sau prepare2 bị
abort/expire, cursor vẫn 2 nhưng binding1 vẫn có thể đọc với generation1 nếu
quyền còn hiệu lực. Không tăng generation projection binding chỉ vì reservation
thất bại; lưu cursor riêng để command tiếp theo dùng expected_generation2.

## Kiểm tra cần có trước khi bật

Unit/contract tests cho adapter và service cần bao quát:

- prepare thành công, thiếu/sai service key, Bearer/phiên hết hạn, actor không
  có quyền Leader, repository không còn được GitHub cấp quyền và timeout;
- idempotency cùng payload, payload khác cùng operation, generation conflict,
  fact sai project/operation/repository và source version cũ;
- Work commit ghi projection + receipt + confirm intent nguyên tử; lỗi trước
  commit không để confirm intent mồ côi;
- dispatcher retry sau mất response, confirm trùng, abort trùng, status khi
  kết quả chưa rõ và confirm/abort muộn sau generation mới;
- Integration chỉ kích hoạt sau khi xác minh callback receipt Work hợp lệ;
  callback giả, receipt thiếu/sai operation hoặc receipt chưa commit bị từ chối;
- event trùng, event cũ, nhảy generation, callback/event đến sai thứ tự và
  lỗi khi lưu consumer offset/receipt;
- verify reference thành công và các nhánh ref không thuộc repo, sai generation,
  URL/metadata không hợp lệ, quyền actor bị thu hồi;
- disconnect idempotent, race với prepare/confirm và không ảnh hưởng Project
  khác dùng cùng installation.

Test fixture kiểm logic Work riêng; test `test_integration_wire.py` chạy hai
backend và adapter HTTP thật với database riêng, có tùy chọn Kafka test.
GitHub/Identity ở phép thử đó là stub. GitHub thật/deployment vẫn chưa xác minh
cho tới khi nghiệm thu với credential và repository thử nghiệm được cấp quyền.

## Rollout

1. Đối chiếu implementation Work với operation/schema receipt `planned` trong
   contract; kiểm tra đường dẫn/gateway chặn internal path, key hai chiều và timeout.
2. Triển khai schema/outbox/dispatcher/consumer nhưng giữ
   `WORK_GITHUB_CONNECTION_ENABLED=false`. Chạy test adapter, contract và
   test tích hợp; xác nhận retry, duplicate, recovery và observability.
3. Bật adapter HTTP ở môi trường thử nghiệm với cờ tắt nghiệp vụ; kiểm tra
   health, key rotation, receipt, Kafka ACL (Integration produce, Work consume)
   và thử kết nối GitHub bằng repo thử nghiệm.
4. Bật flag theo môi trường/nhóm nhỏ sau khi migration và worker sẵn sàng; theo
   dõi lỗi 401/403/409/503, tuổi confirm intent, reservation quá hạn, độ trễ
   callback và consumer lag. Tăng phạm vi sau khi xử lý được lỗi tồn đọng.
5. Rollback bằng cách tắt flag trước; giữ receipt/outbox để dispatcher tiếp tục
   hoàn tất operation đã commit. Không xóa dữ liệu hoặc key cũ khi còn operation
   chưa reconcile. Chỉ dừng worker sau khi backlog confirm/abort đã được xử lý.

## Hiện trạng đã đối chiếu

- **Đã triển khai:** adapter Work định nghĩa và kiểm tra `ConnectionFact`,
  `ReferenceFact`; service chọn repository khóa Project và gọi adapter ngoài
  transaction, rồi kiểm tra quyền/generation và ghi projection/receipt.
- **Đã triển khai phía Work:** HTTP adapter prepare/confirm/abort/status/reference,
  receipt nội bộ, recovery bền vững, consumer connection, disconnect và cấu hình
  Work liên quan. Authorize `github.read` cho AI nằm ngoài lượt nối Work này.
- **Chưa xác minh:** GitHub live cho luồng Project mới, staging/production và
  credential/ACL của môi trường triển khai. Xem phạm vi test service thật với
  GitHub/Identity stub trong [hướng dẫn Work](../project-service/github-integration.md).

Các nhãn trên chỉ mô tả file được đối chiếu; trước khi phát hành cần kiểm tra
toàn bộ source, deployment và test liên quan theo contract mới.
