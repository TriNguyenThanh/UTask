from uuid import uuid4

import pytest
from conftest import FakeAuthenticator
from httpx import ASGITransport, AsyncClient

from main import create_app
from models.logging_context import request_id_context


@pytest.mark.parametrize("broken", [False, True])
async def test_api_binds_and_resets_trace_for_success_and_failure(broken):
    trace = str(uuid4())
    observed = []

    class Application:
        async def get_request(self, *args, **kwargs):
            observed.append(request_id_context.get())
            if broken:
                raise ValueError("private")
            from errors import failure

            raise failure("REQUEST_NOT_FOUND", 404)

    app = create_app(application=Application(), authenticator=FakeAuthenticator())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            f"/api/ai/v1/requests/{uuid4()}",
            headers={"Authorization": "Bearer owner", "X-Request-ID": trace},
        )
    assert observed == [trace]
    assert response.status_code == (500 if broken else 404)
    assert response.headers["X-Request-ID"] == trace
    assert request_id_context.get() is None
