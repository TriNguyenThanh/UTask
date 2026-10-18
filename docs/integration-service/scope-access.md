# Phạm vi và quyền truy cập Integration Service

**Trạng thái: Một phần.** Quyền sở hữu account và xác thực actor được chốt;
API GET/DELETE account cùng persistence có trong source. Consent GitHub,
credential và các luồng Project còn là mục tiêu. [API](api.md) ghi chi tiết
route; [foundation](foundation.md) ghi bằng chứng source/test.

## 1. Quyền sở hữu

| Dữ liệu/trách nhiệm | Chủ sở hữu |
| --- | --- |
| Tài khoản UTask, JWT, phiên và xác minh Bearer | Identity |
| Mapping `user_id`–GitHub, consent GitHub cá nhân, provider credential và dữ liệu GitHub | Integration |
| Project, ProjectMember, Task, quyền user/project và Task–GitHub nghiệp vụ | Work |
| Group/GroupMember và quyền phạm vi lớp | Classroom |

Integration lưu `user_id` UUID như tham chiếu logic. Không có FK xuyên service,
không đọc DB Identity/Work, không migrate hoặc tự nhập mapping GitHub legacy
từ Identity/Work. Việc có cùng GitHub ID ở hệ thống cũ không tự tạo record
Integration.

Mapping Integration chỉ xác định account GitHub được liên kết với actor UTask.
Nó không chứng minh quyền Project, quyền thành viên, quyền cài đặt GitHub App
hay quyền trên repository. OAuth consent cá nhân không cần Project ID, leader
role hoặc quyền Work.

## 2. Xác thực actor

API account nhận Bearer từ caller. Integration gọi endpoint Identity hiện có
`GET /users/me`, chuyển tiếp Bearer; Identity tự kiểm JWT/session và trả user
ID tại `data.id`. Integration dùng ID đó làm actor và chỉ đọc/thu hồi account
của actor hiện tại. `user_id` trong query/body không được chấp nhận.

Không dùng Identity OAuth `SocialAccount`, `profile.github_username`, API
mapping nội bộ hoặc proof exchange làm nguồn quyền/mapping mới. Không cần thêm
Integration vào session-status allowlist vì actor được xác minh qua `/users/me`.
Lỗi 401/403 từ Identity từ chối xác thực; Identity hoặc response lỗi không
được biến thành cho phép.

Đã có source adapter và unit test cho request Bearer, timeout, response/error
handling. Việc Integration gọi Identity xuyên service khi chạy chưa được xác
minh.

## 3. Ma trận hành động

| Hành động | Điều kiện | Trạng thái |
| --- | --- | --- |
| Đọc account GitHub của mình | Bearer hợp lệ; actor lấy từ Identity `/users/me` | Đã có route trong source |
| Thu hồi liên kết account của mình | Bearer hợp lệ; chỉ mapping actor hiện tại bị thu hồi | Đã có route trong source; thao tác GitHub token revoke chưa có |
| Liên kết/đổi GitHub account cá nhân | Consent/provider xác minh GitHub; nếu đang LINKED thì đổi account theo quy tắc unlink trước | Chưa có HTTP OAuth consent; service helper chỉ nhận dữ liệu đã xác minh, chưa nối với provider |
| Đọc hoặc thu hồi account người khác | Không cho phép qua API user | Không có route theo `user_id` |
| Thực hiện OAuth consent | Chính user UTask đã xác thực; không cần Project/leader | Thiết kế mục tiêu M3 |
| Liệt kê installation/repository cá nhân | Consent và credential hiện hành, quyền user GitHub còn hiệu lực | Chưa triển khai |
| Đọc snapshot Work cho Project | API REST GET thuộc Work và phạm vi được contract cho phép | Tích hợp runtime chưa có; GET không cấp quyền ghi |
| Ghi Project/Task/TaskGitHubLink hoặc prepare/confirm | Contract Work có sẵn, quyền và CAS được Work bảo đảm | Chưa mở; không dùng snapshot GET để suy quyền ghi |
| Đọc context GitHub cho AI | Contract nội bộ và phạm vi Work đã cấp | Chưa triển khai |

## 4. Ranh giới Work và GitHub

Work sở hữu mọi quyền Project/Task và quyết định thay đổi nghiệp vụ. Integration
có thể dùng snapshot qua API đọc Work hiện có: `/projects/{id}/`,
`/tasks/{id}/`, `/projects/{id}/members/`. Các GET này không đảm bảo authorize
mutation, không cung cấp compare-and-set (CAS) và không thay thế một contract
Work cho prepare/confirm.

Không mở luồng repository/project hoặc Task link nếu contract Work cần thiết
chưa có. Integration không yêu cầu sửa Work trong phạm vi này; adapter Work
hiện mặc định `UnavailableIntegration`. Quyền GitHub user và quyền GitHub App
phải được kiểm tra riêng nếu sau này có use case GitHub. Account link tự thân
không cấp một trong hai quyền.

Integration là service duy nhất được gọi trực tiếp GitHub API. AI/Work không
nhận GitHub token. Notification chỉ nhận event đã có contract; hiện chưa có
publisher Integration.

## 5. Credential và thu hồi

`GitHubAccount` đang lưu mapping và metadata xác minh; hiện model không có
trường token. OAuth consent/token adapter và nơi lưu credential chưa được
triển khai. Khi có consent, credential thuộc Integration, phải được bảo vệ và
không trả về trong API, log, event hoặc context AI.

DELETE `/api/v1/github/account` đánh dấu mapping `REVOKED`, ghi `revoked_at`
và tăng `source_version`; gọi lại không tăng version. Hiện DELETE chưa thể
thu hồi token ở GitHub do token adapter chưa có. Thu hồi account không gỡ GitHub
App installation dùng chung và không thay quyền/membership trong Work.

Không tự động import account/mapping từ các model hoặc API legacy. Chuyển đổi
dữ liệu cần quyết định riêng về consent và xác minh; không suy ra quyền từ một
mapping cũ.

## 6. Bằng chứng hiện trạng

- Source Integration có `GitHubAccount`, migration, validation, service link/
  unlink, view GET/DELETE, Identity client và route `/api/v1/github/account`.
- Unit test bao phủ validation, idempotency, conflict, stale verification và
  hành vi revoke; test integration cần PostgreSQL bao phủ constraint, race
  đồng thời, uniqueness và persistence.
- Chưa có GitHub OAuth client/token adapter, consent endpoint, provider
  verification hay revoke GitHub token.
- Work adapter hiện `UnavailableIntegration`. Adapter cũ không được xem là
  Integration đã tích hợp.
- Identity và Work có source legacy liên quan GitHub. Chúng được giữ nguyên;
  không phải owner mới của mapping do Integration tạo và không phải đường
  migration tự động.

## 7. Ca cần kiểm thử cho các bước kế tiếp

- API account chỉ thao tác account actor trả từ Identity; bỏ qua/không nhận
  `user_id` do client gửi; Identity 401/403 và timeout không cấp quyền.
- GET chưa liên kết trả `UNLINKED`; DELETE liên kết trả `REVOKED`; DELETE lặp
  không đổi version; account khác không bị tác động.
- Khi triển khai consent: state/PKCE/callback gắn đúng actor, account GitHub
  đang LINKED không bị âm thầm đổi; credential không lộ; revoke chặn tái sử
  dụng credential.
- Luồng Project phải dùng contract Work đã chốt và kiểm tra quyền/CAS. Snapshot
  GET hoặc quyền OAuth cá nhân không đủ để cho phép mutation.
