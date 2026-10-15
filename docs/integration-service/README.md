# Integration Service

**Trạng thái: Thiết kế mục tiêu; hạ tầng và các điểm nối phía service gọi mới có
một phần, runtime Integration chưa triển khai trong repo.** Đối chiếu mã nguồn,
cấu hình, hợp đồng và kiểm thử ngày **15/10/2026**. Phạm vi đầu tiên là GitHub.

## Bộ tài liệu thiết kế

- [Phạm vi và quyền truy cập](scope-access.md): nguồn chuẩn về thẩm quyền
  Work/Identity, ma trận caller, quyền GitHub và thu hồi quyền.

- [API docs](api.md): danh mục endpoint đề xuất, quyền, request/response,
  lỗi và yêu cầu tương thích với client Identity/Work/AI.
- [ERD](../diagram/integration-service/erd.md): thực thể và quan hệ dữ liệu khái niệm.
- [BFD](../diagram/integration-service/bfd.md): sơ đồ phân rã chức năng nghiệp vụ.
- [DFD](../diagram/integration-service/dfd.md): sơ đồ luồng dữ liệu context và mức 1.
- [Mục lục sơ đồ](../diagram/integration-service/README.md).

Các tài liệu này là **Thiết kế mục tiêu**, chưa phải schema/API đã nghiệm thu.

## Vai trò và ranh giới

Theo [baseline](<../architecture/UTask_Architecture_Technology_Baseline (1).md>)
mục 4.4, Integration dùng **Python + Django + Django REST Framework (DRF)**,
tích hợp bằng **GitHub App + Webhooks**; Personal Access Token không phải
phương án chính. Integration là service duy nhất gọi trực tiếp GitHub API.

Integration sở hữu installation của GitHub App, kết nối repository, webhook
và dữ liệu GitHub đã chuẩn hóa trong `integration_db`. `user_id`, `project_id`,
`task_id` là tham chiếu logic; không tạo khóa ngoại hoặc đọc database service
khác. Xem [quyền sở hữu dữ liệu](../system/data-ownership.md).

- **Identity** sở hữu tài khoản UTask, phiên đăng nhập và liên kết OAuth.
  Integration đổi OAuth code và xác minh danh tính GitHub cho Identity.
  Liên kết tài khoản OAuth không thay thế quyền cài GitHub App trên repository.
- **Work** sở hữu Project, Task, ProjectMember, tiến độ và các liên kết nghiệp
  vụ task–GitHub. Integration cung cấp dữ liệu/xác minh phía GitHub; Work kiểm
  tra quyền và quyết định thay đổi nghiệp vụ. Code Work hiện có
  `TaskGitHubLink` và bản sao metadata kết nối trên Project.
- **AI** lấy hoạt động GitHub đã chuẩn hóa qua domain tool/adapter, không gọi
  GitHub trực tiếp. **Notification** có thể nhận sự kiện khi có use case.

Mapping phía nguồn GitHub chỉ cung cấp dữ kiện/ứng viên; Work sở hữu liên kết
nghiệp vụ đã xác nhận. Kết nối kỹ thuật project–repository chỉ thay đổi theo
Work command đã kiểm quyền leader ACTIVE. Browser trực tiếp thực hiện luồng
cài App và đọc danh sách GitHub có kiểm quyền; callback không tự kết nối
Project. Giai đoạn này thu thập GitHub với quyền đọc, chưa ghi issue/PR/comment
hoặc đẩy code lên GitHub.

## Hiện trạng đã đối chiếu

