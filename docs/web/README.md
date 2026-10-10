# Web Application

**Trạng thái tài liệu: Một phần đã triển khai; xem [student-flow.md](student-flow.md)
cho hiện trạng chi tiết của luồng sinh viên.**

Web Application là giao diện cho người học, giảng viên và các vai trò được hệ
thống cho phép. Ứng dụng gọi API qua API Gateway; không truy cập database hoặc
gọi nhà cung cấp GitHub/LLM trực tiếp.

Các luồng giao diện mục tiêu gồm xác thực, lớp/nhóm, project, backlog, sprint,
task, kết nối GitHub, xem tiến độ, duyệt gợi ý AI và notification. Gợi ý AI chỉ
được áp dụng sau khi người dùng xác nhận qua API của service sở hữu dữ liệu.

API client, cấu trúc feature và thư viện giao diện cần được đối chiếu với hợp
đồng và ứng dụng trước khi mô tả là đã triển khai.

Xem thêm:

- [Luồng sinh viên (Student Flow)](student-flow.md) — hiện trạng từng màn
  hình, phần demo MSW so với phần chưa có backend.
- [Luồng giảng viên (Teacher Flow)](teacher-flow.md) — phạm vi, ma trận quyền,
  API readiness, kế hoạch và kết quả Phase 1: các màn đọc lớp (Home, danh sách
  lớp, tổng quan, sinh viên, nhóm) chạy trên dữ liệu Demo MSW; chưa có thao tác
  ghi, workspace Teacher hay backend. Giao diện theo thiết kế Stitch và màn Giám sát
  (tín hiệu theo quy tắc cố định): xem mục 14 của tài liệu này; dashboard nhóm và workspace chỉ xem cho giảng viên: mục 15; form tạo lớp, import CSV, nháp phản hồi, xem trước điều chỉnh nhóm và tín hiệu rủi ro (mức giao diện, chưa có hợp đồng ghi): mục 16.
- [Phân tích vai trò](utask-role-analysis.md) — nguồn nghiệp vụ về vai trò,
  ma trận quyền và user story.
- Hướng dẫn chạy ứng dụng và tài khoản demo: `apps/web/README.md`.