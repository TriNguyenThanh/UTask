# Lưu trữ file

**Trạng thái: Thiết kế mục tiêu; chưa xác minh adapter upload/download.**
[Baseline](<../architecture/UTask_Architecture_Technology_Baseline (1).md>)
mục 12 chọn Cloudflare R2 cho production, truy cập qua S3-compatible API.
Django service dự kiến dùng `django-storages` + `boto3`; local dùng filesystem.
MinIO chỉ thêm khi cần kiểm tra hành vi S3 ở local.

File mục tiêu gồm avatar, attachment của task/project, tài liệu lớp học,
export và đầu vào AI nếu sản phẩm hỗ trợ. Metadata và quyền truy cập thuộc
service sở hữu nghiệp vụ; bucket/object storage không thay quyền sở hữu này.

Backend kiểm tra quyền, loại và kích thước file; file riêng tư không được
public mặc định. Dùng signed/presigned URL khi phù hợp. Endpoint, bucket,
credential và chính sách retention thuộc cấu hình môi trường; không commit
secret hoặc ghi tên bucket giả như thể đã triển khai.
