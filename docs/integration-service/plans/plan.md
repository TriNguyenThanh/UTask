# Kế hoạch hoàn thiện Integration Service để kết nối Work và AI

## 1. Mục tiêu và ranh giới

- Hoàn thiện contract trước, sau đó mới triển khai runtime Integration.
- Chỉ sửa source trong `apps/integration-service/**`; được sửa `contracts/**`, tài liệu, env/Compose/CI thuộc Integration.
- Không sửa source Work hoặc AI. Thay vào đó tạo hai tài liệu triển khai quyết định-đầy-đủ cho từng service.
- Work là service duy nhất ra lệnh kết nối/ngắt repository và xác minh GitHub reference.
- AI chỉ đọc `github_activity` đã lọc qua REST; không nhận token, không mutation, không gọi GitHub trực tiếp.
- Kafka chỉ phát `integration.project.connection.changed` cho Work trong milestone này; AI chưa consume event.
- Giữ `GitHubInstallation` là metadata hint. Tạo aggregate Project connection riêng, không dùng installation metadata như quyền Project.

## 2. Contract và tài liệu phải hoàn thành trước source

### OpenAPI Integration 1.4.0

Cập nhật `contracts/api/integration-service-v1.yaml`, thêm `ServiceKey` và các internal API sau; tất cả bị chặn tại public gateway:

| API                                                                     | Caller              | Hành vi                                                                                                                     |
| ----------------------------------------------------------------------- | ------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| `POST /api/v1/internal/projects/{project_id}/github/connection/prepare` | Work + Bearer actor | Chuẩn bị `CONNECT` hoặc `DISCONNECT`, kiểm CAS/idempotency và quyền GitHub live; trả `ConnectionFact` trạng thái `PENDING`. |
| `POST .../connection/confirm`                                           | Work                | Xác minh Work đã lưu receipt qua callback Work rồi chuyển connection thành `CONNECTED`/`DISCONNECTED`.                      |
| `POST .../connection/abort`                                             | Work                | Hủy operation `PREPARED`; không tác động generation mới hơn.                                                                |
| `GET .../connection/operations/{operation_id}`                          | Work                | Phục hồi sau timeout/mất response; trả trạng thái `PREPARED`, `CONFIRMED`, `ABORTED` hoặc `EXPIRED`.                        |
| `POST .../github/references/verify`                                     | Work + Bearer actor | Xác minh `BRANCH`, `COMMIT`, `PULL_REQUEST` thuộc repository/generation hiện hành; trả `ReferenceFact`.                     |
| `GET .../github/context`                                                | AI + Bearer actor   | Gọi Work authorize, sau đó trả `ContextDocument(domain="github_activity")` đã giới hạn và lọc.                              |

Quy tắc wire:

- `X-Service-Key` bắt buộc; key Work và AI tách riêng, so sánh constant-time.
- Mutation từ Work forward Bearer actor; Integration xác minh actor qua Identity.
- `prepare` nhận `operation_id`, `action`, `expected_generation`; `github_repo_id` bắt buộc với `CONNECT`, phải `null` với `DISCONNECT`.
- Retry cùng operation và cùng payload trả đúng kết quả cũ; payload khác trả `409 OPERATION_CONFLICT`.
- Generation sai trả `409 VERSION_CONFLICT`; operation hết hạn trả `410 OPERATION_EXPIRED`.
- `ConnectionFact` giữ đúng shape Work đang dùng: project/operation, generation, source version, status, repo ID/owner/name/default branch và `synced_at`.
- `ReferenceFact` giữ đúng shape Work đang validate; URL chỉ được là HTTPS `github.com`, không query/credential.
- AI context dùng schema hiện có của AI: `domain`, `as_of`, `status`, `source_version`, `data`, `warning`. `data` chỉ chứa `commits`, `pull_requests`, `issues`, `mapping_status`; danh sách tối đa 20 phần tử mỗi loại.
- API context trả `partial` khi một loại activity không được cấp quyền, `stale` khi connection cần revalidation, `missing` khi Project chưa kết nối; không giả dữ liệu rỗng thành `available`.
- Error envelope tiếp tục là `{success:false,error:{code,message}}`; không trả chi tiết upstream hoặc secret.
- Contract ban đầu đánh dấu `design-approved-m5/m6`; chỉ đổi sang `implemented` sau khi runtime và contract tests đạt.

