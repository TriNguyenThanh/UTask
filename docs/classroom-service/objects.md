# Chức năng theo tác nhân — Classroom Service

## Trạng thái

Tài liệu này liệt kê **chức năng mục tiêu** theo từng tác nhân. Classroom
Service chỉ dùng **khóa học** (`Course`) để quản lý cấu trúc học tập và quan hệ
học tập. Classroom Service chưa có mã ứng dụng, hợp đồng API hoặc schema sự
kiện trong repository; vì vậy danh sách dưới đây không khẳng định chức năng đã
được triển khai. Các chi tiết còn mở, như quyền ghi của giảng viên được thêm vào
khóa học và hợp đồng API/sự kiện, cần được chốt trước khi triển khai.

## Tác nhân người dùng

| Tác nhân | Chức năng mục tiêu trong phạm vi Classroom Service | Trạng thái quyền |
| --- | --- | --- |
| Giảng viên tạo khóa học | Tạo, sửa, lưu trữ và xóa khóa học; đánh dấu khóa học làm template mẫu (`is_template`) hoặc tạo nhanh khóa học mới từ template; cấu hình số thành viên tối đa mỗi nhóm (`max_group_members`); quản lý giảng viên, sinh viên khóa học và nhóm; xem toàn bộ dữ liệu của khóa học, cả công khai lẫn riêng tư, gồm nhóm, project và task | Quyền quản lý áp dụng cho khóa học do giảng viên tạo. Khi thêm giảng viên khác vào khóa học, người được thêm cũng có quyền truy cập khóa học |
| Giảng viên được thêm vào khóa học | Truy cập khóa học được giảng viên tạo khóa học thêm vào; xem danh sách sinh viên; xem toàn bộ dữ liệu công khai và riêng tư trong phạm vi khóa học, gồm nhóm, project và task | Không mặc nhiên có quyền thêm giảng viên khác hoặc quản lý các khóa học khác |
| Sinh viên | Tham gia hoặc rút khỏi khóa học (qua mã tham gia hoặc được thêm); là sinh viên thuộc khóa học (`course_students`); tự chọn nhóm trong khóa học (tuân theo giới hạn `max_group_members`); xem dữ liệu công khai của khóa học và dữ liệu của nhóm mình tham gia | Không xem dữ liệu riêng tư của khóa học hoặc dữ liệu nhóm khác |
| Quản trị viên hệ thống | Toàn quyền trên hệ thống; trong Classroom Service có thể tạo, sửa, lưu trữ và xóa khóa học, quản lý giảng viên, sinh viên, nhóm, đồng thời xem mọi dữ liệu | Quyền quản trị áp dụng toàn hệ thống |

Giảng viên được thêm vào khóa học do giảng viên tạo khóa học quản lý quyền truy cập.
Phạm vi quyền ghi của giảng viên được thêm, ngoài quyền truy cập và xem toàn
bộ dữ liệu khóa học, cần tuân theo chính sách quản trị khóa học thống nhất khi triển khai.

Quyền xem project và task được thực thi bởi Project Service vì service này sở
hữu dữ liệu đó. Project Service nhận quan hệ khóa học/nhóm và vai trò người dùng qua
hợp đồng liên service; không đọc trực tiếp Classroom DB. Phân loại dữ liệu
công khai/riêng tư của project và task cần được truyền và áp dụng nhất quán ở
service sở hữu.

## Tác nhân hệ thống

| Tác nhân                                      | Chức năng tương tác với Classroom Service                                                                                | Ranh giới                                                                                                                          |
| --------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------- |
| Identity Service                              | Phát hành JWT để các service xác thực danh tính và vai trò người gọi                                                     | Identity Service sở hữu tài khoản, hồ sơ, vai trò toàn hệ thống và thông tin xác thực; Classroom Service xác thực request bằng JWT |
| Project Service                               | Gọi API đồng bộ để xác minh khóa học hoặc nhóm; áp dụng quyền xem project/task theo khóa học, nhóm và vai trò người dùng | Project Service sở hữu project và `ProjectMember`; lưu ID tham chiếu `course_id`/`group_id`, không đọc Classroom DB                |
| Project Service, Progress Service, AI Service | Có thể nhận thông báo thành viên nhóm được thêm hoặc gỡ nếu use case cần                                                 | `group.member.added` và `group.member.removed` mới là sự kiện mục tiêu; schema và consumer chưa được xác nhận                      |

Classroom Service không sở hữu tài khoản, project, thành viên dự án, task,
sprint hoặc dữ liệu GitHub. Không dùng sự kiện Kafka để hỏi–đáp đồng bộ; yêu cầu
xác minh khóa học/nhóm cần câu trả lời ngay thuộc luồng REST.

## Quy tắc vòng đời project gắn với nhóm

- Project liên kết với nhóm sinh viên bằng ID tham chiếu; không tạo khóa ngoại
  xuyên database.
- Khi project bị lưu trữ, project chuyển sang chế độ chỉ xem.
- Khi nhóm bị xóa, project liên kết cũng bị xóa. Project Service thực hiện
  thay đổi trên dữ liệu do service này sở hữu sau khi nhận thông tin nhóm bị
  xóa từ Classroom Service.

Đây là quy tắc nghiệp vụ mục tiêu. Cách thông báo xóa nhóm, thứ tự xử lý,
phục hồi khi một service lỗi và xử lý dữ liệu dẫn xuất cần được quy định trong
hợp đồng liên service; không dùng khóa ngoại hoặc xóa trực tiếp dữ liệu giữa
hai database.

## Các chi tiết cần chốt trước khi triển khai

1. Định nghĩa dữ liệu công khai/riêng tư cho từng loại thông tin khóa học, nhóm,
   project và task.
2. Quy định thao tác ghi của giảng viên được thêm vào khóa học: liệu có được sửa,
   lưu trữ hoặc xóa khóa học, sinh viên và nhóm hay chỉ xem và quản lý nhóm.
3. Chốt ràng buộc tham gia/rời khóa học và tự chọn nhóm, như mã tham gia,
   giới hạn thành viên mỗi nhóm (`max_group_members`), thời điểm cho phép đổi
   nhóm và số nhóm tối đa mỗi sinh viên.
1. Chốt claim, audience, thời hạn, chữ ký/khóa và cách luân chuyển khóa của
   JWT để service xác thực nhất quán.
1. Chốt hợp đồng REST và thông tin quyền mà Project Service cần để lọc project
   và task theo phạm vi xem đã nêu.
1. Chốt sự kiện/hợp đồng báo lưu trữ hoặc xóa nhóm, tính lặp, thứ tự xử lý,
   retry và phục hồi việc xóa project liên kết; xác định riêng project được
   liên kết sẽ ra sao nếu chỉ nhóm được lưu trữ.

## Căn cứ

- [Phân tích Classroom Service](chuc-nang.md) mô tả phạm vi dữ liệu, chức năng
  nghiệp vụ, ranh giới service và hiện trạng triển khai.
- [Mô hình dữ liệu đề xuất](data-model.md) mô tả cấu trúc các bảng xoay quanh
  `courses`.
- [Kiến trúc hệ thống](../system/architecture.md) xác định quyền sở hữu giữa
  Classroom Service, Identity Service và Project Service.
- [Các luồng nghiệp vụ](../system/workflows.md) mô tả luồng tạo khóa học/nhóm và
  kiểm tra nhóm khi tạo project ở mức thiết kế mục tiêu.
