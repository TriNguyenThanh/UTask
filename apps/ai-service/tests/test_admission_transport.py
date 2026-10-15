"""Giới hạn tiếp nhận giữ error envelope v1 và không đổi lỗi budget."""

import json
from uuid import uuid4

import pytest
from conftest import AllowAuthorizer, FakeAuthenticator
from fastapi import Request
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from test_contract import validate

from api.exception_handlers import error_response
from application import AiApplicationService
from errors import ServiceError, failure
from infrastructure.db.tables import DeliveryRow, RequestRow
from main import create_app


@pytest.mark.parametrize("reason", ["REQUEST_RATE_LIMIT", "ACTIVE_REQUEST_LIMIT"])
def test_admission_error_has_retry_after_and_contract_envelope(reason):
    request = Request({"type": "http"})
    request.state.trace_id = str(uuid4())
    response = error_response(
        request,
        ServiceError(
            "RATE_LIMITED",
            "Vượt giới hạn tiếp nhận.",
            429,
            retryable=True,
            details={"reason": reason, "retry_after_seconds": 5},
        ),
    )
    body = json.loads(response.body)
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "5"
    assert body["error"]["request_id"] == request.state.trace_id
    assert body["error"]["retryable"] is True
    validate("ErrorResponse", body)


@pytest.mark.parametrize("retry_after", [None, 0, -1, True, "5", 1.5])
def test_invalid_retry_after_does_not_become_http_header(retry_after):
    response = error_response(
        Request({"type": "http"}),
        ServiceError(
            "RATE_LIMITED",
            "Vượt giới hạn.",
            429,
            details={"reason": "REQUEST_RATE_LIMIT", "retry_after_seconds": retry_after},
        ),
    )
    assert response.status_code == 429
    assert "Retry-After" not in response.headers


@pytest.mark.parametrize("code,status", [("BUDGET_EXCEEDED", 429), ("INTERNAL_ERROR", 500)])
def test_existing_errors_keep_envelope_without_admission_retry_header(code, status):
    error = failure(code, status)
    error.details["retry_after_seconds"] = 5
    request = Request({"type": "http"})
    request.state.trace_id = str(uuid4())
    response = error_response(request, error)
    assert response.status_code == status
    assert "Retry-After" not in response.headers
    body = json.loads(response.body)
    assert body["error"]["code"] == ("RATE_LIMITED" if code == "BUDGET_EXCEEDED" else code)
    if code == "BUDGET_EXCEEDED":
        assert body["error"]["details"]["reason"] == code
    validate("ErrorResponse", body)


@pytest.mark.parametrize(
    "rate,active,reason",
    [(1, 2, "REQUEST_RATE_LIMIT"), (5, 1, "ACTIVE_REQUEST_LIMIT")],
)
async def test_post_limits_new_job_but_replay_and_polling_remain_available(
    repository, payload, vault, rate, active, reason
):
    repository.requests_per_minute = rate
    repository.max_active_requests_per_user = active
    service = AiApplicationService(repository, AllowAuthorizer(), vault, sync_timeout=0)
    app = create_app(application=service, authenticator=FakeAuthenticator())
    headers = {"Authorization": "Bearer owner", "Idempotency-Key": "first"}
    body = payload.model_dump(mode="json")
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            first = await client.post("/api/ai/v1/requests", headers=headers, json=body)
            assert first.status_code == 202
            denied = await client.post(
                "/api/ai/v1/requests",
                headers={**headers, "Idempotency-Key": "new-key"},
                json=body,
            )
            assert denied.status_code == 429
            assert denied.json()["error"]["code"] == "RATE_LIMITED"
            assert denied.json()["error"]["details"]["reason"] == reason
            assert int(denied.headers["Retry-After"]) > 0
            assert denied.json()["error"]["retryable"] is True
            validate("ErrorResponse", denied.json())
            replay = await client.post("/api/ai/v1/requests", headers=headers, json=body)
            assert replay.status_code == 202
            assert replay.json()["request_id"] == first.json()["request_id"]
            polled = await client.get(first.json()["status_url"], headers=headers)
            assert polled.status_code == 200
            changed = {**body, "input": {"description": "Different"}}
            conflict = await client.post("/api/ai/v1/requests", headers=headers, json=changed)
            assert conflict.status_code == 409
            assert "Retry-After" not in conflict.headers
    with repository.sessions() as session:
        assert session.scalar(select(func.count()).select_from(RequestRow)) == 1
        assert session.scalar(select(func.count()).select_from(DeliveryRow)) == 1
