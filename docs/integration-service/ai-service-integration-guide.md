# Tích hợp GitHub context từ AI Service

**Trạng thái: Thiết kế mục tiêu phía AI; provider Integration đã triển khai.** Adapter AI đã có domain
`github_activity` và bộ lọc trường ở mức nền; việc gọi endpoint GitHub context
của Integration bằng service key và hợp đồng response dưới đây chưa được xác
minh. Contract chuẩn là
[Integration Service v1](../../contracts/api/integration-service-v1.yaml).

## Phạm vi và luồng

AI Service lấy context theo yêu cầu đồng bộ qua REST khi workflow gọi domain
tool `github_activity`. Không thêm projection Kafka hoặc lưu bản sao context
trong AI Service. Agent chỉ nhận dữ liệu đã lọc; Integration vẫn sở hữu mapping
GitHub và là service duy nhất gọi GitHub API.

```text
AI Context Layer ── GET project GitHub context ──> Integration
       │                         │                    │
       │ Bearer actor +          │                    ├─ kiểm tra mapping/consent
       │ X-Service-Key           │                    └─ Work authorize github.read
       └<── ContextDocument: github_activity ─────────┘
```

Request dùng `GET /api/v1/internal/projects/{project_id}/github/context`, gửi
Bearer của actor đã xác thực và `X-Service-Key` của AI Service. Contract giới
hạn mỗi loại tối đa 20 item. Không đưa key
service vào tool/agent hoặc chuyển tiếp nó như danh tính người dùng. Integration
dùng Bearer để yêu cầu Work kiểm tra quyền `github.read`; quyền được đánh giá
tại thời điểm đọc, không cache ở AI. AI không gọi Work trực tiếp cho quyền
GitHub và không đọc database của Work hay Integration.

Response là `ContextDocument` với `domain: "github_activity"`, `as_of`,
`status`, `source_version` nullable, `data` và `warning` nullable. `data` có
`commits`, `pull_requests`, `issues` (mỗi loại tối đa 20 item) và
`mapping_status`. Enum mapping hiện được contract chốt là `CONNECTED`,
`DISCONNECTED` hoặc `REAUTH_REQUIRED`; AI không tự suy ra trạng thái mapping
từ mảng rỗng. Mỗi item hiện theo schema `GitHubActivityItem` trong contract.

## Cấu hình và thay đổi adapter

Thêm secret `AI_INTEGRATION_SERVICE_KEY` vào cấu hình secret hiện có; cung cấp
nó cho API và worker cùng nơi cấu hình `AI_CONTEXT_URLS`. Đây là tên biến mục
tiêu cần được phản ánh vào settings/config khi triển khai. Không ghi key vào
`infra/env/ai-service.env`, log, lỗi trả client hoặc nội dung gửi model. Thêm
`project:github_activity` vào `AI_CONTEXT_URLS` với URL nội bộ dạng
`https://integration-service/api/v1/internal/projects/{target_id}/github/context`;
adapter hiện thay `{target_id}` từ project đã validate. Không dùng placeholder
`{project_id}` vì adapter chưa hỗ trợ tên đó, và không hard-code host trong
agent. Giữ TLS ngoài môi trường
local development/test theo quy tắc cấu hình AI hiện hành.

Trong `InternalContextAdapter`, chỉ gắn `X-Service-Key` cho request tới
Integration; giữ Bearer actor và timeout hiện có. Bổ sung kiểm soát trạng thái
cho `ContextDocument`: `available` dùng bình thường; `partial` được trả cho
workflow cùng warning để kết luận thận trọng; `stale` trả lỗi `CONTEXT_STALE`;
`missing` phải được tool/workflow biểu diễn tường minh là không có context; không
biến nó thành context `available` hoặc dữ liệu rỗng có vẻ đầy đủ.
`partial` hiện phản ánh một loại hoạt động không được cấp quyền; mỗi danh sách
là cửa sổ tối đa 20 item, không phải lịch sử đầy đủ. Agent phải thấy warning.
Contract trả HTTP 200 cho `available`/`partial`, còn `stale`/`missing` cũng
dùng cùng schema; lỗi khả dụng hiện trả HTTP 503/error envelope. Schema vẫn
dành `unavailable` cho context không có nguồn dùng được; adapter phải kiểm tra `status`, không chỉ
HTTP status. Lỗi HTTP 401/403 là lỗi xác thực/phân quyền; 429 và 503 là lỗi
dịch vụ cần xử lý theo retry/deadline hiện có.
HTTP 409 (`VERSION_CONFLICT` hoặc `GITHUB_REAUTH_REQUIRED`) không được dùng
như context; thông báo cần đồng bộ/cấp quyền lại và không fallback fixture.
`unavailable`, timeout, lỗi 5xx hoặc cấu hình thiếu phải báo context không sẵn
sàng, có retry theo chính sách hiện hành nếu lỗi tạm thời. Payload sai schema,
sai domain, quá lớn hoặc thời điểm không hợp lệ trả `CONTEXT_INVALID`.

Giữ allowlist domain `github_activity` chỉ gồm `commits`, `pull_requests`,
`issues`, `mapping_status` và các trường con đã có trong contract. Không cho
phép response tùy ý mở rộng dữ liệu đưa vào prompt. Kiểm tra giới hạn item,
độ sâu và kích thước trước khi chuyển tiếp; giới hạn contract hiện tại là 20
item mỗi loại.

## Kiểm thử và rollout

Unit test adapter cần bao phủ tối thiểu:

- Thành công: GET đúng URL, gửi cả Bearer và service key; parse domain đúng,
  lọc trường và giữ metadata `as_of`/`source_version`.
- Phân quyền: Integration từ chối hoặc Work không cho `github.read` thì không
  trả context cho agent; không thử endpoint thay thế.
- Thiếu/partial/stale: mapping thiếu được biểu diễn rõ; partial giữ warning;
  stale không được dùng như dữ liệu hiện hành.
- Lỗi biên: key/config thiếu, 5xx, timeout, JSON/schema/domain sai và payload
  vượt giới hạn được ánh xạ đúng; response/log không chứa service key hay token.

Triển khai theo thứ tự: đối chiếu schema response với contract hiện hành; cập
nhật adapter cùng unit test; cấu hình secret và URL cho API/worker ở staging; xác
minh quyền allow/deny, partial, stale và missing với Integration thật; sau đó
mới bật cho workflow cần `github_activity`. Không coi fixture `MOCK_TEST` là
bằng chứng Integration hoặc GitHub thật hoạt động.

## Tham chiếu

- [API và context boundary của AI](../ai-service/api.md#8-context-và-tính-đúng-đắn)
- [Context Tool Pool](../ai-service/workflow.md#4-context-tool-pool)
- [Adapter HTTP hiện tại](../../apps/ai-service/src/infrastructure/context_http.py)
- [Mô hình ContextDocument](../../apps/ai-service/src/models/context.py)
