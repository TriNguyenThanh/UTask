"""Fixture xác định; integration chỉ dùng database test riêng."""

import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from google.adk.models import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.genai import types
from pydantic import PrivateAttr
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from infrastructure.db.tables import Base
from infrastructure.repositories import PostgresRequestRepository
from infrastructure.security import FernetCredentialVault
from models import BacklogGenerationRequest, BacklogInput
from models.context import ContextDocument
from models.security import Principal


@pytest.fixture
def payload():
    return BacklogGenerationRequest(
        intent="backlog_generation", input=BacklogInput(description="Audit")
    )


@pytest.fixture
def principal():
    return Principal("owner", "test-bearer")


@pytest.fixture
def vault():
    return FernetCredentialVault(Fernet.generate_key().decode())


@pytest.fixture
def repository():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Đặt TEST_DATABASE_URL cho PostgreSQL integration tests")
    if make_url(url).database != "ai_test":
        pytest.fail("Integration tests chỉ dùng database riêng tên ai_test")
    engine = create_engine(url, pool_size=10, max_overflow=10)
    schema = "test_" + uuid4().hex
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    scoped = engine.execution_options(schema_translate_map={None: schema})
    Base.metadata.create_all(scoped)
    repo = PostgresRequestRepository(sessionmaker(scoped, expire_on_commit=False))
    yield repo
    with engine.begin() as connection:
        connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    engine.dispose()


class AllowAuthorizer:
    async def authorize(self, principal, request):
        pass


class FakeAuthenticator:
    async def authenticate(self, bearer):
        from errors import failure

        if bearer not in {"owner", "other", "test-bearer"}:
            raise failure("AUTHENTICATION_REQUIRED", 401)
        return Principal("owner" if bearer == "test-bearer" else bearer, bearer)


class FakeGateway:
    async def fetch(self, domain, principal, request):
        return ContextDocument(
            domain=domain,
            as_of=datetime.now(UTC),
            status="available",
            data={"id": str(request.target.id)},
        )


class ScriptedModel(BaseLlm):
    """Test đi qua ADK thật, chỉ thay lời gọi LLM bên ngoài."""

    _responses: list = PrivateAttr()
    _calls: int = PrivateAttr(default=0)

    def __init__(self, responses):
        super().__init__(model="fake")
        self._responses = responses

    async def generate_content_async(self, llm_request, stream=False):
        self._calls += 1
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        if isinstance(item, types.Part):
            part = item
        else:
            part = types.Part(text=item)
        yield LlmResponse(
            content=types.Content(role="model", parts=[part]),
            usage_metadata=types.GenerateContentResponseUsageMetadata(candidates_token_count=10),
        )
