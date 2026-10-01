# Hướng dẫn phát triển

## Trước khi thay đổi

1. Đọc tài liệu service liên quan và [quy tắc agent](../../AGENTS.md).
2. Khi công việc đụng tới hiện trạng, kiểm tra mã nguồn, cấu hình, hợp đồng và
   kiểm thử trước khi cập nhật trạng thái tài liệu.
3. Giữ quyền sở hữu dữ liệu theo service. Không tạo khóa ngoại hoặc truy cập
   database xuyên service.
4. Chỉ thêm service hoặc công nghệ mới khi có quyết định kiến trúc được ghi
   nhận.

## Khi thay đổi hành vi

Cập nhật hợp đồng API/sự kiện và tài liệu service bị ảnh hưởng cùng với thay đổi.
Mô tả rõ lỗi, quyền truy cập, xử lý lặp và ảnh hưởng tới các service nhận sự kiện khi phù
hợp. Không viết đường dẫn API, sự kiện hay luồng thiết kế như thể đã chạy.

## Khi cập nhật tài liệu

- Tài liệu cho đội phát triển dùng tiếng Việt rõ ràng; giữ nguyên tên kỹ thuật
  cần thiết và giải thích thuật ngữ khó ở lần đầu.
- Mỗi chủ đề có một tài liệu chuẩn. README ở app chỉ dẫn tới tài liệu trong
  `docs/`.
- Gắn nhãn `Thiết kế mục tiêu`, `Chưa xác minh`, `Đã triển khai`, `Một phần`
  hoặc `Chưa triển khai` đúng với bằng chứng đã kiểm tra.
- Cập nhật link sau khi di chuyển hoặc xóa tài liệu.

## Kiểm tra trước khi báo hoàn thành

Chạy formatter, lint, kiểm thử và build phù hợp với thay đổi. Với thay đổi tài
liệu, kiểm tra link nội bộ, tham chiếu tên cũ và file rỗng liên quan. Nêu rõ
những gì đã kiểm tra và chưa kiểm tra.
