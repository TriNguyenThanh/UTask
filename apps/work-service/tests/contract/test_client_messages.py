from uuid import uuid4

import pytest
from django.db import transaction
from rest_framework.exceptions import (
    ErrorDetail,
    NotAuthenticated,
    ParseError,
    Throttled,
    ValidationError,
)

from apps.messaging.models import IdempotencyRecord
from apps.messaging.services.receipts import claim_receipt, replay_response, save_receipt
from common.errors import WorkError
from common.exception_handler import exception_handler
from common.responses import build_envelope

pytestmark = pytest.mark.contract


@pytest.mark.parametrize(
    "issue",
    [
        "This value does not match the required pattern.",
        '<ul class="errorlist"><li>Enter a valid UUID.</li></ul>',
        "database driver diagnostic: hidden",
    ],
)
def test_framework_and_business_validation_issues_are_plain_vietnamese(issue):
    for exception in [
        ValidationError({"color": [ErrorDetail(issue, code="invalid")]}),
        WorkError(
            "VALIDATION_ERROR",
            "Thông tin không hợp lệ.",
            details=[{"field": "color", "issue": issue}],
        ),
    ]:
        reply = exception_handler(exception, {})
        detail = reply.data["error"]["details"][0]
        assert reply.status_code == 400 and detail["field"] == "color"
        assert detail["issue"] == (
            "Giá trị không đúng định dạng yêu cầu."
            if issue.startswith("This value")
            else "Giá trị không hợp lệ. Vui lòng kiểm tra lại thông tin."
        )
        assert "<" not in detail["issue"] and "hidden" not in str(reply.data)


def test_framework_headers_and_json_parser_diagnostics_are_preserved_or_hidden():
    unauthenticated = NotAuthenticated()
    unauthenticated.auth_header = "Bearer"
    denied = exception_handler(unauthenticated, {})
    assert denied.status_code == 401 and denied["WWW-Authenticate"] == "Bearer"
    throttled = exception_handler(Throttled(wait=7), {})
    assert throttled.status_code == 429 and throttled["Retry-After"] == "7"
    assert throttled.data["message"] == "Bạn đã gửi quá nhiều yêu cầu. Vui lòng chờ rồi thử lại."
    malformed = exception_handler(ParseError("JSON parse error - hidden-decoder-detail"), {})
    assert malformed.status_code == 400 and "hidden-decoder-detail" not in str(malformed.data)
    assert malformed.data["message"] == "Dữ liệu yêu cầu gửi lên không đúng định dạng."


@pytest.mark.django_db(transaction=True)
def test_receipt_message_commits_with_result_and_replay_keeps_original_envelope(actors):
    scope = {
        "user_id": actors["leader"],
        "http_method": "POST",
        "endpoint_path": "/api/v1/projects/",
        "idempotency_key": "outcome-message",
    }
    with transaction.atomic():
        claim_receipt(scope, {})
        first = save_receipt(scope, {}, {"id": str(uuid4())}, status=201, message="Đã tạo dự án.")
    saved = IdempotencyRecord.objects.get()
    assert saved.response_body == first.data and saved.response_body["message"] == "Đã tạo dự án."
    assert replay_response(saved).data == first.data
    with transaction.atomic():
        replay = save_receipt(scope, {}, {"unexpected": True}, message="Đã đổi thông tin.")
    assert replay.status_code == 201 and replay.data == first.data
    legacy_scope = scope | {"idempotency_key": "legacy-call"}
    with transaction.atomic():
        legacy = save_receipt(legacy_scope, {}, {"saved": True})
    assert legacy.data == build_envelope({"saved": True})
