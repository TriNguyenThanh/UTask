# Classroom Service — Hướng dẫn đọc bộ sơ đồ

**Trạng thái: Thiết kế mục tiêu**, cập nhật 15/10/2026. Bộ sơ đồ đã đồng bộ với
nghiệp vụ nhóm tự chọn đề tài và nhiều dự án đồng thời. Backend hiện có mã
nguồn/migration; kết quả nghiệm thu được ghi tại
backend Classroom (bản local `backend-validation.md`), tách khỏi hình thiết kế.

**Nghiệp vụ đã chốt:** Giảng viên tạo lớp → Sinh viên vào lớp, lập nhóm và tự
chọn đề tài → Trưởng nhóm tạo dự án ở Work → Giảng viên theo dõi dự án của lớp.

**Quyết định chính:** mỗi nhóm có nhiều dự án hoạt động đồng thời. Classroom
lưu `GROUP_PROJECT_LINKS`; đề tài, thời hạn và công việc nằm ở Work. Chi tiết
điều chỉnh và phần triển khai còn thiếu tại [ghi chú Classroom](../../classroom-service/README.md#rest-nội-bộ-và-kafka).

Đọc theo thứ tự:

1. [BFD](bfd.md): lớp học cần những chức năng nào? Có ví dụ cô Lan, An và Nhóm A.
2. [Quyền sử dụng](usecase.md): ai được tạo lớp, vào nhóm, loại người hoặc chuyển quyền?
3. [Trình tự xử lý](sequence.md): một yêu cầu được thực hiện qua những bước nào?
4. [Dữ liệu](erd.md): cần lưu những thông tin gì để làm được các việc trên?

Đọc trực tiếp các nguồn Markdown ở trên. HTML, assets và generator là công
cụ local bị ignore, không có trong checkout Git; chúng không phải điều kiện
để đọc hoặc kiểm tra nguồn sơ đồ.

Trong hình dùng tên tiếng Việt: Hệ thống lớp học = Classroom; Hệ thống tài khoản
= Identity; Hệ thống công việc = Work. Mã UC/SQ dùng để tra cứu giữa các tệp.

## 1. Căn cứ và phạm vi

Đọc [baseline](../../architecture/UTask_Architecture_Technology_Baseline%20%281%29.md)
mục 4.3, 8–11, 17 và 29; [ADR-001](../../adr/001-adopt-architecture-baseline.md),
[ownership](../../system/data-ownership.md), [giao tiếp](../../system/communication.md)
và yêu cầu (đầu vào local `UTask - Phân tích thiết kế yêu cầu.md`)
US-1.2–1.4, US-2.1–2.5, US-4.4 và mục 8.

| Phạm vi | Cần làm |
| --- | --- |
| P0 | Môn học/lớp; quyền giảng viên; mã lớp; ghi danh; thêm một hoặc nhiều sinh viên bằng JSON; giao diện đọc Excel và cho xem trước; tạo/tham gia nhóm; mã mời, loại thành viên/chuyển Trưởng nhóm; Giảng viên chốt nhóm; xác minh nhóm/quyền cho Work; sự kiện đổi thành viên qua Kafka; liên kết dự án do nhóm tự chọn đề tài |
| P1 | Giảng viên phân/chuyển/loại sinh viên, kể cả sau khi chốt nhóm; xử lý nhóm ngoại lệ và xác minh quyền nhận xét/nhắc tên |
| P2 | Điểm danh/điểm số vẫn thuộc Classroom; thiết kế bảng khi triển khai học vụ, theo yêu cầu mục 8.3/8.5 |

Chuyển Trưởng nhóm là P0; Giảng viên đúng lớp cũng có quyền chuyển theo yêu
cầu mục 1.2. Phân/chuyển nhóm ngoại lệ thuộc P1 theo US-2.5. Đọc Excel và xem
trước thuộc Web; phía máy chủ Classroom chỉ nhận danh sách đã có cấu trúc.

MVP giữ mỗi sinh viên tối đa một nhóm đang hoạt động trong lớp và một mã
mời hiện hành mỗi nhóm. Một lớp có nhiều dự án thông qua các nhóm. **Đã triển
khai backend cho nhiều dự án hoạt động đồng thời mỗi nhóm**; thay đổi Work tại
[ghi chú Work](../../work-service/classroom-project-linking.md). Lời mời
riêng từng người và đổi liên kết dự án không nằm trong lát đầu.

## 2. Các quyết định giữ thiết kế đơn giản

| Phần | Cách làm | Đánh đổi |
| --- | --- | --- |
| Dữ liệu | 10 bảng: 7 nghiệp vụ và 3 hỗ trợ; điểm danh/điểm số ở giai đoạn sau | Chưa bao phủ toàn bộ quản lý học vụ |
| Đề tài | Nhóm tự nhập đề tài ở Work; Classroom chỉ lưu liên kết | Cần tích hợp với Work để đọc nội dung dự án |
| Nhiều dự án mỗi nhóm | `GROUP_PROJECT_LINKS` có mã dự án duy nhất, mã nhóm không duy nhất | Work phải bỏ giới hạn cũ khi triển khai |
| Thêm danh sách | Web đọc Excel; Classroom nhận JSON tối đa 100 phần tử | Danh sách lớn cần chia lô có khóa riêng |
| Mã vào lớp/mã mời | Mã ngẫu nhiên, chỉ lưu HMAC-SHA-256; giá trị đang dùng là duy nhất trong từng loại; không có bảng lời mời riêng | Chưa có lời mời riêng cho từng người |
| Hồ sơ hiển thị | Lấy tên/ảnh theo danh sách tài khoản của trang hiện tại | Chưa có bản sao hồ sơ riêng trong Classroom |
| Danh sách | Copy bộ phân trang cursor của Work, đổi salt/phạm vi cho Classroom; lọc quyền trước tìm kiếm | Trang sâu ổn định theo thời gian và mã dòng; chỉ tối ưu thêm khi có số đo |
| Đồng bộ thành viên | Gửi đầy đủ danh sách và phiên bản nhóm sau mỗi thay đổi | Lớn hơn sự kiện chỉ chứa phần thay đổi nhưng xử lý thiếu sự kiện đơn giản hơn |

Giao tiếp tối thiểu được chốt theo baseline, không biến Kafka thành RPC:

| Khi nào | Cơ chế | Luồng Classroom P0 |
| --- | --- | --- |
| Cần kết quả ngay để tiếp tục yêu cầu | REST | Classroom gọi Identity cấp/tìm tài khoản; Work hỏi thông tin nhóm và quyền giảng viên |
| Thông báo thay đổi đã lưu thành công | Kafka qua Outbox | Classroom phát danh sách thành viên; Classroom nhận `project.created` để ghi liên kết, xử lý lặp an toàn |
| Công việc nền nội bộ service | Celery + Redis | Publisher retry Outbox; không dùng để đọc Excel hoặc thêm danh sách tối đa 100 phần tử |

Kafka gửi sự kiện đã lưu; REST trả lời yêu cầu xác minh trực tiếp. Outbox là
bảng sự kiện chờ gửi, được lưu cùng thay đổi nghiệp vụ trong một giao dịch.

Số bảng chỉ là kết quả của phạm vi, không phải tiêu chí chất lượng. Các bảo đảm
cần giữ: lớp/nhóm đúng phạm vi, ghi danh không trùng, nhóm không vượt giới hạn,
đúng một Trưởng nhóm hoạt động, một dự án chỉ liên kết đúng một lớp/nhóm, lịch
sử và thông báo chờ gửi lưu cùng thay đổi nghiệp vụ. Bản ghi chống lặp bảo vệ
các thao tác có thể gửi lại. Mã đang dùng xác định đúng một lớp/nhóm. Dùng cơ
chế có sẵn của Django/PostgreSQL; ma trận constraint/index nằm trong [ERD](erd.md#3-đặc-tả-ràng-buộc-để-tạo-migration).

## 3. Thư viện thực sự giúp giảm công triển khai

Tra tài liệu chính thức ngày 15/10/2026; đây là đánh giá kỹ thuật theo luồng
Classroom, chưa phải benchmark tốc độ hay cam kết số ngày hoàn thành.

| Lựa chọn | Phần được thư viện làm sẵn | Điểm phải tự làm / đánh đổi | Quyết định |
| --- | --- | --- | --- |
| Django 5.2 + DRF | ORM/migration, serializer, generic list/detail, pagination | Scope queryset và quyền create/command, rule nhóm | Dùng stack hiện có, `ListAPIView`/`RetrieveAPIView`; command qua `GenericAPIView` |
| `django-filter` | DRF FilterSet/backend | Chỉ allowlist status/course/class; quyền lọc trước filter | Dùng |
| `drf-spectacular` | OpenAPI từ serializer/URLconf, annotation response | Validate schema và error contract | Dùng baseline, không viết spec thủ công song song |
| `PyJWT[crypto]` + `requests` | Verify chữ ký RS256, gọi JWKS/session-status | Check issuer/audience/session, timeout, lỗi dependency | Tái sử dụng cách Work đã làm; không dựng auth/OAuth Classroom |
| DRF `ListField` + bộ kiểm tra phần tử | Kiểm mảng JSON, số lượng và lỗi theo từng sinh viên | Vẫn phải tự kiểm quyền lớp, dữ liệu trùng, bản ghi chống lặp và ghi danh | Dùng ở Classroom; không viết trình đọc Excel phía máy chủ |
| Trình đọc Excel phía Web | Đọc tệp, kiểm tra cột và tạo bản xem trước trước khi gọi API | Web hiện mới đọc CSV và từ chối Excel; cần chọn/thêm thư viện ở phạm vi Web | Trách nhiệm của Web; **Chưa triển khai** khả năng Excel |
| `confluent-kafka` | Kafka producer/consumer, delivery callback | DB outbox, version, schema, retry; broker ACK không đồng nghĩa consumer đã apply | Dùng baseline, tham khảo publisher Work |
| Celery + Redis | Chạy job/publisher nội bộ, retry | Không atomic DB/broker; cần retry từ Outbox còn pending | Dùng cho publisher; **không thêm job nhập tệp P0** |
| `django-guardian`, FSM/audit package | Permission object/lịch sử/transition tổng quát | Thêm model/convention; không thay rule nhóm hoặc transactional outbox | Chưa cần; `BasePermission`, `TextChoices`, Activity đơn giản đủ |

Căn cứ đọc được:

- [DRF generic views](https://www.django-rest-framework.org/api-guide/generic-views/)
  cung cấp list/detail/mixin. [DRF permissions](https://www.django-rest-framework.org/api-guide/permissions/)
  nhắc rằng object permission không tự lọc list hoặc bảo vệ create; phải kiểm scope.
- [django-filter DRF](https://django-filter.readthedocs.io/en/stable/guide/rest_framework.html)
  và [drf-spectacular](https://drf-spectacular.readthedocs.io/en/latest/customization.html)
  giảm code filter/schema; không sinh permission domain.
- [Identity serializer](../../../apps/identity-service/accounts/serializers/provisioning.py)
  đã dùng `ListField` giới hạn 1–100 phần tử. Classroom nên dùng cùng hình dạng
  danh sách ở boundary nội bộ thay vì chuyển tệp giữa các backend.
- [Web parser hiện tại](../../../apps/web/src/features/teacher/lib/csvImport.ts)
  mới đọc CSV và trả lỗi rõ ràng cho Excel. Đây là bằng chứng Web Excel còn thiếu,
  không phải lý do đưa `openpyxl` hoặc trình đọc tệp vào phía máy chủ Classroom.
- [Confluent producer](https://docs.confluent.io/platform/current/clients/confluent-kafka-python/html/index.html)
  có delivery callback qua poll/flush; chỉ callback thành công mới mark Outbox.
  [Celery Django](https://docs.celeryq.dev/en/stable/django/first-steps-with-django.html)
  có `delay_on_commit`; vẫn giữ pending Outbox làm nguồn retry bền vững.

Chốt dependency từ dải version đang dùng trong
[Work pyproject](../../../apps/work-service/pyproject.toml), pin bằng `uv.lock`
và test compatibility. Không lấy số version trang docs `latest` làm version
đã kiểm với UTask; chưa cài thư viện backend hoặc triển khai runtime trong lượt này.

## 4. Dùng lại code hiện có đến đâu

| Phần | Bằng chứng source | Cách tận dụng |
| --- | --- | --- |
| Identity provisioning | [URLconf](../../../apps/identity-service/accounts/urls.py), [serializer ≤100](../../../apps/identity-service/accounts/serializers/provisioning.py), [service/receipt/per-row result](../../../apps/identity-service/accounts/services/provisioning.py), [tests](../../../apps/identity-service/tests/test_provisioning.py) | Gọi endpoint hiện có; Identity tạo Student pending và activation, Classroom chỉ tạo enrollment |
| Profile batch | [BatchUsersView](../../../apps/identity-service/accounts/views/profiles.py) | `POST /users/batch` một lần cho UUID của một trang; hồ sơ không cấp quyền lớp |
| Group snapshot | [GroupSnapshot](../../../apps/work-service/infrastructure/classroom.py), [membership sync](../../../apps/work-service/apps/projects/services/membership.py) | Cấp đúng group/class/version/members, UUID user unique, đúng một Leader active |
| Teacher feedback P1 | [VerifiedFeedbackScope](../../../apps/work-service/infrastructure/collaboration_scope.py) | Trả facts actor/project/group/version/expiry; Work adapter dựng dataclass, không thêm dịch vụ ký token |
| Kafka/receipt | [Work messaging](../../../apps/work-service/apps/messaging/models.py) | Tái sử dụng ý tưởng và test pattern có chọn lọc trong package Classroom; không import model/DB Work |

**Đã triển khai backend** Identity–Classroom–Work trong phạm vi kế hoạch P0/P1.
Kiểm thử HTTP/Kafka thật và giới hạn xác minh tại trang nghiệm thu. Giao diện
và P2 ngoài phạm vi lần triển khai này; không suy kiểm thử fixture thành E2E.

[Migration Work](../../../apps/work-service/apps/projects/migrations/0002_multiple_group_projects.py)
bỏ ràng buộc `uq_one_primary_project_per_group`. [Ghi chú Work](../../work-service/classroom-project-linking.md)
ghi cơ chế nhiều dự án, consumer theo từng dự án và tác vụ đọc bù.

## 5. Cấu trúc và thứ tự triển khai

Kế hoạch triển khai đầy đủ (bản local `implementation-plan.md`)
ghi vị trí mã theo cấu trúc Identity/Work hiện có, thứ tự thực hiện, kiểm thử
cùng từng luồng và bảng truy vết 16 Use Case, 9 Sequence sang đầu việc.

```text
apps/classroom-service/
├── config/                # settings, urls, celery, wsgi
├── apps/
│   ├── courses/           # Course, ClassSection, ClassTeacher, Enrollment
│   ├── groups/            # StudyGroup, GroupMember, GroupProjectLink, snapshot/scope
│   └── messaging/         # Activity, OutboxEvent, IdempotencyRecord
├── common/                # auth, response/error, strict serializers
├── infrastructure/        # Identity HTTP, Kafka client
└── tests/
```

Mỗi app có models/serializers/views/urls/services/queries khi cần. Không thêm
repository interface, unit-of-work abstraction, shared domain package hoặc
plugin system cho các command CRUD nhỏ.

1. Class/enrollment: auth Identity, Course/lớp/Teacher, thời gian học kỳ,
   join-code và list/detail có scope; test đúng lớp + khác lớp.
2. Thêm danh sách: nhận JSON ≤100 sinh viên → kiểm từng phần tử → Identity →
   enrollment/receipt với kết quả từng phần tử. Test danh sách rỗng/quá giới
   hạn, dữ liệu trùng, lỗi riêng từng phần tử và gửi lại; không kiểm thử trình đọc Excel ở phía máy chủ.
3. Group: create/join/rotate/remove/transfer/lock; constraint và row lock cùng
   lớp. Test hai request join slot cuối, Leader cuối không được rời và quyền
   thay đổi sau khi Giảng viên chốt nhóm.
4. Liên kết Work + Kafka: xác minh nhóm/quyền; sự kiện đổi thành viên qua
   Outbox; nhận sự kiện tạo dự án để ghi liên kết nhóm–dự án. Tạo OpenAPI và
   schema sự kiện từ phần triển khai thật, kiểm thử rồi khóa phiên bản; không
   đồng bộ dự án lưu trữ/xóa và không ghi liên kết mới khi lớp/nhóm đã đóng.
5. P1 sau khi P0 chạy trong lớp thử nghiệm; P2 chưa tạo migration/module.

OpenAPI/schema event là đầu ra của bước tích hợp. Tên event trong diagram là
tên thiết kế; không tự tạo file giả trong `contracts/` trước serializer,
URL, producer/consumer và kiểm thử tương ứng.

## 6. Các quyết định đã chốt cho kế hoạch

Các quyết định sau là đầu vào của kế hoạch, không còn là câu hỏi mở:

- Giảng viên đang phụ trách chủ động chốt giai đoạn lập nhóm; hệ thống không
  tự chốt theo thời gian.
- Sau khi chốt, Trưởng nhóm vẫn được loại thành viên thường của nhóm mình;
  Giảng viên phụ trách được phân, chuyển hoặc loại sinh viên trong đúng lớp.
  Mọi thao tác phải giữ Trưởng nhóm, giới hạn tối đa, lý do và lịch sử.
- Quản trị viên hệ thống được tạo lớp và thêm sinh viên. Khi tạo lớp thay,
  Quản trị viên phải chỉ định một Giảng viên đang hoạt động làm người phụ
  trách chính; vai trò Quản trị viên không tự cấp quyền xem nội dung dự án.
- Classroom không tạo liên kết dự án mới khi lớp hoặc nhóm đã đóng/lưu trữ.
  Liên kết lịch sử đã có vẫn được giữ.
- Work chỉ áp dụng thay đổi thành viên cho các dự án đang hoạt động; không
  đồng bộ dự án đã lưu trữ hoặc đã xóa và không tự mở lại dự án.
- Classroom và Identity nhận tối đa 100 sinh viên mỗi request. Web chia danh
  sách lớn thành các lô tối đa 100, mỗi lô có khóa chống lặp riêng và giao diện
  hiển thị kết quả từng lô; không chuyển việc đọc Excel sang backend.
- [Ghi chú Classroom](../../classroom-service/README.md#rest-nội-bộ-và-kafka) ghi bảng liên kết và đường nhận sự
  kiện qua Kafka và trạng thái cập nhật sơ đồ; [ghi chú Work](../../work-service/classroom-project-linking.md)
  chỉ ghi các thay đổi phía Work. Hợp đồng giao nhận và xử lý lỗi được tạo,
  kiểm thử và khóa phiên bản trong bước tích hợp trước nghiệm thu.

## 7. Bộ sơ đồ và bản xem

Tổng cộng 20 sơ đồ: 6 BFD, 4 Use Case, 9 Sequence và 1 ERD. Các hình đã cập
nhật theo [nghiệp vụ đã chốt](../../classroom-service/README.md#rest-nội-bộ-và-kafka).

| File | Nội dung |
| --- | --- |
| [bfd.md](bfd.md) | PlantUML: tổng thể và chi tiết chức năng MVP |
| [usecase.md](usecase.md) | 4 sơ đồ PlantUML, 16 trường hợp sử dụng có mã và bảng truy vết yêu cầu → BFD → UC → SQ |
| [sequence.md](sequence.md) | 9 luồng Mermaid: quyền, danh sách JSON, nhóm tự chọn đề tài, nhiều dự án và liên kết qua Kafka |
| [erd.md](erd.md) | ERD P0 10 bảng và quy tắc ràng buộc |

BFD/Use Case dùng PlantUML; ERD/Sequence dùng Mermaid. Markdown là nguồn
được quản lý trong Git. Bản render chỉ phục vụ đọc hình; không thay kiểm thử
backend, migration hoặc delivery Kafka. Không yêu cầu generator/HTML local
để kiểm liên kết và cú pháp nguồn trên checkout sạch.
