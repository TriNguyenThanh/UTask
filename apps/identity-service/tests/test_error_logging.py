import logging
from types import SimpleNamespace

import pytest
from rest_framework.exceptions import ValidationError

from common.errors import IdentityAPIError
from common.exception_handler import identity_exception_handler, logger

pytestmark = pytest.mark.unit


@pytest.fixture
def api_logs(caplog, monkeypatch):
    monkeypatch.setattr(logger, "propagate", True)
    caplog.set_level(logging.WARNING, logger=logger.name)
    return caplog


def test_validation_log_has_code_without_request_values_or_traceback(api_logs):
    request = SimpleNamespace(
        method="POST", path="/login", data={"password": "INPUT_SECRET_CANARY"}
    )
    response = identity_exception_handler(
        ValidationError({"password": ["INPUT_SECRET_CANARY"]}), {"request": request}
    )
    assert response.status_code == 400
    assert api_logs.records[-1].levelno == logging.WARNING
    assert "code=VALIDATION_ERROR" in api_logs.text
    assert "INPUT_SECRET_CANARY" not in api_logs.text
    assert "File " not in api_logs.text


def test_server_log_preserves_public_reason_and_cause_location_without_secret_messages(api_logs):
    try:
        try:
            raise ValueError("CAUSE_SECRET_CANARY")
        except ValueError as cause:
            raise IdentityAPIError(
                "IDENTITY_UNAVAILABLE", "Mail encryption is not configured.", status_code=503
            ) from cause
    except IdentityAPIError as exc:
        response = identity_exception_handler(exc, {})
    assert response.status_code == 503
    assert api_logs.records[-1].levelno == logging.ERROR
    assert "Mail encryption is not configured." in api_logs.text
    assert "IdentityAPIError:" in api_logs.text and "ValueError:" in api_logs.text
    assert "test_error_logging.py" in api_logs.text
    assert "CAUSE_SECRET_CANARY" not in api_logs.text


def test_unexpected_error_log_hides_exception_value_and_keeps_generic_response(api_logs):
    try:
        raise RuntimeError("UNEXPECTED_SECRET_CANARY")
    except RuntimeError as exc:
        response = identity_exception_handler(exc, {})
    assert response.status_code == 500
    assert response.data["error"] == {"code": "INTERNAL_SERVER_ERROR", "details": []}
    assert api_logs.records[-1].levelno == logging.ERROR
    assert "RuntimeError:" in api_logs.text
    assert "UNEXPECTED_SECRET_CANARY" not in api_logs.text
