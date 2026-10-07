# Identity Service

**Trạng thái tài liệu: Thiết kế mục tiêu; hiện trạng mã nguồn chưa xác minh.**

Theo [baseline](<../architecture/UTask_Architecture_Technology_Baseline (1).md>),
mục 4.1 và 7, service dùng Python + Django + DRF, Django Authentication,
JWT access token và refresh token; không dùng Keycloak ở giai đoạn hiện tại.

Identity Service sở hữu tài khoản, hồ sơ, vai trò toàn hệ thống, xác thực,
token và phiên/refresh token. Các service khác dùng `user_id` làm ID tham chiếu;
chúng không đọc Identity DB.

Service này không sở hữu lớp, nhóm, project, task, GitHub hay tiến độ. Các API
đăng ký, đăng nhập, đăng xuất, hồ sơ và quản lý token cần được mô tả theo
hợp đồng đã chốt; tài liệu này không khẳng định endpoint nào đã chạy.

Phạm vi bao gồm password reset và OAuth mở rộng Google/GitHub nếu sản phẩm
cần; có thể dùng `django-allauth`, chưa khẳng định dependency đã được cài.
Mật khẩu dùng Django password hashing; login và endpoint nhạy cảm cần rate
limit. API phải dùng HTTPS ngoài môi trường local phù hợp.

Các service xác thực token nhưng không truy cập Identity DB. Phân quyền kết
hợp global RBAC (Admin, Teacher, User) với quyền trên tài nguyên/project
(Leader/Owner, Member). Identity cấp danh tính và vai trò toàn hệ thống;
service sở hữu tài nguyên kiểm tra membership và quyền nghiệp vụ ở backend.
Cơ chế key/token verification cụ thể cần hợp đồng xác thực, không suy ra từ
identity header bootstrap.

Xem thêm: [kiến trúc](../system/architecture.md), [quyền sở hữu dữ liệu](../system/data-ownership.md).
