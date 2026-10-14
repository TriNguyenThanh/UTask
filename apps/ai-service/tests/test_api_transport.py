from uuid import uuid4

import pytest
from conftest import FakeAuthenticator
from httpx import ASGITransport, AsyncClient

from main import create_app


@pytest.mark.asyncio
async def test_http_auth_validation_trace_and_health():
    app = create_app(authenticator=FakeAuthenticator())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        trace = str(uuid4())
        health = await client.get("/healthz", headers={"X-Request-ID": trace})
        assert health.json() == {"status": "ok"} and health.headers["X-Request-ID"] == trace
        forged = await client.get(
            "/api/ai/v1/requests/" + str(uuid4()), headers={"X-Authenticated-User-ID": "owner"}
        )
        assert forged.status_code == 401
        assert forged.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"
        assert forged.headers["X-Request-ID"]
        response = await client.post(
            "/api/ai/v1/requests",
            headers={"Authorization": "Bearer owner"},
            json={"intent": "unknown", "input": {}},
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "INVALID_INPUT"
        assert "input" not in response.json()["error"]["details"]
        bad = await client.get(
            "/api/ai/v1/requests/not-uuid", headers={"Authorization": "Bearer owner"}
        )
        assert bad.status_code == 422


@pytest.mark.asyncio
async def test_internal_error_is_sanitized_and_has_trace_id():
    class Broken:
        async def get_request(self, *args, **kwargs):
            raise ValueError("token/database secret")

    app = create_app(application=Broken(), authenticator=FakeAuthenticator())
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test"
    ) as client:
        result = await client.get(
            "/api/ai/v1/requests/" + str(uuid4()), headers={"Authorization": "Bearer owner"}
        )
        assert result.status_code == 500 and "secret" not in result.text
        assert result.json()["error"]["code"] == "INTERNAL_ERROR"
