# Architecture baseline

**Trạng thái: Thiết kế mục tiêu.** Nguồn baseline được người dùng cung cấp là
[UTask – Architecture & Technology Baseline](<UTask_Architecture_Technology_Baseline (1).md>).
Giữ nguyên bản này để truy nguyên quyết định; không dùng nó làm bằng chứng
rằng công nghệ, endpoint hoặc worker đã chạy.

## Cách sử dụng

- Baseline xác định ranh giới nghiệp vụ, công nghệ nền và nguyên tắc vận hành.
- [Tổng quan hệ thống](../system/README.md) điều hướng tới tài liệu chi tiết
  được cập nhật theo baseline; không tạo bản sao toàn bộ baseline.
- `contracts/` giữ hợp đồng máy đọc được. Ví dụ URL/event trong baseline không
  tự thay thế một hợp đồng đã chốt; thay đổi không tương thích phải có version
  hoặc quy tắc chuyển đổi.
- [ADR](../adr/README.md) ghi quyết định giải quyết khác biệt và thiết kế mới.
- Hiện trạng được kiểm tra riêng trong source, cấu hình và kiểm thử, chẳng hạn
  [code map AI Service](../ai-service/code-map.md).

Việc thay ranh giới Project/Progress và cách lấy context AI được ghi trong
[ADR-001](../adr/001-adopt-architecture-baseline.md).

## Những điểm baseline chưa quy định

Baseline chọn Celery + Redis cho job nội bộ và Kafka cho sự kiện giữa service.
Nó chưa quy định worker AI là singleton, số process/container, ngưỡng trả
`202`, cơ chế polling/SSE hay schema event kết quả AI. Không coi phương án
thảo luận là quyết định baseline nếu chưa ghi vào tài liệu hoặc hợp đồng.

Baseline có cả ví dụ route theo service (`/api/work/*`) và URL version
(`/api/v1/...`). Prefix cụ thể và rewrite tại Nginx cần đối chiếu contract
từng service; không suy ra endpoint production từ những ví dụ này.
