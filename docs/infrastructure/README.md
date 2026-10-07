# Hạ tầng và phát triển local

Thư mục này là nguồn chuẩn cho môi trường và quy trình phát hành. Trước khi
đổi hướng dẫn vận hành, đối chiếu lại Docker Compose, tệp môi trường và GitHub
Actions có liên quan.

Thiết kế mục tiêu theo [architecture baseline](../architecture/README.md).
Tách lựa chọn công nghệ trong baseline khỏi cấu hình runtime đã xác minh.

- [Chạy local](local-development.md)
- [Biến môi trường](environment.md)
- [Kafka](kafka.md)
- [Redis](redis.md)
- [Job nền và Celery worker](background-jobs.md)
- [Lưu trữ file và Cloudflare R2](storage.md)
- [CI/CD](ci-cd.md)

Tài liệu cơ sở dữ liệu nằm trong [quyền sở hữu dữ liệu](../system/data-ownership.md).
Không suy luận các service đã kết nối Kafka/Redis chỉ vì hạ tầng được cấu hình.
