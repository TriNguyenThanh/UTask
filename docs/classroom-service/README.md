# Classroom Service

**Trạng thái tài liệu: Thiết kế mục tiêu; hiện trạng mã nguồn chưa xác minh.**

Theo [baseline](../architecture/README.md), mục 4.3, service dùng Python +
Django + DRF, sở hữu cả điểm danh, điểm số và liên kết nhóm–project.

Classroom Service quản lý cấu trúc học tập và quan hệ trong lớp: môn học, lớp,
giảng viên, sinh viên, ghi danh, nhóm, thành viên nhóm và kỳ học nếu cần. Câu
hỏi service này trả lời là: **ai học với ai, thuộc lớp nào và thuộc nhóm nào?**

```text
Classroom: Teacher → Class → Group / GroupMember
                              │ liên kết bằng ID
Work:                     Project / ProjectMember → Sprint → Task
```

Classroom Service sở hữu `GroupMember`; Work Service sở hữu
`ProjectMember`. Giảng viên xem project qua quan hệ lớp → nhóm → project, không
cần được thêm làm thành viên dự án. `class_id` và `group_id` ở Work Service
chỉ là ID tham chiếu, không phải khóa ngoại xuyên database.

Thay đổi cần câu trả lời ngay có thể dùng REST. Thông báo việc lớp, nhóm hoặc
thành viên thay đổi đi qua Kafka. API và sự kiện cụ thể chỉ được ghi như đã có
sau khi đối chiếu hợp đồng API/sự kiện.
