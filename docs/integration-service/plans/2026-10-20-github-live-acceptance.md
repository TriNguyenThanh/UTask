# Kế hoạch phiên tiếp theo: nghiệm thu GitHub thật

Ngày lập: 20/10/2026. **Trạng thái: Kế hoạch đã chốt, chưa thực hiện.**
Hiện trạng đầu vào nằm tại [checkpoint 20/10/2026](../checkpoint-2026-10-20.md).
Kế hoạch này không thay thế [hợp đồng API](../api.md) hoặc khẳng định các ca
GitHub thật đã đạt.

## Mục tiêu và phạm vi

Hoàn tất luồng đăng nhập UTask → cấp quyền GitHub → cài App → đọc repo,
sau đó kiểm tra refresh token, gỡ App, thu hồi authorization và kết nối lại.

Các lựa chọn đã chốt với người dùng:

- Dùng GitHub App dev hiện tại, tài khoản UTask đang thử và repository thử riêng.
- Người dùng thao tác trên GitHub/Reqable; agent kiểm tra backend, chẩn đoán
  và sửa lỗi tái hiện được.
- Kiểm tra refresh GitHub thật ngay trong phiên bằng quy trình có kiểm soát,
  không chờ token đến hạn tự nhiên.
- Chưa triển khai UI, liên kết repo–Project, đồng bộ commit/PR, migration hoặc
  API nghiệp vụ mới. Identity giữ phiên UTask; Work giữ Project và quyền nghiệp vụ.

## Quy trình thực hiện

### 1. Kiểm tra trạng thái đầu phiên

- Đọc checkpoint và kiểm tra diff; giữ nguyên các thay đổi chưa commit.
- Kiểm tra index GitNexus; cập nhật index nếu kết quả không khớp source trước
  khi phân tích sửa code.
- Kiểm tra API, worker, Beat, Redis, database và gateway; xác nhận URL ngrok
  và webhook đang dùng.
- Kiểm tra cấu hình trong container bằng kết quả đạt/không đạt, không in secret.
- Đăng nhập UTask thật, xác minh token qua `/users/me`; dùng actor này để đối
  chiếu dữ liệu Integration, không chọn tùy tiện bản ghi đầu tiên.

### 2. Hoàn tất kết nối bằng Reqable

- Chuẩn hóa các request login, account, authorization start/complete,
  installation start/complete và repository list.
- Giải quyết lỗi installation bằng một lần start mới; đối chiếu cùng Bearer,
  đúng cookie installation, đúng state và thời hạn.
- Chẩn đoán bằng kết quả so khớp và trạng thái pending; không ghi token,
  cookie, state hoặc code nguyên bản vào log/checkpoint.
- Nếu lỗi do cấu hình Reqable, cập nhật hướng dẫn. Nếu tái hiện lỗi backend,
  viết test hồi quy rồi sửa; giữ nguyên các kiểm tra bảo vệ consent.
- Kết quả cần đạt: account authorization `ACTIVE`, installation complete
  `ACTIVE`, đọc được repository thử đã chọn.

### 3. Kiểm tra refresh thật ngay trong phiên

Dùng quy trình operator riêng, không thêm endpoint force refresh vào API.
Đây là thao tác có thay đổi metadata trên credential thử, không phải smoke chỉ đọc.

1. Chọn đúng credential của actor thử; xác nhận trạng thái `ACTIVE`, refresh
   token chưa hết hạn và không có refresh đang chạy.
2. Trong transaction, khóa bản ghi và đối chiếu generation/version; chỉ điều
   chỉnh `expires_at` local thành thời điểm hiện tại cộng 30 giây. Không thay
   nội dung token hoặc thời hạn token ở GitHub.
3. Gọi API liệt kê installation để kích hoạt luồng refresh hiện có.
4. Xác minh credential trở lại `ACTIVE`, version tăng, hạn dùng được cập nhật
   và API repository tiếp tục thành công; không xuất nội dung token.
5. Nếu phản hồi refresh không rõ kết quả, giữ cơ chế `REAUTH_REQUIRED` và cấp
   quyền lại. Không khôi phục token cũ vì GitHub có thể đã xoay token.

