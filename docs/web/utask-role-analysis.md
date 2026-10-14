# 1. Mô hình vai trò

## 1.1 Danh sách vai trò

| Vai trò | Phạm vi | Trách nhiệm chính |
| --- | --- | --- |
| Guest | Không phải role lưu trong dữ liệu | Người chưa đăng nhập; chỉ sử dụng đăng ký, đăng nhập và khôi phục tài khoản. |
| Student | Tài khoản hoặc enrollment trong lớp | Tham gia lớp, xem yêu cầu, tạo nhóm hoặc tham gia nhóm. |
| Team Member | Membership trong nhóm | Thực hiện task, cập nhật tiến độ, trao đổi và liên kết hoạt động GitHub. |
| Team Leader | Membership trong nhóm | Có quyền của Member và thêm quyền điều phối backlog, Sprint, thành viên và integration. |
| Teacher | Tài khoản hoặc quyền trong lớp | Tạo lớp, quản lý nhóm, theo dõi tiến độ và phản hồi cho nhóm. |
| System Admin | Vai trò toàn hệ thống | Quản trị tài khoản, quyền tạo lớp, cấu hình và trạng thái vận hành. |

## 1.2 Vòng đời Student trong lớp và nhóm

| Trạng thái trước | Hành động | Trạng thái sau | Quy tắc |
| --- | --- | --- | --- |
| Student chưa có nhóm | Tạo nhóm | Student và Team Leader | Hệ thống tạo nhóm, gán người tạo làm Leader và sinh mã mời. |
| Student chưa có nhóm | Chấp nhận lời mời hoặc nhập mã | Student và Team Member | Hệ thống kiểm tra cùng lớp, giới hạn nhóm và membership hiện tại. |
| Student và Team Member | Được chuyển quyền | Student và Team Leader | Leader hiện tại hoặc Teacher xác nhận chuyển quyền; hệ thống ghi lịch sử. |
| Student và Team Leader | Rời nhóm | Tùy điều kiện | Phải chuyển quyền, yêu cầu Teacher xử lý hoặc xóa nhóm nếu chưa bắt đầu project. |

## 1.3 Quy tắc vai trò

- Student vẫn là Student sau khi trở thành Member hoặc Leader.
- Một Student chỉ thuộc tối đa một nhóm đang hoạt động trong cùng lớp, trừ khi lớp có cấu hình khác.
- Leader của nhóm A không có quyền Leader trong nhóm B.
- Teacher chỉ quản lý các lớp được phân công phụ trách hoặc lớp được họ tạo ra.
- Admin không mặc định được đọc hoặc sửa nội dung project của sinh viên.
- Project thuộc nhóm và kế thừa danh sách thành viên từ nhóm.
- Việc kiểm tra quyền phải được thực hiện ở backend, không chỉ ẩn nút trên giao diện.

# 2. Ma trận phân quyền vai trò

## 2.1. Quyền của Student, Member và Leader

| Hành động | Student chưa có nhóm | Member | Leader |
| --- | --- | --- | --- |
| Tạo nhóm trong lớp | Có điều kiện | Không | Không |
| Tham gia nhóm bằng mã hoặc lời mời | Có điều kiện | Không | Không |
| Mời thành viên vào nhóm | Không | Không | Có |
| Thay đổi Leader, đuổi Member | Không | Không | Có |
| Xem project và backlog của nhóm | Không | Có | Có |
| Tạo task trong backlog | Không | Không | Có |
| Cập nhật trạng thái task | Không | Task được giao | Có |
| Gán task và thay đổi ưu tiên | Không | Không mặc định | Có |
| Quản lý Sprint | Không | Chỉ xem | Có |
| Comment trong task | Không | Có | Có |
| Xem dashboard nhóm | Không | Có | Có |
| Kết nối GitHub repository | Không | Không | Có |
| Liên kết PR hoặc commit với task | Không | Có | Có |
| Yêu cầu AI phân rã task | Không | Không | Có |
| Phê duyệt backlog AI | Không | Không | Có |
| Xem cảnh báo rủi ro | Không | Có trong nhóm | Có |
| Quản trị tài khoản và tích hợp | Không | Không | Không |

## 2.2. Quyền của Teacher và Admin

