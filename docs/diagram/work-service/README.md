# Sơ đồ thiết kế Work / Project Service

**Trạng thái: Thiết kế mục tiêu**, đồng bộ ngày 08/10/2026; chưa có Work source/migration/runtime được nghiệm thu.

Nguồn chuẩn:
- [Kiến trúc hệ thống](../../system/architecture.md), [ownership](../../system/data-ownership.md), [giao tiếp](../../system/communication.md).
- [Yêu cầu nghiệp vụ](../../architecture/UTask%20-%20Phân%20tích%20thiết%20kế%20yêu%20cầu.md).
- [Work API v1.4](../../architecture/Work_Service_API_Specification.md).
- [Baseline kỹ thuật](../../architecture/UTask_Architecture_Technology_Baseline%20%281%29.md); nguồn hiện hành khi có mâu thuẫn vẫn là docs/system.

## Các nguồn sơ đồ

| File | Nội dung |
| --- | --- |
| [bfd.md](bfd.md) | 7 nhóm chức năng; ownership và RACI |
| [usecase.md](usecase.md) | Actor và 6 phân hệ, quyền mục tiêu |
| [sequence.md](sequence.md) | 12 luồng command/event, transaction và đối chiếu Plane |
| [erd.md](erd.md) | 20 bảng mục tiêu, facts/snapshot và invariant |
| [index.html](index.html) | Bản xem được sinh từ các file Markdown trên |

Classroom sở hữu Group/GroupMember; Work sở hữu ProjectMember và công việc. AI đọc context riêng qua Kafka; Work tính số liệu; GitHub link mới cần user confirm. Sprint P1, GitHub/AI/dashboard nằm trong P0 theo PRD. Plane commit 7466675e471efe1c96b122615f7a0d30c9b2eb05 chỉ là tham khảo kỹ thuật, không thay quy tắc UTask.

## Sinh bản xem

Chạy từ repository root:

```powershell
python scripts/sync_work_diagrams.py
python scripts/sync_work_diagrams.py --check
```

Không sửa định nghĩa sơ đồ trong HTML bằng tay. Markdown là nguồn; generator cập nhật dictionary và số thực thể trong HTML, giữ UI zoom/pan/export. Bản xem hiện dùng Mermaid/PlantUML renderer như trước; không được gọi là runtime nghiệp vụ.

## Nghiệm thu

Kiểm link/JSON ví dụ, parity HTML↔Markdown và render cú pháp Mermaid/PlantUML trước khi giao tài liệu. Khi có code thật cần kiểm permission, transaction, migration, PostgreSQL concurrency, Kafka/provider và E2E riêng. Nhãn Approved hoặc một sơ đồ đẹp không xác nhận service đã chạy.

Thiết kế gọn: 20 bảng; bộ đếm ở Project, Activity chung, upload cùng Attachment; giữ CommentMention M:N có căn cứ. Sequence 12 luồng đều là sequenceDiagram, kèm ma trận source Plane và giới hạn kế thừa.

Quyết định v6: Epic có căn cứ baseline 4.2, Story dùng Task.type; Attachment chung cho Task/Project theo baseline 12. Giữ 20 bảng theo nhu cầu dữ liệu, không yêu cầu người dùng tự quyết số bảng; audit mục 6 ghi lựa chọn và lý do cho từng bảng.

[Biên bản ERD audit theo PRD/Plane](../../project-service/erd-audit-20261008.md) và `python scripts/check_work_design.py` kiểm kê entity/FK/từ điển/Sequence/HTML. Không lấy con số bảng làm bằng chứng 3NF hoặc production readiness.

[Bằng chứng từng bảng/từng cột](../../project-service/erd-field-evidence.md) có file/dòng, trường gốc và lý do Work cho 234 cột. Khi có checkout Plane tại commit ghi trong tài liệu, chạy thêm `python scripts/check_work_design.py --plane-root <đường-dẫn-checkout-Plane>` để kiểm field/line bằng AST; không cần khởi động Plane hoặc đọc database.
