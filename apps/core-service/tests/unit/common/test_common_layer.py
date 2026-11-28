"""Unit tests for the unified common/ layer (errors, handler, renderer, parser, pagination)."""

import io

import pytest
from django.core.exceptions import RequestDataTooBig
from rest_framework.exceptions import ParseError, Throttled, ValidationError
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory
from rest_framework_simplejwt.exceptions import InvalidToken

from common.errors import CoreAPIError
from common.exception_handler import core_exception_handler, format_validation_issue
from common.json_validation import has_excessive_json_nesting
from common.parsers import StrictJSONParser
from common.renderers import EnvelopeJSONRenderer

pytestmark = pytest.mark.unit


def test_exception_handler_unifies_rate_limit_and_token_codes():
    req = APIRequestFactory().get("/api/work/projects/")

    throttled_resp = core_exception_handler(Throttled(wait=30), {"request": req})
    assert throttled_resp.status_code == 429
    assert throttled_resp.data["success"] is False
    assert throttled_resp.data["error"]["code"] == "RATE_LIMIT_EXCEEDED"

    expired_resp = core_exception_handler(InvalidToken(code="TOKEN_EXPIRED"), {"request": req})
    assert expired_resp.status_code == 401
    assert expired_resp.data["error"]["code"] == "TOKEN_EXPIRED"

    too_big_resp = core_exception_handler(RequestDataTooBig(), {"request": req})
    assert too_big_resp.status_code == 400
    assert too_big_resp.data["error"]["code"] == "VALIDATION_ERROR"


def test_exception_handler_translates_validation_and_blocks_html():
    req = APIRequestFactory().post("/api/classroom/courses/")
    resp = core_exception_handler(
        ValidationError(
            {"code": ["This field is required."], "bio": ["<script>alert(1)</script>"]}
        ),
        {"request": req},
    )
    assert resp.status_code == 400
    details = resp.data["error"]["details"]
    assert {"field": "code", "issue": "Trường này là bắt buộc."} in details
    assert any(item["field"] == "bio" and "<script>" not in item["issue"] for item in details)
    assert format_validation_issue("Unknown raw English failure") == (
        "Giá trị không hợp lệ. Vui lòng kiểm tra lại thông tin."
    )


def test_core_api_error_supports_positional_and_keyword_status():
    err1 = CoreAPIError("CONFLICT", "Xung đột dữ liệu.", 409)
    err2 = CoreAPIError("FORBIDDEN", "Không có quyền.", status_code=403)
    assert err1.status_code == 409
    assert err2.status_code == 403


def test_envelope_renderer_handles_library_detail_and_passthrough():
    renderer = EnvelopeJSONRenderer()
    rendered_detail = renderer.render({"detail": "Successfully logged out."})
    assert b'"success":true' in rendered_detail
    assert b'"data":null' in rendered_detail

    pre_wrapped = {
        "success": True,
        "message": "OK",
        "data": {"id": 1},
        "meta": None,
        "error": None,
    }
    assert b'"id":1' in renderer.render(pre_wrapped)


def test_strict_json_parser_blocks_excessive_nesting():
    nested: dict = {}
    cur = nested
    for _ in range(105):
        nxt: dict = {}
        cur["a"] = nxt
        cur = nxt
    assert has_excessive_json_nesting(nested) is True

    raw = (b'{"a":' * 105) + b"{}" + (b"}" * 105)
    parser = StrictJSONParser()
    with pytest.raises(ParseError):
        parser.parse(io.BytesIO(raw))
    _ = Request(APIRequestFactory().post("/"))
