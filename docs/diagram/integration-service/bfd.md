# Integration Service — BFD

**Trạng thái: Thiết kế mục tiêu.** BFD phân rã trách nhiệm nghiệp vụ cho tích
hợp GitHub; runtime Integration chưa được triển khai. Nguồn kiến trúc là
[tài liệu Integration](../../integration-service/README.md),
[luồng hệ thống](../../system/workflows.md#github) và
[giao tiếp](../../system/communication.md). Quyền từng caller theo
[phạm vi và quyền truy cập](../../integration-service/scope-access.md).

```mermaid
mindmap
  root((0. Integration Service))
    1. Quản lý GitHub App và repository được cấp quyền
      1.1 Tạo phiên cài App cho user đã đăng nhập
      1.2 Callback chỉ ghi nhận installation và phiên cài đặt
      1.3 Theo dõi cài đặt, tạm ngưng, gỡ bỏ và phạm vi repository
      1.4 Liệt kê installation/repository theo GitHub user đã chứng minh quyền
    2. Phục vụ lệnh kết nối repository qua Work
      2.1 Xác minh quyền App hiện hành trên repository
      2.2 Chỉ nhận lệnh chọn/đổi/ngắt ProjectConnection từ Work
      2.3 Trả trạng thái, generation và metadata GitHub cho Work
    3. Xác minh danh tính GitHub
      3.1 Nhận yêu cầu đổi OAuth code từ Identity
      3.2 Gọi GitHub và xác minh danh tính
      3.3 Trả proof ngắn hạn có binding cho Identity
    4. Nhận và chuẩn hóa dữ liệu GitHub
      4.1 Xác minh chữ ký webhook
      4.2 Chống xử lý lặp theo delivery
      4.3 Chỉ đọc và đồng bộ commit, branch, issue và pull request
      4.4 Cung cấp hoạt động nguồn, không sao chép contribution tổng hợp
    5. Cung cấp dữ liệu nội bộ
      5.1 Trả facts kết nối và metadata cho Work
      5.2 Xác minh reference cho Work
      5.3 Cấp context hoạt động đã lọc theo Project cho AI qua REST
      5.4 Không cho AI liệt kê installation hoặc ghi command/job
    6. Đồng bộ và phát sự kiện
      6.1 Lập job nền và retry có giới hạn
      6.2 Ghi outbox cùng transaction dữ liệu
      6.3 Publisher gửi event bất đồng bộ qua Kafka
```

Identity sở hữu tài khoản UTask/OAuth liên kết; Integration đổi code với
GitHub và chỉ trả proof danh tính cho Identity. OAuth link không chứng minh
quyền quản trị repository. Work sở hữu Project, Task, quyền user/project và
`TaskGitHubLink`; chỉ lệnh Work sau khi kiểm tra leader `ACTIVE` mới được đổi
`ProjectConnection`. Callback cài App chỉ ghi nhận installation/phiên, không
kết nối Project. Cài App cũng không tự cấp quyền Project UTask. AI chỉ đọc
context GitHub đã lọc theo Project qua domain adapter, không liệt kê
installation, tạo command hoặc ghi job. Webhook có chữ ký xác thực nguồn gửi,
không cấp quyền cho user. Integration và worker chỉ thu thập dữ liệu GitHub
READ-ONLY; không tạo/sửa Issue, PR, comment hoặc repository contents. Job nền
dùng danh tính worker riêng và quyền App hiện hành, không impersonate user hay
dựa vào JWT user đã hết hạn. Notification nhận Kafka event khi có use case;
REST không phải đường mặc định để thông báo. Chỉ Integration gọi trực tiếp
GitHub API.
