# Integration Service — DFD

**Trạng thái: Thiết kế mục tiêu.** Sơ đồ mô tả luồng dữ liệu dự kiến, không
xác nhận endpoint, database hoặc worker Integration đã chạy. Nguồn chuẩn:
[Integration Service](../../integration-service/README.md),
[API Integration](../../integration-service/api.md),
[giao tiếp](../../system/communication.md) và
[luồng GitHub](../../system/workflows.md#github). Quy tắc quyền chuẩn tại
[phạm vi và quyền truy cập](../../integration-service/scope-access.md).

## DFD context

Integration là một tiến trình trong sơ đồ context. REST trả kết quả đồng bộ;
Kafka chỉ nhận event bất đồng bộ đã commit. Identity nhận proof danh tính OAuth;
Work kiểm quyền user/project và là nơi duy nhất ra lệnh đổi liên kết repository
của Project. Trình duyệt chỉ dùng luồng cài App và đọc installation/repository
đã chứng minh quyền GitHub; callback không tự kết nối Project.

```mermaid
flowchart LR
    U[Người dùng / trình duyệt]
    GH[GitHub App, REST API và Webhook]
    ID[Identity Service]
    W[Work Service]
    AI[AI Service]
    K[Kafka]
    I([P0 Integration Service])

    U -->|Start installation với phiên đăng nhập| I
    I -->|installation URL và hạn state| U
    U -->|Mở URL cài đặt GitHub App| GH
    GH -->|Redirect trình duyệt kèm installation context| U
    U -->|Callback cài đặt có state và installation context| I
    I -->|Ghi nhận installation/phiên; trả trạng thái callback| U
    U -->|Đọc installation và repository trong scope user đã xác minh| I
    I -->|Danh sách giới hạn theo GitHub user và phiên| U
    U -->|Chọn/đổi/ngắt repository gắn Project| W
    GH -->|Installation event, webhook và dữ liệu GitHub| I
    I -->|Đổi code và xác minh danh tính| GH
    I -->|Proof ngắn hạn cho operation/user| ID
    ID -->|OAuth code cùng binding đã kiểm tra| I
    W -->|REST command: chọn/đổi/ngắt ProjectConnection; Work kiểm leader ACTIVE| I
    I -->|REST: facts trạng thái kết nối và reference đã xác minh| W
    AI -->|REST read-only: context GitHub của Project đã được cấp scope| I
    I -->|REST: context đã lọc theo Project| AI
    I -.->|Event đã commit, phát bất đồng bộ| K
```

## DFD level 1

```mermaid
flowchart LR
    ID[Identity Service]
    W[Work Service]
    AI[AI Service]
    U[Người dùng / trình duyệt]
    GH[GitHub]
    R[(Redis / Celery broker)]
    K[Kafka]

    P1([1. Đổi OAuth code và tạo proof])
    P2([2. Ghi nhận installation; liệt kê scope GitHub user])
    P7([7. Xử lý lệnh ProjectConnection từ Work])
    P3([3. Nhận, xác minh và khử trùng webhook])
    P4([4. Đồng bộ và chuẩn hóa dữ liệu GitHub])
    P5([5. Phục vụ API nội bộ cho Work và AI])
    P6([6. Phát outbox đã commit])

    D1[(D1 Installation, repository và ProjectConnection)]
    D2[(D2 GitHubReference và facts chuẩn hóa)]
    D3[(D3 WebhookDelivery)]
    D4[(D4 SyncJob)]
    D5[(D5 OutboxEvent)]

    ID -->|Code, verifier, redirect và operation/user binding| P1
    P1 -->|Đổi code, lấy danh tính GitHub| GH
    GH -->|Kết quả xác minh danh tính| P1
    P1 -->|Proof ngắn hạn gắn binding| ID

    U -->|POST start installation trong phiên user| P2
    P2 -->|Trước start/list/callback: xác nhận actor, project, action và phiên| W
    W -->|Kết quả: leader ACTIVE, project ghi được và phiên hợp lệ| P2
    P2 -->|installation URL và hạn state| U
    U -->|Mở URL cài đặt GitHub App| GH
    GH -->|Redirect trình duyệt cùng installation context| U
    U -->|Callback cài đặt có state và installation context| P2
    P2 -->|Xác minh installation từ GitHub; không tạo ProjectConnection| GH
    GH -->|Installation metadata| P2
    P2 -->|Lưu installation và phiên cài đặt| D1
    P2 -->|Callback thành công/thất bại| U
    U -->|GET installation/repository theo user GitHub đã xác minh| P2
    P2 -->|Đọc mapping GitHub đã liên kết của actor| ID
    ID -->|github_user_id đã liên kết; chỉ là mapping danh tính| P2
    P2 -->|Đọc danh sách hiện hành trong scope phiên| GH
    GH -->|Quyền hiện hành của GitHub user và App; installation/repository| P2
    P2 -->|Danh sách chỉ cho user/scope đã kiểm tra| U
    U -->|Yêu cầu chọn/đổi/ngắt repository gắn Project| W

    W -->|REST command kèm action, project và actor đã xác thực| P7
    P7 -->|Kiểm action/target/actor: leader ACTIVE, project ghi được| W
    W -->|Kết quả phân quyền cho action/project/actor| P7
    P7 -->|Chọn: kiểm quyền chính GitHub user và App trên repository| GH
    GH -->|Kết quả quyền user + App và repository metadata| P7
    P7 -->|Ghi ProjectConnection/generation; ngắt không cần quyền GitHub còn hiệu lực| D1
    P7 -->|Ghi outbox trong cùng transaction với mutation| D5
    P7 -->|REST response connection fact| W

    GH -->|Webhook/install event + app ID, delivery ID, chữ ký| P3
    P3 -->|Claim delivery ID, ghi trạng thái xử lý| D3
    P3 -->|Installation được xác minh hoặc thu hồi quyền| D1
    P3 -->|Outbox event quyền App đã commit| D5
    D3 -->|Delivery mới đã xác minh| P4
    P4 -->|Lập job đồng bộ nền| D4
    P8([8. Dispatch job nội bộ])
    D4 -->|Job pending| P8
    P8 -->|Giao job bằng danh tính worker riêng| R
    R -->|Job được worker nhận bằng danh tính riêng| P4
    D4 -->|Job target và generation yêu cầu| P4
    D1 -->|ProjectConnection hiện hành; kiểm generation và App scope| P4
    P4 -->|Chỉ đọc GitHub khi generation khớp và App còn quyền| GH
    GH -->|Quyền App hiện hành và commit, branch, issue, pull request| P4
    P4 -->|Upsert dữ liệu chuẩn hóa| D2
    P4 -->|Ghi event cùng transaction mutation| D5
    P4 -->|Cập nhật kết quả delivery/job| D3
    P4 -->|Cập nhật trạng thái job| D4

    W -->|REST query: facts connection/reference; user và project scope| P5
    AI -->|REST read-only: context project đã được cấp scope| P5
    P5 -->|REST: xác minh quyền user/project tại Work khi cần| W
    W -->|Kết quả quyền và phạm vi được phép| P5
    D1 -->|Facts ProjectConnection do lệnh Work quản lý| P5
    D2 -->|Reference và hoạt động chuẩn hóa| P5
    P5 -->|Facts GitHub đã xác minh, REST response| W
    P5 -->|Context read-only đã lọc, REST response| AI
    P5 -->|REST API GitHub: chỉ đọc để xác minh reference| GH
    GH -->|Kết quả reference hiện hành| P5

    D5 -->|Event pending sau commit| P6
    P6 -.->|Publish bất đồng bộ| K
    K -.->|ACK giao nhận| P6
    P6 -->|Đánh dấu published / retry metadata| D5
```

Callback cài App chỉ ghi nhận installation và phiên; việc user thấy App hoặc
repository không chứng minh quyền Project UTask. Danh sách công khai chỉ nằm
trong scope GitHub user đã liên kết/xác minh và phiên hiện hành; repository
được App cấp quyền không mặc nhiên hiển thị cho mọi user. Với start/list/callback,
P2 hỏi Work xác nhận actor, project, action, leader `ACTIVE`, project ghi được
và phiên; mapping Identity chỉ cho biết GitHub user đã liên kết, không chứng
minh quyền GitHub. Work kiểm tra action/project/actor cho mỗi mutation; chọn
repository cần quyền của chính GitHub user và App, còn ngắt kết nối vẫn được
phép khi quyền App đã bị thu hồi. Mutation ProjectConnection ghi outbox cùng
transaction. Webhook signature chỉ xác thực nguồn gửi, không cấp quyền user.
AI chỉ đọc context đã lọc theo project; không truy vấn installation hay ghi
command/job. Worker đọc generation hiện hành từ D1, dùng danh tính riêng và
kiểm quyền App; không impersonate user hay phụ thuộc JWT user hết hạn. Tác vụ
GitHub chỉ READ-ONLY. Webhook và
đồng bộ cần chống lặp riêng; consumer Kafka cần chống lặp theo `event_id`.
Outbox có thể phát sinh từ webhook, job hoặc command Work nên không tương ứng
một-một với delivery/job. Notification nhận event Kafka theo hợp đồng/use case;
không dùng Kafka làm request-response hoặc REST làm mặc định để thông báo.