### 4. Kiểm tra vòng đời quyền và phục hồi

Thực hiện tuần tự và ghi kết quả từng ca:

- **Bỏ quyền repo thử:** danh sách live không còn repo đó. Ghi nhận cấu hình
  repository selection trước khi thay đổi và khôi phục sau phép thử.
- **Uninstall App:** webhook được nhận, job hoàn tất, installation đã lưu
  chuyển `DELETED`; API không tiếp tục truy cập installation cũ.
- **Cài lại App:** bắt đầu installation mới và đọc lại được repo thử, không
  mặc định tái sử dụng installation ID cũ.
- **Revoke authorization trên GitHub:** credential local chuyển `REVOKED`,
  token mã hóa bị xóa; truy cập yêu cầu cấp quyền lại.
- **Ngắt kết nối từ UTask:** mapping/credential bị thu hồi local, revoke job
  được xử lý.
- **Kết nối lại lần cuối:** để môi trường ở trạng thái account/installation
  hoạt động và đọc được repo thử.

Với mỗi thao tác, đối chiếu response API, delivery và job trong thời hạn quan
sát 60 giây. Chỉ ghi kết quả đạt khi có bằng chứng; nếu delivery không đến,
kiểm tra ngrok và GitHub Recent deliveries trước khi kết luận lỗi worker.

## Công cụ và giao diện thay đổi

- Giữ nguyên hợp đồng API Integration hiện tại và mã lỗi công khai.
- Mở rộng [smoke script](../../../scripts/smoke_integration_github.py) với tùy
  chọn `INTEGRATION_SMOKE_EXPECTED_REPOSITORY_ID`. Khi cấu hình tùy chọn này
  phải có installation ID; script kiểm tra repo kỳ vọng qua các trang và
  thất bại nếu không tìm thấy.
- Smoke script tiếp tục chỉ đọc, không tự refresh cưỡng bức, uninstall hoặc
  revoke; không theo redirect mang Bearer.
- Ghi riêng quy trình refresh có kiểm soát trong tài liệu nghiệm thu, không
  thay mặc định runtime. Quy trình này thuộc service sở hữu credential;
  không đọc hoặc sửa database Identity/Work.

## Kiểm thử và tiêu chí nghiệm thu

- Bổ sung test cho smoke: repo kỳ vọng xuất hiện, không xuất hiện, nằm ở
  trang sau, pagination lặp, ID không hợp lệ và lỗi không làm lộ credential.
- Với mọi hàm chức năng bị sửa, cập nhật unit test đường thành công và nhánh
  lỗi tương ứng trong cùng thay đổi.
- Chạy suite Integration trên PostgreSQL kiểm thử riêng; không trỏ pytest
  vào database runtime.
- Chạy các test hạ tầng liên quan, Ruff lint/format check, Compose validation,
  kiểm tra link tài liệu và `git diff --check`. Build lại image nếu sửa mã
  chạy trong container.
- Trước sửa symbol chạy GitNexus impact; cuối phiên chạy detect changes và
  review diff.

Phiên đạt mục tiêu khi có bằng chứng kết nối/đọc repo, refresh thật, xử lý
uninstall/revoke và kết nối lại. Ca chưa chạy hoặc phụ thuộc GitHub chưa đáp
ứng phải ghi riêng là **Chưa xác minh**.

## Bàn giao và mặc định

- Cập nhật checkpoint theo ngày thực hiện, phân biệt kiểm thử mock, kiểm tra
  runtime và phép thử GitHub thật.
- Bàn giao checklist Reqable tái sử dụng, nguyên nhân lỗi installation và kết
  quả từng ca; không lưu secret trong tài liệu.
- Không xóa repository thử, sửa quyền repo nghiệp vụ, đổi khóa mã hóa, commit
  hoặc deploy staging/production trong phạm vi phiên.
- Nếu còn lỗi nền tảng, tập trung xử lý và ghi bằng chứng; không chuyển sang
  triển khai UI hoặc Integration–Work trong phiên này.
