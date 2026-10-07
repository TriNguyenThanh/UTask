# Chuẩn hóa source AI Service

## Mục tiêu và hiện trạng

Bootstrap đang có 8 test pass. `api.py` gom route, dependency, middleware và
exception handler; `models.py` gom request, result và response. Hàm application
vừa điều phối vừa dựng response nên khó đọc luồng chính.

## Phạm vi và tác động

- Chuyển `api.py` thành package `api/` với từng trách nhiệm riêng.
- Chuyển `models.py` thành package `models/`; giữ tên model và import public
  qua `models/__init__.py` để các module sử dụng không phải đổi tên.
- Tách bước dựng response khỏi `AiApplicationService.create_request`.
- Làm gọn timeout wrapper và khai báo kiểu của test doubles.
- Cập nhật code map và task log trong scope AI Service.

GitNexus: tác động của `models.py` là MEDIUM (5 module import trực tiếp);
`api.py`, application, app factory và workflow là LOW. Test fixture được
Pytest gọi động nên graph báo UNKNOWN; đã kiểm tra source/test sử dụng fixture.

## Tiêu chí hoàn thành

Giữ nguyên route, JSON schema, status code, idempotency và ownership lookup.
Chạy lại các test cũ và thêm test replay success/failure, timeout, ownership,
validation theo intent và middleware. So sánh fingerprint OpenAPI/Pydantic trước
và sau; chạy Ruff, Pytest, build Docker và smoke test container. Kiểm tra link,
đường dẫn cũ và cập nhật index/detect_changes sau refactor.

Auth gateway, queue, provider thật, Kafka và DB vẫn thuộc các task triển khai
tiếp theo; thay đổi này chỉ tổ chức lại bootstrap hiện có.

## Kết quả thực hiện

Đã hoàn thành tách module và giữ public model imports. 39 test, Ruff,
locked dependency sync, Docker build và container smoke đều pass. Fingerprint
OpenAPI/request/response không đổi. Link nội bộ và file rỗng đã kiểm tra.

Index GitNexus đã cập nhật theo source mới. `detect_changes` chỉ bao phủ diff
tracked (tài liệu), chưa bao phủ source untracked; xem test và fingerprint
contract để biết phạm vi kiểm chứng hành vi. Chi tiết nằm trong `TASKS.md`.
