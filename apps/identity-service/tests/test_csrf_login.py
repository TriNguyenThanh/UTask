"""Login issues CSRF cookies through the real response middleware."""

from unittest.mock import patch
from uuid import uuid4

import pytest
from rest_framework import serializers
from rest_framework.test import APIClient

from accounts.models import User
from authentication.views.auth import LoginView


@pytest.mark.unit
def test_fresh_browser_login_issues_csrf_without_visiting_swagger(settings):
    class Credentials(serializers.Serializer):
        def validate(self, attrs):
            return {"user": User(id=uuid4(), email="csrf@example.invalid")}

    class Tokens(serializers.Serializer):
        access = serializers.CharField()
        refresh = serializers.CharField()

    client = APIClient(enforce_csrf_checks=True)
    with (
        patch.object(LoginView, "serializer_class", Credentials),
        patch.object(LoginView, "get_response_serializer", return_value=Tokens),
        patch("dj_rest_auth.views.jwt_encode", return_value=("access", "refresh")),
    ):
        response = client.post("/login", {}, format="json", secure=True)
    assert response.status_code == 200
    assert response.cookies[settings.CSRF_COOKIE_NAME].value
    assert response.cookies[settings.CSRF_COOKIE_NAME]["secure"]
    assert response.cookies["refresh_token"]["httponly"]
    assert response["Cache-Control"] == "no-store"
