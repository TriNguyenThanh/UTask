# Bàn giao kết quả worker cho process API

## Goal

Worker bàn giao kết quả và thông báo cho process API của AI; API tiếp nhận
và cập nhật trạng thái/kết quả cuối trong PostgreSQL. Không chạy lại LLM khi
thông báo bị lặp, API khởi động lại hoặc kết nối listener gián đoạn.

## Current state

Worker hiện gọi repository.finish để ghi terminal result; API đọc DB bằng
polling. API, worker và dispatcher thuộc cùng AI Service, dùng chung DB.

## Constraints

Giữ REST quyền/context, Redis broker và contract POST/GET v1. Không Kafka
request-response, không sửa Work, không lưu nội dung context. LISTEN/NOTIFY
là tín hiệu trong DB AI, không là domain event hoặc hàng đợi kết quả bền vững.

## Proposed changes

- Thêm migration/bảng ai_completion: request ID, execution token, response
  đã validate và thời điểm bàn giao. Worker insert + pg_notify cùng transaction.
- API lifespan chạy listener với một connection PostgreSQL riêng/autocommit;
  sau LISTEN, khi có tín hiệu và định kỳ phục hồi, application tiếp nhận inbox.
- Tiếp nhận khóa request bằng SKIP LOCKED, kiểm tra token/schema/intent/version,
  ghi terminal result, xóa inbox và credential trong cùng transaction.
- Kết quả bàn giao hợp lệ trước deadline không bị dispatcher timeout vì API
  tạm dừng. Worker quá deadline bàn giao lỗi timeout; worker cũ không ghi đè.
- Giữ POST/GET polling cho client; không thêm endpoint công khai hoặc dependency.

## Test strategy

Unit tests cho worker, application accept, listener reconnect/cancel/cleanup.
PostgreSQL thật cho notification sau commit, rollback, receive/restart,
duplicate/stale token, deadline, schema sai và nhiều API consumer đồng thời.
Migration upgrade/downgrade/schema drift; Celery/Redis thật bàn giao sang API.

## Validation

Ruff format/check, toàn bộ pytest với DB ai_test/Redis test riêng, Docker build,
kiểm tra tài liệu/link/diff; cập nhật task log và code map. Không gọi LLM trả phí.

## Risks

NOTIFY không bền vững nên inbox mới là nguồn phục hồi. Listener cần connection
trực tiếp hoặc session pooling; không dùng transaction pooling. API tạm dừng
thì request có completion giữ running cho tới khi API tiếp nhận, không chạy
lại model. Rolling deploy cần nâng schema và phối hợp đổi API/worker.