| Hành động | Teacher | Admin |
| --- | --- | --- |
| Xem thông tin và mốc của lớp | Có | Có 😊 |
| Tạo nhóm trong lớp | Có | Có 😊 |
| Tham gia nhóm bằng mã hoặc lời mời | Không | Có 😊 |
| Phân thành viên vào nhóm | Có | Có 😊 |
| Thay đổi thành viên hoặc Leader | Có | Có 😊 |
| Xem project và backlog của nhóm | Chỉ xem lớp phụ trách | Có 😊 |
| Tạo task trong backlog | Không | Có 😊 |
| Cập nhật trạng thái task | Không | Có 😊 |
| Gán task và thay đổi ưu tiên | Không | Có 😊 |
| Quản lý Sprint | Chỉ xem | Có 😊 |
| Comment trong task | Có | Có 😊 |
| Xem dashboard nhóm | Có với lớp phụ trách | Có 😊 |
| Kết nối GitHub repository | Không mặc định | Có 😊 |
| Liên kết PR hoặc commit với task | Chỉ xem | Có 😊 |
| Yêu cầu AI phân rã task | Không | Có 😊 |
| Phê duyệt backlog AI | Không | Có 😊 |
| Xem cảnh báo rủi ro | Có với lớp phụ trách | Có 😊 |
| Quản trị tài khoản và tích hợp | Có với lớp phụ trách | Có 😊 |

## 2.3. Nguyên tắc kiểm tra quyền

- Hệ thống kiểm tra người dùng đã đăng nhập trước khi kiểm tra quyền nghiệp vụ.
- Hệ thống kiểm tra enrollment trong lớp trước khi cho phép tạo hoặc tham gia nhóm.
- Hệ thống kiểm tra membership và vai trò trong đúng nhóm trước khi cho phép thao tác project.
- Hệ thống kiểm tra lại quyền tại thời điểm xác nhận hành động AI hoặc GitHub.
- Mọi thay đổi quyền, thành viên, phân công và integration quan trọng phải được ghi audit log.

# 3. Epic 1 Account and Class Access

## 3.1. User Stories

| Mã | Actor | User Story | Ưu tiên |
| --- | --- | --- | --- |
| US-1.1 | User | Là người có tài khoản, tôi muốn đăng nhập để truy cập đúng không gian làm việc theo quyền của mình. | Must |
| US-1.2 | Teacher | Là giảng viên, tôi muốn tạo lớp và mã tham gia để tổ chức sinh viên thực hiện đồ án. | Must |
| US-1.3 | Student | Là sinh viên, tôi muốn tham gia lớp bằng mã hoặc lời mời để tiếp cận yêu cầu đồ án và thành lập nhóm. | Must |
| US-1.4 | Teacher | Là giảng viên, tôi muốn thêm sinh viên từ danh sách lớp học để hệ thống tạo tài khoản cho sinh viên chưa tồn tại hoặc thêm tài khoản đã tồn tại vào lớp. | Must |

## 3.2. Acceptance criteria

**US-1.1 Đăng nhập**
- Thông tin hợp lệ tạo phiên đăng nhập an toàn.
- Tài khoản bị khóa hoặc vô hiệu hóa không thể đăng nhập.
- Sau đăng nhập, người dùng chỉ thấy lớp và project được cấp quyền.
- Thông báo lỗi không tiết lộ một email có tồn tại trong hệ thống hay không.

**US-1.2 Tạo lớp**
- Chỉ tài khoản có quyền Teacher hoặc admin mới thực hiện được.
- Teacher thiết lập tên lớp, thời gian và giới hạn thành viên nhóm.
- Hệ thống sinh mã tham gia có thể đổi hoặc vô hiệu hóa.
- Người tạo lớp được gán làm Teacher phụ trách lớp đó.

**US-1.3 Tham gia lớp**
- Mã hoặc lời mời phải hợp lệ và còn hiệu lực.
- Hệ thống không tạo enrollment trùng.
- Tham gia lớp chỉ cấp vai trò Student trong lớp, không tự động thêm vào nhóm.
- Student có thể xem yêu cầu, mốc thời gian và trạng thái thành lập nhóm của lớp.

