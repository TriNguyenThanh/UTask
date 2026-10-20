# Cách hoạt động của liên kết repository GitHub

**Trạng thái: Một phần.** Integration Service đã có luồng cấp quyền GitHub
App, cài đặt App và đọc repository theo quyền live của GitHub. Work Service đã
có projection repository của Project và bảng liên kết hoạt động GitHub của
Task, kèm guard và test với adapter giả. Tuy nhiên adapter live nối Work với
Integration và GitHub thật vẫn chưa được xác minh. Tài liệu tách rõ phần đã có
trong source, phần có contract nhưng chưa nối runtime và thiết kế mục tiêu.

## Phân biệt các khái niệm

Trong luồng hiện tại, “liên kết repository” có nghĩa là UTask có thể xác định
installation và đọc được repository mà GitHub App được cấp quyền truy cập.
Nó chưa có nghĩa là repository đã được gắn vào một Project UTask.

| Khái niệm | Ý nghĩa | Nơi sở hữu |
| --- | --- | --- |
| Cấp quyền GitHub | UTask đổi consent lấy GitHub user access/refresh token có hạn | Integration |
| Installation | Một lần GitHub App được cài vào tài khoản hoặc tổ chức GitHub | Integration lưu metadata |
| Repository access | Danh sách repository hiện GitHub cho phép user và App đọc | GitHub là nguồn live |
| Project connection | Gắn một repository chính vào Project và áp dụng quyền Work | Work có source/contract; live adapter chưa xác minh |

Installation metadata trong Integration chỉ là thông tin trạng thái. Quyền
đọc repository luôn được kiểm tra lại từ GitHub; không dùng metadata cũ để cấp
quyền. Integration là service duy nhất gọi GitHub API. Work chỉ nhận các fact
đã được adapter xác minh, không nhận GitHub token và không gọi GitHub trực
tiếp.

## Luồng tổng quát

```text
Người dùng đăng nhập UTask
        |
        v
Identity xác minh Bearer qua /users/me
        |
        v
Integration authorization start/complete
        |
        v
GitHub user authorization ACTIVE
        |
        v
Integration installation start
        |
        v
Người dùng cài GitHub App trên GitHub
        |
        v
installation complete: kiểm tra state + nonce + actor + credential
        |
        v
Installation ACTIVE -> đọc danh sách repository live
        |
        v
Leader → Work chọn repository chính của Project
        |
        v
Work → adapter Integration xác minh → Project CONNECTED
        |
        v
Member → Work liên kết branch/commit/PR vào Task
        |
        v
Work → adapter Integration xác minh → TaskGitHubLink CONFIRMED
```

Mỗi request user phải dùng Bearer UTask của chính actor đó. Integration không
nhận `user_id` từ client để chọn người khác.

## Điều kiện trước khi cài App

1. Người dùng đăng nhập UTask và có access token hợp lệ.
2. Integration gọi Identity `GET /users/me` để xác minh actor.
3. Người dùng hoàn tất GitHub App user authorization, để account có
   `authorization_status=ACTIVE`.
4. GitHub App đã được bật và cấu hình đúng App ID, App slug, OAuth client,
   redirect/setup URI, webhook secret và credential key ring.

Nếu credential chưa hoạt động, provider bị tắt hoặc cấu hình thiếu, endpoint
provider trả lỗi thay vì tạo liên kết giả.

## Các bước cài App và đọc repository

### 1. Bắt đầu installation

Client gọi:

```http
POST /api/v1/github/installations/start
Authorization: Bearer <utask_access_token>
```

Request không có body hoặc query. Integration:

- kiểm tra credential GitHub đang hoạt động;
- tạo `state` và nonce ngẫu nhiên;
- lưu bản băm của state, nonce, actor, Bearer session, generation và
  credential version trong Integration database;
- hủy các pending installation cũ của actor;
- đặt cookie HttpOnly `utask_github_installation`;
- trả `installation_url` và `expires_at`.

