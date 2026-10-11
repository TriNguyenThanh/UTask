# Identity Service — Sơ đồ theo source hiện hành

Đối chiếu ngày 2026-10-07. **Trạng thái: Một phần**: sơ đồ mô tả code Identity,
không xác nhận provider/Kafka/email hoặc consumer liên service đã được nghiệm thu.
Hướng dẫn tích hợp chuẩn ở [docs/identity-service](../../identity-service/README.md).

| Tài liệu | Nội dung |
| --- | --- |
| [Use case](usecase.md) | 29 use cases, 7 actor maps; API/input/lỗi/giới hạn và nguồn code/test |
| [Sequence](sequence.md) | 23 luồng; hooks thư viện, transaction/lock và boundary bên ngoài |
| [ERD](erd.md) | 8 bảng nghiệp vụ; quan hệ allauth/SimpleJWT và các bảng framework |
| [API](../../architecture/Identity_Service_API_Specification.md) | Contract chi tiết; OpenAPI sinh từ URLconf/serializers thật |
| [Kiểm thử](../../architecture/Identity_Service_Test_Specification.md) | Ma trận/cách chạy pytest; source test không thay kết quả E2E |

## Nguồn thực thi và quy ước

- Routes: [authentication.urls](../../../apps/identity-service/authentication/urls.py),
  [accounts.urls](../../../apps/identity-service/accounts/urls.py),
  [config.urls](../../../apps/identity-service/config/urls.py).
- Hooks/settings: [settings.py](../../../apps/identity-service/config/settings.py).
  Django Auth/dj-rest-auth/allauth/SimpleJWT/Axes/Argon2 thực thi các bước tương ứng;
  adapters bổ sung lifecycle, phiên, audit/outbox và Integration boundary.
- Models/constraints: [models.py](../../../apps/identity-service/accounts/models.py)
  và [migrations](../../../apps/identity-service/accounts/migrations/).
- Response: common renderer/exception handler; envelope success/message/data/meta/error;
  details là mảng, giữ WWW-Authenticate/Retry-After. JWKS keys ở root.
- Code/test quyết định phần hiện hành; yêu cầu ngoài source phải ghi mục tiêu/chưa xác
  minh. Không dùng tham khảo dự án khác để thay implementation UTask.

Mặc định có25 operations trên23 paths nghiệp vụ; OAuth/avatar thêm8 operations khi
flags bật. GET activate trả405, không thuộc contract. Health/OpenAPI/Swagger là routes
hỗ trợ. Giữ mã UC-ID-01..27/SQ-ID-01..21 để link hiện hữu tiếp tục dùng; UC28/SQ22 là
resend public, UC29/SQ23 là GitHub mapping nội bộ.

## Ma trận luồng

