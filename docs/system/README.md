# Tài liệu hệ thống UTask

Thư mục này là nguồn chuẩn cho kiến trúc và cách các phần của UTask phối hợp.
Tài liệu ở đây mô tả **thiết kế mục tiêu**. Trạng thái triển khai trong mã
nguồn chưa được rà soát trong lần chuẩn hóa này; không dùng nội dung thiết kế
để kết luận một tính năng đã chạy.

## Đọc theo chủ đề

- [Kiến trúc và ranh giới service](architecture.md)
- [Các luồng nghiệp vụ](workflows.md)
- [Giao tiếp REST và Kafka](communication.md)
- [Quyền sở hữu dữ liệu](data-ownership.md)
- [Danh mục sự kiện Kafka](kafka-events.md)
- [Hướng dẫn phát triển](development.md)
- [Tài liệu theo service](../)
- [Hạ tầng](../infrastructure/README.md)

## Quy ước trạng thái

- **Đã triển khai**: đã xác minh trong mã nguồn và kiểm tra liên quan.
- **Một phần**: chỉ một phần phạm vi đã được xác minh.
- **Chưa triển khai**: đã kiểm tra và chưa có phần triển khai tương ứng.
- **Thiết kế mục tiêu**: quyết định kiến trúc hoặc hành vi dự kiến; không khẳng
  định mã nguồn đã có.
- **Chưa xác minh**: chưa kiểm tra mã nguồn, cấu hình và hợp đồng để kết luận.

Khi tài liệu cần nói về hiện trạng, người cập nhật phải kiểm tra mã nguồn, cấu
hình, hợp đồng và kiểm thử. Nếu chưa kiểm tra, dùng **Chưa xác minh**.
