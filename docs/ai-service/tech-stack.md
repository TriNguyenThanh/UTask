# Stack AI Service giai đoạn 1

**Trạng thái: Thiết kế mục tiêu; chưa được xác minh trong implementation.**

Stack đề xuất cho ba workflow `backlog_generation`, `task_decomposition` và
`risk_analysis` như sau:

| Lớp           | Lựa chọn                                                |
| ------------- | ------------------------------------------------------- |
| Runtime       | Python 3.12.x, pin bằng `.python-version`               |
| API           | FastAPI + Uvicorn                                       |
| Schema/config | Pydantic v2 + `pydantic-settings`                       |
| Dependency    | `uv`, `pyproject.toml`, `uv.lock`                       |
| Kafka         | `aiokafka` cho consumer bất đồng bộ                     |
| Context DB    | PostgreSQL `ai_context_db`                              |
| Persistence   | SQLAlchemy 2 async + `asyncpg` + Alembic                |
| LLM provider  | Model/provider adapter hoặc router; model cụ thể cần benchmark |
| Agent layer   | Google ADK 2.0: Workflow + LlmAgent + Context Tool Pool |
| Test          | Pytest + HTTPX, fake LLM provider                       |
| Quality       | Ruff                                                    |
| Deploy        | Docker                                                  |

Lý do chọn:

- FastAPI phù hợp API AI, hỗ trợ type hints, OpenAPI, JSON Schema và Pydantic validation. [FastAPI documentation](https://fastapi.tiangolo.com/)
- `uv` đã khớp với CI hiện tại của repository và cung cấp lockfile reproducible. [uv project guide](https://docs.astral.sh/uv/guides/projects/)
- `aiokafka` phù hợp với service Python async và mô hình context nhận qua Kafka. [aiokafka documentation](https://aiokafka.readthedocs.io/en/stable/)
- SQLAlchemy có hỗ trợ asyncio chính thức; Alembic phù hợp migration cho PostgreSQL. [SQLAlchemy asyncio](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html), [Alembic](https://alembic.sqlalchemy.org/en/latest/)
- Google ADK 2.0 phù hợp với kiến trúc bounded agent của UTask: Workflow kiểm
  soát macro-flow, `LlmAgent` tự reasoning và chọn tool, còn Context Tool Pool
  che giấu Kafka/database/cache. Model/provider phải nằm sau adapter để có thể
  benchmark, đổi model hoặc fallback mà không đổi business logic.

Dependency direction nên là:

```text
FastAPI route
    ↓
Application service
    ↓
Google ADK Workflow
    ↓
LlmAgent / agent-as-tool
    ↓
Context Tool Pool
    ↓
Kafka, PostgreSQL, model/provider adapters
```

Chưa nên thêm ở v1:

- LangChain, CrewAI hoặc nhiều agent framework cùng lúc;
- Redis nếu chưa có yêu cầu cache/rate-limit cụ thể;
- vector database;
- multi-agent orchestration cho request đơn giản;
- gọi REST đồng bộ sang Project/Classroom/Integration Service.

Model cụ thể chưa được chốt; cần benchmark tại thời điểm triển khai. OpenAI,
Gemini hoặc provider khác chỉ là lựa chọn phía sau adapter/router. Stack này
cũng phù hợp với dấu vết CI Python service hiện có trong [CI Python service](/home/trislord/Code/UTask/UTask/.github/workflows/python-service.yml:1)
và cấu hình FastAPI dự kiến trong [README root](/home/trislord/Code/UTask/UTask/README.md:24).
