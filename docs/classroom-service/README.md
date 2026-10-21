# Classroom Service

Đối chiếu riêng ngày20/10/2026 cho đường Classroom→Identity: HTTP thật đã kiểm
JWKS/session-status, tạo lớp và phân công giáo viên, provisioning JSON từng dòng,
idempotency, enrich hồ sơ batch, quyền lớp, thu hồi phiên và dependency lỗi/khôi phục.
Kết quả local tại `artifacts/identity/classroom-integration/runtime.json`; bộ mặc định
Classroom308 ca đạt,17 E2E/external được loại theo cấu hình pytest. Không đồng nghĩa
đã nghiệm thu gateway/staging hoặc chạy lại toàn pipeline Classroom–Work.
Classroom chưa có endpoint resend public riêng; hợp đồng resend nội bộ hiện ở Identity.

**Trạng thái: Đã triển khai backend P0/P1 trong mã nguồn. Các số nghiệm thu local là snapshot từng lần chạy, xem
kết quả kiểm thử (bản local `backend-validation.md`).** Không gồm giao
diện, bước 8 của kế hoạch hoặc học vụ P2; không suy trạng thái staging từ local.
Lượt hiệu chỉnh mới nhất đạt 283 ca trong tiến trình cùng 26 workflow HTML
qua HTTP thật; kết quả 17 ca HTTP/Kafka E2E trước đó được giữ riêng như
snapshot. Công cụ HTML có 32 thao tác API công khai và hướng dẫn chạy tại
workflow API (bản local `api-workflows.md`).

Cụm local `utask` hiện có đã được cấu hình và giữ chạy với kết nối thật
Identity–Classroom–Work/Kafka; migration, chín nhóm kiểm tra HTTP/Kafka và sáu
mẫu HTML được chọn đều đạt. Xem bằng chứng của cụm đang dùng (bản local `backend-validation.md`);
các số 283/26 phía trên thuộc snapshot kiểm thử trước.

Các kế hoạch, báo cáo nghiệm thu và hướng dẫn workflow ghi là “bản local”
không thuộc checkout Git. Chúng là dấu vết từng lần chạy, không thay bằng
chứng runtime hoặc trạng thái staging hiện tại. Tài liệu API và mã nguồn
được liên kết trong các mục dưới là nguồn dùng khi review checkout sạch.

Theo [baseline](../architecture/README.md), mục 4.3, service dùng Python +
Django + DRF, sở hữu cả điểm danh, điểm số và liên kết nhóm–project.

Classroom Service quản lý môn học, lớp theo học kỳ, giảng viên, sinh viên, ghi
danh, nhóm, thành viên nhóm và liên kết dự án. Nhóm tự chọn đề tài và tạo dự
án tại Work; Classroom không giữ danh mục đề bài chung của giảng viên.

```text
Classroom: Teacher → Class → Group / GroupMember
                              │ GroupProjectLink: mã dự án do Work cấp
Work:                     Project / ProjectMember → Sprint → Task
```

Classroom sở hữu `GroupMember`; Work sở hữu `Project` và `ProjectMember`.
Giảng viên xem dự án qua quan hệ lớp → nhóm → dự án mà không cần được thêm
làm thành viên dự án. Mã lớp/nhóm/dự án giữa hai dịch vụ là tham chiếu logic,
không phải khóa ngoại xuyên cơ sở dữ liệu.

Thay đổi cần câu trả lời ngay có thể dùng REST. Thông báo việc lớp, nhóm hoặc
thành viên thay đổi đi qua Kafka. API và sự kiện cụ thể chỉ được ghi như đã có
sau khi đối chiếu hợp đồng API/sự kiện.

## Thiết kế chi tiết

Kế hoạch triển khai (bản local `implementation-plan.md`) đi từ khung dịch vụ, dữ liệu,
lớp/ghi danh/nhóm đến tích hợp Work–Kafka và Web; có vị trí mã, kiểm thử theo
từng bước và bảng truy vết toàn bộ sơ đồ.

Bộ sơ đồ tại [docs/diagram/classroom-service](../diagram/classroom-service/README.md)
phân tích phạm vi P0/P1/P2, actor/quyền, các luồng Classroom–Identity–Work và
ERD PostgreSQL mục tiêu. Các bản vẽ đã đồng bộ với nhóm tự chọn đề tài và nhiều
dự án hoạt động đồng thời, xem kế hoạch triển khai (bản local `implementation-plan.md`).
Phạm vi triển khai và kiểm tra thực tế được ghi riêng trong trang nghiệm thu.

