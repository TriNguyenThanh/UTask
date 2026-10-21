# Nghiệp vụ và quyền của Identity, Classroom và Work

Tài liệu này giải thích bằng ngôn ngữ gần gũi ba phần chính của UTask: **ai là
ai**, **học/làm việc cùng lớp và nhóm nào**, rồi **làm dự án ra sao**. Đây là
tài liệu định hướng cho người dùng và đội phát triển; hợp đồng API chi tiết vẫn
ở tài liệu từng service.

## Nhìn nhanh

```text
Identity:   tạo và bảo vệ tài khoản
Classroom:  quản lý môn, lớp, giảng viên, sinh viên và nhóm học tập
Work:       quản lý dự án, công việc, Sprint và trao đổi trong dự án
```

Một người trước hết có tài khoản ở Identity. Khi đã vào lớp, Classroom xác định
người đó thuộc lớp và nhóm nào. Nhóm trưởng có thể tạo dự án ở Work; từ đó các
thành viên quản lý và thực hiện công việc của nhóm.

Mỗi service chỉ quản lý dữ liệu của mình. Ví dụ Classroom không tự sửa công
việc trong dự án và Work không tự đổi thành viên nhóm; hai bên kiểm tra thông
tin cần thiết qua API/sự kiện đã công bố.

## Các loại quyền cần hiểu trước

| Loại quyền | Ý nghĩa bình dân |
| --- | --- |
| `STUDENT` | Vai trò sinh viên trên toàn hệ thống. |
| `TEACHER` | Vai trò giảng viên trên toàn hệ thống; chưa đủ để quản lý mọi lớp. |
| `SYSTEM_ADMIN` | Quản trị hệ thống; có các quyền quản trị đã được chọn cho từng service. |
| Giảng viên phụ trách lớp | Người vừa có vai trò `TEACHER`, vừa được phân công đang hiệu lực trong chính lớp đó. |
| Thành viên/Trưởng nhóm | Quan hệ trong một nhóm học tập cụ thể. Trưởng nhóm điều phối nhóm. |
| Thành viên/Trưởng nhóm dự án | Quan hệ trong một dự án cụ thể. Trưởng nhóm dự án có quyền điều phối dự án. |

Vì vậy, chỉ có vai trò giảng viên không tự xem hay sửa được mọi lớp; chỉ là
quản trị viên cũng không tự có quyền đọc mọi dự án Work. Hệ thống còn kiểm tra
quan hệ thực tế với lớp, nhóm hoặc dự án.

## 1. Identity: tài khoản và đăng nhập

**Identity trả lời câu hỏi: “Bạn là ai và có đang đăng nhập hợp lệ không?”**

### Nghiệp vụ chính

- Đăng ký, kích hoạt tài khoản, đăng nhập, làm mới phiên đăng nhập và đăng xuất.
- Đổi mật khẩu, yêu cầu đặt lại mật khẩu, xem các thiết bị đã đăng nhập và thu
  hồi từng thiết bị hoặc toàn bộ thiết bị.
- Xem/sửa hồ sơ cá nhân và cập nhật ảnh đại diện khi môi trường đã bật chức năng này.
- Lưu mã số sinh viên, họ tên, trạng thái tài khoản và vai trò toàn hệ thống.
- Quản trị danh sách người dùng: cấp/gỡ vai trò, tạm đình chỉ hoặc mở lại tài khoản.
- Hỗ trợ Classroom tạo hoặc tìm tài khoản sinh viên khi giảng viên thêm danh sách
  sinh viên vào lớp.

Tài khoản có thể ở trạng thái chờ kích hoạt, đang hoạt động hoặc bị đình chỉ.
Khi đổi mật khẩu, đổi vai trò hoặc đình chỉ tài khoản, các phiên liên quan được
thu hồi để giảm rủi ro dùng tiếp quyền cũ.

### Ai được làm gì?