**US-1.4 Thêm sinh viên từ danh sách lớp**
- Chỉ Teacher phụ trách lớp hoặc Admin mới được thêm sinh viên vào lớp.
- Teacher có thể thêm từng sinh viên hoặc nhập danh sách sinh viên từ file CSV hoặc Excel.
- Hệ thống kiểm tra tài khoản hiện có bằng email hoặc mã sinh viên trước khi xử lý.
- Nếu sinh viên chưa có tài khoản, hệ thống tạo tài khoản Student ở trạng thái chờ kích hoạt và tạo enrollment với lớp.
- Sinh viên có tài khoản mới nhận được liên kết kích hoạt để tự thiết lập mật khẩu.
- Nếu sinh viên đã có tài khoản, hệ thống sử dụng tài khoản hiện có và chỉ tạo enrollment với lớp.
- Nếu sinh viên đã thuộc lớp, hệ thống không tạo enrollment trùng và thông báo cho Teacher.
- Nếu email đã thuộc tài khoản Teacher hoặc Admin, hệ thống không tự động thay đổi vai trò và đưa bản ghi vào danh sách cần kiểm tra.
- Việc thêm sinh viên vào lớp chỉ cấp vai trò Student trong lớp, không tự động cấp vai trò Member hoặc Leader.
- Sau khi xử lý, hệ thống hiển thị số tài khoản được tạo mới, số tài khoản hiện có được thêm vào lớp, số bản ghi trùng và số bản ghi thất bại.
- Hệ thống hiển thị nguyên nhân đối với từng bản ghi bị bỏ qua hoặc xử lý thất bại.
- Mọi thao tác tạo tài khoản và thêm sinh viên vào lớp phải được ghi audit log.

# 4. Epic 2 Team and Project Setup

## 4.1. User Stories

| Mã | Actor | User Story | Ưu tiên |
| --- | --- | --- | --- |
| US-2.1 | Student | Là sinh viên chưa có nhóm, tôi muốn tạo nhóm trong lớp để bắt đầu tổ chức thực hiện đồ án. | Must |
| US-2.2 | Student | Là sinh viên chưa có nhóm, tôi muốn tham gia nhóm bằng mã hoặc lời mời để cộng tác với các thành viên khác. | Must |
| US-2.3 | Team Leader | Là trưởng nhóm, tôi muốn mời và quản lý thành viên để xây dựng nhóm phù hợp với giới hạn của lớp. | Must |
| US-2.4 | Team Leader | Là trưởng nhóm, tôi muốn cấu hình thông tin project để xác định đề tài, mục tiêu và thời gian thực hiện. | Must |
| US-2.5 | Teacher | Là giảng viên, tôi muốn xem và điều chỉnh danh sách nhóm khi cần để bảo đảm mọi sinh viên được tổ chức hợp lệ. | Should |

## 4.2. Acceptance criteria

**US-2.1 Tạo nhóm**
- Student phải thuộc lớp và lớp đang mở giai đoạn thành lập nhóm.
- Student chưa thuộc nhóm đang hoạt động trong cùng lớp.
- Hệ thống tạo nhóm và gán người tạo làm Leader.
- Hệ thống sinh mã hoặc liên kết mời và áp dụng giới hạn thành viên của lớp.

**US-2.2 Tham gia nhóm**
- Student và nhóm phải thuộc cùng lớp.
- Student chưa thuộc nhóm khác trong lớp.
- Nhóm chưa đạt giới hạn thành viên.
- Tham gia thành công tạo TeamMembership với vai trò Member.

**US-2.3 Quản lý thành viên**
- Leader có thể tạo hóa mã mời.
- Chỉ Student cùng lớp và chưa có nhóm mới có thể chấp nhận lời mời.
- Không thể thay đổi thành viên sau khi thành lập nhóm. Có thể kick thành viên bởi Leader
- Nhóm luôn phải có ít nhất một Leader, Leader không thể rời nhóm trước khi chuyển quyền.

**US-2.4 Cấu hình project**
- Leader có thể nhập tên, mô tả, mục tiêu, tech stack và thời gian dự kiến.
- Project thuộc nhóm và kế thừa membership từ nhóm.
- Một nhóm có một project chính trong MVP.
- Các thay đổi thông tin project được ghi lại người thực hiện và thời điểm.

