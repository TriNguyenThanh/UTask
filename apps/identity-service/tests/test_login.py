import hashlib
from datetime import timedelta

import pytest
from axes.models import AccessAttempt
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import AccountStatus, UserSession
from tests.helpers import PASSWORD, create_user, login

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db,
    pytest.mark.postgres,
]


def test_login_then_me_uses_real_library_chain():
    user = create_user(first_name="Linh", last_name="Tran")
    client = APIClient()
    response = login(client, user)
    body = response.json()
    assert set(body) == {"success", "message", "data", "meta", "error"}
    assert body["data"]["refresh"] == ""
    cookie = response.cookies["refresh_token"]
    assert cookie["httponly"] and cookie["secure"] and cookie["samesite"] == "Lax"
    session = UserSession.objects.get(user=user)
    assert session.refresh_token_hash == hashlib.sha256(cookie.value.encode()).hexdigest()
    assert session.expires_at - session.created_at <= timedelta(days=7)
    me = client.get("/api/v1/users/me")
    assert me.status_code == 200
    assert me.json()["data"]["id"] == str(user.pk)
    assert me.json()["data"]["roles"] == ["STUDENT"]
    assert "password" not in me.json()["data"]


@pytest.mark.parametrize("field", ["email", "username"])
def test_login_identifier_normalization(field):
    user = create_user()
    client = APIClient()
    response = client.post(
        "/api/v1/auth/login",
        {field: " " + getattr(user, field).upper() + " ", "password": PASSWORD},
        format="json",
    )
    assert response.status_code == 200


@pytest.mark.parametrize(
    "state,status,code",
    [
        (AccountStatus.SUSPENDED, 403, "ACCOUNT_SUSPENDED"),
        (AccountStatus.PENDING_ACTIVATION, 403, "ACCOUNT_PENDING_ACTIVATION"),
        ("deleted", 401, "INVALID_CREDENTIALS"),
        ("unusable", 401, "INVALID_CREDENTIALS"),
    ],
)
def test_unavailable_accounts_never_receive_credentials(state, status, code):
    user = create_user()
    if state == "deleted":
        user.deleted_at = timezone.now()
    elif state == "unusable":
        user.set_unusable_password()
    else:
        user.account_status = state
    user.save()
    response = APIClient().post(
        "/api/v1/auth/login", {"email": user.email, "password": PASSWORD}, format="json"
    )
    assert response.status_code == status
    assert response.json()["error"] == {"code": code, "details": []}
    assert response.json()["data"] is None
    assert "refresh_token" not in response.cookies
    assert not UserSession.objects.filter(user=user).exists()


@pytest.mark.parametrize("identifier", ["known", "unknown"])
def test_bad_password_does_not_enumerate_users(identifier):
    user = create_user()
    email = user.email if identifier == "known" else "unknown@example.edu.vn"
    response = APIClient().post(
        "/api/v1/auth/login", {"email": email, "password": "WrongPassword!"}, format="json"
    )
    assert response.status_code == 401
    assert response.json()["error"] == {"code": "INVALID_CREDENTIALS", "details": []}
    assert response["WWW-Authenticate"].startswith("Bearer")


def test_axes_five_failures_and_fixed_cooldown():
    user = create_user()
    client = APIClient()
    for i in range(5):
        response = client.post(
            "/api/v1/auth/login", {"email": user.email, "password": "WrongPassword!"}, format="json"
        )
        assert response.status_code == (429 if i == 4 else 401)
    attempt = AccessAttempt.objects.get(username=str(user.pk))
    timestamp, failures = attempt.attempt_time, attempt.failures_since_start
    response = client.post(
        "/api/v1/auth/login", {"email": user.email, "password": PASSWORD}, format="json"
    )
    assert response.status_code == 429
    assert response["Retry-After"] == "900"
    attempt.refresh_from_db()
    assert attempt.attempt_time == timestamp
    assert attempt.failures_since_start == failures
    AccessAttempt.objects.update(attempt_time=timezone.now() - timedelta(minutes=16))
    assert login(client, user).status_code == 200
