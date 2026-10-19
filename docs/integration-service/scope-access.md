# Phạm vi và quyền truy cập Integration Service

**Trạng thái: Một phần.** Account consent, credential và installation APIs
có trong source; quyền GitHub thật/triển khai production chưa xác minh. Xem
[API](api.md) và [foundation](foundation.md).

## Quyền sở hữu

| Dữ liệu/trách nhiệm | Chủ sở hữu |
| --- | --- |
| Tài khoản UTask, JWT, session và xác minh Bearer | Identity |
| Mapping `user_id`–GitHub, consent, credential user token và metadata GitHub App | Integration |
| Project, ProjectMember, Task và quyền nghiệp vụ | Work |
| Group/GroupMember và quyền phạm vi lớp | Classroom |

`user_id` là UUID tham chiếu logic; không có FK xuyên service, không đọc DB
Identity/Work và không nhập mapping legacy. Integration gửi Bearer tới
Identity `GET /users/me`, dùng `data.id` làm actor. Không dùng SocialAccount,
profile GitHub hay proof exchange nội bộ làm quyền.

## Ranh giới quyền

Mapping account xác nhận danh tính GitHub đã consent, không chứng minh quyền
Project hay repository. Consent cá nhân và cài đặt GitHub App không cần
`project_id` hoặc leader role. User token được dùng để truy vấn
`/user/installations` và danh sách repository hiện hành; Integration không
cache repository grant và kiểm tra credential/generation vẫn hiện hành sau
provider call.

Metadata installation lưu tại Integration chỉ là gợi ý trạng thái. Nó không
cấp quyền cho Work/AI và không thay thế việc kiểm tra live của GitHub. Work
tiếp tục sở hữu Project/Task, authorize và mutation; chưa có API Integration
để ghi Project. Không gửi GitHub token tới Work, AI hoặc Kafka.

## Ma trận hành động

| Hành động | Điều kiện | Trạng thái |
| --- | --- | --- |
| Đọc/thu hồi account của mình | Bearer được Identity xác minh | Đã triển khai trong source |
| Consent GitHub App | Actor hiện tại, state, PKCE, Bearer và nonce khớp | Đã triển khai trong source |
| Refresh credential | Credential active, generation/version hiện hành; không retry refresh mơ hồ | Đã triển khai trong source |
| Thu hồi credential | DELETE account hoặc authorization revoke webhook | Đã triển khai trong source; provider revoke được giao job |
| Cài đặt App / liệt kê installation và repository | User token hiện hành; kiểm tra live, phân trang | Đã triển khai trong source |
| Nhận webhook | HMAC hợp lệ, delivery ID duy nhất | Đã triển khai trong source; chạy thật chưa xác minh |
| Đọc hoặc thu hồi account người khác | Không có API nhận actor tùy ý | Chưa triển khai |
| Ghi Project/Task hoặc cấp quyền từ installation | Contract và quyền Work cần có | Chưa triển khai |
| AI context hoặc Kafka event | Contract riêng cần quyết định | Chưa triển khai |

## Thiết kế mục tiêu và giới hạn

M4 triển khai nền tảng GitHub App theo yêu cầu hiện tại, không tự mở luồng
nghiệp vụ Work. User authorization hiện dùng quyền `Metadata: read` trên
GitHub App registration; client không dùng GitHub App private key. Cấu hình
registration và quyền hiệu lực trên GitHub production **Chưa xác minh**.
Không diễn giải một installation hoặc `repository_selection` như quyền
Project của UTask.
