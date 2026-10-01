# Identity Service

**Trạng thái tài liệu: Thiết kế mục tiêu; hiện trạng mã nguồn chưa xác minh.**

Identity Service sở hữu tài khoản, hồ sơ, vai trò toàn hệ thống, xác thực,
token và phiên/refresh token. Các service khác dùng `user_id` làm ID tham chiếu;
chúng không đọc Identity DB.

Service này không sở hữu lớp, nhóm, project, task, GitHub hay tiến độ. Các API
đăng ký, đăng nhập, đăng xuất, hồ sơ và quản lý token cần được mô tả theo
hợp đồng đã chốt; tài liệu này không khẳng định endpoint nào đã chạy.

Xem thêm: [kiến trúc](../system/architecture.md), [quyền sở hữu dữ liệu](../system/data-ownership.md).
