from uuid import uuid4

import pytest
from pydantic import TypeAdapter

from application.service import _fingerprint, _service_error_from_payload
from models import CreateAiRequest, ErrorPayload


def test_fingerprint_normalizes_key_order_and_default_fields() -> None:
    adapter = TypeAdapter(CreateAiRequest)
    first = adapter.validate_python(
        {"intent": "backlog_generation", "input": {"description": "Project", "goals": []}}
    )
    reordered = adapter.validate_python(
        {"input": {"description": "Project"}, "intent": "backlog_generation"}
    )
    changed = adapter.validate_python(
        {"intent": "backlog_generation", "input": {"description": "Other project"}}
    )

    assert _fingerprint(first) == _fingerprint(reordered)
    assert _fingerprint(first) != _fingerprint(changed)


@pytest.mark.parametrize(
    ("code", "status_code"), [("PROVIDER_UNAVAILABLE", 502), ("WORKFLOW_TIMEOUT", 504)]
)
@pytest.mark.parametrize("request_id", [None, uuid4()])
def test_replayed_error_preserves_payload_and_status(code, status_code, request_id) -> None:
    payload = ErrorPayload(
        code=code,
        message="Stored error",
        details={"reason": "provider"},
        request_id=request_id,
        retryable=True,
    )

    error = _service_error_from_payload(payload)

    assert error.code == code
    assert error.status_code == status_code
    assert error.message == payload.message
    assert error.details == payload.details
    assert error.retryable == payload.retryable
    assert error.request_id == (str(request_id) if request_id is not None else None)
