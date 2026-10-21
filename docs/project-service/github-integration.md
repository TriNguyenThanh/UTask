# Work kết nối repository với Integration

**Trạng thái: Đã triển khai; đã kiểm một phần với GitHub thật trên staging local.**
Đã chạy Compose staging bằng `.env.staging`, Identity/Integration thật,
connect/confirm, receipt/replay, branch/commit, disconnect và recovery sau khi
worker dừng. Luồng pytest trước đó vẫn dùng stub Identity/GitHub; không dùng
kết quả mock làm bằng chứng provider thật. Chưa nghiệm thu PR thành công,
mọi crash/race, VPS hoặc production. Các lỗi và giới hạn thực tế nằm trong
[báo cáo HTTP staging local](../infrastructure/staging-http-validation-20261021.md).

## Trách nhiệm và phần dùng lại

Work kiểm quyền Project/Task, giữ kết nối repository đã được chấp nhận và
liên kết Task–GitHub. Integration là bên duy nhất gọi GitHub, giữ credential
và xác minh quyền repository live. Hai service giao tiếp bằng REST và event,
không đọc database của nhau.

Triển khai dùng [adapter HTTP](../../apps/work-service/infrastructure/integration.py),
[operation service](../../apps/work-service/apps/integrations/services/operations.py),
[repository service](../../apps/work-service/apps/integrations/services/repositories.py)
và [Task link service](../../apps/work-service/apps/integrations/services/links.py).
Chỉ thêm một model `GitHubConnectionOperation`; dùng lại Project barrier,
Activity/Outbox, receipt HTTP, Celery/Beat, Kafka config, `ConsumedEvent` và DLQ.
Không có framework dispatcher hoặc hệ thống job mới.

Hợp đồng provider theo [ADR-005](../adr/005-integration-work-ai-contracts.md),
[guide wire](../integration-service/work-service-integration-guide.md),
[OpenAPI Integration](../../contracts/api/integration-service-v1.yaml) và
[event v1](../../contracts/events/integration.project.connection.changed.v1.json).
API phía Work được sinh tại [OpenAPI Work](../../contracts/api/work-service.yaml).

## API Work

Qua gateway, các đường công khai dưới đây có prefix `/api/work`.

| Method/path | Quyền và hành vi |
| --- | --- |
| GET `/projects/{project_id}/github/repository/` | Quyền đọc Project hiện có; chỉ đọc Work, không gọi provider. |
| POST cùng path | Leader ACTIVE trên Project còn ghi được; body `github_repo_id` là chuỗi số nguyên dương, `operation_id`, `expected_connection_generation`. |
| DELETE cùng path | Leader ACTIVE; body `operation_id`, `expected_connection_generation`; không gỡ GitHub App của Project khác. |
| POST `/tasks/{task_id}/github-links/` | Thành viên ACTIVE có quyền ghi; gửi `link_type` và `github_ref_id`, metadata lấy từ Integration. |
| GET/confirm/DELETE Task link | Giữ quyền, receipt và tombstone hiện có; xác nhận/merge PR không hoàn thành Task. |

POST/DELETE kết nối trả **202 PENDING** sau khi Work commit quyết định chấp
nhận. `Idempotency-Key` tùy chọn; khi không có, dùng `operation_id` làm key.
Retry cùng actor/operation/nội dung trả lại kết quả đã ghi; đổi payload hoặc
chiếm operation của actor khác bị từ chối. `operation_id` dài tối đa 100 ký tự
ASCII chữ/số/`._:-`, không nhận riêng `.` hoặc `..`.

GET repository có `command_generation`: dùng giá trị này cho
`expected_connection_generation` của lệnh tiếp theo. `connection_generation`
là generation của dữ liệu binding đang hiển thị; không suy cursor command
từ binding cũ sau abort/expiry. Khi có operation pending, response hiển thị
PENDING cùng operation/snapshot đó; các trường repository trên Project vẫn
giữ binding đã confirm để phục hồi. Pending chặn liên kết Task mới. Khi đang
abort, GET giữ binding hiện hành và cursor đã dành; request mới vẫn bị chặn
cho tới khi operation kết thúc.

Lỗi provider được ánh xạ sang thông báo tiếng Việt an toàn; không đưa raw
response/exception hoặc credential ra client. Dữ liệu nguồn không hợp lệ hay
timeout không được đổi thành kết quả cho phép.

