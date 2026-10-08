import hashlib
from datetime import timedelta
from unittest.mock import patch

import pytest
from allauth.account.forms import default_token_generator
from allauth.account.utils import user_pk_to_url_str
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
from rest_framework_simplejwt.tokens import UntypedToken

from accounts.models import UserSession
from authentication.adapters.session_tokens import FamilyRefreshToken
from tests.helpers import NEW_PASSWORD, create_user, login, refresh_from_body

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db,
    pytest.mark.postgres,
]


def test_rotation_caps_access_refresh_and_cookie_at_absolute_deadline():
    user = create_user()
    client = APIClient()
    raw = login(client, user).cookies["refresh_token"].value
    token = FamilyRefreshToken(raw)
    deadline = timezone.now() + timedelta(seconds=120)
    token["exp"] = token["family_exp"] = int(deadline.timestamp())
    shortened = str(token)
    UserSession.objects.filter(user=user).update(
        expires_at=deadline, refresh_token_hash=hashlib.sha256(shortened.encode()).hexdigest()
    )
    OutstandingToken.objects.filter(jti=token["jti"]).update(token=shortened)
    response = refresh_from_body(client, shortened)
    assert response.status_code == 200
    assert UntypedToken(response.cookies["refresh_token"].value)["exp"] == token["exp"]
    assert UntypedToken(response.json()["data"]["access"])["exp"] <= token["exp"]
    assert int(response.cookies["refresh_token"]["max-age"]) <= 120


def test_reset_generator_expires_at_fifteen_minutes():
    user = create_user()
    before = user.password
    token = default_token_generator.make_token(user)
    future = default_token_generator._now() + timedelta(minutes=16)
    with patch.object(default_token_generator, "_now", return_value=future):
        response = APIClient().post(
            "/api/v1/auth/password-reset/confirm",
            {
                "uid": user_pk_to_url_str(user),
                "token": token,
                "new_password1": NEW_PASSWORD,
                "new_password2": NEW_PASSWORD,
            },
            format="json",
        )
    assert response.status_code == 400
    user.refresh_from_db()
    assert user.password == before
