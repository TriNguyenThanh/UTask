# Tiến độ — chuyển về Work Service

**Trạng thái: Thiết kế cũ đã được thay thế.** Baseline mục 4.2 đặt Task Progress
và Project Progress trong Work Service, không có Progress Service riêng ở
giai đoạn đầu. Giữ trang này làm điểm chuyển hướng cho liên kết cũ.

Nguồn chuẩn hiện tại: [Work Service](../project-service/README.md) và
[quyền sở hữu dữ liệu](../system/data-ownership.md). Tiến độ tính bằng công
thức/quy tắc và không phụ thuộc AI. Không tạo `progress_db` hoặc process
Progress riêng từ tài liệu cũ.

Contract context cũ có producer `progress-service`; đó là khoảng trống chuyển
đổi, không xác nhận runtime. Xem [danh mục sự kiện](../system/kafka-events.md)
và [ADR cập nhật baseline](../adr/001-adopt-architecture-baseline.md).
