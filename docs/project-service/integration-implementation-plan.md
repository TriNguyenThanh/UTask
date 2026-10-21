# Kế hoạch nối Work với Integration bằng nền hiện có

**Trạng thái: Đã triển khai phía Work — 21/10/2026.** Source và cấu hình Work
đã hoàn thiện theo W1–W4; kết quả kiểm tra và giới hạn nằm ở §9. Luồng hai
backend đã chạy qua HTTP/PostgreSQL/Kafka test riêng với Identity/GitHub stub.
GitHub live cho Project và staging/production chưa xác minh; mặc định giữ tắt.

## 1. Phạm vi và nguồn quyết định

Phạm vi là hoàn thiện phía Work: code, migration, settings và test trong
`apps/work-service/**`, cùng toàn bộ cấu hình, contract và tài liệu phục vụ
Work dù nằm ngoài thư mục app. Các phần Work trong `.env.example`, mapping,
Compose, Nginx và test cấu hình liên quan đều thuộc kế hoạch, phải làm đồng bộ.
File kế hoạch này thuộc tài liệu Work ở `docs/project-service/` theo
[index hệ thống](../system/README.md); Project Service là tên cũ của Work.
Phần thiết kế dưới đây giữ căn cứ/thứ tự của kế hoạch ban đầu; trạng thái thực
thi xem §9 và [hướng dẫn vận hành hiện hành](github-integration.md).

Nguồn hợp đồng là [ADR-005](../adr/005-integration-work-ai-contracts.md),
[guide Work](../integration-service/work-service-integration-guide.md),
[OpenAPI Integration](../../contracts/api/integration-service-v1.yaml) và
[event kết nối](../../contracts/events/integration.project.connection.changed.v1.json).
Không sao chép backend Integration vào Work hoặc đổi contract provider để
né phần Work cần bổ sung. Kế hoạch này chỉ chọn cách thực hiện phía Work.

**Ranh giới service:** không sửa code nghiệp vụ, model/migration hoặc hợp đồng
riêng của Integration, Identity, Classroom hay AI. Dùng provider Integration
đã có theo contract hiện hành. File cấu hình dùng chung được sửa đúng phần
phục vụ Work, giữ nguyên các phần không liên quan. §7 là công việc bắt buộc
trong kế hoạch này, không phải phần chờ xin phép riêng vì nằm ngoài thư mục app.

Không làm frontend, AI context/authorize `github.read`, đồng bộ OAuth account
sang ProjectMember, tự tìm commit/PR để tạo candidate, tự hoàn thành Task,
service mới, dependency mới hoặc chỉnh CI tổng thể.

## 2. Snapshot trước triển khai làm điểm bắt đầu

| Thành phần | Trạng thái và căn cứ hiện tại |
| --- | --- |
| Kiểm quyền, khóa Project, gọi provider ngoài transaction, ghi lại sau khi kiểm quyền lần hai | Đã triển khai trong [repositories.py](../../apps/work-service/apps/integrations/services/repositories.py) ở snapshot trước triển khai. Giữ cách tổ chức này. |
| Projection repository trên Project, Activity và Outbox | Đã triển khai trong [Project](../../apps/work-service/apps/projects/models.py) và [apply_connection_locked](../../apps/work-service/apps/integrations/services/repositories.py). Chưa tách binding đã confirm với operation pending. |
| Fact dữ liệu và adapter thay thế được | Đã triển khai trong [integration.py](../../apps/work-service/infrastructure/integration.py); mặc định `UnavailableIntegration`, chưa có HTTP adapter. |
| TaskGitHubLink, kiểm quyền thành viên, xác nhận và gỡ link | Đã triển khai trong [model](../../apps/work-service/apps/integrations/models.py), [service](../../apps/work-service/apps/integrations/services/links.py), [URLconf](../../apps/work-service/apps/integrations/urls.py). Provider trong các test GitHub hiện được thay bằng [fixture](../../apps/work-service/tests/fixtures/github.py). |
| Receipt API, hash và replay | Đã triển khai trong [receipts.py](../../apps/work-service/apps/messaging/services/receipts.py). Receipt này gắn user/method/path/key, hạn tạo mặc định 24 giờ; không phải receipt operation mà Integration yêu cầu. |
| Celery/Beat, quét phục hồi sau lỗi giao task | Đã có mẫu trong [projects/tasks.py](../../apps/work-service/apps/projects/tasks.py) và [settings](../../apps/work-service/config/settings/base.py). Tận dụng process Work hiện có. |
| Chống lặp event, xử lý record và Kafka config/DLQ | Đã có [consumer.py](../../apps/work-service/apps/messaging/consumer.py), [ConsumedEvent](../../apps/work-service/apps/messaging/models.py), [command Classroom](../../apps/work-service/apps/messaging/management/commands/consume_classroom.py), [Kafka config](../../apps/work-service/infrastructure/kafka/configuration.py). Tận dụng cơ chế; không dùng validator Classroom cho envelope Integration. |
| Provider connection và receipt callback | Đã triển khai phía Integration trong [services.py](../../apps/integration-service/apps/github_connections/services.py) và [WorkClient](../../apps/integration-service/infrastructure/work.py); chưa có endpoint receipt tương ứng trong Work. |