**US-2.5 Điều chỉnh nhóm**
- Teacher chỉ quản lý các nhóm thuộc lớp mình phụ trách.
- Teacher có thể xử lý Student chưa có nhóm, chuyển thành viên và chỉ định Leader.
- Hệ thống cảnh báo khi thao tác làm nhóm vi phạm giới hạn thành viên.
- Lịch sử membership và đóng góp trước đó không bị xóa khi Student chuyển nhóm.

# 5. Epic 3 Task and Sprint Management

## 5.1. User Stories

| Mã | Actor | User Story | Ưu tiên |
| --- | --- | --- | --- |
| US-3.1 | Team Leader | Là trưởng nhóm, tôi muốn tạo, sắp xếp và phân công backlog để nhóm biết công việc và trách nhiệm của từng người. | Must |
| US-3.2 | Team Member | Là thành viên nhóm, tôi muốn xem backlog và Kanban Board để biết kế hoạch cũng như trạng thái project. | Must |
| US-3.3 | Team Member | Là thành viên được giao task, tôi muốn cập nhật nội dung, trạng thái để phản ánh tiến độ thực tế. | Must |
| US-3.4 | Team Leader | Là trưởng nhóm, tôi muốn lập và kết thúc Sprint để quản lý công việc theo từng chu kỳ. | Should |

## 5.2. Acceptance criteria

**US-3.1 Quản lý backlog**
- Leader có thể tạo Work Item với tiêu đề, mô tả, loại, priority, deadline và story point.
- Assignee phải là thành viên đang hoạt động của cùng nhóm.
- Leader có thể sắp xếp thứ tự ưu tiên và lưu trữ task không còn cần thiết.
- Hệ thống ghi lịch sử thay đổi assignee, priority, deadline và trạng thái.

**US-3.2 Xem backlog và Kanban**
- Member chỉ xem project thuộc nhóm mình.
- Board hiển thị task theo trạng thái workflow.
- Người dùng có thể tìm và lọc theo trạng thái, assignee, priority và deadline.
- Task quá hạn và task blocked được hiển thị rõ.

**US-3.3 Cập nhật task**
- Member cập nhật được trạng thái và nội dung thực hiện của task được giao.
- Member có thể đánh dấu blocked và ghi nguyên nhân.
- Member không mặc định được thay đổi assignee của người khác, deadline chung hoặc phạm vi Sprint.
- Mọi thay đổi được ghi người thực hiện và thời điểm.

**US-3.4 Quản lý Sprint**
- Leader tạo Sprint với mục tiêu, ngày bắt đầu và ngày kết thúc.
- Project chỉ có một Sprint đang hoạt động trong MVP.
- Thay đổi phạm vi Sprint đang chạy phải kèm lý do và được ghi lịch sử.
- Khi kết thúc Sprint, task chưa hoàn thành được chuyển về backlog hoặc Sprint tiếp theo.

# 6. Epic 4 Collaboration and Progress Tracking

## 6.1. User Stories

| Mã | Actor | User Story | Ưu tiên |
| --- | --- | --- | --- |
| US-4.1 | Team Member | Là thành viên nhóm, tôi muốn trao đổi trong task và nhắc tới người liên quan để thảo luận đúng ngữ cảnh. | Must |
| US-4.2 | Team Member | Là thành viên nhóm, tôi muốn nhận thông báo khi được giao việc, được nhắc tới hoặc gần deadline để không bỏ lỡ công việc. | Must |
| US-4.4 | Teacher | Là giảng viên, tôi muốn xem dashboard tất cả các nhóm kèm dấu hiệu rủi ro để xác định nhóm cần hỗ trợ. | Must |
| US-4.5 | Teacher | Là giảng viên, tôi muốn xem chi tiết và phản hồi cho một nhóm để hướng dẫn nhóm điều chỉnh kế hoạch. | Should |

## 6.2. Acceptance criteria

**US-4.1 Trao đổi trong task**
- Chỉ người có quyền xem task mới được comment.
- Người dùng có thể mention thành viên cùng nhóm và Teacher phụ trách khi được phép.
- Comment hiển thị tác giả và thời điểm; chỉnh sửa hoặc xóa phải giữ dấu vết phù hợp.
- Người được mention nhận thông báo liên quan.

