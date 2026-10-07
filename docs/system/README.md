# Tài liệu hệ thống UTask

Đọc [architecture baseline](../architecture/README.md) trước để biết nguồn
quyết định công nghệ và phạm vi hệ thống. Thư mục này diễn giải các quyết định
đó theo chủ đề; tài liệu service/hạ tầng giữ chi tiết tương ứng.

Tài liệu kiến trúc mô tả **thiết kế mục tiêu**. Hiện trạng được ghi riêng khi
đã đối chiếu source, cấu hình và kiểm thử; không suy ra một tính năng đã chạy
từ baseline. AI Service hiện có bootstrap, xem [code map](../ai-service/code-map.md).

## Đọc theo chủ đề

- [Kiến trúc và ranh giới service](architecture.md)
- [Các luồng nghiệp vụ](workflows.md)
- [Giao tiếp REST và Kafka](communication.md)
- [Quyền sở hữu dữ liệu](data-ownership.md)
- [Danh mục sự kiện Kafka](kafka-events.md)
- [Hướng dẫn phát triển](development.md)
- [Identity Service](../identity-service/README.md)
- [Work Service](../project-service/README.md)
- [Classroom Service](../classroom-service/README.md)
- [Integration Service](../integration-service/README.md)
- [Notification Service](../notification-service/README.md)
- [AI Service](../ai-service/README.md)
- [Web](../web/README.md)
- [Hạ tầng](../infrastructure/README.md)
- [Job nền và worker](../infrastructure/background-jobs.md)
- [Quyết định kiến trúc](../adr/README.md)
- [Chuyển từ thiết kế cũ sang baseline](../adr/001-adopt-architecture-baseline.md)

## Quy ước trạng thái

- **Đã triển khai**: đã xác minh trong mã nguồn và kiểm tra liên quan.
- **Một phần**: chỉ một phần phạm vi đã được xác minh.
- **Chưa triển khai**: đã kiểm tra và chưa có phần triển khai tương ứng.
- **Thiết kế mục tiêu**: quyết định kiến trúc hoặc hành vi dự kiến; không khẳng
  định mã nguồn đã có.
- **Chưa xác minh**: chưa kiểm tra mã nguồn, cấu hình và hợp đồng để kết luận.

Khi tài liệu cần nói về hiện trạng, người cập nhật phải kiểm tra mã nguồn, cấu
hình, hợp đồng và kiểm thử. Nếu chưa kiểm tra, dùng **Chưa xác minh**.
