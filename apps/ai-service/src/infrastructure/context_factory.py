"""Lắp cùng nguồn quyền/context cho API và worker, không đổi pipeline."""

import httpx

from config import Settings

from .context_fixtures import FixtureContextAdapter
from .context_http import InternalContextAdapter


def build_context_adapter(
    settings: Settings, client: httpx.AsyncClient
) -> FixtureContextAdapter | InternalContextAdapter:
    if settings.mock_test:
        return FixtureContextAdapter(settings)
    return InternalContextAdapter(settings, client)