| Người dùng | Quyền trong Identity |
| --- | --- |
| Chưa đăng nhập | Đăng ký, đăng nhập, kích hoạt tài khoản và yêu cầu đặt lại mật khẩu. |
| Người đã đăng nhập | Xem/sửa hồ sơ của chính mình, gồm MSSV; đổi mật khẩu, xem/đăng xuất thiết bị của chính mình. Không tự cấp vai trò hoặc sửa email. MSSV phải chưa gán cho tài khoản khác; mã tự nhập chưa được đối chiếu với dữ liệu học vụ. |
| `SYSTEM_ADMIN` | Xem danh sách tài khoản, đổi trạng thái và cấp/gỡ vai trò. Không được tự gỡ quyền quản trị của chính mình. |
| Classroom (gọi nội bộ) | Cấp/tìm tài khoản sinh viên theo yêu cầu hợp lệ của giảng viên hoặc quản trị viên; Identity không tự ghi sinh viên vào lớp. |

Google/GitHub OAuth và gửi email thực tế phụ thuộc cấu hình/nhà cung cấp;
không xem việc có endpoint hay sự kiện nội bộ là bằng chứng người dùng đã đăng
nhập hay nhận email thành công ở môi trường thật.

## 2. Classroom: môn học, lớp và nhóm

**Classroom trả lời câu hỏi: “Bạn học/dạy lớp nào, thuộc nhóm nào?”**

### Nghiệp vụ chính

- Tạo và quản lý môn học.
- Mở lớp theo học kỳ, gán giảng viên phụ trách, đóng/lưu trữ lớp khi cần.
- Sinh viên tham gia lớp bằng mã; giảng viên hoặc quản trị viên thêm, cho rời
  hoặc loại sinh viên khỏi lớp.
- Sinh viên lập nhóm hoặc tham gia nhóm bằng mã mời; hệ thống giới hạn số người
  theo quy định của lớp.
- Chuyển trưởng nhóm, rời/loại thành viên và để giảng viên điều chỉnh sinh viên
  giữa các nhóm, vẫn giữ lịch sử tham gia.
- Chốt giai đoạn lập nhóm để không ai tự đổi nhóm sau mốc đó.
- Ghi nhận nhóm nào liên kết với dự án nào ở Work, để giảng viên theo dõi đúng
  dự án của lớp mình.

Điểm danh và điểm số vẫn thuộc Classroom về mặt phạm vi sản phẩm, nhưng **chưa
triển khai** trong phần backend P0/P1 hiện có.

### Ai được làm gì?

| Người dùng | Quyền trong Classroom |
| --- | --- |
| Sinh viên đang ghi danh | Xem lớp của mình, vào/rời lớp theo điều kiện; xem nhóm mình đang tham gia; dùng mã mời để vào nhóm khi lớp còn cho lập nhóm. |
| Thành viên nhóm | Xem thông tin nhóm của mình; tự rời nhóm nếu không phải trưởng nhóm. |
| Trưởng nhóm | Điều phối nhóm: chuyển trưởng nhóm, loại thành viên hoặc thao tác nhóm theo quy định của lớp. Khi rời/loại trưởng nhóm phải chọn người kế nhiệm trước. |
| Giảng viên phụ trách | Phải có cả vai trò `TEACHER` và phân công đang hiệu lực trong lớp. Khi đó có thể quản lý lớp, sinh viên, nhóm và điều chỉnh thành viên trong lớp mình. |
| `SYSTEM_ADMIN` | Quản lý theo các quyền Classroom đã được chọn, như quản lý môn/lớp hoặc một số thao tác nhóm. Quản trị viên không tự thành giảng viên phụ trách và không tự có quyền đọc toàn bộ nội dung Work. |

Một giảng viên đã rời phân công hoặc mất vai trò `TEACHER` sẽ mất quyền giảng
viên ở lớp đó. Việc có vai trò toàn hệ thống không thay thế quan hệ thực tế với
lớp.

## 3. Work: dự án và công việc của nhóm

**Work trả lời câu hỏi: “Nhóm đang làm dự án gì, ai đang làm việc nào và tiến
độ đến đâu?”**

### Nghiệp vụ chính

- Trưởng nhóm học tập tạo dự án cho nhóm đã được Classroom xác minh. Dự án có
  danh sách thành viên riêng, nhưng danh sách này được đồng bộ từ nhóm học tập.
- Quản lý thông tin dự án, thành viên, sức chứa công việc, các cột trạng thái
  của bảng công việc và việc lưu trữ dự án.
- Lập hạng mục lớn (Epic), nhãn và các việc cần làm; chia thành việc con, giao
  người làm, đặt ưu tiên, hạn hoàn thành và khối lượng ước tính.
