# Work Service — Hỗ trợ nhiều dự án của cùng nhóm

**Trạng thái: Đã triển khai phía backend, cập nhật 16/10/2026.**
Phạm vi đối chiếu gồm model/migration Project, tạo và đồng bộ thành viên,
adapter Classroom, consumer Kafka và tác vụ phục hồi của Work. Kết quả chạy
HTTP/Kafka kết hợp được ghi riêng trong nghiệm thu backend (bản local `backend-validation.md`).
Không bao gồm giao diện hoặc P2.

## 1. Nghiệp vụ đã chốt

Trưởng nhóm tự nhập tên đề tài, mô tả, mục tiêu và tạo dự án ở Work.
**Đã chốt: một nhóm được có nhiều dự án đang hoạt động đồng thời.**

- Work sở hữu dự án, đề tài cụ thể, thành viên dự án và công việc.
- Mỗi dự án gắn một nhóm đã được Classroom xác minh; nhiều dự án có thể cùng
  tham chiếu một `classroom_group_id` và cùng `class_id`.
- Không bổ sung quy trình giảng viên duyệt đề tài trong phạm vi đã chốt.

Thiết kế bảng, bộ nhận sự kiện và kế hoạch sửa sơ đồ Classroom nằm riêng tại
[ghi chú Classroom](../classroom-service/README.md#rest-nội-bộ-và-kafka).

Ranh giới theo [kiến trúc](../system/architecture.md) và
[quyền sở hữu dữ liệu](../system/data-ownership.md).

## 2. Work hiện đã có gì?

| Phần | Bằng chứng mã nguồn | Kết luận |
| --- | --- | --- |
| Nhận đề tài nhóm tự nhập | [CreateProjectSerializer](../../apps/work-service/apps/projects/serializers/projects.py) nhận tên, mô tả, mục tiêu, công nghệ, thời gian và `classroom_group_id` | Đã triển khai trong mã nguồn; không cần mã đề bài chung |
| Xác minh nhóm | [API tạo](../../apps/work-service/apps/projects/views/projects.py) lấy thông tin nhóm; [hàm tạo](../../apps/work-service/apps/projects/services/projects.py) kiểm đúng nhóm và Trưởng nhóm | Đã triển khai: `RemoteClassroom` gọi REST nội bộ bằng khóa dịch vụ và Bearer của người thực hiện |
| Xác định lớp | Hàm tạo lấy `class_id` từ thông tin nhóm đã xác minh | Không tin mã lớp do trình duyệt tự khai |
| Lưu dự án | Hàm tạo lưu Project, ProjectMember, State, lịch sử, Outbox và kết quả chống lặp trong cùng giao dịch | Đã triển khai trong mã nguồn |
| Thông báo tạo dự án | Hàm tạo lưu `project.created` với [ProjectSerializer](../../apps/work-service/apps/projects/serializers/projects.py); [Outbox](../../apps/work-service/apps/messaging/services/outbox.py) giữ sự kiện bền vững | Có dữ liệu mã dự án, mã nhóm và mã lớp; chưa chứng minh Classroom đã nhận |
| Nhiều dự án | [Model](../../apps/work-service/apps/projects/models.py) và [migration](../../apps/work-service/apps/projects/migrations/0002_multiple_group_projects.py) bỏ ràng buộc một dự án hoạt động mỗi nhóm; giữ `identifier` duy nhất | Nhiều dự án khác mã cùng nhóm được hoạt động; gửi lại cùng khóa/nội dung vẫn trả dự án cũ |

**Không cần thêm `class_work_item_id` vào Work theo nghiệp vụ này.** Yêu cầu
thêm trường đó trong bản thiết kế trước đã được thay thế bởi mục 1.

## 3. Cơ chế đã triển khai

Các cơ chế sau nằm trong mã Work:

1. Bỏ ràng buộc `uq_one_primary_project_per_group` bằng migration; dùng chỉ mục
   nhóm trên dự án hoạt động để tìm các dự án cần đồng bộ, giữ duy nhất `identifier`.
2. Phân biệt yêu cầu tạo dự án mới với yêu cầu gửi lại: khác khóa chống lặp và
   khác mã dự án được tạo cho cùng nhóm; cùng khóa/nội dung trả kết quả cũ.
   Không còn trả `GROUP_PROJECT_ALREADY_EXISTS` chỉ vì nhóm có dự án hoạt động.
3. Rà xử lý tạo, lưu trữ và mở lại dự án để nhiều dự án của cùng nhóm cùng hoạt
   động được; không tự chuyển trạng thái dự án khác của nhóm.
4. Khi nhận thay đổi thành viên nhóm, tìm các dự án liên quan theo mã nhóm và
   áp dụng theo phiên bản riêng của từng dự án **đang hoạt động**. Không đồng
   bộ dự án đã lưu trữ/xóa, không tự mở lại dự án và không làm mất phân công,
   giờ khả dụng hoặc lịch sử đóng góp.
5. Kiểm tra lại danh sách và quyền xem theo từng dự án; không dùng việc cùng
   nhóm để bỏ qua kiểm tra thành viên/trạng thái hiện hành.

## 4. Trách nhiệm giao tiếp của Work

- Xác minh lớp, nhóm, Trưởng nhóm và thành viên qua REST của Classroom trước
  khi tạo; `class_id` lấy từ dữ liệu đã xác minh.
- Lưu dự án, thành viên, lịch sử, Outbox và kết quả chống lặp trong cùng giao
  dịch. Work là nơi xác nhận dự án đã được tạo thành công.
- Phát `project.created` qua Kafka để bên nhận ghi liên kết. Sự kiện
  cần mã dự án, mã nhóm, mã lớp và thông tin nguồn/phiên bản theo hợp đồng đã
  chốt; không thêm mã đề bài chung.
- Không bổ sung bước gọi REST ngược về Classroom chỉ để ghi cùng liên kết.
  Lỗi hoặc độ trễ bên nhận không được làm Work tạo lại dự án đã tồn tại.
- Sau commit tạo Project, giao Celery task `recover_project_membership(project_id)`.
  Task gọi đường `recovery-snapshot/` bằng credential dịch vụ, không lưu Bearer.
  Beat chạy `recover_active_memberships` mỗi 300 giây để bù trường hợp crash hoặc
  Redis lỗi sau commit; quét Project hoạt động, không thêm bảng job/dispatcher.

Phát sự kiện tạo dự án đã có đường Outbox trong mã nguồn. OpenAPI và schema
sự kiện là đầu ra của bước triển khai tích hợp: tạo từ adapter/serializer và
producer/consumer thật, kiểm thử rồi khóa phiên bản; không tạo hợp đồng giả
trước mã nguồn. Kết quả chạy thật nằm tại trang nghiệm thu backend. Phần nhận sự kiện thuộc
[Classroom](../classroom-service/README.md#rest-nội-bộ-và-kafka).

## 5. Kiểm thử và hợp đồng

- Hai dự án khác mã được tạo và cùng hoạt động trên một nhóm, kể cả tạo đồng thời.
- Gửi lại cùng khóa/nội dung chỉ có một dự án, một kết quả và bộ sự kiện tương ứng.
- Cùng khóa nhưng khác nội dung vẫn bị từ chối; mã dự án trùng vẫn bị từ chối.
- Người không là Trưởng nhóm và kết quả xác minh sai nhóm vẫn bị từ chối.
- Mở lại dự án không xung đột chỉ vì cùng nhóm có dự án khác đang hoạt động.
- Thay đổi thành viên được áp dụng vào nhiều dự án đúng nhóm, đúng phiên bản;
  lỗi xử lý một dự án không làm mất cập nhật cho các dự án còn lại.
- Dự án đã lưu trữ/xóa không nhận thay đổi thành viên và không tự được mở lại.

Consumer tại [classroom_consumer.py](../../apps/work-service/apps/messaging/classroom_consumer.py)
giữ receipt theo từng dự án. Nhận lại sự kiện tiếp tục các dự án chưa xử lý;
chỉ commit offset sau lưu thành công hoặc DLQ được Kafka xác nhận. Consumer
chạy bằng `python manage.py consume_classroom`.

API được sinh tại [OpenAPI Work](../../contracts/api/work-service.yaml).
[Schema project.created](../../contracts/events/work.project.created.v1.json)
được sinh bằng `export_event_contract` đã khôi phục, từ serializer Project thực tế.
Topic mặc định `utask.work.events` và `utask.classroom.events`; cấu hình nhóm đọc,
thử lại và DLQ theo [hướng dẫn backend Classroom](../classroom-service/README.md).
