# Classroom Service

**Trạng thái tài liệu: Thiết kế mục tiêu; hiện trạng mã nguồn chưa xác minh.**

Classroom Service quản lý cấu trúc học tập và quan hệ trong lớp: môn học, lớp,
giảng viên, sinh viên, ghi danh, nhóm, thành viên nhóm và kỳ học nếu cần. Câu
hỏi service này trả lời là: **ai học với ai, thuộc lớp nào và thuộc nhóm nào?**

```text
Teacher → Class → Group → Project → Sprint → Task
   └────────── Classroom Service ─────┘
                         └── Project Service ──┘
```

Classroom Service sở hữu `GroupMember`; Project Service sở hữu
`ProjectMember`. Giảng viên xem project qua quan hệ lớp → nhóm → project, không
cần được thêm làm thành viên dự án. `class_id` và `group_id` ở Project Service
chỉ là ID tham chiếu, không phải khóa ngoại xuyên database.

Thay đổi cần câu trả lời ngay có thể dùng REST. Thông báo việc lớp, nhóm hoặc
thành viên thay đổi đi qua Kafka. API và sự kiện cụ thể chỉ được ghi như đã có
sau khi đối chiếu hợp đồng API/sự kiện.
