# Stack AI Service

**Trạng thái: Một phần.** Runtime và dependencies pipeline đã có; integration
production và evaluation LLM chưa xác minh. Theo [baseline](../architecture/README.md)
và [ADR-002](../adr/002-ai-request-pipeline.md).

| Layer | Đã triển khai |
| --- | --- |
| API | Python 3.12, FastAPI/Uvicorn, Pydantic v2 |
| Workflow/agent | Google ADK custom BaseAgent + LlmAgent + Runner |
| Provider | Google GenAI/Gemini adapter; model qua `AI_MODEL` |
| Identity | PyJWT RS256/ES256, issuer/audience, public key/JWKS |
| Context | HTTPX, REST adapter + domain tools + filter/freshness/size |
| Job | Celery + Redis broker; worker và dispatcher riêng |
| Persistence | PostgreSQL riêng, SQLAlchemy + Psycopg, Alembic migration |
| Credential | Fernet từ cryptography; khóa cấu hình ngoài source |
| Quality | uv/lock, Ruff, Pytest, fake ADK model, PostgreSQL/Redis integration |
| Image | Dockerfile chung API/worker/dispatcher và migrations |

Version cụ thể nằm trong `apps/ai-service/uv.lock`, không suy ra từ ví dụ SDK.
Kafka/projection/event publisher chưa có use case/contract runtime và không
được thêm vào agent. Không thêm framework khác, vector DB hoặc HTTP tool tự do.

ADK callback/Runner và Celery late-ack được đối chiếu
[tài liệu ADK](https://adk.dev/agents/llm-agents/) và
[tài liệu Celery Redis](https://docs.celeryq.dev/en/stable/getting-started/backends-and-brokers/redis.html).
Idempotency, deadline, budget và result vẫn được AI persistence/application
kiểm soát; broker/framework không thay thế những bảo đảm này.
