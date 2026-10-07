import pytest
from httpx import AsyncClient

HEADERS = {
    "X-Authenticated-User-ID": "user-1",
    "Idempotency-Key": "request-1",
}
PAYLOAD = {
    "intent": "backlog_generation",
    "input": {"description": "Nền tảng đặt lịch phòng họp"},
}


@pytest.mark.asyncio
async def test_request_requires_authenticated_identity(client: AsyncClient) -> None:
    response = await client.post(
        "/api/ai/v1/requests", headers={"Idempotency-Key": "request-1"}, json=PAYLOAD
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"

@pytest.mark.asyncio
async def test_request_fails_closed_when_provider_is_unconfigured(client: AsyncClient) -> None:
    response = await client.post("/api/ai/v1/requests", headers=HEADERS, json=PAYLOAD)

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "PROVIDER_UNAVAILABLE"
    assert response.json()["error"]["request_id"]


@pytest.mark.asyncio
async def test_request_rejects_idempotency_reuse_with_different_payload(
    client: AsyncClient,
) -> None:
    first = await client.post("/api/ai/v1/requests", headers=HEADERS, json=PAYLOAD)
    assert first.status_code == 502

    second = await client.post(
        "/api/ai/v1/requests",
        headers=HEADERS,
        json={**PAYLOAD, "input": {"description": "Nội dung khác"}},
    )

    assert second.status_code == 409
    assert second.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"


@pytest.mark.asyncio
async def test_request_status_is_owned_by_requester(client: AsyncClient) -> None:
    response = await client.post("/api/ai/v1/requests", headers=HEADERS, json=PAYLOAD)
    request_id = response.json()["error"]["request_id"]

    hidden = await client.get(
        f"/api/ai/v1/requests/{request_id}",
        headers={"X-Authenticated-User-ID": "another-user"},
    )
    visible = await client.get(
        f"/api/ai/v1/requests/{request_id}",
        headers={"X-Authenticated-User-ID": "user-1"},
    )

    assert hidden.status_code == 404
    assert visible.status_code == 200
    assert visible.json()["status"] == "failed"


@pytest.mark.asyncio
async def test_request_validation_rejects_unknown_intent(client: AsyncClient) -> None:
    response = await client.post(
        "/api/ai/v1/requests",
        headers=HEADERS,
        json={"intent": "unknown", "input": {}},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_configured_provider_returns_typed_success(configured_client: AsyncClient) -> None:
    response = await configured_client.post("/api/ai/v1/requests", headers=HEADERS, json=PAYLOAD)

    assert response.status_code == 200
    assert response.json()["status"] == "succeeded"
    assert response.json()["result"]["items"] == []
