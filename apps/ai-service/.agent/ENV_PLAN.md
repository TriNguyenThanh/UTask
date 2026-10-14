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

Domain production chưa xác minh. LLM nay dùng LiteLLM tới endpoint custom tương
thích OpenAI; cần model ID, base URL và key hợp lệ từ nhà cung cấp trước khi có
thể xác minh inference. Lỗi quyền Google 403 trước đó không kiểm tra được endpoint
custom và không khẳng định đã được khắc phục.