Work từ chối ref COMMIT không phải 7–40 ký tự hex bằng lỗi validation 400
trước khi gọi Integration; provider cũng kiểm cùng định dạng ở boundary nội
bộ. Adapter Work giữ timeout kết nối 2 giây, đọc 20 giây cho các lượt kiểm
GitHub tuần tự, vẫn từ chối khi hết hạn và không giữ transaction qua HTTP.

Khi liên kết thủ công cùng PR lần nữa, snapshot đã xác minh có thể cập nhật
tiêu đề/trạng thái dù `source_version` của connection giữ nguyên. Work dùng
`synced_at` từ provider để bỏ qua snapshot cũ; không dùng version connection
như version riêng của PR. Đường ingest fact thông thường vẫn kiểm conflict
version như trước. Cập nhật PR không tự hoàn thành Task.

## Ghi dữ liệu và phục hồi

1. Work kiểm quyền và cursor dưới khóa Project, lưu định danh operation trước
   khi gọi prepare. Operation là nơi lưu công việc bền vững, không chứa Bearer.
2. Gọi Integration ngoài transaction. Prepare/reference dùng service key và
   Bearer actor; confirm/abort/status dùng service key, không giả danh bằng JWT cũ.
3. Khóa lại Project, kiểm quyền/generation lần hai. Nếu hợp lệ, commit snapshot
   prepare, receipt chấp nhận bất biến, ý định confirm và Activity/Outbox/receipt
   HTTP trong một transaction. Nếu quyền/trạng thái đã đổi, lưu ý định abort;
   trả lỗi không được làm rollback mất công việc cần hủy.
4. Celery task `apps.integrations.tasks.recover_connections` đọc status rồi
   confirm/abort; response cuối và Kafka cùng dùng service áp dụng kết quả.
   Integration chỉ confirm sau khi đọc receipt Work đã commit.
5. Nếu process chết sau prepare nhưng trước Work chấp nhận, recovery chỉ abort
   reservation tìm được; không tự chấp nhận thay người dùng. Retry request có
   Bearer mới có thể tiếp tục cùng operation khi còn ở trạng thái NEW.

Beat quét mỗi 10 giây, tối đa 20 operation/lượt; NEW intent có khoảng đợi 30
giây để không tranh với prepare đang chạy. Retry tăng dần tối đa 300 giây,
tự động tối đa 10 lần cho confirm/abort, giữ record và log lỗi an toàn khi hết
giới hạn. Khi retry có Bearer mới được chấp nhận, ngân sách retry được đặt lại
để Beat vẫn phục hồi được nếu giao task sau commit thất bại.
Không giả định worker singleton; khóa Project và idempotency provider bảo vệ
khi task được giao nhiều lần.

NEW vẫn được đọc status sau khi hết số lần thử vì chưa có kết quả cuối.
Nếu status 404 và khoảng đợi prepare đã hết, Work đóng intent thành FAILED,
không tạo receipt chấp nhận và không khóa lệnh mới/Leader mới. Record này vẫn
được theo dõi bằng task hiện có: sau 30 giây rồi tối đa mỗi 300 giây. Reservation
đến muộn bị abort; generation thực tế được giữ lại. Khi một generation mới
đã được cấp, prepare cũ không thể thắng kiểm tra generation của provider nên
Work dừng theo dõi intent cũ. Không xóa record chưa đối chiếu xong theo retention.

Sau khi sửa nguyên nhân, có thể yêu cầu xử lý lại đúng record bằng task đang
có, không sửa state hoặc xóa receipt bằng SQL:

```python
from apps.integrations.tasks import recover_connections
recover_connections.delay("<UUID record GitHubConnectionOperation>")
```

Thực hiện trong shell quản trị của chính Work với đúng môi trường. Task có
ID cụ thể cho phép thử lại sau khi hết giới hạn tự động; vẫn kiểm operation
hiện hành. Không dùng `operation_id` nghiệp vụ thay UUID record.

Receipt operation giữ tối thiểu 30 ngày; không dọn binding đang được Project
tham chiếu, operation chưa rõ kết quả hoặc record đang giữ cursor mới nhất.
Receipt HTTP chung vẫn giữ cơ chế/hạn hiện có. Migration mới bảo vệ identity
operation và các trường receipt đã chấp nhận khỏi sửa đổi sau commit.

Work phát `project.repository.requested` sau chấp nhận pending và
`project.repository.updated` khi binding thực sự đổi; các event này đi qua
Outbox Work cùng transaction tương ứng.

## Receipt nội bộ và Kafka

Integration gọi trực tiếp trên mạng backend:

`GET /api/v1/internal/integration/projects/{project_id}/github/operations/{operation_id}`

Endpoint chỉ nhận key chiều Integration→Work, không dùng Bearer làm thay thế.
Trả đúng `applied`, `project_id`, `operation_id`, `generation`, `status=PENDING`,
`repo_id`, `source_version` từ receipt đã commit; đây là bằng chứng chấp nhận,
không phải projection mới nhất. Không có/chưa chấp nhận trả 404. Không nhận
query/body. Gateway chặn `/api/work/api/v1/internal` và mọi path con bằng 404.

Command `consume_integration` đọc topic `utask.integration.events`. Envelope
Integration dùng `payload`, không phải `data` của Work/Identity/Classroom.
Chống lặp theo event ID/hash, kiểm producer/schema/binding và operation đã được
Work chấp nhận trước khi áp dụng. Receipt event commit cùng mutation; offset
chỉ commit sau đó hoặc sau DLQ ACK. Lỗi tạm thời thử lại tối đa 5 lần, sau đó
đưa DLQ có ACK; lỗi DLQ không cho offset đi tiếp.

Event thu hồi binding cũ vẫn được áp dụng khi operation mới pending. Cursor
command không thay generation binding cho kiểm tra này. Event cũ hoặc trùng
không đổi binding mới và không tự xác nhận Task link.

## Cấu hình và khởi động

Pipeline: `.env` của môi trường → `infra/env/work-service.env` → Compose
`env_file` → settings Work. Mẫu tại `.env.example`; không ghi secret thật vào
mapping hay tài liệu.

| Biến Work | Giá trị mặc định / mục đích |
| --- | --- |
| `WORK_INTEGRATION_ADAPTER` | `infrastructure.integration.UnavailableIntegration`; chọn `infrastructure.integration.RemoteIntegration` khi môi trường sẵn sàng. |
| `WORK_GITHUB_CONNECTION_ENABLED` | `false`; bật nhận connect/disconnect mới. |
| `WORK_INTEGRATION_BASE_URL` | `http://integration-service:8000`; origin nội bộ, không có path/query/credential. |
| `WORK_INTEGRATION_SERVICE_KEY` | Key outbound Work→Integration, khớp caller `work` trong `INTEGRATION_SERVICE_KEYS` phía Integration. |
| `WORK_INTEGRATION_INBOUND_KEYS` | JSON list 1–2 key hiện tại/trước của Integration→Work; mặc định `[]`. Key hiện hành khớp `INTEGRATION_WORK_SERVICE_KEY` phía Integration. |
| `WORK_INTEGRATION_KAFKA_GROUP` | `work-integration-connections-v1`. |
| `WORK_INTEGRATION_DLQ_TOPIC` | `utask.work.integration.dlq`. |

Mỗi key là chuỗi ASCII in được 32–4096 ký tự, không có khoảng trắng đầu/cuối;
keys hai chiều khác nhau. Inbound list không được trùng key; cấu hình sai đóng
receipt endpoint. Khi xoay khóa chỉ giữ previous trong tối đa 24 giờ theo
contract, sau đó operator loại bỏ. Không lưu secret trong operation/event.

Integration cần connection/Kafka enabled và key/URL callback đúng theo
[hướng dẫn provider](../integration-service/runtime-connections.md).
Không thay source hoặc hợp đồng Integration/Identity/AI để bật Work. Môi trường
local Kafka startup tạo topic nghiệp vụ và DLQ; broker bên ngoài cần provision
topic cùng ACL Integration produce / Work consume và quyền ghi DLQ phù hợp.

Work chỉ có một container `work-consumer` ở local và staging, chạy
`python manage.py consume_work`. Lệnh này khởi chạy các command hiện có trong
cùng container; mỗi tiến trình giữ group/offset/retry/DLQ riêng. Classroom luôn
chạy; Identity chạy khi có `WORK_IDENTITY_KAFKA_TOPIC`; Integration chạy khi
adapter khác `UnavailableIntegration`. Cờ nhận command GitHub không dừng consumer
Integration để còn xử lý backlog khi rollback. Không cần profile consumer riêng.
Ví dụ local, sau khi đã điền cấu hình và Integration đã chạy:

```bash
docker compose --profile kafka --profile integration-service up -d --build work-service work-publisher work-beat work-consumer
```