State có thời hạn 600 giây. Client phải giữ nguyên Bearer và cookie này cho
đến bước complete. Cookie installation khác cookie consent authorization
`utask_github_consent`.

### 2. Người dùng cài App trên GitHub

Client mở `installation_url`. Người dùng chọn tài khoản/tổ chức và phạm vi
repository trên GitHub. Sau khi hoàn tất, GitHub chuyển về setup URI với các
giá trị:

- `state`: state của lần start mới nhất;
- `installation_id`: ID installation GitHub;
- `setup_action`: `install`, `update` hoặc `request`.

Đây là callback của GitHub App installation, không phải OAuth callback có
`code`.

### 3. Hoàn tất installation

Client gửi các giá trị callback về:

```http
POST /api/v1/github/installations/complete
Authorization: Bearer <utask_access_token>
Cookie: utask_github_installation=<nonce>
Content-Type: application/json

{
  "state": "<state>",
  "installation_id": "123456",
  "setup_action": "install"
}
```

Integration chỉ chấp nhận request khi đồng thời thỏa các điều kiện:

- actor từ Bearer là actor đã tạo pending installation;
- state tồn tại, chưa dùng và chưa hết hạn;
- cookie nonce khớp với pending record;
- generation và credential version chưa thay đổi;
- `installation_id` là chuỗi số dương hợp lệ.

Với `install` hoặc `update`, Integration dùng GitHub user token để:

1. đọc danh sách `/user/installations` theo từng trang;
2. tìm installation có ID tương ứng;
3. kiểm tra App ID đúng với App của UTask và installation không bị suspended;
4. gọi danh sách repository của installation để xác nhận quyền truy cập;
5. lưu metadata installation và trả `status=ACTIVE`.

Nếu `setup_action=request`, GitHub mới ghi nhận yêu cầu chờ phê duyệt. Kết
quả là `PENDING_APPROVAL`, không được coi là installation hoạt động.

### 4. Đọc installation và repository

Liệt kê installation:

```http
GET /api/v1/github/installations?page=1&per_page=30
Authorization: Bearer <utask_access_token>
```

Đọc repository của một installation:

```http
GET /api/v1/github/installations/123456/repositories?page=1&per_page=30
Authorization: Bearer <utask_access_token>
```

Hai endpoint đều lấy dữ liệu live từ GitHub. `page` mặc định là `1`,
`per_page` mặc định là `30` và tối đa là `100`. Kết quả có dạng envelope:

```json
{
  "success": true,
  "data": {
    "items": [
      {
        "repository_id": "987654",
        "name": "utask-demo",
        "full_name": "example/utask-demo",
        "private": true
      }
    ],
    "next_page": null
  }
}
```

Danh sách installation được lọc theo App ID của UTask và bỏ installation đã
suspended. Danh sách repository không được cache như nguồn cấp quyền. Trước
khi trả kết quả, Integration kiểm tra credential và generation vẫn hiện hành.

## Lớp Work: chọn repository chính cho Project

Sau khi Integration đã có installation và quyền đọc repository, Leader chọn
một repository chính cho Project qua Work:

```http
POST /projects/<project_id>/github/repository/
Authorization: Bearer <utask_access_token>
Idempotency-Key: <optional-key>
Content-Type: application/json

{
  "github_repo_id": "987654",
  "operation_id": "operation-01",
  "expected_connection_generation": 0
}
```

Work không tin các metadata repository do client gửi. Quy trình source hiện tại
là:

1. Khóa Project và kiểm tra actor là Leader ACTIVE, Project chưa bị archive/
   delete và `expected_connection_generation` còn đúng.
2. Ghi nhận idempotency receipt nếu operation đã từng xử lý.
3. Gọi `integration_client().select_repository(...)` qua ranh giới adapter,
   truyền Project, actor, Bearer và operation. Lời gọi này phải được thực hiện
   ngoài transaction/lock của Work.
