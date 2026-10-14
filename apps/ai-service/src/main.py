"""Composition root API; startup không tạo schema hoặc chạy worker ngầm."""

import asyncio
from contextlib import asynccontextmanager, suppress

import httpx
from fastapi import FastAPI

from api import router
from api.exception_handlers import register_exception_handlers
from api.middleware import request_id_middleware
from application import AiApplicationService
from config import Settings, get_settings
from infrastructure.bootstrap import build_repository
from infrastructure.completions import CompletionListener
from infrastructure.context_factory import build_context_adapter
from infrastructure.security import FernetCredentialVault, JwtAuthenticator


def create_app(
    settings: Settings | None = None,
    *,
    application=None,
    authenticator=None,
    completion_listener=None,
) -> FastAPI:
    settings = settings or get_settings()
    client = httpx.AsyncClient()
    engine = None
    if application is None:
        repository, engine = build_repository(settings)
        application = AiApplicationService(
            repository,
            build_context_adapter(settings, client),
            FernetCredentialVault(
                settings.credential_key.get_secret_value() if settings.credential_key else None
            ),
            settings.sync_timeout_seconds,
            settings.poll_interval_seconds,
        )
        completion_listener = completion_listener or CompletionListener(
            settings.database_url,
            application.accept_completions,
            reconcile_seconds=settings.completion_reconcile_seconds,
        )

    @asynccontextmanager
    async def lifespan(app):
        listener_task = (
            asyncio.create_task(completion_listener.run()) if completion_listener else None
        )
        try:
            yield
        finally:
            try:
                try:
                    if listener_task:
                        listener_task.cancel()
                        with suppress(asyncio.CancelledError):
                            await listener_task
                finally:
                    await client.aclose()
            finally:
                if engine:
                    engine.dispose()

    app = FastAPI(title=settings.app_name, version="1.0.0", lifespan=lifespan)
    app.state.application = application
    app.state.authenticator = authenticator or JwtAuthenticator(settings)
    app.middleware("http")(request_id_middleware)
    register_exception_handlers(app)
    app.include_router(router)
    return app


app = create_app()