Các quyết định chính:

- P0 tập trung môn học/lớp, ghi danh, nhóm và liên kết dự án. ERD mục tiêu có
  10 bảng, trong đó `GROUP_PROJECT_LINKS` lưu nhiều dự án của cùng nhóm; ERD
  đã nêu ma trận constraint, khóa ngoại cùng lớp và chỉ mục migration đầu tiên.
- Mã vào lớp/mã mời là chuỗi ngẫu nhiên; chỉ lưu HMAC-SHA-256 và giá trị đang
  dùng là duy nhất trong từng loại để một mã xác định đúng một lớp/nhóm.
- Quyền Teacher trên lớp cần đồng thời role `TEACHER` và phân công
  `ClassTeacher` đang `ACTIVE`; `PRIMARY` và `CO_TEACHER` có quyền ngang nhau.
  Hủy phân công làm mất quyền ngay, kể cả khi Work gọi scope nội bộ.
- Giảng viên phụ trách chủ động chốt nhóm. Sau khi chốt, Leader vẫn được loại
  thành viên thường; Giảng viên được phân/chuyển/loại trong đúng lớp với lý do,
  lịch sử, giới hạn tối đa và quy tắc giữ Trưởng nhóm.
- Admin hệ thống giữ các quyền đã chọn trong bảng quyền chuẩn.
  Phần bổ sung được chốt lần này gồm LH10 loại ghi danh người khác, LH13 chốt
  lập nhóm, LH15 điều chỉnh thành viên; NH01 xem mọi nhóm, NH02 tạo
  nhóm thay cho Leader được chỉ định, NH03/NH04/NH09/NH12 lần lượt xem chi tiết,
  sửa nhóm, loại thành viên và xem lịch sử. Với NH03, sinh viên chỉ xem nhóm
  đang là thành viên ACTIVE của chính mình. Các API NH05/NH07/NH10/NH11 không
  có nhánh Admin. Admin không vì thế có quyền đọc toàn bộ nội dung Work.
- Classroom gọi API Identity đã có để cấp/tìm tài khoản khi thêm danh sách sinh viên;
  không đọc hoặc ghi `identity_db`.
- Work lấy snapshot/scope cần phản hồi qua REST và nhận membership event qua
  Kafka sau commit; hai service không tạo foreign key xuyên database.
- Classroom không ghi liên kết mới khi lớp/nhóm đã đóng. Work không đồng bộ
  thành viên vào dự án đã lưu trữ/xóa.
- Web đọc và phân tích Excel thành danh sách; phía máy chủ Classroom chỉ nhận JSON
  tối đa 100 sinh viên/request qua API Identity hiện có, không nhận hoặc lưu
  tệp và không có trình đọc Excel.
- Attendance/Grade vẫn thuộc Classroom ở P2; chưa thiết kế bảng học vụ trong
  migration MVP vì yêu cầu loại quy trình này khỏi MVP.

**Đã triển khai trong mã nguồn:** liên kết dự án qua Kafka, adapter Classroom
thật và nhiều dự án hoạt động đồng thời mỗi nhóm. Work có migration bỏ
ràng buộc cũ. Không cần
`class_work_item_id` theo nghiệp vụ đã chốt. Phần việc Work và bằng chứng nằm tại
[ghi chú Work](../project-service/classroom-project-linking.md).
OpenAPI và schema sự kiện được sinh/tạo từ phần triển khai thật, kiểm thử và
khóa phiên bản trong bước tích hợp; không tạo hợp đồng giả trước mã nguồn.

## API backend và quyền

Nguồn mã tại [apps/classroom-service](../../apps/classroom-service/) có ba app
`courses`, `groups`, `messaging`. Mỗi miền tách models, serializers, queries,
services, views và urls. Bộ dùng chung copy/điều chỉnh từ Work theo bảng 2.1
của kế hoạch; không import Work ở runtime. Model/migration có 10 bảng, khóa
ngoại ghép bảo đảm thành viên, ghi danh và liên kết cùng lớp.

