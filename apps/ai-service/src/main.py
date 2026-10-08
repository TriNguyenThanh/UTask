"""Composition root API; startup không tạo schema hoặc chạy worker ngầm."""

from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from api import router
from api.exception_handlers import register_exception_handlers
from api.middleware import request_id_middleware
from application import AiApplicationService
from config import Settings, get_settings
from infrastructure.bootstrap import build_repository
from infrastructure.context_http import InternalContextAdapter
from infrastructure.security import FernetCredentialVault, JwtAuthenticator


def create_app(
    settings: Settings | None = None, *, application=None, authenticator=None
) -> FastAPI:
    settings = settings or get_settings()
    client = httpx.AsyncClient()
    engine = None
    if application is None:
        repository, engine = build_repository(settings)
        application = AiApplicationService(
            repository,
            InternalContextAdapter(settings, client),
            FernetCredentialVault(
                settings.credential_key.get_secret_value() if settings.credential_key else None
            ),
            settings.sync_timeout_seconds,
            settings.poll_interval_seconds,
        )

    @asynccontextmanager
    async def lifespan(app):
        try:
            yield
        finally:
            try:
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
