# Hướng dẫn nối Work Service với Integration Service

**Trạng thái: Thiết kế mục tiêu.** Work có adapter với `ConnectionFact` và
`ReferenceFact`, cùng logic kiểm tra quyền, generation, receipt và projection.
`WORK_INTEGRATION_ADAPTER` mặc định trỏ tới `UnavailableIntegration`; source
được kiểm tra chưa chứng minh adapter HTTP, các endpoint nội bộ, dispatcher
confirm hoặc consumer Kafka đã chạy. Các test Work dùng adapter giả không xác
minh kết nối giữa hai service hay GitHub thật. Xem
[luồng liên kết repository](github-repository-linking.md),
[ADR-003](../adr/003-integration-auth-and-contracts.md) và
[contract Integration](../../contracts/api/integration-service-v1.yaml).

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

Tên dưới đây là quy ước cấu hình đích cho adapter và dispatcher; source Work
hiện chỉ có `WORK_INTEGRATION_ADAPTER`, chưa có bằng chứng các biến này được
đọc hoặc được cấu hình khi deploy.

| Biến | Chủ sở hữu | Mục đích |
| --- | --- | --- |
| `WORK_INTEGRATION_BASE_URL` | Work | URL nội bộ Integration, không phải URL gateway công khai. |
| `WORK_INTEGRATION_SERVICE_KEY` | Work | Key riêng Work→Integration. |
| `INTEGRATION_WORK_BASE_URL` | Integration | URL nội bộ Work để kiểm quyền và gửi callback receipt. |
| `INTEGRATION_WORK_SERVICE_KEY` | Integration | Key riêng Integration→Work. |
| `WORK_GITHUB_CONNECTION_ENABLED` | Work | Cờ bật luồng kết nối; mặc định `false`. |

Giữ các key trong secret store của môi trường, không ghi vào repo, log hoặc
response. HTTP timeout theo hướng dẫn hiện tại là 2 giây kết nối và 3 giây
đọc. Timeout/lỗi nguồn không được đổi thành kết quả cho phép. Tên biến và
đường dẫn route cụ thể phải đồng bộ với contract trước khi triển khai adapter.

## Giao diện nội bộ

Contract Integration là nguồn chuẩn cho path, schema, mã lỗi và trạng thái
endpoint. Các endpoint dưới đây đã có trong contract với trạng thái
`design-approved-m5`; đó là quyết định thiết kế, chưa phải bằng chứng runtime.
Request/response dùng envelope `success` và `data` theo schema được dẫn.

| Operation | Bên gọi → bên nhận | Dữ liệu/hiệu lực |
| --- | --- | --- |
| `prepare` | `POST /api/v1/internal/projects/{project_id}/github/connection/prepare`; Work → Integration | `ConnectionPrepareRequest`: `operation_id`, `action` (`CONNECT`/`DISCONNECT`), `expected_generation`, `github_repo_id` (ID khi connect, `null` khi disconnect); Bearer actor + Work service key. Trả `ConnectionFact` trạng thái `PENDING`. |
| `confirm` | `POST /api/v1/internal/projects/{project_id}/github/connection/confirm`; dispatcher bền vững Work → Integration | `ConnectionOperationRequest`: `operation_id`, `generation`; chỉ service key. Integration đọc receipt Work trước khi finalize. Idempotent, không nhận Bearer actor cũ. |
| `abort` | `POST /api/v1/internal/projects/{project_id}/github/connection/abort`; Work → Integration | Cùng `ConnectionOperationRequest`; chỉ hủy operation `PREPARED` khớp project/operation/generation. Abort trùng cùng payload thành công; lệnh muộn không ảnh hưởng connection/generation mới. |
| `status` | `GET /api/v1/internal/projects/{project_id}/github/connection/operations/{operation_id}`; Work → Integration | Chỉ service key; trả operation state `PREPARED`, `CONFIRMED`, `ABORTED` hoặc `EXPIRED`, cùng snapshot kết quả nếu có. Không tự confirm. |
| `verify reference` | `POST /api/v1/internal/projects/{project_id}/github/references/verify`; Work → Integration | `ReferenceVerifyRequest`: `repo_id`, `generation`, `link_type`, `ref_id`; Bearer actor + Work service key. Trả `ReferenceFact`; không tạo `TaskGitHubLink`. |
| `receipt` | `GET /api/v1/internal/integration/projects/{project_id}/github/operations/{operation_id}`; Integration → Work | Endpoint Work mục tiêu, chỉ service key Integration→Work. Trả `applied`, `project_id`, `operation_id`, `generation`, `status`, `repo_id`, `source_version`; hiện chưa có trong contract máy đọc. |

Contract đánh dấu operation Integration là thiết kế đã duyệt. Riêng callback
receipt Work là path/schema mục tiêu cần được bổ sung vào contract Work trước
khi triển khai; payload phải khớp operation đã commit, không chỉ trạng thái
projection hiện thời.

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
là thiết kế theo ADR/contract; chưa xác minh cấu hình runtime hay hành vi GitHub
thật.

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

Adapter giả hiện tại chỉ kiểm thử logic Work; cần kiểm tra contract giữa hai
service bằng test tích hợp có service thật trong môi trường thử nghiệm. GitHub
thật/deployment vẫn là phạm vi chưa xác minh cho tới khi chạy smoke test với
credential và repository thử nghiệm được cấp quyền.

## Rollout

1. Hoàn thiện các operation nội bộ và receipt schema trong contract; kiểm tra
   đường dẫn/gateway chặn internal path, key hai chiều và timeout.
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
- **Một phần:** Work có projection, outbox và idempotency; contract cũ mô tả
  selection trực tiếp. Chưa có bằng chứng trong file source được kiểm tra về
  prepare/confirm/abort/status, callback receipt, dispatcher durable, consumer
  `integration.project.connection.changed`, disconnect qua contract mới hoặc
  rollout flag.
- **Chưa xác minh:** adapter Integration thật, triển khai gateway/internal
  routes, cấu hình key/URL và kết nối tới GitHub thật.

Các nhãn trên chỉ mô tả file được đối chiếu; trước khi phát hành cần kiểm tra
toàn bộ source, deployment và test liên quan theo contract mới.
