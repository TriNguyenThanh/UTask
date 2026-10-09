import asyncio
from unittest.mock import AsyncMock, Mock

import pytest

import main


@pytest.mark.parametrize("case", ["ok", "app_error", "close_error"])
async def test_api_lifespan_releases_http_and_database_even_on_failure(monkeypatch, case):
    client = Mock(aclose=AsyncMock())
    if case == "close_error":
        client.aclose.side_effect = RuntimeError("close failed")
    engine = Mock()
    stopped = asyncio.Event()

    async def listen():
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()

    listener = Mock(run=listen)
    monkeypatch.setattr(main.httpx, "AsyncClient", lambda: client)
    monkeypatch.setattr(main, "build_repository", lambda settings: (Mock(), engine))
    app = main.create_app(completion_listener=listener)

    async def lifespan():
        async with app.router.lifespan_context(app):
            await asyncio.sleep(0)
            if case == "app_error":
                raise RuntimeError("app failed")

    if case == "ok":
        await lifespan()
    else:
        with pytest.raises(RuntimeError):
            await lifespan()
    client.aclose.assert_awaited_once()
    engine.dispose.assert_called_once()
    assert stopped.is_set()