**US-4.2 Nhận thông báo**
- Hệ thống thông báo khi người dùng được giao task hoặc được mention.
- Hệ thống nhắc trước deadline theo cấu hình và cảnh báo khi task quá hạn.
- Một sự kiện không tạo nhiều thông báo trùng cho cùng người dùng.
- Người dùng có thể đánh dấu đã đọc và xem tài nguyên liên quan.

**US-4.3 Dashboard nhóm**
- Dashboard hiển thị tiến độ Sprint hoặc Kanban, task quá hạn.
- Leader xem phân bổ task và story point theo thành viên.
- Hệ thống hiển thị dữ liệu nguồn và thời điểm cập nhật.
- Dashboard không kết luận năng suất chỉ từ số lượng task hoặc commit.

**US-4.4 Dashboard lớp**
- Teacher chỉ xem các lớp mình phụ trách.
- Dashboard hiển thị danh sách nhóm, tiến độ, task quá hạn và hoạt động gần nhất.
- Nhóm có dấu hiệu rủi ro được đánh dấu kèm nguyên nhân.
- Teacher có thể mở chi tiết dữ liệu nguồn của cảnh báo.

**US-4.5 Phản hồi cho nhóm**
- Teacher có thể comment ở cấp task hoặc project trong lớp phụ trách.
- Nhóm nhận thông báo khi có phản hồi mới.
- Phản hồi của Teacher không tự thay đổi trạng thái hoặc phân công task.
- Hệ thống lưu lịch sử phản hồi để phục vụ theo dõi quá trình.

# 7. Epic 5 Intelligent Project Assistant and GitHub Traceability

## 7.1. Vòng lặp nghiệp vụ

- Leader lựa chọn và kết nối một GitHub repository chính với project.
- Repository được kết nối có thể thuộc tài khoản GitHub của Leader hoặc GitHub Organization mà Leader có đủ quyền cấp phép.
- Mỗi project chỉ sử dụng một repository chính trong phạm vi MVP.
- Các Member không kết nối repository riêng; mọi branch, commit và Pull Request được truy xuất từ repository chính mà Leader đã kết nối.
- Member có thể cung cấp hoặc xác nhận tài khoản GitHub của mình để UTask ánh xạ hoạt động GitHub với thành viên tương ứng.
- Leader nhập mô tả project hoặc chức năng và yêu cầu AI đề xuất backlog.
- Nhóm xem xét, chỉnh sửa và phê duyệt các task cần tạo.
- Member thực hiện task trên repository chính và liên kết task với branch, commit hoặc Pull Request liên quan.
- UTask nhận webhook từ repository chính, cập nhật dữ liệu phát triển và lưu thời điểm đồng bộ.
- Hệ thống bỏ qua hoặc từ chối dữ liệu GitHub đến từ repository không được kết nối với project.
- Hệ thống phát hiện tín hiệu rủi ro theo rule; AI tổng hợp, giải thích và đề xuất hành động.
- Leader hoặc Teacher xem dữ liệu nguồn trước khi quyết định điều chỉnh.

## 7.2. User Stories

| Mã | Actor | User Story | Ưu tiên |
| --- | --- | --- | --- |
| US-5.1 | Team Leader | Là trưởng nhóm, tôi muốn kết nối một GitHub repository chính với project để UTask thu thập tập trung hoạt động phát triển của cả nhóm. | Must |
| US-5.2 | Team Member | Là thành viên nhóm, tôi muốn liên kết task với branch, commit hoặc Pull Request trong repository chính của project để truy vết công việc với thay đổi mã nguồn. | Must |
| US-5.3 | Team Member | Là thành viên nhóm, tôi muốn xem hoạt động phát triển được truy xuất từ repository chính ngay trong task để biết công việc đang ở giai đoạn nào. | Could |
| US-5.4 | Team Leader | Là trưởng nhóm, tôi muốn AI đề xuất backlog từ mô tả project hoặc chức năng để nhóm có điểm bắt đầu cho việc lập kế hoạch. | Must |
| US-5.5 | Team Member | Là thành viên nhóm, tôi muốn AI phân rã một task phức tạp thành các subtask nhỏ hơn để dễ ước lượng và thực hiện. | Must |
| US-5.6 | Team Leader | Là trưởng nhóm, tôi muốn AI phân tích dữ liệu task và GitHub để phát hiện nguy cơ ảnh hưởng đến Sprint hoặc deadline và giải thích nguyên nhân. | Should |
| US-5.7 | Teacher | Là giảng viên, tôi muốn xem tổng hợp rủi ro của các nhóm cùng nguyên nhân và dữ liệu liên quan để biết nhóm nào cần được hỗ trợ. | Should |