### Event contract

- Giữ schema v1 `integration.project.connection.changed`; đổi trạng thái từ thiết kế sang implemented khi publisher chạy.
- Chỉ phát trạng thái cuối `CONNECTED` hoặc `DISCONNECTED`, không phát `PENDING`.
- Key Kafka là `project_id`; thứ tự được bảo đảm theo sequence của từng Project.
- Event được tạo cùng transaction xác nhận/ngắt connection; retry broker không tạo event ID mới.
- Kafka không cấp quyền, không xác nhận Task link và không thay REST command.

### Bộ tài liệu bàn giao

Tạo:

- `docs/integration-service/work-service-integration-guide.md`: HTTP adapter, public Work API connect/disconnect, durable confirm/abort dispatcher, receipt callback cho Integration, Kafka consumer, reconcile, service keys, rollout flag và test matrix.
- `docs/integration-service/ai-service-integration-guide.md`: thêm AI service key vào REST adapter, URL mapping `project:github_activity`, Work authorization, ContextDocument mapping, stale/partial behavior và tests.
- ADR mới chốt Work/AI caller matrix, prepare-confirm, callback receipt, AI read-only context và Kafka ownership.
- Cập nhật README/API/repository-linking/communication/Kafka docs; không mô tả Work/AI implementation là đã chạy.

## 3. Triển khai Integration Service

### Persistence và transaction

Tạo app/domain `github_connections` với migration:

- `ProjectConnection`: `project_id` UUID primary key logic; connector `user_id`; installation/repository metadata; `generation`, `source_version`, final status; current operation; timestamps; per-project event sequence.
- `ConnectionOperation`: bigint identity PK; project, operation ID, caller, command, payload hash, expected/result generation, state, result JSON, expiry 24 giờ, tombstone 30 ngày.
- `IntegrationOutboxEvent`: UUID event ID, project/sequence, event envelope, publish state, retry metadata và timestamps.

Ràng buộc:

- Unique `(project_id, operation_id)` và `(project_id, event_sequence)`.
- Check constraint cho state/status/action, generation/version dương và field repo theo trạng thái.
- Partial index cho operation còn `PREPARED`/chưa hết hạn và outbox chưa publish.
- Không FK sang Work, Identity hoặc installation của service khác; `installation_id` chỉ là tham chiếu logic.
- Mọi CAS dùng `select_for_update()` trên ProjectConnection; không giữ DB lock trong lúc gọi GitHub hoặc Work.
- Luồng mutation: đọc/claim ngắn → gọi HTTP ngoài transaction → khóa lại và xác minh generation/operation → commit state + outbox nguyên tử.

### Authentication và service adapters

- Thêm permission nội bộ nhận allowlist `{work, ai}` từ `INTEGRATION_SERVICE_KEYS`.
- Thêm outbound Work client dùng `INTEGRATION_WORK_URL` và key riêng `INTEGRATION_WORK_SERVICE_KEY`, timeout connect 2 giây/read 3 giây, không redirect.
- Confirm gọi endpoint receipt của Work mà guide quy định; chỉ finalize khi project, operation, generation, repo và trạng thái Work khớp.
- AI context gọi Work authorize với action `github.read`; lỗi/timeout fail closed.
- Internal route không phụ thuộc gateway header do client điều khiển và không log service key/Bearer.

### GitHub verification

Mở rộng `GitHubAppClient` bằng method mới, không thay semantics discovery hiện có:

