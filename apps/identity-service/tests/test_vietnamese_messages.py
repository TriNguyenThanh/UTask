"""Public responses localize both framework validation and library outcomes."""

import json

import pytest
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed, ParseError, ValidationError
from rest_framework.response import Response
from rest_framework.test import APIClient

from common.exception_handler import identity_exception_handler
from common.renderers import EnvelopeJSONRenderer

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "data,field,issue",
    [
        ({}, "email", "Trường này là bắt buộc."),
        ({"email": "not-an-email"}, "email", "Nhập một địa chỉ email hợp lệ."),
    ],
)
def test_native_serializer_validation_is_vietnamese(data, field, issue):
    class Input(serializers.Serializer):
        email = serializers.EmailField()

    serializer = Input(data=data)
    assert not serializer.is_valid()
    result = identity_exception_handler(ValidationError(serializer.errors), {})
    assert result.status_code == 400
    assert result.data["error"]["details"] == [{"field": field, "issue": issue}]


def test_library_password_validation_preserves_nested_field_path():
    result = identity_exception_handler(
        ValidationError(
            {
                "credentials": {
                    "old_password": [
                        "Your old password was entered incorrectly. Please enter it again."
                    ]
                }
            }
        ),
        {},
    )
    assert result.data["error"]["details"] == [
        {
            "field": "credentials.old_password",
            "issue": "Mật khẩu hiện tại không đúng. Vui lòng nhập lại.",
        }
    ]


def test_parser_failure_does_not_expose_raw_decoder_message():
    result = identity_exception_handler(ParseError("RAW_DECODER_SECRET"), {})
    assert result.status_code == 400
    assert "RAW_DECODER_SECRET" not in str(result.data)
    assert result.data["error"]["details"][0]["issue"].startswith("Không thể đọc nội dung")


def test_django_list_validation_preserves_useful_issues():
    result = identity_exception_handler(DjangoValidationError(["Mật khẩu quá ngắn."]), {})
    assert result.status_code == 400
    assert result.data["error"]["details"] == [{"field": "", "issue": "Mật khẩu quá ngắn."}]


@pytest.mark.parametrize("code", ["INVALID_CREDENTIALS", "TOKEN_REVOKED", "TOKEN_EXPIRED"])
def test_authentication_messages_never_forward_dependency_diagnostics(code):
    result = identity_exception_handler(
        AuthenticationFailed({"code": code, "message": "PRIVATE_DEPENDENCY_DETAIL"}),
        {},
    )
    assert result.status_code == 401
    assert result.data["error"]["code"] == code
    assert "PRIVATE_DEPENDENCY_DETAIL" not in result.data["message"]


@pytest.mark.parametrize(
    "detail,expected",
    [
        ("Successfully logged out.", "Đăng xuất thành công."),
        ("New password has been saved.", "Đổi mật khẩu thành công. Vui lòng đăng nhập lại."),
        ("Password has been reset with the new password.", "Đặt lại mật khẩu thành công."),
        (
            "Password reset e-mail has been sent.",
            "Nếu tài khoản đủ điều kiện, hướng dẫn đặt lại mật khẩu đã được đưa vào hàng đợi.",
        ),
    ],
)
def test_library_success_messages_use_one_vietnamese_envelope(detail, expected):
    result = json.loads(
        EnvelopeJSONRenderer().render(
            {"detail": detail}, renderer_context={"response": Response(status=200)}
        )
    )
    assert result == {
        "success": True,
        "message": expected,
        "data": None,
        "meta": None,
        "error": None,
    }
    assert json.loads(EnvelopeJSONRenderer().render(result)) == result


def test_real_public_validation_response_is_vietnamese():
    response = APIClient().post("/login", {}, format="json")
    assert response.status_code == 400
    assert response.json()["error"]["details"] == [
        {
            "field": "password",
            "issue": "Trường này là bắt buộc.",
        }
    ]


@pytest.mark.parametrize(
    "message",
    [
        "User is already registered with this e-mail address.",
        "A user is already registered with this e-mail address.",
    ],
)
def test_library_duplicate_email_keeps_field_and_vietnamese_issue(message):
    result = identity_exception_handler(ValidationError({"email": [message]}), {})
    assert result.status_code == 400
    assert result.data["error"]["details"] == [
        {"field": "email", "issue": "Email đã được sử dụng để đăng ký tài khoản."}
    ]
