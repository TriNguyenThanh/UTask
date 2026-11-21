# Tài liệu hệ thống UTask

Thư mục `system/` tập hợp tài liệu dùng chung cho nhiều service: kiến trúc nền,
ranh giới và quyền sở hữu dữ liệu, giao tiếp, vận hành hạ tầng, quy trình phát
triển và quyết định kiến trúc. Tài liệu mô tả thiết kế mục tiêu khi chưa có bằng
chứng triển khai; hiện trạng phải được đối chiếu với source, cấu hình, hợp đồng
và kiểm thử.

## Nội dung dùng chung

- [Architecture baseline](architecture-baseline.md): quyết định công nghệ và phạm vi mục tiêu.
- [Kiến trúc và ranh giới service](architecture.md).
- [Quyền sở hữu dữ liệu](data-ownership.md).
- [Nghiệp vụ và quyền](business-and-permissions.md).
- [Các luồng nghiệp vụ](workflows.md).
- [Giao tiếp REST và Kafka](communication.md) và [danh mục sự kiện](kafka-events.md).
- [Hạ tầng và phát triển local](infrastructure/README.md): môi trường, Kafka, Redis, job nền, lưu trữ và CI/CD.
- [Hướng dẫn phát triển](development.md) và [thiết lập subagent Codex](subagents.md).
- [Quyết định kiến trúc (ADR)](adr/README.md).

## Tài liệu theo service

- [Identity](../identity-service/README.md) · [Classroom](../classroom-service/README.md) · [Work](../project-service/README.md)
- [Integration](../integration-service/README.md) · [Notification](../notification-service/README.md)
- [AI](../ai-service/README.md) · [Web](../web/README.md)

Progress Service là tài liệu cũ đã chuyển về Work; xem [trang chuyển hướng](../progress-service/README.md).

## Quy ước trạng thái

- **Đã triển khai**: đã xác minh trong mã nguồn và kiểm tra liên quan.
- **Một phần**: chỉ một phần phạm vi đã được xác minh.
- **Chưa triển khai**: đã kiểm tra và chưa có phần triển khai tương ứng.
- **Thiết kế mục tiêu**: quyết định kiến trúc hoặc hành vi dự kiến; không khẳng định mã nguồn đã có.
- **Chưa xác minh**: chưa kiểm tra mã nguồn, cấu hình và hợp đồng để kết luận.

Khi tài liệu cần nói về hiện trạng, phải kiểm tra mã nguồn, cấu hình, hợp đồng
và kiểm thử. Nếu chưa kiểm tra, dùng **Chưa xác minh**.
