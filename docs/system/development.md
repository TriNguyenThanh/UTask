# Hướng dẫn phát triển

**Trạng thái: Thiết kế mục tiêu.** Quy ước chung theo
[baseline](../architecture/README.md), mục 16–24 và 27–31. Các lựa chọn công
nghệ không chứng minh dependency hoặc thiết lập GitHub đã được triển khai.

## Công nghệ và tổ chức source

- Backend nghiệp vụ dùng Python, Django, DRF; OpenAPI qua `drf-spectacular`.
  Django app chia theo feature/domain trong mỗi service.
- AI dùng FastAPI + Google ADK; provider đặt sau adapter, model cụ thể cần
  được đánh giá. Không hard-code prompt rải rác trong logic nghiệp vụ.
- Mỗi Python service có `pyproject.toml`, `uv.lock`, Dockerfile và dependency
  riêng; dùng `uv`. API/worker cùng nghiệp vụ thuộc cùng service.
- Web dùng React + Vite + TypeScript và `pnpm`; cấu trúc theo feature. Xem
  [Web](../web/README.md) để phân biệt server state và client state.
- Job nền dùng [Celery + Redis](../infrastructure/background-jobs.md); event
  giữa service dùng [Kafka + outbox](../infrastructure/kafka.md).

## Git và Pull Request

Baseline dùng `main`, không dùng `develop`. Branch ngắn hạn có prefix như
`feat/`, `fix/`, `docs/`, `chore/`, gắn mã issue khi có. Commit theo Conventional
Commits; mở PR tập trung, chạy CI, review và squash merge vào `main`.
Không direct push/force push; mục tiêu là ít nhất một approval và CI pass.
Branch protection thực tế trên GitHub chưa được xác minh.

## Kiểm thử và quan sát vận hành

Backend cần unit, integration, API và contract test; ưu tiên auth/permission,
membership, vòng đời task/sprint, webhook, outbox và consumer idempotency.
AI cần fake provider cho unit test, đánh giá trên dataset chuẩn (golden
dataset), structured output và regression evaluation. Web dùng Vitest/React
Testing Library; E2E dùng Playwright khi được triển khai.

Baseline yêu cầu JSON log có service, request/trace ID, error log và
healthcheck; trace ID được truyền qua API, job và event. Không log secret,
token hoặc mật khẩu. OpenTelemetry là hướng mở rộng; không bắt buộc dựng
toàn bộ hệ thống metrics/tracing trong MVP. Hướng dẫn vận hành nằm trong
[CI/CD](../infrastructure/ci-cd.md).

## Trước khi thay đổi

1. Đọc tài liệu service liên quan và [quy tắc agent](../../AGENTS.md).
2. Khi công việc đụng tới hiện trạng, kiểm tra mã nguồn, cấu hình, hợp đồng và
   kiểm thử trước khi cập nhật trạng thái tài liệu.
3. Giữ quyền sở hữu dữ liệu theo service. Không tạo khóa ngoại hoặc truy cập
   database xuyên service.
4. Chỉ thêm service hoặc công nghệ mới khi có quyết định kiến trúc được ghi
   nhận.

## Khi thay đổi hành vi

Cập nhật hợp đồng API/sự kiện và tài liệu service bị ảnh hưởng cùng với thay đổi.
Mô tả rõ lỗi, quyền truy cập, xử lý lặp và ảnh hưởng tới các service nhận sự kiện khi phù
hợp. Không viết đường dẫn API, sự kiện hay luồng thiết kế như thể đã chạy.

## Khi cập nhật tài liệu

- Tài liệu cho đội phát triển dùng tiếng Việt rõ ràng; giữ nguyên tên kỹ thuật
  cần thiết và giải thích thuật ngữ khó ở lần đầu.
- Mỗi chủ đề có một tài liệu chuẩn. README ở app chỉ dẫn tới tài liệu trong
  `docs/`.
- Gắn nhãn `Thiết kế mục tiêu`, `Chưa xác minh`, `Đã triển khai`, `Một phần`
  hoặc `Chưa triển khai` đúng với bằng chứng đã kiểm tra.
- Cập nhật link sau khi di chuyển hoặc xóa tài liệu.

## Kiểm tra trước khi báo hoàn thành

Chạy formatter, lint, kiểm thử và build phù hợp với thay đổi. Với thay đổi tài
liệu, kiểm tra link nội bộ, tham chiếu tên cũ và file rỗng liên quan. Nêu rõ
những gì đã kiểm tra và chưa kiểm tra.