Gateway công khai duy nhất `/api/classroom/`, bỏ tiền tố trước khi proxy.
Các đường dưới đây là tài nguyên tương đối. Lệnh có chống lặp nhận
`Idempotency-Key` UUID; lệnh cập nhật kiểm phiên bản. Replay chỉ được xử lý
sau guard quyền hiện hành của chính thao tác đó; kiểm tra nghiệp vụ nào nằm
sau receipt có thể không chạy lại cho replay. Cùng khóa nhưng khác nội dung bị
từ chối; mã thô không có trong GET hoặc receipt. Thứ tự cụ thể xem
[luồng xử lý và replay](../diagram/classroom-service/sequence.md#3-quy-tắc-kỹ-thuật-chung-dành-cho-người-triển-khai).

| Nhóm API | Đường tài nguyên | Quyền |
| --- | --- | --- |
| Môn | `courses/`, `courses/{id}/`, `courses/{id}/archive/` | Đọc sau xác thực; Teacher tạo/sửa/ngừng dùng môn do mình tạo; Admin mọi môn |
| Lớp | `classes/`, `classes/{id}/` | Teacher tạo cho mình; Admin chỉ định Teacher đang hoạt động |
| Trạng thái/phân công | `classes/{id}/state/`, `lock-grouping/`, `teachers/assign/` | Teacher được phân công hoặc Admin theo các quyền đã chọn; Admin có các quyền trạng thái/phân công được đánh dấu trong bảng chuẩn, gồm LH13 |
| Giảng viên lớp | `classes/{id}/teachers/` | Sinh viên trong lớp đọc phân công ACTIVE; người quản lý được xem lịch sử |
| Mã lớp/ghi danh | `classes/{id}/join-code/`, `classes/join/`, `classes/{id}/students/`, `enrollments/` | Student dùng mã; Teacher đúng lớp hoặc Admin thêm sinh viên |
| Nhóm | `groups/`, `groups/{id}/`, `classes/{id}/groups/` | NH01 Admin xem mọi nhóm; NH02 Teacher/Admin tạo thay Leader đang ghi danh; NH03 Student chỉ xem nhóm mình đang là thành viên ACTIVE |
| Mã/thành viên | `groups/{id}/invite-code/`, `groups/join/`, `members/`, `leave/`, `remove-member/`, `transfer-leader/` | Admin không có quyền NH05/NH07/NH10; NH09 cho phép Admin loại thành viên |
| Điều chỉnh P1 | `classes/{id}/adjust-member/` | Teacher đang được phân công hoặc Admin; có lý do và xử lý kế nhiệm Leader |
| Liên kết | `groups/{id}/projects/` | Thành viên đúng nhóm hoặc giảng viên đúng lớp |
| Lịch sử | `classes/{id}/activities/`, `groups/{id}/activities/` | Giảng viên đúng lớp hoặc Admin; thành viên chỉ xem lịch sử đúng nhóm |

Chi tiết các lựa chọn đã duyệt và phần để lại nằm tại
bảng quyền ngày 18/10/2026. `PRIMARY` và `CO_TEACHER`
có quyền ngang nhau trong lớp; Admin chỉ có quyền được chọn cho từng thao tác.

[OpenAPI Classroom](../../contracts/api/classroom-service.yaml) được sinh từ
triển khai thật. Envelope giữ `success/message/data/meta/error`, thông báo
tiếng Việt. Danh sách lớp, giảng viên lớp, ghi danh, nhóm, thành viên, liên
kết và lịch sử có trang mặc định 20, tối đa 100; cursor gắn phạm vi/bộ lọc.
Danh mục Course sắp theo mã/ID, chưa phân trang do model không có trường thời gian.
`Course.created_by_id` là UUID tùy chọn, tham chiếu logic tới Identity và chỉ đọc
trên API. Teacher chỉ sửa/ngừng dùng môn mình tạo; Admin có thể quản lý mọi môn.
Môn cũ có `created_by_id=NULL` chỉ Admin được sửa/ngừng dùng.

Xác thực dùng JWT RS256/JWKS và kiểm phiên qua Identity. Vai trò toàn cục đọc
từ `/users/me` trong request; phân công hiện hành mới cấp quyền giảng viên
trên lớp. `/users/batch` bổ sung hồ sơ và xác minh `account_status` cùng `roles`
khi chọn giảng viên hoặc tạo nhóm thay sinh viên. Quyền giảng viên cần role
`TEACHER` hiện hành và phân công lớp `ACTIVE`; mất một trong hai điều kiện sẽ
mất quyền, kể cả API nội bộ cấp phạm vi giảng viên cho Work. Role Admin không
tự cấp quyền giảng viên hay quyền đọc dự án Work.

Thêm sinh viên nhận JSON `students` gồm 1–100 đối tượng. Receipt `PREPARED`
và khóa upstream ổn định được commit trước lời gọi Identity ngoài khóa dữ
liệu. Giao dịch cuối kiểm lại quyền/trạng thái lớp rồi lưu ghi danh, lịch sử
và kết quả từng phần tử. Timeout gửi lại cùng khóa/nội dung; không xóa bù tài
khoản. Chuẩn hóa email/mã sinh viên để đánh dấu trùng trước lời gọi Identity;
chỉ gửi danh sách duy nhất theo thứ tự ổn định và ghép kết quả về thứ tự gốc.
Phần tử trùng có `account_result=NOT_REQUESTED`, `reason=DUPLICATE_IN_LIST`.
Kết quả tài khoản và ghi danh cùng tổng kết tách riêng, không suy email đã giao.

Sinh viên đang ghi danh xem được phân công giảng viên hoạt động trong lớp;
lịch sử phân công đã rời chỉ cho người quản lý. Mất phân công làm mất quyền
giảng viên trên lớp; global role không tự cấp quyền đó. Quyền trong lớp được
đánh giá theo quan hệ hiện hành, không đồng nhất với danh mục global role.

## REST nội bộ và Kafka

Các đường `/internal/` gọi trực tiếp giữa backend. Nginx chặn cả
`/api/classroom/internal` và đường con, kể cả OPTIONS. Tất cả dùng
`X-Service-Key` Work; chỉ đường phục hồi không cần Bearer người dùng.

| Đường sau `/internal/` | Kết quả | Actor |
| --- | --- | --- |
| `GET groups/{id}/snapshot/` | Nhóm/lớp/phiên bản, trạng thái mới nhất mỗi người, đúng một Leader | Bearer |
| `GET groups/{id}/recovery-snapshot/` | Cùng ảnh chụp, phục vụ phục hồi thành viên | Credential dịch vụ |
| `GET teachers/groups/` | `group_ids` theo phân công hiện hành | Bearer |
| `POST groups/{id}/feedback-scope/` | actor/project/group/version/expiry; liên kết đúng dự án | Bearer |
| `GET groups/{id}/mention-scope/` | Người được nhắc tên trong phạm vi | Bearer |

Work phát `project.created`; Classroom ghi liên kết duy nhất theo `project_id`.
Nhận lặp đúng lớp/nhóm không ghi lịch sử trùng, khác lớp/nhóm là xung đột.
Classroom phát `classroom.group.membership.changed` một lần mỗi thay đổi nhóm;
Work áp dụng theo phiên bản/receipt riêng từng Project hoạt động. Giữ capacity,
assignment và đóng góp; Project lưu trữ/xóa không nhận thay đổi thành viên.

Đổi hoặc tắt mã mời cũng tăng `source_version` của nhóm để lệnh dùng phiên bản
cũ không ghi đè mã mới. Thao tác mã mời không phát sự kiện đổi thành viên; chỉ
thay đổi thành viên mới ghi ảnh chụp vào Outbox. Phản hồi cấp mã trả phiên bản
mới, còn gửi lại cùng khóa không cấp lại mã thô đã băm.

Publisher giữ `event_id`, gửi theo thứ tự lớp với partition key mã lớp, chỉ
đánh dấu sau ACK Kafka. Consumer chỉ commit offset sau commit DB hoặc DLQ
(topic sự kiện lỗi) được ACK. [Schema Work](../../contracts/events/work.project.created.v1.json)
và [schema Classroom](../../contracts/events/classroom.group.membership.changed.v1.json)
dùng envelope `data`, không đổi theo ví dụ `payload` trong baseline.

| Hướng | Topic mặc định | Nhóm đọc | DLQ |
| --- | --- | --- | --- |
| Work → Classroom | `utask.work.events` | `classroom-work-projects-v1` | `utask.classroom.work.dlq` |
| Classroom → Work | `utask.classroom.events` | `work-classroom-groups-v1` | `utask.work.classroom.dlq` |

Work giao task đọc bù sau tạo Project bằng credential dịch vụ, không lưu
Bearer; Beat quét dự án hoạt động mỗi 300 giây để bù crash/Redis lỗi sau
commit. Không thêm bảng job, không tạo Project để bù liên kết trễ.

## Cấu hình và chạy

Quyền ghi danh mục Course và hành vi của `created_by_id` được mô tả cùng bảng
quyền API ở mục [API backend và quyền](#api-backend-và-quyền).

Classroom nhận cấu hình theo pipeline `.env` → `infra/env/classroom-service.env`
→ Compose `env_file` → settings; xem [tài liệu biến môi trường](../infrastructure/environment.md).
Đặt `CLASSROOM_DJANGO_SECRET_KEY`, `CLASSROOM_ACCESS_CODE_HMAC_KEY`,
`IDENTITY_CLASSROOM_SERVICE_KEY` và `CLASSROOM_WORK_SERVICE_KEY`; caller
`classroom`/`work` trong `IDENTITY_SERVICE_KEYS` phải khớp khóa tương ứng.
Các khóa này không có secret mặc định. Celery Classroom dùng Redis DB3, Work DB2.

Quy trình local chuẩn, gồm một lệnh build/khởi động và các điều kiện đầu vào,
nằm tại [hướng dẫn chạy local](../infrastructure/local-development.md#khởi-động-identity-classroom-và-work).
Dockerfile của API chạy migration Django trong entrypoint trước Gunicorn; Docker
build không kết nối database. Worker dùng cùng image nhưng lệnh Celery/consumer
bỏ qua migration. Compose đợi API Classroom healthy trước khi chạy publisher,
Beat và consumer; worker Work cũng đợi API Work healthy. Work có một container
`work-consumer` chạy các nguồn event, không cần profile hồ sơ riêng.
Cấu hình và triển khai staging độc lập với luồng local.

Sau khi thay đổi biến môi trường, tạo lại container để nạp giá trị mới. Deploy
staging vẫn chạy migration tuần tự trước khi cập nhật runtime; entrypoint API
có thể chạy migration lần nữa, Django bỏ qua các migration đã áp dụng. Migration
đạt và container healthy chưa tự xác nhận tích hợp HTTP/Kafka; phạm vi và bằng
chứng kiểm tra hiện có được ghi tại nghiệm thu backend (bản local `backend-validation.md`)
và [Kafka](../infrastructure/kafka.md).

## Cấu trúc kiểm thử và CI

Công cụ HTML workflow API (bản local `api-workflows.md`) dùng lại bộ chạy của Work,
có request/assertion cho Classroom và gọi HTTP thật từ trình duyệt. Đây là
công cụ dành cho người phát triển, tách khỏi giao diện sản phẩm và các gate
pytest; trạng thái nghiệm thu được ghi riêng trong báo cáo backend.

Classroom dùng discovery và workflow Python hiện có: lint/format, kiểm
Django/migration, chạy `uv run pytest` cho bộ mặc định của service. `ci-result`
chặn release nếu kiểm tra được chọn lỗi; release giữ cơ chế build/push image
theo digest. Không thêm job phân tầng hoặc E2E dùng chung. Xem
[CI/CD](../infrastructure/ci-cd.md#classroom-dùng-nền-ci-chung).

Test trong service tách `tests/unit`, `tests/integration`, `tests/contract`.
Kiểm thử OpenAPI dùng schema sinh trực tiếp từ URLconf/serializer bằng
`SchemaGenerator`, cùng cách của Work. Không cần có tệp
`contracts/api/classroom-service.yaml` để chạy nhóm test OpenAPI; YAML xuất
từ code phục vụ chia sẻ và review hợp đồng.
E2E nằm riêng tại `tests/e2e`, chạy bằng image gunicorn/Nginx và PostgreSQL,
Kafka, Redis/Celery thật trong Docker project riêng; không dùng fixture giả
Identity hoặc container đang có của người phát triển. Bộ E2E chạy riêng khi
chủ động gọi pytest, không tự chạy trong CI hoặc `ci_local.py`.
JUnit/diagnostics nằm trong artifact từng lần chạy; số test đạt
không thay coverage hoặc bằng chứng staging.

Fixture Docker để Compose tự đọc `.env.example`, rồi nạp file chỉ chứa giá trị
test ghi đè; không tự phân tích hoặc bọc lại giá trị JSON của mẫu môi trường.
Stack riêng bật profile Kafka, dùng `work-consumer` chung và tạo đầy đủ topic
trước khi chờ các consumer healthy. Không dùng `.env` hoặc credential staging
cho bộ e2e này.

Các ca đồng bộ thành viên gọi helper publisher thật sau mutation để chủ động
phát outbox; fixture không chạy publisher/Beat Classroom tự động. Vì vậy bộ
này kiểm HTTP → outbox → Kafka → consumer, không chứng minh lịch chạy Beat.
