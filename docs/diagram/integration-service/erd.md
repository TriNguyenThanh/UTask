# Integration Service — ERD khái niệm

**Trạng thái: Thiết kế mục tiêu; đề xuất khái niệm, chưa phải schema đã chốt.**
Integration runtime, database schema và migration chưa được triển khai trong
repo. Xem [tài liệu service](../../integration-service/README.md),
[quyền sở hữu dữ liệu](../../system/data-ownership.md) và
[hợp đồng API](../../integration-service/api.md), cùng
[phạm vi và quyền truy cập](../../integration-service/scope-access.md).

ERD tập trung dữ liệu GitHub thuộc Integration. `project_id` là ID tham chiếu
logic tới Work, không có quan hệ FK. `TaskGitHubLink` thuộc Work nên được loại
khỏi ERD này. Không lưu contribution tổng hợp trùng nguồn; không lưu OAuth code,
access token hoặc refresh token như dữ liệu nghiệp vụ. Credential GitHub App
nếu cần phải được quản lý bằng cơ chế bí mật, ngoài ERD khái niệm này.

`ProjectConnection` biểu diễn installation/repository mà Integration đang dùng
cho một Project theo command đã được Work cho phép; đây là metadata liên kết
GitHub, không phải nguồn quyền user/project. Chỉ Work kiểm tra ProjectMember và
leader `ACTIVE`, rồi gửi command chọn/đổi/ngắt kết nối. Callback cài App ghi
nhận installation/phiên nhưng không tạo hoặc đổi `ProjectConnection`. Việc cài
App, liên kết OAuth hay thấy repository trong danh sách không tự chứng minh
quyền thao tác Project. `TaskGitHubLink` và quyền thành viên vẫn do Work sở hữu.
Webhook signature chỉ xác minh nguồn gửi; dữ liệu GitHub được thu thập READ-ONLY.

```mermaid
erDiagram
    Installation ||--o{ InstallationRepository : grants
    Repository ||--o{ InstallationRepository : access_scope
    InstallationRepository ||--o{ ProjectConnection : available_selection_scope
    Repository ||--o{ GitHubReference : contains
    Installation o|--o{ WebhookDelivery : receives
    Repository o|--o{ WebhookDelivery : identifies_repository
    Installation o|--o{ SyncJob : scopes_sync
    Repository o|--o{ SyncJob : sync_target
    WebhookDelivery o|--o{ SyncJob : may_schedule

    Installation {
        string github_installation_id PK
        string github_app_id
        string account_login
        string account_type
        string status
        datetime installed_at
        datetime suspended_at
        datetime removed_at
        bigint source_version
    }

    Repository {
        string github_repository_id PK
        string owner_login
        string name
        string full_name
        string default_branch
        string visibility
        string status
        datetime updated_at
        bigint source_version
    }

    InstallationRepository {
        string github_installation_id PK, FK
        string github_repository_id PK, FK
        string access_status
        datetime granted_at
        datetime revoked_at
        bigint source_version
    }

    ProjectConnection {
        uuid id PK
        string project_id "Logical Work reference; Work-authorized command; no FK"
        string github_installation_id FK
        string github_repository_id FK
        string status
        bigint generation
        bigint source_version
        string last_operation_id
        datetime connected_at
        datetime disconnected_at
        datetime synced_at
    }

    GitHubReference {
        uuid id PK
        string github_repository_id FK
        string reference_type "COMMIT, BRANCH, ISSUE, PULL_REQUEST"
        string provider_ref_id
        string title
        string status
        string url
        datetime provider_updated_at
        datetime synced_at
        bigint source_version
    }

    WebhookDelivery {
        uuid id PK
        string github_app_id
        string github_delivery_id
        string event_name
        string action
        string github_installation_id FK
        string github_repository_id FK
        string payload_digest
        string processing_status
        datetime received_at
        datetime processed_at
        string failure_code
    }

    SyncJob {
        uuid id PK
        string project_id "Logical reference to Work; no FK"
        string github_installation_id FK
        string github_repository_id FK
        uuid webhook_delivery_id FK
        string job_type
        string idempotency_key
        bigint generation
        string status
        int attempt_count
        datetime scheduled_at
        datetime started_at
        datetime completed_at
        string failure_code
    }

    OutboxEvent {
        uuid id PK
        string aggregate_type
        string aggregate_id
        string event_type
        int event_version
        string event_id UK
        string payload
        datetime created_at
        datetime published_at
        int attempt_count
    }
```

## Cardinality và quy tắc duy nhất đề xuất

- Installation và Repository có quan hệ nhiều-nhiều theo quyền cài App; bảng
  nối lưu trạng thái cấp quyền và phiên bản nguồn. Cặp
  `(github_installation_id, github_repository_id)` là duy nhất.
- Một repository có thể được nhiều Project tham chiếu. `ProjectConnection`
  giữ `project_id` logic; đề xuất tối đa một kết nối đang hoạt động cho mỗi
  project, còn lịch sử có thể giữ theo `generation`. Cần đối chiếu API và luồng
  đổi repository trước khi chốt constraint.
- GitHubReference dùng ID nội bộ riêng; định danh phía provider duy nhất theo
  repository, loại reference và ID provider ổn định. Số issue/PR và tên branch
  chỉ có ý nghĩa trong repository.
- Khóa delivery đề xuất là duy nhất theo cặp
  `(github_app_id, github_delivery_id)` để chống nhận lặp trong từng GitHub App.
  Delivery có thể không cần job hoặc kích hoạt nhiều job; đồng bộ/API cũng có
  thể tạo job không gắn delivery. Vì vậy quan hệ này tùy chọn và không 1:1.
- `idempotency_key` của SyncJob cần có phạm vi theo loại job và target; cách
  ghép khóa cần chốt cùng retry/replay policy. `project_id` là tham chiếu logic
  để giới hạn quyền đọc job; `generation` giúp nhận diện kết quả cũ khi kết nối
  repository thay đổi.
- OutboxEvent ghi thông báo từ mutation đã commit. Một delivery hoặc job có thể
  tạo không event, một event hoặc nhiều event; event cũng có thể do REST command
  tạo. Không áp đặt quan hệ 1:1 với WebhookDelivery/SyncJob. `aggregate_type`,
  `aggregate_id`, `event_id` là định danh/tham chiếu logic; publisher đánh dấu
  đã phát sau Kafka ACK.

Kiểu trường chỉ minh họa miền dữ liệu. Index, retention, payload schema,
constraint cuối cùng, quản lý secret và transaction boundary phải được chốt
trước migration. Đây không phải hợp đồng máy đọc được.
