# API Integration Service

**Trạng thái: Một phần.** `/healthz` và API đọc/thu hồi liên kết GitHub cá
nhân có route trong source. OAuth consent, GitHub provider và các API dữ liệu
Project chưa triển khai. [Hợp đồng OpenAPI](../../contracts/api/integration-service-v1.yaml)
là hợp đồng máy đọc được; phần dưới mô tả hiện trạng và mục tiêu, không thay
thế schema hợp đồng.

[Phạm vi và quyền](scope-access.md) là nguồn chuẩn về quyền caller và quyền sở
hữu. Xác thực user dùng Identity `GET /users/me`; không có OAuth proof
exchange hoặc API mapping Identity trong luồng Integration.

## 1. API đã có trong source

Các path dưới đây tính từ root server Integration, chưa bao gồm prefix gateway.

| Method và path | Trạng thái | Hành vi đã kiểm tra trong source |
| --- | --- | --- |
| GET/HEAD `/healthz` | Đã triển khai | Health DB; xem [foundation](foundation.md) |
| GET `/api/v1/github/account` | Đã triển khai trong source | Đọc account của actor hiện tại; không nhận query hoặc body; `Cache-Control: private, no-store` |
| DELETE `/api/v1/github/account` | Đã triển khai trong source | Thu hồi liên kết của actor hiện tại; lặp lại là idempotent |

Hai route account xác thực `Authorization: Bearer <token>` bằng cách chuyển
Bearer tới Identity `GET /users/me`. Identity kiểm JWT/session và trả
`data.id`; Integration dùng UUID đó làm `user_id`. Client không được truyền
`user_id`, và endpoint từ chối query hoặc request body.

Response thành công được tạo từ source theo envelope sau. Trường GitHub và
thời điểm xác minh rỗng khi trạng thái không phải `LINKED`; account chưa có
record trả `UNLINKED`, `source_version: 0`.

```json
{
  "success": true,
  "data": {
    "user_id": "11111111-1111-4111-8111-111111111111",
    "status": "LINKED",
    "github_user_id": "12345",
    "github_username": "octocat",
    "verified_at": "2026-10-18T06:30:00+00:00",
    "linked_at": "2026-10-18T06:30:00+00:00",
    "revoked_at": null,
    "source_version": 1
  }
}
```

DELETE chỉ thu hồi mapping Integration; endpoint chưa gọi GitHub để revoke
token vì OAuth/token adapter chưa có. Response DELETE giữ cùng dạng account
data. Route này không đổi OAuth link trong Identity và không ảnh hưởng quyền
Project/Task trong Work.

## 2. Xác thực Identity hiện có

`INTEGRATION_IDENTITY_URL` mặc định là `http://identity-service:8000`.
Integration gọi `GET {base}/users/me` với đúng Bearer của request; timeout kết
nối/đọc lần lượt 2/3 giây, không theo redirect, giới hạn response 64 KiB.
Identity 401/403 thành lỗi xác thực; lỗi upstream hoặc response sai thành lỗi
khả dụng Identity. Đây là xác minh actor qua API Identity hiện có, không phải
JWT validation cục bộ hay thêm Integration vào session-status allowlist.

Hiện chưa xác minh luồng xuyên service đang chạy. Unit test xác nhận cách gọi,
giới hạn và ánh xạ lỗi; không chứng minh Identity/Gateway thực tế.

## 3. API mục tiêu: OAuth consent cá nhân

**Thiết kế mục tiêu M3; chưa có route hoặc provider adapter.** Integration sẽ
sở hữu consent GitHub cá nhân và vòng đời credential cần cho quyền theo user.
Consent không cần `project_id`, quyền leader hoặc quyền ghi Project. Kết quả
link account thuộc Integration; schema chi tiết phải theo hợp đồng OpenAPI đã
chốt, không suy rộng từ các ví dụ route cũ.

Luồng mục tiêu cần bảo vệ state/PKCE, ràng buộc callback với user/session,
xác minh danh tính và quyền token với GitHub, lưu credential theo chính sách
bảo vệ bí mật, không trả token ra client, log, event hay context AI; thu hồi
liên kết phải chặn việc tiếp tục dùng credential tương ứng. Chi tiết provider,
scopes, refresh/revoke semantics và response chỉ được coi là quyết định khi
có trong hợp đồng hiện hành. Chưa có mã kiểm chứng OAuth end-to-end.

Không dùng endpoint OAuth callback của Identity làm nguồn mapping; không gọi
Identity SocialAccount/profile hay API mapping nội bộ; không đổi code thành
proof để Identity sở hữu GitHub mapping.

## 4. Tích hợp Work và dữ liệu Project

Work Service vẫn sở hữu quyền Project, ProjectMember, Task và mọi mutation
nghiệp vụ. Integration không đọc DB Work. Có thể dùng các GET Work hiện có để
lấy snapshot đọc gồm `/projects/{id}/`, `/tasks/{id}/` và
`/projects/{id}/members/`; snapshot này không bảo đảm authorize hoặc CAS cho
thay đổi.

Không mở API chọn repository, prepare/confirm, link Task hay mutation Project
chỉ dựa trên các GET đó. Nếu Work chưa có contract hỗ trợ một thao tác, thao
tác vẫn chưa khả dụng; không yêu cầu sửa code Work trong phạm vi Integration
này. Work adapter hiện `UnavailableIntegration`, nên chưa có tích hợp runtime.

## 5. Các API chưa có

Các luồng sau vẫn **Chưa triển khai**; path/payload chỉ được thêm khi có
contract đã chốt:

- GitHub App installation, repository discovery, webhook và đồng bộ.
- API Integration cho facts/reference/context Work hoặc AI.
- Command thay đổi Project, prepare/confirm/abort và durable dispatch.
- Kafka outbox publisher/consumer.

Không coi route minh họa trong baseline, kế hoạch cũ hoặc snapshot ở `plans/`
là API đang chạy hay schema được phê duyệt.