- Tìm repository theo ID trong các installation live với giới hạn trang hữu hạn.
- Lấy repository metadata gồm owner, name, default branch.
- Xác minh branch, commit và PR bằng endpoint GitHub tương ứng.
- Đọc tối đa 20 commit/PR/issue gần nhất cho AI context; validate chặt response và giới hạn body.
- Pin GitHub API version hiện hành; yêu cầu App permissions `Metadata`, `Contents` và `Pull requests: read`; Issues là tùy chọn và làm context `partial`.
- Dùng credential của actor đã tạo connection để đọc repository cho Project. Revoke/reauth của actor làm connection không còn phục vụ context/reference cho tới khi reconnect.
- Sau mọi provider call, kiểm tra lại credential generation/version trước khi commit hoặc trả fact.

### Lifecycle và failure recovery

- `prepare CONNECT`: kiểm repo live, tạo operation `PREPARED`, tăng generation đúng một lần và trả `PENDING`.
- `confirm`: kiểm Work receipt ngoài lock, sau đó CAS operation hiện hành, chuyển `CONNECTED`, tăng source version và tạo outbox.
- `abort`: chỉ hủy đúng operation/generation đang `PREPARED`; operation cũ không được đụng connection mới.
- `DISCONNECT` dùng cùng prepare/confirm protocol; kết quả cuối xóa metadata repo và phát `DISCONNECTED`.
- Beat tự expire `PREPARED` quá 24 giờ; giữ tombstone để retry muộn không chạy lại.
- Webhook uninstall/suspend/repository removed và account revoke phải tìm connection liên quan, chuyển `DISCONNECTED` nguyên tử và tạo outbox. Event added/unsuspend chỉ đánh dấu cần revalidation, không tự reconnect.
- Status endpoint là nguồn phục hồi khi Work mất response; không cho retry tạo generation mới.
- Giữ GitHub webhook jobs hiện có; thêm job kind riêng cho expire/reconcile nếu cần, không trộn payload secret vào outbox.

### Kafka và hạ tầng

- Thêm `confluent-kafka`, Kafka connection validation và publisher idempotent.
- Celery Beat quét outbox; worker publish theo head từng Project, backoff tối đa 300 giây và giữ event để replay thủ công.
- Kafka lỗi không rollback connection đã commit và không làm health API thất bại; quan sát qua pending age/retry/error class.
- Bổ sung Integration topic vào script tạo topic, env local/staging, Compose dependency tùy chọn và certificate mount cho SSL/SASL.
- Feature flags mặc định tắt: `INTEGRATION_CONNECTIONS_ENABLED`, `INTEGRATION_KAFKA_ENABLED`, `INTEGRATION_AI_CONTEXT_ENABLED`.
- Rollout: migration → deploy API/worker/Beat với flags tắt → cấu hình keys/Work callback/Kafka → smoke internal APIs → bật Work REST → bật Kafka → bật AI context.

## 4. Yêu cầu triển khai trong tài liệu Work và AI

### Work Service

Guide phải yêu cầu đội Work:

- Thêm HTTP adapter thay `UnavailableIntegration`, nhưng giữ flag rollback.
- Không giữ Work transaction/row lock qua HTTP.
- Sau `prepare`, recheck Leader/generation, lưu projection `PENDING`, receipt và confirm intent trong cùng transaction.
- Durable dispatcher gọi confirm; nếu Work từ chối sau prepare thì ghi abort intent; timeout phải đọc operation status trước khi retry.
- Thêm internal receipt endpoint chỉ dành cho Integration, không cần Bearer cũ.
- Thêm `DELETE /projects/{id}/github/repository/` dùng protocol `DISCONNECT`.
- Consumer Kafka dedupe `event_id`, chỉ áp dụng operation đã được Work chấp nhận và generation/source version mới hơn.
- Adapter verify reference map chính xác sang `ReferenceFact`.
- Test race membership/generation, response loss, duplicate command/event, stale event, confirm/abort muộn và rollback sang unavailable adapter.

### AI Service

