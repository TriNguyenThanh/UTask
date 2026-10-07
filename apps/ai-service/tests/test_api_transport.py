from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient

PAYLOAD = {"intent": "backlog_generation", "input": {"description": "Project test"}}
HEADERS = {"X-Authenticated-User-ID": "user-1", "Idempotency-Key": "key-1"}


@pytest.mark.asyncio
async def test_middleware_preserves_client_trace_id(client: AsyncClient) -> None:
    response = await client.get("/healthz", headers={"X-Request-ID": "trace-123"})

    assert response.headers["X-Request-ID"] == "trace-123"


@pytest.mark.asyncio
async def test_middleware_adds_trace_id_to_error_response(client: AsyncClient) -> None:
    response = await client.post(
        "/api/ai/v1/requests", headers={"Idempotency-Key": "key-1"}, json=PAYLOAD
    )

    assert response.status_code == 401
    assert UUID(response.headers["X-Request-ID"])


@pytest.mark.asyncio
async def test_success_can_be_read_and_replayed(configured_client: AsyncClient) -> None:
    created = await configured_client.post("/api/ai/v1/requests", headers=HEADERS, json=PAYLOAD)
    repeated = await configured_client.post("/api/ai/v1/requests", headers=HEADERS, json=PAYLOAD)
    retrieved = await configured_client.get(
        f"/api/ai/v1/requests/{created.json()['request_id']}", headers=HEADERS
    )

    assert created.status_code == repeated.status_code == retrieved.status_code == 200
    assert created.json() == repeated.json() == retrieved.json()


@pytest.mark.asyncio
async def test_failed_request_replays_error_envelope(client: AsyncClient) -> None:
    created = await client.post("/api/ai/v1/requests", headers=HEADERS, json=PAYLOAD)
    repeated = await client.post("/api/ai/v1/requests", headers=HEADERS, json=PAYLOAD)

    assert created.status_code == repeated.status_code == 502
    assert created.json() == repeated.json()


@pytest.mark.asyncio
async def test_missing_idempotency_key_keeps_validation_error(client: AsyncClient) -> None:
    response = await client.post(
        "/api/ai/v1/requests",
        headers={"X-Authenticated-User-ID": "user-1"},
        json=PAYLOAD,
    )

    assert response.status_code == 422
    assert any(error["loc"] == ["header", "Idempotency-Key"] for error in response.json()["detail"])


@pytest.mark.asyncio
async def test_unknown_request_returns_stable_404(client: AsyncClient) -> None:
    response = await client.get(f"/api/ai/v1/requests/{uuid4()}", headers=HEADERS)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "REQUEST_NOT_FOUND"
