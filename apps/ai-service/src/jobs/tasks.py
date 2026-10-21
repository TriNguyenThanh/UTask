"""Task entry point: nhận UUID, lắp adapter và gọi application."""

import asyncio
import logging
from datetime import UTC, datetime
from uuid import UUID

import httpx
from sqlalchemy.exc import OperationalError

from application.execution import RequestWorker
from config import get_settings
from infrastructure.bootstrap import build_repository
from infrastructure.context_factory import build_context_adapter
from infrastructure.observability import bind_request_id
from infrastructure.providers import AdkRequestExecutor, AdkRuntime
from infrastructure.security import FernetCredentialVault, JwtAuthenticator

from .celery_app import celery_app

logger = logging.getLogger(__name__)


async def execute_request(request_id: UUID):
    settings = get_settings()
    repository, engine = build_repository(settings)
    try:
        async with httpx.AsyncClient() as client:
            adapter = build_context_adapter(settings, client)
            vault = FernetCredentialVault(
                settings.credential_key.get_secret_value() if settings.credential_key else None
            )
            worker = RequestWorker(
                repository,
                JwtAuthenticator(settings),
                adapter,
                vault,
                AdkRequestExecutor(AdkRuntime(settings), adapter),
            )
            with bind_request_id(str(request_id)):
                return await worker.execute(request_id)
    finally:
        engine.dispose()


@celery_app.task(name="utask_ai.execute_request")
def run_request(request_id: str):
    return asyncio.run(execute_request(UUID(request_id)))


@celery_app.task(
    name="utask_ai.cleanup_terminal",
    autoretry_for=(OperationalError,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    max_retries=3,
)
def cleanup_terminal():
    """Một batch mỗi lần gọi; retry sau commit không xóa lại cùng request."""
    settings = get_settings()
    repository, engine = build_repository(settings)
    try:
        deleted = repository.cleanup_terminal(
            datetime.now(UTC),
            retention_days=settings.terminal_retention_days,
            limit=settings.retention_batch_size,
        )
        logger.info(
            "AI retention batch deleted=%d limit=%d", deleted, settings.retention_batch_size
        )
        return deleted
    finally:
        engine.dispose()
