# Stack AI Service

**Trạng thái: Một phần.** Bootstrap đã dùng Python 3.12, FastAPI/Uvicorn,
Pydantic v2, `pydantic-settings`, `uv`, Pytest, Ruff và Docker. Các adapter
provider/context, ADK, Celery, Kafka và persistence chưa triển khai.

Thiết kế công nghệ theo [baseline](../architecture/README.md), mục 4.6, 9–11,
18 và 28; trạng thái dependency thực tế nằm trong [code map](code-map.md).

| Lớp                | Lựa chọn mục tiêu                                                                 | Hiện trạng                                                       |
| ------------------ | --------------------------------------------------------------------------------- | ---------------------------------------------------------------- |
| API/runtime        | Python + FastAPI; bootstrap Python 3.12/Uvicorn                                   | Đã có bootstrap                                                  |
| Agent              | Google ADK; workflow và domain tools                                              | Chưa có dependency/runtime                                       |
| Provider           | Model/provider adapter; model chọn qua evaluation                                 | Chỉ có protocol và provider mặc định báo lỗi                     |
| Schema/config      | Pydantic và cấu hình môi trường                                                   | Đã có bootstrap                                                  |
| Context            | Internal API qua Context Layer; projection/cache khi có use case                  | Chưa có adapter/tool                                             |
| Job nội bộ         | Celery + Redis                                                                    | Chưa có dependency/worker/queue                                  |
| Event giữa service | Kafka; Python ưu tiên `confluent-kafka`                                           | Chưa có SDK/producer/consumer                                    |
| Dữ liệu AI         | PostgreSQL riêng; SQLAlchemy/asyncpg/Alembic là phương án trong thiết kế AI trước | Chưa có database client/migration; baseline không ấn định ORM AI |
| Package            | `uv`, `pyproject.toml`, `uv.lock`                                                 | Đã có                                                            |
| Test/quality       | Pytest/HTTPX, fake provider, evaluation; Ruff                                     | Có test bootstrap, chưa có evaluation LLM                        |
| Deploy             | Docker; API và worker có entry point riêng khi triển khai job                     | Có Dockerfile API, chưa có worker topology                       |

Redis là broker job nội bộ theo baseline, không cần đợi một use case cache
mới để ghi nhận lựa chọn Celery + Redis. Kafka không thay Redis trong luồng
Celery. Worker thuộc AI Service, không phải service worker dùng chung và chưa
được quy định singleton. Xem [job nền](../infrastructure/background-jobs.md).

Không pin phiên bản SDK hoặc model chỉ từ tài liệu: kiểm tra dependency và
đánh giá provider tại thời điểm triển khai. Không thêm LangChain/CrewAI, vector
DB hoặc nhiều agent framework nếu chưa có use case/quyết định. Baseline chưa
chọn model cụ thể và không quy định toàn bộ các khả năng AI phải có trong API v1.

Tài liệu framework/provider chỉ phục vụ tra cứu kỹ thuật; các quyết định UTask
lấy từ baseline và tài liệu service, không từ tính năng mới của SDK.
