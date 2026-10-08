"""Task entry point: nhận UUID, lắp adapter và gọi application."""

import asyncio
from uuid import UUID

import httpx

from application.execution import RequestWorker
from config import get_settings
from infrastructure.bootstrap import build_repository
from infrastructure.context_http import InternalContextAdapter
from infrastructure.providers import AdkRequestExecutor, AdkRuntime
from infrastructure.security import FernetCredentialVault, JwtAuthenticator

from .celery_app import celery_app


async def execute_request(request_id: UUID):
    settings = get_settings()
    repository, engine = build_repository(settings)
    try:
        async with httpx.AsyncClient() as client:
            adapter = InternalContextAdapter(settings, client)
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
            return await worker.execute(request_id)
    finally:
        engine.dispose()


@celery_app.task(name="utask_ai.execute_request")
def run_request(request_id: str):
    return asyncio.run(execute_request(UUID(request_id)))