## 3. Thiết kế nhỏ nhất cần bổ sung

### 3.1. Một adapter HTTP cụ thể

Thêm `RemoteIntegration` tại `infrastructure/integration.py`, giữ
`UnavailableIntegration` để mặc định đóng và rollback. Dùng `requests` đang có;
adapter chỉ gửi HTTP, kiểm response và chuyển thành fact Python.

- Gọi prepare/confirm/abort/status và verify reference đúng OpenAPI provider.
- CONNECT map `expected_connection_generation` thành `expected_generation`,
  thêm `action=CONNECT`; DISCONNECT gửi `github_repo_id=null`.
- Reference map `github_ref_id` thành `ref_id`. Không truyền nguyên payload
  hoặc actor object vào JSON. UUID/timestamp phải parse trước khi tạo fact.
- Request từ view hiện mang toàn header Authorization; tách đúng Bearer một
  lần, không tạo `Bearer Bearer ...`. Prepare/reference mang Bearer actor và
  key Work→Integration; confirm/abort/status chỉ dùng service key.
- Timeout 2 giây kết nối/3 giây đọc, không redirect, giới hạn response,
  validate kiểu/binding/status và ánh xạ lỗi an toàn. Không gọi mạng khi giữ
  transaction/khóa. Không lưu hoặc log Bearer, key hay raw exception.

Không tạo base HTTP client, provider registry, repository wrapper hoặc
framework điều phối chung. Giữ `ConnectionFact`/`ReferenceFact` nếu còn phù hợp;
siết validation ở biên HTTP theo contract thật, không tin metadata client.

### 3.2. Một model operation, không thêm bảng job riêng

**Thiết kế đã triển khai:** `GitHubConnectionOperation` trong `apps/integrations/models.py`.
Một record phục vụ cả theo dõi thao tác, receipt callback và công việc cần
retry. Các nhóm dữ liệu cần có:

- Project, operation ID, actor khởi tạo, action và hash nội dung chuẩn hóa;
  unique theo Project/operation, không cho actor khác chiếm operation.
- Yêu cầu ban đầu, snapshot prepare đã xác minh và quyết định Work có chấp
  nhận hay không. Receipt chấp nhận được đóng băng sau commit.
- Tiến độ confirm/abort/status, số lần thử, thời điểm thử tiếp và nhóm lỗi an
  toàn; kết quả cuối để phục hồi và xử lý lặp.
- Thời điểm tạo/hoàn tất/phục vụ retention; index cho các record còn phải xử lý.

Chốt field/constraint bằng migration mới sau khi kiểm source và dữ liệu.
Không sửa migration cũ, không thêm FK xuyên service, không thêm các bảng
Receipt/ConfirmIntent/DispatchJob riêng cho cùng một operation. Receipt API
chung vẫn dùng cho HTTP replay; không đổi TTL toàn bộ API sang 30 ngày.

Giữ các trường repository hiện tại trên Project cho binding đã được xác nhận.
Lưu con trỏ generation cho command mới riêng với generation của binding;
operation pending nằm trong model mới. GET repository phải thể hiện pending
mà không báo repository mới đã CONNECTED. Khi còn pending, chặn xác minh/link
mới theo hành vi provider, dù vẫn giữ snapshot binding cũ để phục hồi.
`expected_connection_generation` phải có nguồn đọc rõ cho command tiếp theo;
nếu cần thêm trường cursor vào response thì cập nhật serializer/schema/test
theo §7, không đổi ngầm nghĩa trường generation của binding.

