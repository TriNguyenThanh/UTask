# Input và output chức năng — Classroom Service

## Trạng thái và cách đọc

Tài liệu này diễn giải các chức năng mục tiêu trong
[chức năng theo tác nhân](objects.md) thành input và output ở mức nghiệp vụ.
Classroom Service chỉ dùng **khóa học** (`Course`) để quản lý cấu trúc học tập
và quan hệ học tập (không duy trì đối tượng lớp học riêng, không quản lý quy trình ghi danh/điểm danh phức tạp).
**Chưa triển khai**: repository hiện mới có khung Django cơ bản cho Classroom
Service; chưa có mã nghiệp vụ, hợp đồng API hoặc schema sự kiện để xác nhận các
hàm này. Đây không phải đặc tả endpoint hay schema máy đọc được; tên trường,
quy tắc kiểm tra, mã lỗi, phân trang và định dạng phản hồi cần được chốt trong
hợp đồng trước khi triển khai.

Trong các mục dưới đây, `actor` là người gọi đã được xác thực; `id` là mã định
danh của đối tượng. Các thuộc tính ví dụ như tên, mô tả và trạng thái chỉ giúp
làm rõ dữ liệu cần thiết, chưa phải danh sách trường bắt buộc. Mỗi thao tác chỉ
thực hiện khi quyền của tác nhân cho phép theo `objects.md`.

## Khóa học và giảng viên khóa học

| Hàm nghiệp vụ | Tác nhân mục tiêu | Input | Output mục tiêu |
| --- | --- | --- | --- |
| Tạo khóa học | Giảng viên tạo khóa học; quản trị viên hệ thống | `actor`; thông tin khóa học, ví dụ tên, mã, mô tả, học kỳ, thời gian, mã tham gia, `max_group_members`, cờ `is_template` (yes/no) | Khóa học mới với `id` và thông tin đã lưu; `actor` mặc định là chủ khóa học |
| Tạo khóa học từ template | Giảng viên tạo khóa học; quản trị viên hệ thống | `actor`; `course_id` của template được chọn; thông tin khóa học mới (tên, mã, học kỳ, ngày bắt đầu/kết thúc...) | Khóa học mới độc lập được tạo nhanh bằng cách copy snapshot cấu hình hiện tại từ template (`max_group_members`, mô tả...); không tạo quan hệ phụ thuộc giữa hai khóa học |
| Sửa khóa học | Giảng viên tạo khóa học có quyền quản lý; quản trị viên hệ thống | `actor`; `course_id`; các trường cần thay đổi (tên, mô tả, `max_group_members`, `is_template`...) | Khóa học sau cập nhật |
| Xem khóa học | Giảng viên trong khóa học, sinh viên trong khóa học, quản trị viên hệ thống | `actor`; `course_id` | Chi tiết khóa học trong phạm vi quyền xem của tác nhân |
| Liệt kê khóa học | Tác nhân đã xác thực; quyền xem được áp dụng theo từng khóa học | `actor`; điều kiện lọc (ví dụ lọc danh sách template: `is_template=true`) hoặc phân trang nếu có | Các khóa học hoặc danh sách template tác nhân được phép xem |
| Lưu trữ khóa học | Giảng viên tạo khóa học có quyền quản lý; quản trị viên hệ thống | `actor`; `course_id` | Khóa học ở trạng thái đã lưu trữ; tác động lên nhóm và project liên quan cần được chốt |
| Xóa khóa học | Giảng viên tạo khóa học có quyền quản lý; quản trị viên hệ thống | `actor`; `course_id` | Kết quả xác nhận xóa khóa học; xử lý nhóm, sinh viên và project liên quan cần được chốt |
| Thêm giảng viên vào khóa học | Giảng viên tạo khóa học; quản trị viên hệ thống | `actor`; `course_id`; `user_id` của giảng viên được thêm | Quan hệ giảng viên-khóa học mới (`course_instructors`); người được thêm có thể truy cập và xem dữ liệu khóa học theo mục tiêu |
| Gỡ giảng viên khỏi khóa học | Giảng viên tạo khóa học; quản trị viên hệ thống | `actor`; `course_id`; `user_id` của giảng viên cần gỡ | Quan hệ giảng viên-khóa học được chấm dứt (`removed_at`) |

Quyền ghi của giảng viên được thêm vào khóa học cần được quy định thống nhất khi
triển khai; không mặc nhiên suy ra toàn quyền sửa, lưu trữ hoặc xóa khóa học từ
quyền truy cập và xem.

## Sinh viên khóa học

