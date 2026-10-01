# Web Application

**Trạng thái tài liệu: Thiết kế mục tiêu; hiện trạng triển khai chưa xác minh.**

Web Application là giao diện cho người học, giảng viên và các vai trò được hệ
thống cho phép. Ứng dụng gọi API qua API Gateway; không truy cập database hoặc
gọi nhà cung cấp GitHub/LLM trực tiếp.

Các luồng giao diện mục tiêu gồm xác thực, lớp/nhóm, project, backlog, sprint,
task, kết nối GitHub, xem tiến độ, duyệt gợi ý AI và notification. Gợi ý AI chỉ
được áp dụng sau khi người dùng xác nhận qua API của service sở hữu dữ liệu.

API client, cấu trúc feature và thư viện giao diện cần được đối chiếu với hợp
đồng và ứng dụng trước khi mô tả là đã triển khai.