- Chuyển việc qua các trạng thái như chưa làm, đang làm, chờ kiểm tra, hoàn
  thành; đánh dấu vướng mắc và mối quan hệ phụ thuộc giữa các việc.
- Lập Sprint: chọn việc cho một đợt làm việc, bắt đầu, theo dõi, kết thúc và
  quyết định các việc còn dang dở sẽ chuyển đi đâu.
- Bình luận, nhắc tên, đính kèm tài liệu, xem lịch sử thay đổi và nhận nhận xét
  của giảng viên phụ trách.
- Xem bảng công việc, dashboard tiến độ, phân bổ công việc và biểu đồ Sprint.
  Tiến độ được tính từ dữ liệu công việc theo quy tắc của Work, không do AI tự quyết.

### Ai được làm gì?

| Người dùng | Quyền trong Work |
| --- | --- |
| Thành viên dự án | Xem dự án, bảng việc, tiến độ và trao đổi của dự án mình. Có thể cập nhật việc được giao theo các trường được cho phép và bình luận/đính kèm nội dung trong phạm vi dự án. |
| Trưởng nhóm dự án | Tạo dự án từ nhóm mình là trưởng nhóm; điều phối dự án, cột trạng thái, Sprint, hạng mục, nhãn và công việc. Các thay đổi điều phối như tạo việc hoặc đổi trường quan trọng cần quyền trưởng nhóm. |
| Giảng viên phụ trách lớp | Xem dự án của các nhóm thuộc lớp mình và gửi nhận xét trong phạm vi đã được Classroom xác minh. Giảng viên không tự trở thành thành viên dự án và không có quyền tự sửa công việc của nhóm. |
| `SYSTEM_ADMIN` | Không tự có quyền xem hoặc sửa mọi dự án. Quyền nhận xét trong dự án gắn lớp chỉ được cấp khi Work xác minh đủ điều kiện. |

Khi dự án hoặc công việc đã lưu trữ/xóa, hệ thống chuyển sang chỉ đọc đối với
các thao tác không còn phù hợp. Nếu thành viên bị loại hoặc rời nhóm, Classroom
là nơi ghi thay đổi trước; Work tiếp nhận và áp dụng thay đổi theo luồng đồng bộ.

Tích hợp GitHub và đề xuất AI đã có phần mã/hợp đồng liên quan, nhưng **mới một
phần**: chưa được nghiệm thu đầy đủ với GitHub, nhà cung cấp AI hoặc staging.
AI chỉ đề xuất; người dùng xác nhận và Work kiểm tra lại quyền/quy tắc nghiệp
vụ trước khi áp dụng.

## Luồng thường gặp

1. Sinh viên có tài khoản ở **Identity** và đăng nhập.
2. Giảng viên phụ trách mở lớp trong **Classroom**; sinh viên vào lớp và lập nhóm.
3. Trưởng nhóm tạo dự án của nhóm trong **Work**.
4. Trưởng nhóm chia việc, mở Sprint; thành viên thực hiện, cập nhật việc được giao
   và trao đổi ngay trong dự án.
5. Giảng viên xem tiến độ/nhận xét theo lớp mình phụ trách; Classroom vẫn là nơi
   quyết định lớp, nhóm và thành viên nhóm.

## Trạng thái và phạm vi kiểm tra

- **Identity:** Đã triển khai các luồng tài khoản, phiên, hồ sơ, vai trò và
  provisioning nội bộ trong source hiện tại. Chưa xác minh nhà cung cấp OAuth,
  email và gateway/staging trong tài liệu này.
- **Classroom:** Đã triển khai backend P0/P1 cho môn, lớp, ghi danh, nhóm và
  liên kết nhóm–dự án trong source hiện tại. Điểm danh/điểm số chưa triển khai.
- **Work:** Mã nguồn hiện có các phạm vi dự án, công việc, Sprint, trao đổi,
  tiến độ và kiểm quyền nêu trên. Tài liệu này chưa thay cho một lượt nghiệm
  thu runtime toàn bộ Work ở môi trường staging.

Xem chi tiết kỹ thuật tại [Identity](../identity-service/README.md),
[Classroom](../classroom-service/README.md), [Work](../project-service/README.md),
[kiến trúc](architecture.md) và [quyền sở hữu dữ liệu](data-ownership.md).