| Hàm nghiệp vụ | Tác nhân mục tiêu | Input | Output mục tiêu |
| --- | --- | --- | --- |
| Thêm sinh viên vào khóa học | Giảng viên quản lý khóa học; quản trị viên hệ thống; sinh viên tự tham gia qua mã tham gia | `actor`; `course_id`; `user_id` sinh viên; `student_code` nếu có; `join_code` nếu tự tham gia | Bản ghi sinh viên khóa học mới (`course_students`) |
| Xem danh sách sinh viên | Giảng viên trong khóa học; sinh viên trong khóa học; quản trị viên hệ thống | `actor`; `course_id`; điều kiện lọc/phân trang nếu có | Danh sách sinh viên thuộc khóa học (`course_students`) trong phạm vi quyền xem |
| Cập nhật trạng thái sinh viên | Giảng viên quản lý khóa học; quản trị viên hệ thống | `actor`; `course_id`; `user_id`; trạng thái mới (`ACTIVE`, `DROPPED`, `COMPLETED`) | Trạng thái sinh viên trong khóa học sau cập nhật |
| Thôi học / gỡ sinh viên khỏi khóa học | Giảng viên quản lý khóa học; sinh viên tự rút khỏi khóa học; quản trị viên hệ thống | `actor`; `course_id`; `user_id` | Sinh viên được cập nhật trạng thái kết thúc tham gia khóa học (`left_at`) |

Mã tham gia khóa học (nếu dùng), cách xử lý khi sinh viên rút khỏi khóa học và
chính sách lưu lịch sử hay xóa vật lý cần được xác nhận bằng quy tắc nghiệp vụ
cụ thể.

## Nhóm và thành viên nhóm

| Hàm nghiệp vụ | Tác nhân mục tiêu | Input | Output mục tiêu |
| --- | --- | --- | --- |
| Tạo nhóm | Giảng viên tạo khóa học có quyền quản lý; quản trị viên hệ thống | `actor`; `course_id`; thông tin nhóm, ví dụ tên và mô tả | Nhóm mới với `id`, thông tin đã lưu và gắn trực tiếp với khóa học (`course_id`) |
| Sửa nhóm | Giảng viên có quyền quản lý nhóm/khóa học; quản trị viên hệ thống | `actor`; `group_id`; các trường cần thay đổi | Nhóm sau cập nhật |
| Xem nhóm | Giảng viên trong khóa học; sinh viên trong phạm vi nhóm được phép xem; quản trị viên hệ thống | `actor`; `group_id` | Thông tin nhóm trong phạm vi quyền xem |
| Liệt kê nhóm | Người có quyền xem khóa học; quản trị viên hệ thống | `actor`; `course_id`; điều kiện lọc hoặc phân trang nếu có | Danh sách nhóm thuộc khóa học mà tác nhân được phép xem |
| Lưu trữ nhóm | Giảng viên có quyền quản lý nhóm/khóa học; quản trị viên hệ thống | `actor`; `group_id` | Nhóm ở trạng thái đã lưu trữ; tác động lên project liên quan cần được chốt |
| Xóa nhóm | Giảng viên có quyền quản lý nhóm/khóa học; quản trị viên hệ thống | `actor`; `group_id` | Kết quả xác nhận xóa nhóm; theo quy tắc mục tiêu, Project Service xóa project liên kết sau khi nhận thông tin từ Classroom Service; thứ tự và phục hồi lỗi cần được chốt |
| Thêm thành viên nhóm / chọn nhóm | Sinh viên tự chọn nhóm; giảng viên có quyền quản lý nhóm; quản trị viên hệ thống | `actor`; `group_id`; `user_id` người học (mặc định người gọi khi tự chọn) | Quan hệ thành viên nhóm mới; nếu sự kiện được chốt, phát thông báo mục tiêu `group.member.added`. Ràng buộc: người học phải là sinh viên đang hoạt động trong `course_students` của khóa học; số lượng thành viên nhóm không vượt quá `max_group_members` của khóa học |
| Rời nhóm / gỡ thành viên | Sinh viên tự rời nhóm; giảng viên có quyền quản lý nhóm; quản trị viên hệ thống | `actor`; `group_id`; `user_id` người học | Quan hệ thành viên được gỡ; nếu sự kiện được chốt, phát thông báo mục tiêu `group.member.removed` |

Việc sinh viên có thể thuộc nhiều nhóm trong cùng khóa học, giới hạn số lượng
thành viên nhóm, thời điểm đổi nhóm và quyền giảng viên được thêm vào khóa học
đối với thao tác nhóm đều cần được quyết định. Tên sự kiện trong bảng là tên mục
tiêu. Producer Kafka nền tảng đã được cấu hình; luồng phát sự kiện nghiệp vụ,
topic, schema, phiên bản và consumer vẫn chưa được chốt.

