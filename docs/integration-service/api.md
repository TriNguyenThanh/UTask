# API Integration Service

**Trạng thái: Một phần.** `/healthz` và API đọc/thu hồi liên kết GitHub cá
nhân, OAuth consent và GitHub provider có trong source. Các API dữ liệu
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
| DELETE `/api/v1/github/account` | Đã triển khai trong source | Thu hồi liên kết và vô hiệu consent của actor; lặp lại giữ nguyên account version |
| POST `/api/v1/github/authorizations/start` | Đã triển khai trong source | Không nhận query/body; trả `authorization_url`, `expires_at` và đặt cookie nonce |
| POST `/api/v1/github/authorizations/complete` | Đã triển khai trong source | Chỉ nhận JSON `code`, `state`; kiểm nonce/Bearer và trả account đã xác minh |

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

DELETE chỉ thu hồi mapping Integration và vô hiệu consent đang chờ; không gọi
GitHub để revoke token vì M3 không lưu token. Response DELETE giữ cùng dạng account
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

## 3. OAuth consent cá nhân M3

**Đã triển khai trong source; chưa xác minh OAuth GitHub thực tế.** Hai route
POST yêu cầu Bearer được Identity `/users/me` xác minh. Consent không cần
`project_id`, vai trò leader hoặc quyền Work. Response thành công dùng envelope
`success: true, data: ...` và `Cache-Control: private, no-store`.

Start không nhận query/body, trả URL `https://github.com/login/oauth/authorize`
với state, redirect đã cấu hình và PKCE S256; không yêu cầu scope repository.
Cookie `utask_github_consent` chứa browser nonce, `HttpOnly`, `SameSite=Lax`,
path `/`, TTL 600 giây và `Secure` mặc định. Mỗi actor chỉ có một consent mới
nhất còn dùng được; start mới vô hiệu consent trước.

Complete chỉ nhận `code`, `state` và cần cookie nonce cùng Bearer đã dùng lúc
start. Identity `/users/me` không cung cấp session ID, nên Integration ràng
buộc chính xác access Bearer bằng HMAC-SHA256 với khóa consent, đồng thời kiểm
actor, hash state/nonce và thời hạn. Refresh access token giữa luồng yêu cầu
start consent mới. State dùng một lần: được đánh dấu consumed và xóa verifier
mã hóa trước khi gọi provider; timeout hoặc lỗi provider vẫn phải start lại.

Provider exchange code tại GitHub, sau đó gọi `https://api.github.com/user`
để lấy ID số nguyên dương và login hợp lệ; không lấy danh tính từ client.
Cả hai request không theo redirect, timeout kết nối/đọc 2/3 giây và giới hạn
response 64 KiB. Token chỉ được dùng trong adapter rồi bỏ, không lưu, trả về
hoặc ghi log. Complete thành công trả account data như GET và xóa cookie.

Generation của actor được kiểm lại sau exchange. DELETE tăng generation và
hủy pending consent kể cả khi chưa có mapping, nên callback đến muộn không
thể tạo lại liên kết. Nếu đang `LINKED`, đổi sang GitHub ID khác cần unlink
trước; GitHub ID đang được actor khác liên kết cũng bị từ chối.

| HTTP | Trường hợp |
| --- | --- |
| 400 | Payload/query sai; state hết hạn, replay, sai actor/Bearer hoặc nonce |
| 401 | Thiếu hoặc sai Bearer, phiên bị Identity từ chối |
| 409 | Generation thay đổi, consent hết hạn sau exchange, xung đột account hoặc cần unlink trước |
| 503 | Identity/storage không khả dụng; cấu hình consent/provider sai, timeout hoặc response GitHub không hợp lệ |

Lỗi dùng envelope `success: false, error: {code, message}`; lỗi provider có mã
`GITHUB_UNAVAILABLE`, thông báo chung không chứa credential.

Cấu hình bắt buộc: `INTEGRATION_GITHUB_CLIENT_ID`,
`INTEGRATION_GITHUB_CLIENT_SECRET`, `INTEGRATION_GITHUB_REDIRECT_URI` và
`INTEGRATION_CONSENT_KEY`. Khóa consent là Fernet key: 32 byte ngẫu nhiên được
mã hóa base64url; dùng riêng cho Integration để mã hóa verifier PKCE tạm thời.
Redirect dùng HTTPS; HTTP chỉ chấp nhận loopback phục vụ phát triển.
`INTEGRATION_CONSENT_COOKIE_SECURE` mặc định `true`, chỉ đặt `false` khi chạy
localhost qua HTTP. Thiếu hoặc sai cấu hình làm luồng đóng với 503.

M3 không lưu/refresh/revoke token, không liệt kê repository hoặc cấp quyền
Project. Không dùng callback Identity, SocialAccount/profile hoặc proof
exchange làm nguồn mapping. Unit test provider dùng mock; chưa có bằng chứng
OAuth end-to-end với GitHub hay Identity thật.

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
