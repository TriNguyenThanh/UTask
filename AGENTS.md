# Quy tắc cho agent

## Nguồn tài liệu chuẩn

- Bắt đầu từ [tổng quan tài liệu](docs/system/README.md); đọc tài liệu hệ
  thống hoặc service liên quan trước khi thay đổi kiến trúc hay hợp đồng.
- Nội dung kiến trúc chuẩn nằm trong `docs/`. AGENTS chỉ giữ quy tắc làm việc,
  không sao chép tài liệu kiến trúc dài.
- Khi mô tả hiện trạng, kiểm tra mã nguồn, cấu hình, hợp đồng và kiểm thử.
  Dùng nhãn `Đã triển khai`, `Một phần`, `Chưa triển khai`, `Thiết kế mục tiêu`
  hoặc `Chưa xác minh` theo bằng chứng. Không suy luận mã đã triển khai từ
  thiết kế.

## Ranh giới kiến trúc

- Giữ ranh giới service và quyền sở hữu dữ liệu theo
  [kiến trúc hệ thống](docs/system/architecture.md) và
  [quyền sở hữu dữ liệu](docs/system/data-ownership.md).
- Không tạo khóa ngoại xuyên service, không đọc database service khác và không
  tạo service/công nghệ mới nếu chưa có quyết định kiến trúc.
- Dùng REST khi cần phản hồi ngay; dùng Kafka để thông báo sự kiện bất đồng bộ.
  Không biến Kafka thành request-response cho truy vấn đồng bộ.
- AI Service là service nội bộ. API AI nhận ý định người dùng; ngữ cảnh nghiệp
  vụ đi qua Kafka vào dữ liệu đọc riêng. AI không gọi REST hoặc database service
  khác để lấy ngữ cảnh, không sở hữu dữ liệu nghiệp vụ gốc và chỉ đề xuất thay
  đổi.
- Integration Service là service duy nhất gọi GitHub API.
- Progress Service tính chỉ số bằng công thức/quy tắc rõ ràng và không phụ
  thuộc AI.
- Project, Task, Sprint và Comment cùng thuộc Project Service. Classroom
  Service sở hữu Group/GroupMember; Project Service sở hữu Project/
  ProjectMember.

## Tài liệu và hợp đồng

- Tài liệu cho đội phát triển viết bằng tiếng Việt dễ hiểu. Giữ tên kỹ thuật
  cần thiết và giải thích thuật ngữ khó ở lần đầu.
- Không mô tả tính năng, API, sự kiện hoặc luồng mục tiêu như đã chạy. Đặt tài
  liệu chuẩn theo service trong `docs/`; README cạnh app chỉ trỏ tới tài liệu
  đó.
- Khi hành vi thay đổi, cập nhật tài liệu, hợp đồng API/sự kiện và kiểm thử bị
  ảnh hưởng. Không tạo schema giả để lấp đầy `contracts/`.
- Cập nhật link sau khi di chuyển hoặc xóa tài liệu; không giữ hai nguồn chuẩn
  cho cùng một chủ đề.

## Kỹ năng

Chỉ dùng skill phù hợp với công việc; không nạp toàn bộ skill nếu công việc không cần.

- `django-expert`: Django, DRF, ORM, migration, API và kiểm thử Django.
- `supabase-postgres-best-practices`: thiết kế, truy vấn, migration và bảo mật
  PostgreSQL. Áp dụng hướng dẫn PostgreSQL chung, bỏ qua nội dung chỉ dành cho
  dịch vụ Supabase nếu dự án không dùng tính năng đó.
- `vercel-react-best-practices`: hiệu năng React và tải dữ liệu phía client.
  Bỏ qua hướng dẫn Next.js/server khi thay đổi ứng dụng Vite phía client.
- `vercel-composition-patterns`: thiết kế component và cách ghép component trong React.

Không sao chép kiến trúc UTask vào skill. Skill chỉ bổ sung hướng dẫn chuyên
môn có ích cho loại công việc tương ứng.

## Hoàn tất công việc

Chạy formatter, lint, kiểm thử và build phù hợp với thay đổi trước khi báo hoàn
thành. Với thay đổi tài liệu, kiểm tra link nội bộ, tham chiếu cũ và file rỗng
liên quan. Báo rõ những gì đã kiểm tra và phần chưa xác minh.