Guide phải yêu cầu đội AI:

- Adapter context gửi `X-Service-Key` riêng AI cùng Bearer actor; không gửi key xuống agent.
- `AI_CONTEXT_URLS["project:github_activity"]` trỏ endpoint Integration.
- Quyền Project vẫn được Work kiểm; Integration gọi Work authorize trước khi trả context.
- Giữ filtering/budget hiện có; không thêm tool hạ tầng hoặc cho agent gọi Integration trực tiếp.
- Map `available/partial/stale/missing/unavailable` sang behavior hiện hành; stale/missing không được silently fallback fixture ngoài development/test.
- Test service key, actor không có quyền, context partial/stale, response quá lớn, timeout và schema sai.

## 5. Kiểm thử, nghiệm thu và giả định

### Test Integration bắt buộc

- Contract: OpenAPI hợp lệ; mọi request/response/example mới validate; internal routes yêu cầu đúng caller key; không leak secret.
- Unit: permission/service-key, Work client, GitHub parsing/limits, payload digest, CAS validation, ContextDocument mapping và Kafka configuration.
- PostgreSQL integration:
  - prepare/confirm/abort/status thành công;
  - replay cùng payload và conflict khác payload;
  - hai prepare đồng thời;
  - confirm/abort cũ sau generation mới;
  - provider/Work timeout không giữ lock;
  - outbox commit cùng connection;
  - webhook/revoke disconnect đúng connection;
  - expire operation và retention.
- Kafka: retry giữ nguyên event ID; publish theo project sequence; broker lỗi để row pending; cleanup chỉ xóa row đã publish quá retention.
- Runtime fake-service E2E: Work stub → Integration → GitHub fake → confirm callback → event; AI stub → Work authorize → Integration context.
- Live dev acceptance: connect repo, verify branch/commit/PR, đổi quyền repo, revoke/reconnect, broker restart; không dùng live test trong CI.

### Lệnh xác minh

- `cd apps/integration-service && uv sync --all-groups --locked`
- `uv run ruff check .`
- `uv run ruff format --check .`
- `uv run python manage.py check`
- `uv run python manage.py makemigrations --check --dry-run`
- `uv run pytest`
- `python3 -m unittest scripts.tests.test_integration_compose`
- Render cả `docker-compose.yml` và `docker-compose.staging.yml` với profile Integration.
- Validate OpenAPI, JSON Schema event, link tài liệu, `git diff --check`.
- Trước commit chạy GitNexus `detect_changes(scope="all")`; kết quả partial/truncated không được coi là sạch.

### Tiêu chí hoàn tất

- Integration provider side chạy được mà không cần sửa source Work/AI trong cùng thay đổi.
- Contract được tạo trước code và runtime cuối khớp contract.
- Connect/disconnect/reference verification có idempotency, CAS và recovery đầy đủ.
- AI context read-only đúng schema, được Work authorize và không lộ credential.
- Outbox/event bền vững, có retry/replay và không làm mất transaction nghiệp vụ.
- Work và AI có guide đủ chi tiết để triển khai không cần tự quyết thêm interface.
- Chỉ sau E2E với implementation thật của Work/AI mới đổi tài liệu từ “sẵn sàng kết nối” sang “đã tích hợp runtime”.

### Giả định đã khóa

- “contacts” được hiểu là `contracts/`.
- OpenAPI giữ cùng file `integration-service-v1.yaml`, tăng minor version lên 1.4.0 vì chỉ thêm endpoint.
- Không tạo OpenAPI giả cho Work/AI trước khi source hai service tồn tại; interface phía họ nằm trong guide và ADR.
- GitNexus đã refresh với PDG tại HEAD `f70e5e7`; PDG không trích được control-flow hữu ích cho các hàm Python trung tâm, và impact metadata có kết quả risk không nhất quán. Source hiện tại là bằng chứng chính; thay đổi `GitHubInstallation` được xem là rủi ro cao và tránh chỉnh semantics.