4. Kiểm tra `ConnectionFact` trả về: đúng Project, operation, repository,
   generation, source version và trạng thái hợp lệ.
5. Khóa lại Project, kiểm tra Leader/generation lần hai để chống race.
6. Lưu projection gồm repository ID, owner, name, default branch, trạng thái,
   generation, source version và thời điểm đồng bộ; đồng thời ghi Activity,
   Outbox event và receipt.

Trạng thái có thể là `PENDING`, `CONNECTED` hoặc `DISCONNECTED`. `PENDING`
trả `202`; `CONNECTED` trả `200`. Retry cùng operation trả lại receipt thay vì
tạo connection mới. Generation/source version cũ không được ghi đè connection
mới.

GET cùng route chỉ đọc projection Work, không gọi provider. Work sở hữu quyền
Leader và Project; Integration sở hữu việc xác minh GitHub. Contract chi tiết
nằm trong [Work API](../../contracts/api/work-service.yaml), còn logic hiện
tại ở [repository service](../../apps/work-service/apps/integrations/services/repositories.py)
và [adapter contract](../../apps/work-service/infrastructure/integration.py).

> **Giới hạn hiện trạng:** Work mặc định dùng `UnavailableIntegration`. Các
> test hiện có thay adapter bằng gateway giả để kiểm tra guard, idempotency,
> generation và race; điều đó chưa chứng minh Work gọi được Integration/GitHub
> thật.

## Lớp Work: liên kết hoạt động GitHub vào Task

“Liên kết repo” thường có bước tiếp theo: gắn một branch, commit hoặc Pull
Request của repository chính vào Task. Đây là dữ liệu nghiệp vụ của Work,
không phải bảng của Integration.

### Tạo liên kết

Project phải ở trạng thái `CONNECTED`. Thành viên ACTIVE hoặc Leader gửi tối
thiểu dữ liệu sau:

```http
POST /tasks/<task_id>/github-links/
Authorization: Bearer <utask_access_token>
Idempotency-Key: <optional-key>
Content-Type: application/json

{
  "link_type": "PULL_REQUEST",
  "github_ref_id": "#24"
}
```

Client chỉ gửi loại và mã tham chiếu. Với Pull Request, `#24` được chuẩn hóa
thành `24`. Client không được tự gửi title, status, URL, repository ID hay cờ
verified.

Work lấy repository ID và generation từ Project, sau đó gọi
`integration_client().verify_reference(...)`. Integration/adapter phải trả
`ReferenceFact` đã xác minh, gồm Project, repository, generation, source
version, loại ref, metadata và URL GitHub hợp lệ. Work kiểm tra lại:

- ref thuộc đúng repository chính của Project;
- generation chưa cũ và Project vẫn `CONNECTED`;
- fact có `is_verified=true`;
- loại ref và mã ref khớp request;
- Pull Request có mã số dương và trạng thái hợp lệ.

Khi kiểm tra đạt, Work tạo `TaskGitHubLink`, lấy metadata từ fact, ghi
Activity/Outbox và xác nhận liên kết trong cùng transaction. Liên kết thủ công
thành công trả `201` với `confirmation_status=CONFIRMED`.

### Candidate và xác nhận thủ công

Nguồn đồng bộ hoặc quy trình ingest có thể tạo candidate
`confirmation_status=PENDING`. Người dùng có quyền ghi xác nhận candidate:

```http
POST /tasks/<task_id>/github-links/<link_id>/confirm/
Authorization: Bearer <utask_access_token>
Idempotency-Key: <required-key>
```

Work khóa Task/Project/Link, kiểm tra member ACTIVE, repository và generation
hiện hành, rồi mới chuyển `PENDING` thành `CONFIRMED`. Provider verification
không tự thay thế quyết định xác nhận của người dùng. Việc xác nhận liên kết
GitHub cũng không tự chuyển Task sang `COMPLETED`.

### Đọc và gỡ liên kết

