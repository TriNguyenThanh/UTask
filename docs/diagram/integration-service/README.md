# Sơ đồ Integration Service

**Trạng thái: Thiết kế mục tiêu.** Các sơ đồ đề xuất ranh giới và dữ liệu cho
phạm vi GitHub; Integration chưa có runtime, schema hoặc migration trong repo.
ERD là mô hình khái niệm, chưa phải schema đã chốt.

## Nguồn chuẩn

- [Tài liệu Integration Service](../../integration-service/README.md) ghi vai
  trò, ranh giới, hiện trạng và các điểm nối.
- [Phạm vi và quyền truy cập](../../integration-service/scope-access.md) là
  nguồn chuẩn cho quyền GitHub, cài App, kết nối repository với Project và
  giới hạn của từng caller.
- [API Integration](../../integration-service/api.md) ghi các endpoint và payload
  đề xuất; trạng thái hợp đồng cần theo tài liệu đó.
- [Quyền sở hữu dữ liệu](../../system/data-ownership.md),
  [giao tiếp giữa service](../../system/communication.md) và
  [luồng GitHub](../../system/workflows.md#github) là nguồn kiến trúc.

## Các sơ đồ

| File | Nội dung |
| --- | --- |
| [erd.md](erd.md) | Mô hình dữ liệu khái niệm và quy tắc duy nhất đề xuất |
| [bfd.md](bfd.md) | Phân rã chức năng Integration |
| [dfd.md](dfd.md) | Sơ đồ luồng dữ liệu context và level 1 |

Sơ đồ không xác nhận tính năng đã chạy. Trình duyệt chỉ khởi tạo/callback cài
App và đọc installation/repository trong phạm vi GitHub user đã chứng minh
quyền; việc thấy repository không cấp quyền cho mọi user UTask. Chọn, đổi hoặc
ngắt repository của Project là lệnh qua Work, với quyền leader `ACTIVE` do Work
kiểm tra. `ProjectConnection` chỉ là dữ kiện liên kết GitHub do Integration
quản lý, không phải `TaskGitHubLink`; task link và quyền user/project thuộc Work.
ID `project_id` trong Integration chỉ là tham chiếu logic, không phải khóa
ngoại xuyên service. Xem [phạm vi và quyền truy cập](../../integration-service/scope-access.md)
để biết quy tắc đầy đủ.
