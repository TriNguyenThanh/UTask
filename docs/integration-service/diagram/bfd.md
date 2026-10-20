# Integration Service — BFD

**Trạng thái: Một phần.** Nhánh account cá nhân đã có persistence và API đọc/
thu hồi; GitHub consent/provider và các chức năng GitHub khác là mục tiêu.
Nguồn quyền tại [scope-access](../scope-access.md).

```mermaid
mindmap
  root((Integration Service))
    Account GitHub cá nhân
      Đã có: xác thực Bearer qua Identity GET /users/me
      Đã có: đọc account của actor
      Đã có: thu hồi mapping account của actor
      Mục tiêu M3: consent OAuth thuộc Integration
      Mục tiêu M3: provider và credential adapter
    Work và Project
      Work sở hữu Project, Task và quyền
      Có thể đọc snapshot qua GET Work hiện có
      Chưa có contract ghi/prepare-confirm trong phạm vi này
      Work adapter hiện UnavailableIntegration
    Dữ liệu GitHub
      Mục tiêu: GitHub App, repository, webhook, sync
      Mục tiêu: cung cấp dữ kiện đã chuẩn hóa cho Work/AI
      Integration là service duy nhất gọi GitHub API
```

Identity xác thực tài khoản UTask và phiên; Integration sở hữu mapping
GitHub cá nhân, consent và credential sau khi các phần đó được triển khai.
Luồng link cá nhân không cần project hoặc quyền leader. Link account không
trao quyền truy cập repository và không cấp quyền Work.

Work sở hữu quyền Project/Task và mutation nghiệp vụ. Các API GET Work chỉ
cung cấp snapshot đọc, không bảo đảm authorization/CAS cho ghi. Không mở
luồng project mutation nếu contract Work tương ứng chưa có. Không có luồng
OAuth proof exchange giữa Integration và Identity.