- `GET /tasks/<task_id>/github-links/` trả các link chưa bị tombstone.
- `DELETE /tasks/<task_id>/github-links/<link_id>/` chỉ đánh dấu link đã gỡ
  trong Work; không xóa branch, commit hoặc Pull Request trên GitHub.
- Nếu repository của Project đổi generation, candidate/link cũ không được xác
  nhận hoặc cập nhật vào repository mới. Lịch sử link cũ vẫn giữ repository ID,
  generation và source version để audit.

Logic hiện tại nằm ở [link service](../../apps/work-service/apps/integrations/services/links.py),
[TaskGitHubLink model](../../apps/work-service/apps/integrations/models.py) và
các [integration tests](../../apps/work-service/tests/integration/test_github_api.py).

## Refresh và mất quyền

Khi GitHub access token sắp hết hạn, luồng truy cập có thể kích hoạt refresh
đang có. Refresh dùng claim, version và generation để tránh hai worker cùng
ghi đè credential. Nếu kết quả refresh không rõ hoặc GitHub đã xoay token,
Integration giữ trạng thái `REAUTH_REQUIRED`; không khôi phục token cũ.

GitHub gửi webhook khi quyền thay đổi:

- uninstall App: installation local chuyển `DELETED` sau khi job xử lý;
- suspend hoặc thay đổi repository: metadata bị đánh dấu cần kiểm tra lại;
- revoke authorization: credential local bị thu hồi ngay, token mã hóa bị xóa;
- delivery được xác thực HMAC và lưu bền vững trước khi trả `202`.

Sau khi mất quyền, API repository không được tiếp tục tin vào installation cũ;
client phải yêu cầu cấp quyền lại hoặc cài App lại. Việc cài lại tạo pending
flow mới và không mặc định tái sử dụng installation ID cũ.

## Bảo mật và ranh giới dữ liệu

- Không ghi access token, refresh token, cookie, state hoặc authorization code
  nguyên bản vào log hay tài liệu.
- Credential GitHub được mã hóa và chỉ Integration giải mã.
- Webhook không dùng Bearer; phải có chữ ký `X-Hub-Signature-256`, delivery ID
  và event header hợp lệ.
- Không dùng GitHub installation metadata để suy ra quyền Project hoặc Task.
- Không có khóa ngoại hay truy cập database xuyên service.
- `complete` thành công chỉ chứng minh quyền kỹ thuật đọc repository; nó không
  tự chọn repository chính cho Project.
- Work chỉ áp dụng `ConnectionFact`/`ReferenceFact` sau khi kiểm tra lại actor,
  scope, generation và source version.

## Phần đã có, phần chưa xác minh và phần còn thiếu

| Phần | Trạng thái | Bằng chứng/giới hạn |
| --- | --- | --- |
| GitHub authorization, installation, repository live list | Đã triển khai trong source | Integration API và test mock; GitHub thật chưa xác minh |
| Project repository projection | Một phần | Work source/contract/test có; adapter mặc định `UnavailableIntegration` |
| TaskGitHubLink, confirm, unlink | Một phần | Work source/contract/test có; provider verification live chưa xác minh |
| UI hoàn chỉnh cho toàn bộ luồng | Chưa xác minh | Frontend hiện không phải bằng chứng runtime backend |
| Đồng bộ commit/branch/PR tự động | Chưa triển khai trong Integration | Cần producer/consumer, event contract, retry và reconcile |
| AI context từ repository | Chưa triển khai | AI chỉ nhận context qua contract của service sở hữu |

Các kế hoạch mục tiêu có thể bổ sung prepare/confirm/abort giữa Work và
Integration, event `integration.project.connection.changed` và consumer hoạt
động GitHub. Không mô tả các phần đó như đã chạy nếu chưa có adapter, worker,
contract test và runtime evidence tương ứng.

Xem thêm [API Integration](api.md), [phạm vi và quyền](scope-access.md) và
[contract OpenAPI](../../contracts/api/integration-service-v1.yaml).
