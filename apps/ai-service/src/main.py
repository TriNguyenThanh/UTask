from fastapi import FastAPI

from api import router
from api.exception_handlers import register_exception_handlers
from api.middleware import request_id_middleware
from application import AiApplicationService
from application.ports import RequestRepository
from config import Settings, get_settings
from infrastructure.providers import UnconfiguredProvider
from infrastructure.repositories import InMemoryRequestRepository
from workflow import BoundedWorkflow
from workflow.ports import ModelProvider


def create_app(
    settings: Settings | None = None,
    *,
    provider: ModelProvider | None = None,
    repository: RequestRepository | None = None,
) -> FastAPI:
    """Lắp ghép settings, application và HTTP transport khi server khởi động."""

    settings = settings or get_settings()
    app = FastAPI(title=settings.app_name, version="0.1.0")
    request_repository = repository or InMemoryRequestRepository()
    model_provider = provider or UnconfiguredProvider()
    workflow = BoundedWorkflow(model_provider, timeout_seconds=settings.workflow_timeout_seconds)
    app.state.application = AiApplicationService(request_repository, workflow)

    app.middleware("http")(request_id_middleware)
    register_exception_handlers(app)
    app.include_router(router)
    return app


app = create_app()
