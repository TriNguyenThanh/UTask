# AI Service

**Trạng thái tài liệu: Thiết kế mục tiêu; hiện trạng triển khai chưa xác minh.**

AI Service là service nội bộ của UTask. OpenAI, Gemini hoặc nhà cung cấp mô hình
ngôn ngữ lớn (LLM) khác là hệ thống bên ngoài. Google ADK hoặc framework tác tử
khác là lựa chọn triển khai, không làm thay đổi ranh giới service.

## Yêu cầu và ngữ cảnh

API AI nhận ý định của người dùng, chẳng hạn phân rã task, gợi ý ưu tiên, phân
tích khối lượng công việc hoặc giải thích nguy cơ trễ. Yêu cầu không cần gửi toàn bộ dữ
liệu project. Đường dẫn `POST /api/v1/ai/tasks/{task_id}/decompose` chỉ là ví
dụ thiết kế, chưa phải hợp đồng API đã xác nhận.

Ngữ cảnh nghiệp vụ được đồng bộ qua Kafka vào database riêng `ai_context_db`.
Đây là bản sao đọc tối thiểu để phân tích, không phải dữ liệu gốc. Công cụ của
tác tử chỉ đọc bản sao nội bộ, chẳng hạn dữ liệu project/task, khối lượng công việc, hoạt
động GitHub đã chuẩn hóa và chỉ số tiến độ. AI không gọi REST hoặc database của
Project, Classroom, Integration hay Progress Service để lấy ngữ cảnh trong lúc
xử lý yêu cầu.

Project Service là nguồn dữ liệu đúng cho project và task; Classroom Service
sở hữu lớp/nhóm; Integration Service sở hữu dữ liệu GitHub; Progress Service
sở hữu chỉ số đã tính. Bản sao AI có thể cũ do đồng bộ bất đồng bộ. Mỗi kết quả
cần lưu mốc thời gian và phiên bản dữ liệu đã dùng.

## Thay đổi nghiệp vụ và khả năng chịu lỗi

AI chỉ đưa ra gợi ý. Người dùng xác nhận; service sở hữu dữ liệu kiểm tra quyền
và thực hiện thay đổi. AI không ghi thẳng vào service hoặc database nghiệp vụ.

Khi AI hoặc nhà cung cấp LLM lỗi, chỉ tính năng AI tạm ngừng. Đăng nhập, lớp
học, project, task, tích hợp GitHub, dashboard tiến độ và notification chính
vẫn phải hoạt động.

## Sự kiện và dựng lại ngữ cảnh

Nhóm sự kiện ngữ cảnh mục tiêu gồm `group.member.added`,
`group.member.removed`, `project.*`, `sprint.*`, `task.*`, `github.*` và
`progress.*`. AI có thể phát kết quả như `ai.completed` nếu hợp đồng use case
được chốt. Các tên này chưa được xác nhận bằng schema trong `contracts/events/`.

Để dựng lại database ngữ cảnh, service nhận sự kiện cần nạp lại lịch sử sự kiện hoặc nhận
một ảnh chụp dữ liệu có phiên bản. Cách phát lại sự kiện, thời hạn lưu dữ liệu
và mục tiêu độ trễ hiện **cần quyết định**. Tài liệu này không khẳng định đã có
service nhận sự kiện hoặc quy trình dựng lại.

## Kiểm thử và vận hành

Kiểm thử bằng bộ dữ liệu mẫu được kiểm soát, gồm trường hợp thiếu, trùng và cũ;
không cần dữ liệu production. Kết quả nên có cấu trúc, căn cứ, loại phân tích
và phiên bản luật/mô hình khi đã có môi trường chạy. Cách quản lý chỉ dẫn cho
mô hình, nhà cung cấp, xác thực API và thời hạn lưu dữ liệu vẫn cần được xác
minh hoặc quyết định.

Không có API, service nhận sự kiện, sự kiện phát đi, công cụ, môi trường chạy mô hình hoặc
quy trình dựng lại nào được khẳng định là đã chạy trong tài liệu này.