| Hạng mục | Trạng thái | Bằng chứng và giới hạn |
| --- | --- | --- |
| Server Integration | Chưa triển khai | Chưa có `apps/integration-service/`, Django project, migration, Dockerfile hoặc test riêng của service |
| Khai báo local | Một phần | [Compose local](../../docker-compose.yml) trỏ build tới thư mục chưa tồn tại; không thể coi đây là service chạy được |
| Khai báo staging | Một phần | [Compose staging](../../docker-compose.staging.yml) có image và profile `integration-service`; [service discovery](../../scripts/discover_services.py) chỉ chọn app có đủ manifest, lockfile và Dockerfile |
| Gateway | Một phần | [Nginx](../../infra/nginx/nginx.conf) có `/api/integrations/`, bỏ prefix rồi chuyển tới `integration-service:8000`; chưa có backend tương ứng |
| Database và môi trường | Một phần | [Script khởi tạo DB](../../infra/postgres/init-databases.sh) có `INTEGRATION_DB_NAME`; [env service](../../infra/env/integration-service.env) có tên DB và Django secret. Chưa có schema Integration; tài khoản PostgreSQL vẫn dùng chung theo [hiện trạng hạ tầng](../system/data-ownership.md#hiện-trạng-hạ-tầng) |
| Identity gọi Integration | Một phần | [GitHubIdentityProofClient](../../apps/identity-service/authentication/adapters/github_identity_proof.py) có client đổi code và kiểm tra proof; chưa có server Integration. [Test OAuth](../../apps/identity-service/tests/test_oauth_adapters.py) dùng HTTP giả lập |
| Work dùng dữ liệu Integration | Một phần | [Adapter Work](../../apps/work-service/infrastructure/integration.py) có `ConnectionFact`, `ReferenceFact`, `AccountFact`; [settings](../../apps/work-service/config/settings/base.py) mặc định dùng `UnavailableIntegration`, trả lỗi 503 khi cần xác minh |
| AI đọc GitHub context | Một phần | [ContextToolPool](../../apps/ai-service/src/context/tools.py) có `get_development_context()` cho domain `github_activity`; [cấu hình AI](../ai-service/README.md) yêu cầu URL/mapping do service nguồn công bố |
| API và event contract Integration | Chưa triển khai | [API contracts](../../contracts/api/README.md) chưa có contract riêng Integration; [event contract cũ](../../contracts/events/ai-context-v1.yaml) không chứng minh producer Integration đã có |
| GitHub App, webhook, đồng bộ và publisher | Chưa triển khai | Chưa có mã nguồn Integration để thực hiện các chức năng này |

Các test phía gọi kiểm tra quy tắc và dữ liệu giả lập, không chứng minh kết
nối Identity–Integration–GitHub hoặc Work–Integration đã chạy xuyên service.
Đợt cập nhật này không xác minh container/VPS hay GitHub App thực tế.

## Các chức năng mục tiêu

Toàn bộ chức năng trong bảng là **Thiết kế mục tiêu** của Integration.

| Nhóm chức năng | Trách nhiệm và kết quả |
| --- | --- |
| GitHub App installation | Ghi nhận installation, phạm vi repository được cấp quyền và thay đổi/thu hồi quyền truy cập |
| Kết nối repository | Xác minh quyền truy cập repository; cung cấp kết quả kết nối/ngắt kết nối cho Work lưu trạng thái nghiệp vụ |
| Repository metadata | Chuẩn hóa định danh repository, owner, tên và default branch để service khác sử dụng |
| Webhook | Nhận sự kiện GitHub, xác minh chữ ký, nhận diện lần gửi và chống xử lý lặp trước khi thay đổi dữ liệu |
| Đồng bộ dữ liệu GitHub | Thu thập/cập nhật commit, branch, issue và pull request; đồng bộ ban đầu, theo lịch hoặc khi cần phục hồi dữ liệu |
| Contribution | Cung cấp hoạt động đóng góp GitHub đã chuẩn hóa; công thức tổng hợp và cửa sổ thời gian cần đặc tả, không thay chỉ số tiến độ của Work |
| Xác minh liên kết Task–GitHub | Xác minh repository/ref và cung cấp metadata cho Work; cơ chế phát hiện liên kết từ branch/commit/Issue/PR cần chốt thêm |
| Xác minh tài khoản GitHub | Đổi OAuth code, xác minh danh tính phía GitHub, trả proof cho Identity; cung cấp dữ liệu xác minh cho Work theo hợp đồng sẽ chốt |
| API dữ liệu nội bộ | Trả dữ liệu GitHub chuẩn hóa cho Work/AI khi cần phản hồi ngay, kiểm tra caller và phạm vi user/project |
| Phát sự kiện | Lưu thay đổi cùng outbox, sau đó phát sự kiện Kafka để service khác cập nhật dữ liệu đọc hoặc xử lý nghiệp vụ |
| Job nền và phục hồi | Chạy đồng bộ, retry và publisher bằng Celery + Redis thuộc Integration; quy tắc retry, rate limit và lỗi cuối cần chốt trước triển khai |

## Cấu trúc module đề xuất

**Thiết kế mục tiêu — đề xuất tổ chức code, chưa phải cây thư mục hiện có
hoặc quyết định schema.** Tên module có thể điều chỉnh khi triển khai, giữ
ranh giới trách nhiệm dưới đây. Chưa tạo các thư mục này trong đợt tài liệu.

```text
apps/integration-service/
├── config/                 # Django settings, URL gốc, cấu hình Celery
├── apps/
│   ├── installations/      # GitHub App installation và quyền repository
│   ├── repositories/       # Kết nối và metadata repository
│   ├── webhooks/           # Tiếp nhận, xác minh chữ ký, chống xử lý lặp
│   ├── github_data/        # Commit, branch, issue, PR, contribution chuẩn hóa
│   ├── identity_proofs/    # Đổi OAuth code, proof danh tính cho Identity
│   └── messaging/          # Outbox và publication sự kiện Kafka
├── infrastructure/
│   ├── github/             # Client GitHub, credential/token và xử lý rate limit
│   └── service_clients/    # REST client tới service sở hữu dữ liệu khi cần
└── tests/                  # Unit, API, DB và kiểm thử tích hợp giả lập GitHub
```

Trong mỗi module nghiệp vụ: API/serializer kiểm tra đầu vào; lớp service thực
hiện quy tắc và transaction; model/repository giữ dữ liệu của Integration;
Celery task gọi lại lớp service cho xử lý nền. Chỉ adapter `infrastructure/github/`
giao tiếp GitHub, tránh phân tán HTTP và credential vào từng view/task.

API, Celery worker và outbox publisher là các process thuộc cùng Integration
Service. Redis chuyển job nội bộ; Kafka truyền sự kiện giữa service. Không
suy ra số lượng worker hoặc topology triển khai từ cây module này.

## Các luồng chính

**Thiết kế mục tiêu**, theo [luồng hệ thống](../system/workflows.md#github),
[giao tiếp](../system/communication.md) và [Kafka/outbox](../infrastructure/kafka.md).

```text
GitHub webhook
  → xác minh chữ ký + nhận diện delivery trùng
  → chuẩn hóa dữ liệu → Integration DB + outbox (cùng transaction)
  → publisher → Kafka → Work / AI / Notification theo đăng ký

Đồng bộ ban đầu / theo lịch / retry
  → Redis → Celery worker Integration → GitHub API
  → cập nhật dữ liệu + outbox → Kafka

Work / AI → REST nội bộ Integration → dữ liệu/xác minh GitHub chuẩn hóa
Identity  → REST nội bộ Integration → đổi code và proof danh tính GitHub
```

API đồng bộ trả kết quả trực tiếp qua REST; không dùng Kafka làm
request-response. Việc nhận webhook và việc xử lý job nền phải có quy tắc
chống lặp riêng; consumer sự kiện chống lặp theo `event_id`.

## Điểm nối và hợp đồng cần chốt

- **Identity:** client hiện gọi `POST /api/v1/internal/oauth/github/exchange`
  với `X-Service-Key`, timeout 5 giây. Payload gắn `operation_id`, `user_id`,
  provider, code, verifier, redirect URI và thời hạn; client kiểm tra proof
  trả về khớp binding, danh tính và thời gian. Đây là kỳ vọng phía client,
  chưa phải endpoint Integration đã triển khai. Xem [tài liệu Identity](../identity-service/README.md).
- **Work:** `select_repository()` và `verify_reference()` là phương thức
  adapter nội bộ Work. Các fact có generation/source version nhằm kiểm tra
  dữ liệu cũ hoặc xung đột; không tự dùng dataclass này làm JSON contract của
  Integration. Work hiện xác minh ref loại branch, commit và PR; Issue là
  phạm vi mục tiêu, chưa có trong `ReferenceFact` hiện tại. Xem
  [test fact](../../apps/work-service/tests/unit/test_integration_facts.py) và
  [test API GitHub của Work](../../apps/work-service/tests/integration/test_github_api.py).
- **AI:** `github_activity` là tên domain context; URL, quyền theo target,
  giới hạn dữ liệu, freshness và mapping response cần chốt trước khi nối thật.
- **Kafka:** `github.commit.received`, `github.pull_request.opened`,
  `github.pull_request.merged`, `github.issue.updated` là ví dụ thiết kế trong
  [danh mục sự kiện](../system/kafka-events.md), chưa phải tập event/schema
  cuối cùng. Không tự coi contract context AI cũ là contract producer mới.

Trước triển khai cần chốt: quy trình cài/gỡ App; quyền và vòng đời credential;
quy tắc repository–project/task–ref theo ranh giới đã mô tả; endpoint,
auth và lỗi API/webhook; tập dữ liệu lưu, retention và bảo vệ dữ liệu nhạy cảm;
khóa chống lặp, thứ tự/version khi replay; retry/rate limit; tên/schema event,
consumer và tương thích với contract cũ. ERD và API docs mới là đề xuất thiết
kế; chưa có migration hoặc hợp đồng máy đọc được mới được chốt.

## Tiêu chí kiểm thử khi triển khai

Đây là **Thiết kế mục tiêu cho kiểm thử**, chưa có test suite Integration.
Mỗi hàm chức năng cần unit test đường thành công và nhánh lỗi/biên theo
[quy tắc repo](../../AGENTS.md).

- Webhook: chữ ký hợp lệ/sai, payload lỗi, delivery trùng và xử lý lại sau lỗi.
- GitHub adapter: thành công, quyền bị thu hồi, token hết hạn, timeout và rate limit.
- Kết nối/ref: sai project/repository, generation/version cũ hoặc xung đột;
  dữ liệu chưa xác minh không được dùng để thay đổi Work.
- OAuth proof: code thành công/bị từ chối; sai user/operation/provider, hết hạn
  và replay; không ghi code/token vào log hoặc event.
- DB/outbox: rollback không phát event, publish lỗi được thử lại, consumer
  không tạo hiệu ứng lặp; kiểm tra bằng test tích hợp với hạ tầng phù hợp.
- API nội bộ: caller không hợp lệ, user thiếu quyền và dữ liệu ngoài phạm vi
  project bị từ chối; kiểm thử xuyên service trước khi đánh dấu đã tích hợp.
