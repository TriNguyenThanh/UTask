# Progress Service

**Trạng thái tài liệu: Thiết kế mục tiêu; hiện trạng triển khai chưa xác minh.**

Progress Service nhận các sự kiện cần thiết từ Project, Classroom và Integration,
tính chỉ số bằng công thức hoặc quy tắc rõ ràng, rồi công bố kết quả cho
dashboard và các service nhận sự kiện phù hợp.

Các chỉ số mục tiêu gồm tỷ lệ hoàn thành, tiến độ sprint, số task đã xong, task
trễ hạn, khối lượng công việc và phân bố khối lượng công việc, mức hoạt động, đóng góp GitHub, thời gian
không hoạt động và tín hiệu rủi ro. Ví dụ:

```text
completion_rate = completed_tasks / total_tasks
```

Quy tắc phải giải thích được và tính nhất quán từ dữ liệu đầu vào. AI có thể
diễn giải kết quả hoặc đề xuất hành động nhưng không quyết định giá trị chỉ số.
Dashboard tiến độ không phụ thuộc AI Service.

Chỉ số cụ thể, cửa sổ thời gian, xử lý dữ liệu thiếu và hợp đồng sự kiện cần được
chốt trước khi công bố API hoặc kết quả là đã triển khai.