Receipt callback giữ tối thiểu 30 ngày; record đang đại diện binding hoặc
còn việc phải xử lý không bị dọn vì hết 30 ngày. Sau abort/expire, không lùi
cursor generation, không tự coi quyền binding cũ vẫn hợp lệ. Xử lý theo status
và bằng chứng thu hồi, theo [quyết định wire](../integration-service/work-service-integration-guide.md#quyết-định-wire-cho-runtime-provider).

### 3.3. Một tác vụ phục hồi, một consumer chuyên nghiệp vụ

- Thêm `apps/integrations/tasks.py`: một tác vụ quét batch có giới hạn các
  operation tới hạn, dùng Celery/Beat và queue Work sẵn có. Record operation
  là nguồn bền vững; gọi task sau commit chỉ để giảm độ trễ, không là bảo đảm
  duy nhất. Không thêm dịch vụ dispatcher hoặc container Celery mới.
- Chọn việc trong transaction ngắn, gọi mạng ngoài transaction, khóa Project
  rồi operation để kiểm lại trước khi ghi. Chạy trùng phải an toàn nhờ cùng
  operation/generation và lệnh provider idempotent; không giả định singleton,
  không xây hệ thống lease tổng quát nếu chưa có nhu cầu được chứng minh.
- Đọc status khi kết quả chưa rõ; retry có backoff/giới hạn, lưu lỗi cuối để
  vận hành xử lý. Không đổi operation ID khi timeout, không âm thầm bỏ record
  chưa biết kết quả hoặc dừng hết recovery khi tắt nhận command mới.
- Thêm consumer và management command chuyên event kết nối Integration;
  tái sử dụng `ConsumedEvent`, `consume_event`/`process_record`, Kafka config
  và DLQ hiện có nếu tương thích. Chỉ sửa helper dùng chung khi có test hồi quy
  chứng minh cần thiết; không tái cấu trúc consumer Identity/Classroom.
- Consumer và response confirm dùng chung service áp dụng trạng thái cuối,
  khóa Project, kiểm operation/binding/version và ghi audit/Outbox nguyên tử.
  Receipt chống lặp commit cùng thay đổi, Kafka offset commit sau đó.

## 4. Luồng cần triển khai

1. Giữ GET/POST repository; thêm DELETE cùng tài nguyên. POST là CONNECT,
   DELETE là DISCONNECT; cả hai dùng chung service operation và quyền Leader
   ACTIVE trên Project còn ghi được. Giữ public prefix `/api/work`.
2. Trước prepare, ghi operation và nội dung yêu cầu trong transaction ngắn,
   kiểm quyền/cursor/idempotency. Nhờ vậy process chết sau prepare vẫn có ID
   để tra status. Không lưu token người dùng vào record.
3. Gọi prepare ngoài transaction; lần retry dùng cùng operation và nội dung.
   Nếu mất response, status giúp phân biệt chưa có, PREPARED và trạng thái cuối.
   Worker không tự prepare lại bằng JWT đã lưu; nếu cần Bearer mới, người dùng
   retry cùng operation. PREPARED ở Integration không tự là Work đã chấp nhận.
4. Khóa lại Project và operation, kiểm quyền/generation/binding lần hai.
   Nếu đạt, commit snapshot pending, receipt chấp nhận bất biến, ý định confirm,
   Activity/Outbox và HTTP receipt cùng nhau; trả 202 đúng trạng thái đang chờ.
   Nếu không đạt, giữ binding hiện có và lưu ý định abort bền vững rồi trả lỗi;
   không để rollback nhánh lỗi làm mất cả việc cần abort.
5. Tác vụ phục hồi gửi confirm/abort hoặc đọc status. Confirm chỉ thực hiện
   khi receipt Work đã commit. Response cuối không được ghi đè operation mới,
   binding đã bị thu hồi hoặc source version mới hơn. ABORTED/EXPIRED phải
   giải quyết pending/cursor, không tự bật lại CONNECTED từ snapshot cũ.
6. Receipt nội bộ nhận service key Integration→Work, tra theo Project và
   operation, trả chính xác payload đã chốt ở guide. Không dùng JWT cũ, không
   suy receipt từ projection hiện tại. Chưa chấp nhận/không tìm thấy thì trả
   theo contract, tuyệt đối không tự trả `applied=true`.
7. Consumer đọc `utask.integration.events`, envelope dùng `payload`, không
   phải `data` như event Work/Classroom. Validate producer/type/version và
   binding, chống trùng bằng event ID/hash; chỉ áp dụng operation đã chấp nhận.
   Thu hồi binding cũ vẫn có hiệu lực khi command mới pending; không loại event
   đó chỉ vì generation thấp hơn cursor command. Event không tự confirm Task.
8. Nối `manual_link` với HTTP verify reference; dùng repo/generation của binding
   đã confirm. Giữ kiểm quyền trước/sau HTTP, metadata từ provider, xác nhận
   link và tombstone hiện có. Không đổi trạng thái Task theo trạng thái PR.

Path receipt phải khớp client Integration hiện tại:
`GET /api/v1/internal/integration/projects/{project_id}/github/operations/{operation_id}`.
Đây là đường nội bộ, không đổi public Work về `/api/v1`. Authorize
`github.read` chỉ cần khi nối AI context; không đưa vào lần triển khai này.

## 5. Thứ tự thực hiện và file chịu trách nhiệm

Mỗi bước mang theo test tương ứng; không dồn test xuống bước cuối. Cấu hình
phục vụ bước nào phải hoàn thành cùng bước đó theo §7, không để lại một luồng
chỉ có source nhưng thiếu wiring để chạy.

| Bước | Phạm vi Work | Điều kiện đạt |
| --- | --- | --- |
| W1 — Adapter và cấu trúc operation | `infrastructure/integration.py`, `apps/integrations/models.py`, migration mới; chỉ thêm field Project nếu cần cursor/binding; settings, `.env.example` và mapping Work | Mapping chuẩn, lỗi an toàn, operation unique/rollback/retention; cấu hình mới truyền đủ theo pipeline, giữ tích hợp tắt mặc định. |
| W2 — Connect/disconnect và receipt | `apps/integrations/services/repositories.py`, views/serializers/URLconf hiện có; thêm module operation/receipt theo trách nhiệm khi cần; Nginx và OpenAPI Work | Quyền được kiểm hai lần, không giữ lock qua HTTP, pending/receipt/intent nguyên tử, DELETE đúng contract; receipt không thể giả từ projection và không truy cập được qua gateway công khai. |
| W3 — Phục hồi và consumer | `apps/integrations/tasks.py`, consumer nghiệp vụ, command mới dưới `apps/messaging/management/commands/`, `config/settings/base.py`; phần Work trong Compose/mapping và test cấu hình | Chạy lại sau crash/timeout không sai trạng thái, abort bền vững, event trùng/cũ/revoke đúng; worker/Beat/consumer được khai báo chạy bằng image và Kafka client hiện có. |
| W4 — Reference và nghiệm thu | `apps/integrations/services/links.py`, queries/serializers liên quan; test Work và cấu hình liên quan; contract/tài liệu Work | Branch/commit/PR đi qua adapter thật, repo/generation đúng, thành viên/Teacher/outsider được kiểm; cấu hình Work đầy đủ và chạy kết hợp hai backend thử nghiệm. |

Giữ cấu trúc Django: view xử lý HTTP, serializer validation/representation,
service ghi nghiệp vụ, query đọc và infrastructure giao tiếp bên ngoài.
Không tạo một file cho mỗi hàm. Không chỉnh module Project/Task/Classroom khác
chỉ để làm đẹp cấu trúc. Trước sửa symbol chạy GitNexus impact theo AGENTS;
graph thiếu/stale phải báo giới hạn và đối chiếu source, không xem zero là an toàn.

## 6. Kiểm thử vừa đủ nhưng kiểm đúng rủi ro

- Unit adapter: các call thành công, Bearer/service key đúng, map tên field,
  datetime/UUID, JSON sai/response quá lớn, redirect, 401/403/409/410/503,
  timeout và không rò bí mật. Mock/fake chỉ trong test scope.
- Unit service và PostgreSQL integration: cùng operation cùng payload replay;
  khác actor/payload conflict; mất quyền hoặc generation đổi sau prepare;
  rollback không mất abort; process chết trước/sau prepare hoặc commit; mất
  response confirm; hết retry/expiry; hai request/task đồng thời.
- Consumer: trùng ID cùng/khác hash, sai envelope, operation chưa được chấp
  nhận, event cũ, confirm response/event đến ngược thứ tự, revoke binding cũ
  khi pending mới, DLQ chưa ACK và lỗi commit offset.
- Receipt: key sai/thiếu, không nhận Bearer làm thay service key, chưa commit
  hoặc chưa chấp nhận không thể dùng; snapshot không đổi sau event cuối;
  retention giữ binding đang dùng, không đổi TTL receipt toàn Work.
- Reference/API: repo đang pending/disconnected bị từ chối; branch/commit/PR
  chuẩn hóa; permissions theo service Work hiện có; tiếng Việt trong success,
  business error và serializer/framework validation; merge PR không hoàn Task.
- Trên PostgreSQL test riêng: Django check, migration drift, apply/rollback/apply
  migration mới, các test GitHub/receipt/consumer hiện có và mới. Ruff check và
  format check cho file bị sửa; OpenAPI sinh từ source và validate.
- Test cấu hình Work: biến mẫu → mapping → settings; Compose local/staging
  resolve đúng API/worker/Beat/consumer; gateway chặn receipt nội bộ nhưng
  giữ public API Work; không đổi cấu hình các service khác. Chạy các test
  script/hạ tầng hiện có bị ảnh hưởng và bổ sung assertion đúng phần Work.
- Cuối cùng chạy Work + Integration thật trong môi trường test cô lập qua
  HTTP/Kafka: connect → receipt/confirm → projection → reference → disconnect,
  thêm timeout/replay/revoke. GitHub có thể dùng stub để kiểm boundary nhưng
  phải ghi rõ; nghiệm thu GitHub live chỉ trên repo thử nghiệm được cấp quyền.

Không chạy workflow LIVE đang ghi dữ liệu của người dùng. Không coi mock,
healthcheck hay schema validation là bằng chứng toàn luồng đã chạy.

## 7. Hoàn thiện cấu hình, contract và tài liệu Work

Các việc dưới đây nằm trong phạm vi triển khai phía Work và phải hoàn thành
trước nghiệm thu. Chỉ sửa đúng phần Work trong file dùng chung; không dùng
vị trí file ngoài app làm lý do để bỏ lại cấu hình hoặc yêu cầu quyền riêng.

| Phần phải đồng bộ | Lý do và phạm vi tối thiểu |
| --- | --- |
| `.env.example`, `infra/env/work-service.env` | URL/key Work→Integration, key nhận Integration→Work, cờ bật command và cấu hình consumer cần thiết phải cùng pipeline `.env` → mapping → Compose → settings. Không thêm biến runtime trong Work độc lập với mappings theo AGENTS. Secret thật do môi trường cấp; không đọc/in/commit giá trị. |
| `infra/nginx/nginx.conf` | Chặn prefix internal receipt Work. Hiện chỉ có proxy chung `/api/work/`; key không thay thế việc chặn route nội bộ ở gateway. Không công khai receipt để né sửa Nginx. |
| `docker-compose.yml`, `docker-compose.staging.yml` | Khai báo process consumer bằng command mới, cùng image/env/network Work; không cần broker, DB hoặc Celery worker mới. Không tái cấu trúc topology hiện có. |
| `contracts/api/work-service.yaml` và tài liệu Work liên quan | Xuất lại OpenAPI từ view/serializer thật cho DELETE/receipt và thay đổi response nếu có; cập nhật hướng dẫn cấu hình/khả năng đã có. Không sửa tay contract Integration hoặc tạo schema tưởng tượng. |
| Kết nối với provider Integration hiện có | Cấu hình key/URL/flag và topic/ACL phục vụ kết nối Work theo cơ chế môi trường hiện hành; xác minh keys hai chiều khớp và khác nhau. Nếu cần cập nhật mapping dùng chung hoặc mapping Integration để truyền đúng cấu hình kết nối Work, chỉ sửa các khóa liên quan, không thay nghiệp vụ/hợp đồng provider hoặc cấu hình AI. Test/live nghiệm thu dùng môi trường riêng. |

Chỉ báo hoàn tất sau khi code, cấu hình Work, contract/tài liệu và các kiểm
tra phù hợp đều đạt. Không mở rộng thành chỉnh hạ tầng hoặc nghiệp vụ service
khác. Thiếu credential/provider thực tế phải ghi rõ giới hạn nghiệm thu,
không dùng mock để báo đã kết nối runtime.

Giữ cờ command tắt và adapter unavailable mặc định. Khi tắt nhận command mới,
vẫn cho recovery/receipt xử lý operation đã commit. Môi trường đang có
projection GitHub cũ phải kiểm tra nguồn: không tự dựng receipt từ projection,
không tự tin connection do fixture tạo; chỉ nối lại bằng operation hợp lệ.
Không xóa hay reset dữ liệu cũ hàng loạt.

## 8. Bằng chứng của lượt lập kế hoạch ban đầu

Đã đọc source Work adapter/repository/link/model/receipt/consumer/task,
provider connection/WorkClient phía Integration, ADR-005, guide, contract và
cấu hình liên quan. Các trích dẫn §2 là căn cứ snapshot, không thay review
trước triển khai. GitNexus ở lượt khảo sát trước báo stale; các lần refresh
chưa hoàn tất, không dùng graph đó để tuyên bố phạm vi ảnh hưởng đã xác minh.

Lượt lập kế hoạch chỉ kiểm tra đường dẫn/link, tham chiếu, cấu trúc Markdown
và file rỗng liên quan. Các test và gate ở §5–§6 là việc phải chạy khi triển
khai, không phải kết quả đã đạt của lượt lập kế hoạch. Tại thời điểm đó chưa
sửa source/config, tạo migration, cài dependency, thao tác runtime hoặc commit.

## 9. Kết quả triển khai ban đầu ngày 21/10/2026

**Đã triển khai W1–W4 trong phạm vi Work và cấu hình phục vụ Work.** Không
đổi nghiệp vụ/provider Integration, Identity, Classroom, AI hay frontend;
không thêm dependency, không commit hoặc deploy. Hướng dẫn hiện hành là
[github-integration.md](github-integration.md), tránh dùng snapshot §2 như
hiện trạng sau triển khai.

| Bước | Kết quả và source |
| --- | --- |
| W1 | [RemoteIntegration](../../apps/work-service/infrastructure/integration.py) gửi đúng key/Bearer, map wire, timeout/giới hạn response, kiểm fact và lỗi an toàn. Một [GitHubConnectionOperation](../../apps/work-service/apps/integrations/models.py), migration [0003](../../apps/work-service/apps/integrations/migrations/0003_githubconnectionoperation.py) và [0004](../../apps/work-service/apps/integrations/migrations/0004_connection_operation_guard.py) giữ intent/receipt và bảo vệ bất biến. Không thêm field vào Project. |
| W2 | [Operation service](../../apps/work-service/apps/integrations/services/operations.py) lưu intent trước HTTP, kiểm quyền hai lần, chấp nhận nguyên tử với Activity/Outbox/receipt và giữ abort sau nhánh từ chối. POST/DELETE trả 202, GET có `command_generation`; binding đã confirm lưu riêng với pending. [Receipt view](../../apps/work-service/apps/integrations/views/receipts.py) dùng key chiều riêng, Nginx chặn public prefix internal. |
| W3 | [Recovery task](../../apps/work-service/apps/integrations/tasks.py) dùng worker/Beat Work sẵn có, quét có giới hạn và giữ record khi hết retry. [Consumer](../../apps/work-service/apps/messaging/integration_consumer.py) kiểm envelope `payload`, operation chấp nhận, chống lặp và commit offset sau tác động hoặc DLQ ACK. Có command và consumer profile trong cả Compose local/staging; thêm DLQ vào Kafka startup/mapping. |
| W4 | [Task link service](../../apps/work-service/apps/integrations/services/links.py) dùng binding đã confirm để verify reference qua HTTP adapter; pending chặn link mới. Giữ quyền/confirm/tombstone hiện có. [OpenAPI Work](../../contracts/api/work-service.yaml) được sinh lại từ source; mẫu env, mapping và hướng dẫn đã đồng bộ. |

### Kiểm tra đã chạy

Tất cả database/broker/process bổ sung phục vụ nghiệm thu đều là tài nguyên
test riêng. Không chạy script LIVE hoặc sửa dữ liệu môi trường đang dùng.

| Kiểm tra | Kết quả thực tế |
| --- | --- |
| Work default suite: `python -m pytest -p no:cacheprovider -q` | **815 passed, 3 deselected**. Các marker external/e2e không thuộc lệnh mặc định. |
| `tests/integration/test_integration_wire.py` với `-m e2e`, `WORK_CONNECTION_TEST_KAFKA` trỏ broker test | **1 passed**: Work và Integration chạy Django riêng, database riêng, HTTP adapter và receipt callback thật; connect → replay → PR reference → disconnect; publisher Integration gửi hai event Kafka, Work nhận và kiểm projection. Identity, credential và GitHub boundary là stub test, không phải provider thật. |
| Các tình huống operation bổ sung | **21 passed** riêng module: lost prepare/confirm, crash trước chấp nhận, permission loss, abort/expiry/cursor, revoke binding cũ khi pending mới, concurrent replay, receipt bất biến/retention, event đổi hash, retry cap/manual retry, validation và lỗi ghi Outbox rollback toàn bộ phần chấp nhận. |
| Django check; `makemigrations --check --dry-run` | Không có system check issue hoặc migration drift. |
| Migration mới trên PostgreSQL test | Apply toàn bộ → rollback integrations về 0002 → apply 0003/0004 lại: đạt. Không rollback database runtime. |
| Ruff | Check và format check đạt cho source/test Work bị sửa; test cấu hình scripts kiểm theo cấu hình root. |
| OpenAPI | `spectacular --validate --fail-on-warn` đạt; POST/DELETE 202, receipt và mã lỗi provider được sinh từ view/serializer. |
| Work configuration/local/classroom/Kafka profiles | 25 test chạy trên Windows: **23 đạt, 2 skipped** dành POSIX. Riêng test pin image app/worker/consumer staging đạt. |
| Startup shell trên Linux container | **7 passed**. Một lần chạy ban đầu fail chờ readiness fixture khi build đồng thời; chạy riêng sau đó đạt, không sửa startup để né test. |
| Staging deployment fixtures trên Linux | 51 test được chọn: **50 đạt, 1 skipped** vì container không có Docker CLI. Loại riêng 1 test SSH vì image Work không có `ssh-keygen`. Chạy cả module trên Windows không đạt do Bash/đường dẫn Windows; không coi lượt đó là nghiệm thu deploy. |
| Docker build | Build image `utask/work-service:integration-check-20261021` đạt với dependency production hiện có, không đổi manifest/lock. |
| Docker smoke riêng | API health 200 và public gateway health 200; receipt internal qua gateway 404, `nginx -t` đạt. Redis riêng → Beat gửi `recover_connections` → worker queue `work-publisher` nhận và hoàn tất trên database test; backlog rỗng, không thay cho test nghiệp vụ có operation phía trên. |
| Tài liệu/scope | Kiểm link nội bộ, file Markdown rỗng liên quan và `git diff --check`; thay đổi ngoài phạm vi đã có trong worktree được giữ nguyên. |

GitNexus analyze đã hoàn tất; impact/detect-changes có cảnh báo CRITICAL cho
phạm vi đồ thị và bản diff chung. Đã đọc source trực tiếp và chạy kiểm thử
phạm vi bị ảnh hưởng; không suy CRITICAL thành lỗi runtime đã chứng minh.
Graph có cảnh báo giới hạn callable/process và MCP vẫn báo chậm một commit
sau refresh; các symbol test vừa thêm có thể UNKNOWN. Không coi graph là
bằng chứng đã bao phủ mọi đường gọi hoặc toàn bộ diff của workspace.

### Giới hạn nghiệm thu và bật môi trường

- **Chưa xác minh:** GitHub/Identity live cho luồng Project mới, credential/
  ACL broker của môi trường triển khai, hosted CI, staging và production.
  Không dùng kết quả stub/local để tuyên bố các phần này đã chạy.
- Cờ command mặc định `false`, adapter mặc định unavailable. Chưa thay `.env`
  hoặc recreate container đang dùng. Muốn bật phải cấp key hai chiều khác
  nhau, URL/flag provider và Kafka ACL theo [hướng dẫn Work](github-integration.md#cấu-hình-và-khởi-động).
- Consumer riêng là opt-in. Bổ sung sau review cho deploy/CI được ghi tại §10;
  hướng dẫn Work hiện hành mô tả cách giữ profile consumer qua mỗi release.
- Authorize `github.read` cho AI không thuộc kế hoạch này và không được dựng
  endpoint giả. Projection cũ không có operation hợp lệ không tự thành receipt;
  reconnect phải qua xác minh, không reset dữ liệu hàng loạt.
- Hết 10 lần retry tự động vẫn giữ intent/receipt, có log và cho phép giao lại
  đúng record qua task hiện có. Receipt giữ ít nhất 30 ngày; binding đang dùng
  và cursor mới nhất không bị dọn do hết hạn.

## 10. Sửa lỗi từ rà soát hồi quy ngày 21/10/2026

Phạm vi vẫn là Work và CI/deploy phục vụ Work; không đổi provider Integration,
frontend, credential hoặc `.env.staging` thật, không commit/deploy.

- Reset retry khi chấp nhận operation sau retry người dùng; Beat vẫn chọn được
  CONFIRM khi giao task Redis thất bại. Receipt đã chấp nhận giữ bất biến.
- NEW mất reservation được đóng sau khi status 404 và hết khoảng đợi prepare;
  không chặn lệnh/Leader mới. Task hiện có tiếp tục quan sát intent đã đóng để
  abort reservation đến muộn và giữ generation, hoặc dừng khi generation mới
  đã ngăn prepare cũ thắng. Không tự coi timeout là bằng chứng không có reservation.
- Consumer kiểm `pending is None` để record có payload rỗng không bị thay bằng
  record tiếp theo trước khi DLQ ACK. Có test vòng lặp command với message giả
  có cùng hành vi boolean và test Kafka message thật.
- Snapshot reference đã xác minh qua HTTP có thể cập nhật metadata mới ở cùng
  version connection; timestamp provider ngăn snapshot cũ ghi đè. Ingest thông
  thường vẫn giữ kiểm conflict version. Không hoàn thành Task theo PR.
- Wire fixture chuẩn bị topic trước subscribe. Phần Kafka/bước e2e riêng Work
  từng thêm vào workflow ở snapshot này đã được bỏ theo yêu cầu tại §12.
- Ở snapshot này deploy giữ profile consumer riêng khi môi trường đã chọn;
  tổ chức container hiện hành được thay thế tại §11 theo yêu cầu dùng một consumer.

Kiểm chứng sau sửa trên tài nguyên test riêng:

- Work mặc định: **822 passed, 4 deselected**; toàn bộ 331 file Python Work qua Ruff check và
  format check. Không có Django system issue hoặc migration drift; không sửa
  model/migration trong lượt khắc phục này.
- Wire test với PostgreSQL/Kafka riêng: **2 passed**, gồm luồng hai backend và
  Kafka message rỗng được thử lại trước commit offset. Lượt đầu sau sửa đã chạy
  trên broker chưa có topic; fixture tự chuẩn bị thành công.
- Cấu hình/release/CI trên Windows: **53 test được chọn, 50 đạt, 3 skipped** dành
  POSIX. Các test scripts mới cũng qua Ruff theo cấu hình root.
- Trên Linux: **72 test được chọn, 68 đạt, 4 skipped** do không có Docker CLI
  trong image kiểm thử; loại riêng ca SSH thiếu `ssh-keygen`. Có test script
  deploy giữ profile Work consumer khi đã bật và không tự bật khi chưa chọn.
- Docker image Work build thành công bằng dependency production đã khóa; không
  cài thêm dependency hoặc thay lock. Không deploy và không sửa `.env.staging`.

Hosted CI, VPS/staging và GitHub/Identity live vẫn **Chưa xác minh**. Snapshot
§9 giữ kết quả lượt triển khai trước review, không thay kết quả sau sửa.

## 11. Một container consumer Work

Theo yêu cầu đơn giản hóa, local và staging chỉ còn `work-consumer`, cùng image,
env và profile của Work API. Không còn các service Compose consumer Work riêng
cho từng nguồn hoặc profile consumer mới. `python manage.py consume_work` khởi
chạy lại các command hiện có, giữ group/offset/handler/retry/DLQ từng nguồn:

- Classroom luôn chạy; Identity chạy khi có topic cấu hình.
- Integration chạy khi adapter khác `UnavailableIntegration`, vẫn xử lý backlog
  khi cờ nhận command GitHub tắt. Không tạo biến môi trường hoặc dependency mới.
- Một tiến trình con thoát làm runner dừng, đóng các tiến trình còn lại rồi để
  Docker restart container. Khi dừng bình thường, runner gửi SIGINT, chờ tối đa
  10 giây và kill tiến trình còn treo; Compose cho 15 giây trước cưỡng chế.
- Artifact phát hành tự pin image cho `work-consumer`; deploy không cần mang
  profile consumer riêng. Các command chuyên nguồn vẫn có thể gọi trực tiếp
  để kiểm tra, không có vòng lặp xử lý nghiệp vụ mới.

Thay đổi đi kèm test runner, Compose/healthcheck/env, CA mount, artifact image
và deploy. Module e2e hiện có thêm ca khởi chạy runner thực, nhận event cả ba
nguồn trên Kafka/PostgreSQL test và kiểm shutdown POSIX khi chạy chủ động.
Cách chuyển từ các container
cũ và giới hạn healthcheck nằm tại [hướng dẫn Work](github-integration.md#cấu-hình-và-khởi-động).

Kiểm chứng của lượt gộp container được ghi theo kết quả chạy thực tế; không dùng
kết quả §10 làm bằng chứng runtime của topology mới. Hai lỗi đã nêu trong review
sau §10 (phân loại lỗi status và cleanup đồng thời) chưa được sửa trong phạm vi
gộp container này.

Kết quả lượt gộp container: **277 unit test Work đạt**, gồm 6 ca runner khởi
chạy/dừng/lỗi tiến trình con và cưỡng chế khi quá hạn; Ruff check/format toàn bộ
333 file Python Work và Django system check đạt. Nhóm cấu hình–CI có **66 test
được chọn, 63 đạt, 3 skipped POSIX**, thêm test artifact pin image đạt.
Compose local/staging resolve đúng một `work-consumer` dùng `consume_work`.
Đường dẫn tài liệu và `git diff --check` được kiểm lại.

**Chưa xác minh runtime topology mới:** Docker Desktop không chạy ở lượt này;
lệnh tạo PostgreSQL/Kafka test và build image không kết nối được Docker engine.
Lượt full pytest bị chặn bởi database test không có và đã dừng; không tính các
lỗi kết nối đó thành test nghiệp vụ đạt. Ca e2e ba nguồn được thêm vào module
CI đang chạy nhưng chưa được thực thi local; shutdown POSIX được bỏ qua trên
Windows. Không sửa `.env`/`.env.staging`, không khởi động Docker Desktop hay
container runtime, không commit/deploy. Kết quả runtime §10 không được dùng
để công bố topology mới đã nghiệm thu.

## 12. Bỏ phần Kafka riêng trong workflow

Theo yêu cầu, đã bỏ block Kafka test hardcode theo tên Work và bước e2e riêng
khỏi `python-service.yml`, cùng assertion chỉ dành cho cấu hình đó. Workflow
tiếp tục dùng các bước chung hiện có; không thêm cơ chế discovery hay cấu hình
thay thế. Test e2e trong app vẫn giữ để gọi chủ động khi đã có PostgreSQL/Kafka
test riêng. Không thay Kafka runtime trong Compose, `.env` thật hoặc container
consumer Work trong lượt này.

## 13. Khắc phục lỗi hợp đồng và fixture kiểm thử — 21/10/2026

Đã đồng bộ OpenAPI receipt từ serializer/view thật, giữ ràng buộc dữ liệu đã
chốt và cập nhật trạng thái `implemented`; response thành công đặt
`Cache-Control: no-store`. Không bỏ các ca từ chối payload sai của Integration.
Fixture consumer tạo Project với UUID nhóm/lớp đúng từ đầu, không đổi liên kết
bất biến sau khi tạo.

Fixture e2e Classroom dùng Compose đọc mẫu môi trường và file ghi đè riêng,
bật Kafka, dùng `work-consumer` sẵn có. Ca Admin xóa thành viên gọi helper
publisher thật như các ca đồng bộ khác; bộ này không kiểm lịch Beat Classroom.
Khởi tạo Kafka Docker bổ sung topic hồ sơ Identity và DLQ mà consumer Work
đang dùng. Test cấu hình GitHub dùng file ghi đè để giữ đúng giá trị rỗng trên
cả Windows/Linux. Không thêm service hoặc file test.

Kết quả chạy trên source của lượt sửa:

- Work mặc định: **843 đạt**; chạy lại riêng **25 ca operation/receipt đạt**,
  gồm kiểm header không lưu cache.
- Work–Integration HTTP/PostgreSQL/Kafka và consumer ba nguồn trên Linux:
  **3 đạt**. Identity/GitHub trong wire test vẫn dùng stand-in.
- Integration đầy đủ trên Linux: **985 đạt**, gồm **79 ca contract receipt**.
- Classroom e2e qua Identity/Classroom/Work/Nginx và Kafka thật: **23 đạt**.
- Kiểm tra cấu hình/CI trên Linux: **173 đạt, 1 deselected**, không skip;
  ca gateway được tách chạy với Docker thật trên Windows: **1 đạt**.
- Lint/format Work, Classroom, Integration, xuất OpenAPI, kiểm tra Django và
  migration Work, Docker build Work và liên kết tài liệu liên quan đều đạt.

Các lượt bị Docker Engine lỗi 500 đã bị gián đoạn và được chạy lại tuần tự;
không dùng chúng làm kết quả nghiệm thu. Đợt này không nghiệm thu GitHub live,
VPS hay GitHub Actions hosted; không commit/deploy. Các nhận xét khác của lượt
review trước không được coi là đã giải quyết chỉ vì các bộ test này đạt.