## 7.3. Acceptance criteria

**US-5.1 Kết nối repository chính**
- Chỉ Team Leader của project mới được thiết lập, thay đổi hoặc ngắt kết nối GitHub repository.
- Leader phải có đủ quyền cấp phép trên repository được lựa chọn.
- Repository có thể thuộc tài khoản GitHub của Leader hoặc một GitHub Organization mà Leader có quyền quản trị hoặc cài đặt integration.
- Mỗi project chỉ kết nối một repository chính trong phạm vi MVP.
- Các Team Member không phải và không được kết nối repository riêng vào cùng project.
- Mọi branch, commit, Pull Request và trạng thái review của project được truy xuất từ repository chính đã kết nối.
- UTask lưu mã repository, tên repository, chủ sở hữu, nhánh mặc định, trạng thái kết nối và thời điểm đồng bộ gần nhất.
- Thông tin xác thực GitHub phải được mã hóa và không được xuất hiện trong log.
- UTask chỉ yêu cầu các quyền GitHub tối thiểu cần thiết để đọc metadata, nhận webhook và theo dõi hoạt động phát triển.
- Leader có thể ngắt kết nối hoặc kết nối lại repository.
- Khi quyền GitHub bị thu hồi, hệ thống phải hiển thị trạng thái mất kết nối và ngừng đồng bộ dữ liệu mới.
- Khi Leader thay đổi repository chính, hệ thống phải cảnh báo rằng các liên kết task với dữ liệu của repository cũ có thể không còn được cập nhật.
- Dữ liệu lịch sử từ repository cũ không bị xóa tự động khi thay đổi kết nối.
- Mọi thao tác kết nối, thay đổi hoặc ngắt kết nối repository phải được ghi activity log hoặc audit log.

**US-5.2 Liên kết task với dữ liệu GitHub**
- Task phải thuộc project đang kết nối với repository chính.
- Branch, commit hoặc Pull Request được liên kết phải thuộc repository chính của project.
- Member không cần kết nối repository riêng để sử dụng chức năng liên kết.
- Member có thể liên kết thủ công branch, commit hoặc Pull Request với task.
- UTask có thể đề xuất liên kết dựa trên mã task xuất hiện trong tên branch, nội dung commit hoặc tiêu đề Pull Request.
- Member hoặc Leader phải xác nhận trước khi một liên kết được đề xuất trở thành liên kết chính thức.
- Hệ thống không cho phép liên kết task với branch, commit hoặc Pull Request thuộc repository khác.
- Webhook phải được kiểm tra repository nguồn trước khi xử lý.
- Webhook được xử lý idempotent để không tạo commit, Pull Request hoặc liên kết trùng.
- Người có quyền có thể hủy liên kết sai và hệ thống phải ghi activity log.
- Việc hủy liên kết không xóa branch, commit hoặc Pull Request trên GitHub.
- Pull Request được merge không tự động chuyển task sang trạng thái Done.

**US-5.3 Xem trạng thái phát triển từ repository chính**
- Task hiển thị branch, commit gần nhất, Pull Request và trạng thái review liên quan từ repository chính của project.
- Giao diện hiển thị rõ repository đang cung cấp dữ liệu.
- Giao diện hiển thị thời điểm đồng bộ gần nhất.
- Hệ thống cảnh báo khi webhook bị lỗi, kết nối bị thu hồi hoặc dữ liệu có thể đã cũ.
- Dữ liệu GitHub đến từ repository khác không được hiển thị trong task.
- Pull Request được merge không tự động chứng minh task đã hoàn thành.
- Số lượng commit không được dùng trực tiếp để kết luận mức độ đóng góp hoặc năng lực của thành viên.
- Member chỉ xem dữ liệu GitHub liên quan đến project của nhóm mình.
- Teacher chỉ xem dữ liệu GitHub của những nhóm thuộc lớp mình phụ trách.

