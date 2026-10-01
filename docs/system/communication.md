# Giao tiếp giữa các service

## Chọn REST hoặc Kafka

| Nhu cầu | Cách dùng | Ví dụ |
| --- | --- | --- |
| Cần phản hồi ngay trong yêu cầu hiện tại | REST API | Project Service kiểm tra group trước khi tạo project |
| Thông báo một việc đã xảy ra để service khác xử lý sau | Sự kiện Kafka | Classroom Service báo thành viên nhóm được thêm |

Không chuyển mọi trao đổi sang Kafka. Không tạo chuỗi request-response qua
Kafka cho truy vấn cần câu trả lời ngay.

## Quy tắc theo service

- Service gọi REST chỉ qua API được service sở hữu công bố; không truy cập
  database của service đó.
- Project Service có thể gọi Classroom Service để kiểm tra lớp hoặc nhóm khi
  cần quyết định đồng bộ.
- Integration Service sở hữu mọi lời gọi trực tiếp tới GitHub. Các service
  khác nhận dữ liệu GitHub đã chuẩn hóa qua API được công bố hoặc sự kiện Kafka.
- Progress Service nhận các sự kiện liên quan và tính chỉ số bằng quy tắc rõ
  ràng; không giao việc tính chỉ số cho AI.
- AI API nhận yêu cầu hoặc ý định người dùng. AI nhận ngữ cảnh nghiệp vụ qua
  Kafka và giữ bản đọc riêng. Agent không gọi REST hay database service khác
  trong lúc xử lý yêu cầu.
- Kết quả AI là đề xuất. Service sở hữu dữ liệu mới xác thực và áp dụng thay
  đổi sau khi có xác nhận của người dùng.

## Tin cậy và xử lý lặp

Service nhận sự kiện phải an toàn khi nhận lại cùng một sự kiện: cùng sự kiện được xử lý nhiều
lần không được làm trạng thái cuối sai. Hợp đồng nên có `event_id` và phiên bản
entity hoặc schema khi cần. Cách chống lặp cụ thể thuộc mã triển khai từng
service nhận sự kiện.

Sự kiện báo việc đã xảy ra, không phải yêu cầu đồng bộ đang chờ một service khác
trả lời.
