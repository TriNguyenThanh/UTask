# Thống nhất cấu hình và secret AI

## Mục tiêu

Một nguồn cấu hình thường `infra/env/ai-service.env`; secret trong `.env`
root. Giữ CI/CD và credential local hiện có; không sửa schema/API nghiệp vụ.

## Thực hiện

1. Settings đọc config rồi secret, env process có ưu tiên cao nhất. Bổ sung
   AI_ENVIRONMENT/MOCK_TEST và chặn mock trong staging/production.
2. Provider nhận key từ Settings để uv và Compose cùng dùng secret root.
3. Compose inject riêng secret AI; factory chọn fixture hoặc REST theo flag.
4. Script setup/refresh JWT local ghi hai file chuẩn, chỉ JWT lưu tại `.env.mock/`.
5. Chuyển secret cũ không in/đổi key; bỏ env mẫu/secret file riêng của AI.
6. Unit tests success/error/precedence/refresh, lint/build/Compose và API/Celery pipeline dùng fixture;
   cập nhật docs/task log. Không gọi model thật hoặc restart stack user khi test.

## Giới hạn

Domain production và quyền project Gemini chưa xác minh; lỗi Google 403 của
project đã quan sát trước không được giải quyết bởi thay đổi cấu hình này.