| Nhóm | Use case | Sequence |
| --- | --- | --- |
| Register → activate → login | [UC01](usecase.md#uc-id-01), [UC12](usecase.md#uc-id-12), [UC02](usecase.md#uc-id-02) | [SQ01](sequence.md#sq-id-01), [SQ09](sequence.md#sq-id-09), [SQ02](sequence.md#sq-id-02) |
| Refresh/logout/devices | [UC03](usecase.md#uc-id-03), [UC06](usecase.md#uc-id-06), [UC07](usecase.md#uc-id-07), [UC08](usecase.md#uc-id-08), [UC09](usecase.md#uc-id-09) | [SQ03](sequence.md#sq-id-03), [SQ05](sequence.md#sq-id-05), [SQ21](sequence.md#sq-id-21) |
| Forgot/reset/change | [UC10](usecase.md#uc-id-10), [UC11](usecase.md#uc-id-11), [UC13](usecase.md#uc-id-13) | [SQ06](sequence.md#sq-id-06), [SQ07](sequence.md#sq-id-07), [SQ08](sequence.md#sq-id-08) |
| JWKS/session-status | [UC04](usecase.md#uc-id-04), [UC05](usecase.md#uc-id-05) | [SQ20](sequence.md#sq-id-20), [SQ04](sequence.md#sq-id-04) |
| Me/profile/batch/admin list | [UC17](usecase.md#uc-id-17), [UC18](usecase.md#uc-id-18), [UC20](usecase.md#uc-id-20), [UC21](usecase.md#uc-id-21), [UC25](usecase.md#uc-id-25) | [SQ15](sequence.md#sq-id-15), [SQ21](sequence.md#sq-id-21) |
| Status/global roles | [UC26](usecase.md#uc-id-26), [UC27](usecase.md#uc-id-27) | [SQ17](sequence.md#sq-id-17), [SQ18](sequence.md#sq-id-18) |
| Provisioning/internal resend | [UC23](usecase.md#uc-id-23), [UC24](usecase.md#uc-id-24) | [SQ11](sequence.md#sq-id-11), [SQ12](sequence.md#sq-id-12) |
| Public resend | [UC28](usecase.md#uc-id-28) | [SQ22](sequence.md#sq-id-22) |
| Google/GitHub/unlink | [UC14](usecase.md#uc-id-14), [UC15](usecase.md#uc-id-15), [UC16](usecase.md#uc-id-16) | [SQ13](sequence.md#sq-id-13), [SQ14](sequence.md#sq-id-14) |
| GitHub mapping | [UC29](usecase.md#uc-id-29) | [SQ23](sequence.md#sq-id-23) |
| Avatar | [UC19](usecase.md#uc-id-19) | [SQ16](sequence.md#sq-id-16) |
| Classroom import — boundary mục tiêu | [UC22](usecase.md#uc-id-22) | [SQ10](sequence.md#sq-id-10) |
| Outbox/handoff | Use cases ghi event | [SQ19](sequence.md#sq-id-19): chỉ ghi outbox đã có code |

## Chính sách cần giữ khi tích hợp

Register tạo pending; activate không cấp JWT, login riêng. Refresh là JWT SimpleJWT,
cập nhật cùng session ID/family, hạn family7 ngày tuyệt đối. Replay còn hạn thu hồi
family trước401. Password reset/change và mutation status/roles thu hồi credential liên
quan; change password gồm cả thiết bị hiện tại. Consumer chỉ kiểm chữ ký không tự có
revocation tức thì: cần session-status rồi kiểm quyền tài nguyên do chính service sở hữu.

Không có reset/activation/OAuth tables tự viết; allauth sở hữu email/social identity,
Axes sở hữu lockout, SimpleJWT sở hữu outstanding/blacklist. Email/username/MSSV xóa mềm
vẫn reserved. SYSTEM_ADMIN/Django metadata không là project/classroom permission bypass.

Google account/link và token issuance có transaction riêng; unlink không có link vẫn
200 và ghi audit/user.updated. JWKS một khóa không kid; chưa hỗ trợ overlap nhiều khóa.
Publisher/ACK Kafka, mail delivery, consumer và Classroom enrollment cần triển khai/
nghiệm thu riêng. Chỉ Integration gọi GitHub API; Identity không sở hữu repo/membership.

## Nguồn hình và tái sinh

Source chuẩn là31 khối PlantUML trong Markdown:7 use-case maps,23 sequences,1 ERD.
SVG tại assets/ là output, không sửa riêng khỏi nguồn. Renderer PlantUML1.2025.10 với
UTF-8; use case/ERD dùng Smetana để không cần Graphviz riêng.

Sau khi trích mỗi fence thành file .puml theo tên @startuml, chạy:

```text
java "-Djava.awt.headless=true" -jar <plantuml-1.2025.10.jar> -charset UTF-8 -checkonly <sources-dir>
java "-Djava.awt.headless=true" -jar <plantuml-1.2025.10.jar> -charset UTF-8 -tsvg <sources-dir>
```

Đưa SVG tương ứng vào assets/, kiểm số lượng/ID, link/anchor và đọc hình để phát hiện
cắt chữ/chồng nội dung. Render/link hợp lệ không thay regression PostgreSQL, test provider
hoặc nghiệm thu liên service. Không đưa secret/token/cookie thật vào source/hình.