## Xem dữ liệu theo quyền

| Hàm nghiệp vụ | Tác nhân mục tiêu | Input | Output mục tiêu |
| --- | --- | --- | --- |
| Xem dữ liệu riêng tư của khóa học | Giảng viên tạo khóa học, giảng viên được thêm vào khóa học trong phạm vi xem đã nêu, quản trị viên hệ thống | `actor`; `course_id`; loại dữ liệu cần xem | Chỉ dữ liệu riêng tư trong khóa học mà tác nhân được phép xem |
| Xem dữ liệu công khai của khóa học | Người có quyền truy cập khóa học; sinh viên trong khóa học; quản trị viên hệ thống | `actor`; `course_id`; loại dữ liệu cần xem | Dữ liệu công khai của khóa học |
| Xem dữ liệu nhóm | Giảng viên trong khóa học xem toàn bộ theo mục tiêu; sinh viên chỉ xem nhóm mình tham gia; quản trị viên hệ thống | `actor`; `group_id`; loại dữ liệu cần xem | Dữ liệu nhóm trong phạm vi quyền xem |

Project và task không thuộc dữ liệu Classroom Service. Khi cần hiển thị chúng,
ứng dụng phải lấy dữ liệu qua Project Service; Project Service tự áp dụng quyền
truy cập theo khóa học, nhóm và vai trò. Classroom Service không đọc Project DB.

## Tương tác giữa các service

| Hàm nghiệp vụ | Bên gọi / bên nhận | Input | Output mục tiêu |
| --- | --- | --- | --- |
| Xác thực người gọi | Request đến Classroom Service / Classroom Service | JWT do Identity Service phát hành | Danh tính và vai trò người gọi đã xác thực, hoặc kết quả từ chối; claim và cách kiểm tra cần được chốt |
| Xác minh khóa học hoặc nhóm | Project Service gọi Classroom Service qua REST | Ngữ cảnh người gọi; `course_id` hoặc `group_id`; thông tin cần xác minh, chẳng hạn nhóm có thuộc khóa học hay không | Kết quả hợp lệ/không hợp lệ và quan hệ cần thiết để Project Service quyết định; cấu trúc phản hồi và quy tắc quyền chưa được chốt |
| Thông báo thay đổi thành viên nhóm | Classroom Service phát Kafka / Project, Progress, AI có thể nhận | Thay đổi thành viên đã được lưu: nhóm, người dùng, loại thay đổi; trường và phiên bản schema chưa được chốt | Không có phản hồi đồng bộ từ consumer; kết quả là sự kiện mục tiêu `group.member.added` hoặc `group.member.removed` |

Project Service dùng REST khi cần câu trả lời ngay để xác minh nhóm hoặc khóa
học. Kafka chỉ thông báo thay đổi đã xảy ra; không dùng Kafka để chờ kết quả xác
minh.

## Kết quả lỗi và các quyết định còn mở

Ở mức nghiệp vụ, thao tác có thể không thành công khi input không hợp lệ, đối
tượng không tồn tại hoặc tác nhân không có quyền. Mã lỗi, định dạng lỗi, quy tắc
xử lý xung đột và hành vi lặp chưa được chốt; không xem các trường hợp này là
hợp đồng API đã phát hành.

Các điểm cần quyết định trước khi chuyển các hàm mục tiêu thành hợp đồng gồm:

- Trường dữ liệu và điều kiện bắt buộc cho khóa học, sinh viên và nhóm.
- Quyền ghi của giảng viên được thêm vào khóa học và việc gỡ giảng viên.
- Mã tham gia khóa học, sức chứa nhóm và quy tắc chọn/đổi/rời nhóm.
- Ý nghĩa lưu trữ và xóa, cùng tác động tới sinh viên, nhóm và project liên quan.
- Cấu trúc REST để Project Service xác minh khóa học/nhóm và schema, phiên bản,
  thứ tự, retry cho sự kiện thành viên nhóm.

## Tài liệu liên quan

- [Chức năng theo tác nhân](objects.md) — quyền và phạm vi chức năng mục tiêu.
- [Mô hình dữ liệu đề xuất](data-model.md) — cấu trúc bảng đề xuất xoay quanh
  `courses`.
- [Kiến trúc hệ thống](../system/architecture.md) — quyền sở hữu dữ liệu và
  ranh giới Classroom/Project.
- [Giao tiếp giữa các service](../system/communication.md) — khi nào dùng
  REST và Kafka.
- [Danh mục sự kiện Kafka](../system/kafka-events.md) — tên sự kiện mục tiêu,
  chưa phải schema đã chốt.