Chạy migration trước consumer; Work API entrypoint hiện có thực hiện migration,
consumer local đợi API healthy. Staging dùng quy trình migration/deploy hiện
có, tự cập nhật consumer cùng image pin Work. Giữ `kafka` trong profile nếu dùng
broker Docker. Khi thao tác thủ công có thể
khởi động consumer bằng image đã pin trong `staging-images.json`:

```bash
docker compose -f docker-compose.staging.yml -f staging-images.json --profile work-service up -d --no-build --no-deps work-consumer
```

Chỉ chạy sau khi migration, Kafka và provider đã sẵn sàng; không build lại trên
staging. Artifact release đã bao gồm image pin cho consumer. Cập nhật env phải recreate các process Work nhận
mapping, không chỉ restart.

Một tiến trình con dừng bất thường làm lệnh chung dừng và đóng các tiến trình
còn lại; Docker restart cả container. SIGTERM/SIGINT cho thời gian dừng tối đa
10 giây rồi cưỡng chế tiến trình chưa thoát. Healthcheck chỉ kiểm lệnh chung
đang sống, không chứng minh Kafka/database hoặc cả luồng nghiệp vụ đã hoạt động.

Khi chuyển từ Compose cũ, sau khi image mới sẵn sàng cần dừng/xóa đúng các
container consumer Work cũ của deployment đó trước khi chạy `work-consumer`.
Không xóa volume hoặc dùng `--remove-orphans` cho cả stack. Các group Kafka
không đổi nên giữ vị trí đọc; consumer cũ đã dừng không nên chạy song song.

Khi rollback tính năng, tắt nhận command mới trước; **giữ RemoteIntegration,
key và worker/consumer để hoàn tất backlog đã commit**. Chỉ chuyển unavailable
hoặc dừng process sau khi đối chiếu và xử lý xong backlog. Không reset projection
cũ hoặc dựng receipt từ dữ liệu fixture; kết nối cũ chưa có operation hợp lệ
cần reconnect có xác minh.

## Kiểm chứng và giới hạn

Các test mới nằm ở `tests/unit/test_integration_transport.py`,
`tests/unit/test_integration_consumer.py`, `tests/integration/test_connection_operations.py`
và `tests/integration/test_integration_wire.py` trong app Work; cấu hình được
kiểm ở `scripts/tests/test_work_integration_configuration.py`.

Wire test chạy riêng Django Work và Django Integration, database riêng,
adapter HTTP thật và receipt callback thật. Nếu đặt
`WORK_CONNECTION_TEST_KAFKA` tới broker **test riêng**, test cho publisher
Integration gửi event thật, Work consume và kiểm trạng thái cuối. Nó không
dùng GitHub/Identity thật và không sửa source provider; stand-in chỉ nằm trong
`tests/fixtures/integration_server.py`. Fixture chuẩn bị topic và đợi partition
sẵn sàng trước subscribe; có ca kiểm Kafka message rỗng qua cả vòng lặp command
và retry DLQ. Pytest mặc định và CI hiện không chạy e2e; chủ động gọi module
này trên PostgreSQL/Kafka test riêng khi cần. Workflow dùng chung không dựng
Kafka hoặc hardcode bước kiểm thử theo tên Work.

Chạy bằng môi trường dependency Work đã có và PostgreSQL test, ví dụ trong app:

```bash
python -m pytest -p no:cacheprovider tests/unit/test_integration_transport.py tests/unit/test_integration_consumer.py tests/integration/test_connection_operations.py
python -m pytest -p no:cacheprovider -m e2e tests/integration/test_integration_wire.py
```

Không chỉ định broker runtime hoặc database đang có dữ liệu người dùng cho
các phép thử này. Kết quả chi tiết của lượt triển khai được cập nhật trong
[kế hoạch](integration-implementation-plan.md), không suy staging/provider live
từ test mock, health hoặc schema.

Biên nhận nội bộ đặt `Cache-Control: no-store`. OpenAPI 1.5 sinh từ source giữ
schema `WorkGitHubOperationReceipt`/`WorkGitHubOperationReceiptEnvelope`, ví dụ
kết nối/ngắt kết nối và địa chỉ server nội bộ; không công bố qua gateway.
Hook tài liệu chỉ bổ sung ràng buộc wire đã chốt (trường bất biến, ID và số
phiên bản), không thay validation hoặc trạng thái nghiệp vụ. Test consumer ba
nguồn tạo Project với UUID nhóm/lớp hợp lệ ngay từ đầu, không sửa liên kết
Project sau khi tạo để tránh vượt ràng buộc sở hữu dữ liệu.
