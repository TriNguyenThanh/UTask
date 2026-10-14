import pytest
from rest_framework.exceptions import (
    ErrorDetail,
    NotAuthenticated,
    ParseError,
    Throttled,
    ValidationError,
)

from common.errors import WorkError
from common.exception_handler import exception_handler

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