**US-5.4 AI đề xuất backlog**
- AI nhận context gồm mô tả project, mục tiêu, tech stack, deadline và ràng buộc do người dùng cung cấp.
- Kết quả tuân theo schema gồm loại Work Item, tiêu đề, mô tả, priority, ước lượng, dependency và acceptance criteria.
- Kết quả chỉ là bản nháp; Leader có thể sửa, chọn hoặc loại bỏ từng đề xuất.
- Task chỉ được tạo sau khi Leader xác nhận và backend kiểm tra lại quyền.
- Hệ thống đánh dấu task có nguồn đề xuất từ AI và ngăn xác nhận lặp tạo dữ liệu trùng.

**US-5.5 AI phân rã task**
- Member chỉ yêu cầu phân rã task thuộc project của nhóm mình.
- AI sử dụng mô tả, acceptance criteria và dependency của task cha.
- Mỗi subtask đề xuất có tiêu đề, kết quả cần đạt và dependency nếu có.
- Member được sửa hoặc loại bỏ đề xuất nhưng không thể dùng AI để vượt quyền phân công.
- Task cha không tự đổi trạng thái sau khi tạo subtask.

**US-5.6 AI phân tích rủi ro**
- AI chỉ phân tích dữ liệu GitHub lấy từ repository chính của project.
- Mỗi cảnh báo nêu nguyên nhân, dữ liệu nguồn và thời điểm phân tích.
- Hệ thống phân biệt không có dữ liệu với không có hoạt động.
- Hệ thống phân biệt thành viên chưa ánh xạ tài khoản GitHub với thành viên không có hoạt động.
- Các tín hiệu cơ bản được tính bằng rule xác định trước; AI chịu trách nhiệm tổng hợp và giải thích.
- AI không tự đổi deadline, assignee, trạng thái hoặc phạm vi Sprint.
- Người dùng có thể đánh dấu đề xuất hữu ích hoặc không phù hợp.

**US-5.7 Giảng viên xem rủi ro**
- Teacher chỉ xem nhóm thuộc lớp mình phụ trách.
- Mỗi nhóm có mức cảnh báo kèm nguyên nhân và đường dẫn tới dữ liệu nguồn.
- Dashboard hiển thị repository chính đang được sử dụng bởi từng project.
- Dữ liệu GitHub lỗi, chưa đồng bộ hoặc mất kết nối phải được đánh dấu rõ.
- Trường hợp chưa ánh xạ được hoạt động GitHub với thành viên phải được hiển thị là chưa xác định, không được tự động kết luận thành viên không đóng góp.
- Teacher có thể ghi nhận phản hồi; cảnh báo không tự động chuyển thành điểm số.

## 7.4. Nguyên tắc quản lý repository và tài khoản GitHub

**Repository cấp project**
- Repository được kết nối ở cấp project, không được kết nối riêng cho từng Member.
- Mỗi project có một repository chính trong MVP.
- Team Leader chịu trách nhiệm thiết lập kết nối repository.
- Mọi dữ liệu GitHub của project phải được truy xuất từ repository chính.
- Team Member chỉ làm việc trên branch, commit và Pull Request thuộc repository chính.

**Ánh xạ tài khoản GitHub với thành viên**
Việc không yêu cầu Member kết nối repository riêng không có nghĩa hệ thống không cần biết tài khoản GitHub của Member. UTask cần ánh xạ:
- UTask User
- GitHub Username
- GitHub User ID
- Team Membership
- Verification Status

- Member có thể nhập GitHub username hoặc xác nhận tài khoản GitHub của mình.
- Xác nhận tài khoản GitHub chỉ dùng để xác định hoạt động nào thuộc về Member, không tạo thêm kết nối repository.
- Một tài khoản GitHub không được ánh xạ đồng thời cho nhiều Member trong cùng project.
- Nếu commit sử dụng email khác hoặc tài khoản chưa được ánh xạ, hoạt động được hiển thị là chưa xác định.
- Leader có thể yêu cầu Member xác nhận lại tài khoản GitHub nhưng không được tự nhận hoạt động của người khác cho Member.
- Việc ánh xạ tài khoản không được dùng làm bằng chứng duy nhất để đánh giá mức độ đóng góp.

## 7.5. Quyền của AI

AI trong MVP hoạt động theo nguyên tắc đề xuất, xác nhận và ghi lịch sử.

