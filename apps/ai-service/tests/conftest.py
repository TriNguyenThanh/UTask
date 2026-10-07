from collections.abc import AsyncIterator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from main import create_app
from models import BacklogResult, CreateAiRequest


class FakeProvider:
    def __init__(self, result: BacklogResult) -> None:
        self.result = result

    async def generate(self, request: CreateAiRequest) -> BacklogResult:
        del request
        return self.result


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as test_client:
        yield test_client


@pytest_asyncio.fixture
async def configured_client() -> AsyncIterator[AsyncClient]:
    app = create_app(
        provider=FakeProvider(
            BacklogResult(
                items=[],
                warnings=["Bootstrap provider chỉ dùng cho test."],
            )
        )
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as test_client:
        yield test_client