**AI được phép**
- Đọc dữ liệu project mà người yêu cầu có quyền truy cập.
- Đọc metadata phát triển được đồng bộ từ repository chính của project.
- Tạo bản nháp backlog, task và subtask.
- Đề xuất mô tả, acceptance criteria, priority, ước lượng và dependency.
- Tổng hợp tín hiệu tiến độ và giải thích nguyên nhân rủi ro.
- Đề xuất hành động để Leader hoặc Teacher xem xét.

**AI không được phép trong MVP**
- Kết nối hoặc thay đổi repository thay Team Leader.
- Đọc repository khác ngoài repository chính đã được cấp quyền.
- Tự tạo hoặc xóa task chính thức.
- Tự giao việc, đổi deadline hoặc chuyển trạng thái task.
- Tự chấm điểm hoặc kết luận năng lực sinh viên.
- Tự loại thành viên khỏi nhóm hoặc gửi nhận xét thay Teacher.

# 8. Phạm vi MVP nên ưu tiên

## 8.1. Mức P0 MVP sử dụng được
P0 phải tạo được một luồng hoàn chỉnh từ lớp học đến công việc và bằng chứng phát triển. Đây là phạm vi cần hoàn thành trước khi mở rộng phân tích rủi ro.
- Epic 1 gồm US-1.1 đến US-1.4 để tạo tài khoản, đăng nhập, tạo lớp và tham gia lớp.
- Epic 2 gồm US-2.1 đến US-2.4 để Student tạo hoặc tham gia nhóm, Leader quản lý thành viên và cấu hình project.
- Epic 3 gồm US-3.1 đến US-3.3 để quản lý backlog, Kanban Board và trạng thái task.
- Epic 4 gồm US-4.1, US-4.2 và US-4.4 để trao đổi, nhận thông báo và giúp Teacher theo dõi các nhóm.
- Epic 5 gồm US-5.1 đến US-5.5 để kết nối repository, liên kết task với GitHub, hiển thị trạng thái phát triển và dùng AI tạo hoặc phân rã task.

## 8.2. Mức P1 Pilot trong lớp
- US-2.5 để Teacher xử lý Student chưa có nhóm và các ngoại lệ membership.
- US-3.4 để bổ sung Sprint sau khi quy trình Kanban cơ bản đã ổn định.
- US-4.3 và US-4.5 để Leader xem workload và Teacher phản hồi có cấu trúc.
- US-5.6 phiên bản rule based để tổng hợp và giải thích rủi ro project.
- US-5.7 để Teacher xem cảnh báo có giải thích và dữ liệu nguồn.

## 8.3. Mức P2 Sau MVP
- AI đề xuất phân bổ lại workload dựa trên dữ liệu lịch sử và kỹ năng do nhóm cung cấp.
- Nhiều repository cho một project và đồng bộ trạng thái hai chiều nâng cao.
- Mô hình dự đoán nguy cơ trễ dựa trên dữ liệu nhiều Sprint.
- Quản lý điểm số, điểm danh và quy trình đánh giá học tập đầy đủ.
- Agent thực hiện hành động sau quy trình phê duyệt nhiều bước.

## 8.4. Điều kiện hoàn thành MVP
MVP được xem là hoàn thành khi chứng minh được luồng nghiệp vụ sau trong một lớp thử nghiệm:
- Teacher tạo lớp và Student tham gia lớp.
- Student tạo hoặc tham gia nhóm và nhận đúng vai trò Leader hoặc Member.
- Nhóm tạo backlog, phân công và cập nhật task trên Kanban Board.
- Leader kết nối repository và Member liên kết hoạt động GitHub với task.
- AI đề xuất backlog hoặc phân rã task; người dùng chỉnh sửa và xác nhận trước khi lưu.
- Teacher xem được tiến độ, task quá hạn và dữ liệu liên quan của các nhóm trong lớp.

## 8.5. Các nội dung không thuộc MVP
- AI tự động giao việc, thay đổi deadline hoặc đóng task.
- Tự động chấm điểm sinh viên từ số lượng commit hoặc task.
- Điểm danh, quản lý điểm số đầy đủ và LMS tổng quát.
- Nhiều repository, nhiều nhà cung cấp Git và workflow tùy biến hoàn toàn.
- Microservice và hạ tầng phân tán khi chưa có nhu cầu tải hoặc tổ chức tương ứng.