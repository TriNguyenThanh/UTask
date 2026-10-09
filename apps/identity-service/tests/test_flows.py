import hashlib
import json

import pytest
import requests
from allauth.account.models import EmailAddress, EmailConfirmation
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import UntypedToken

from accounts.models import AccountStatus, OutboxEvent, User, UserSession
from tests.helpers import NEW_PASSWORD, PASSWORD, create_user, login, mail_secret

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db,
    pytest.mark.postgres,
]


@pytest.fixture
def active_account(transactional_db):
    return create_user()


@pytest.fixture
def http_client(live_server):
    with requests.Session() as client:
        client.trust_env = False
        yield client


def http_login(client, base_url, user, password=PASSWORD, *, field="email"):
    client.headers.pop("Authorization", None)
    response = client.post(
        f"{base_url}/login",
        json={field: getattr(user, field), "password": password},
        timeout=10,
    )
    assert response.status_code == 200, response.json()
    client.headers["Authorization"] = "Bearer " + response.json()["data"]["access"]
    return response


@pytest.mark.http
@pytest.mark.django_db(transaction=True)
@pytest.mark.case_id(
    "TC_REG_001", "TC_PWD_010", "TC_AUTH_001", "TC_AUTH_009", "TC_AUTH_012", "TC_PROF_001"
)
def test_register_verify_login_me_refresh_logout(http_client, live_server, signup_data):
    client, base = http_client, live_server.url
    response = client.post(f"{base}/register", json=signup_data, timeout=10)
    assert response.status_code == 201, response.json()
    assert response.json()["data"]["user"]["roles"] == ["STUDENT"]
    assert response.json()["data"]["user"]["student_id"] is None
    user = User.objects.get(pk=response.json()["data"]["user"]["id"])
    assert user.account_status == AccountStatus.PENDING_ACTIVATION
    assert OutboxEvent.objects.filter(
        aggregate_id=user.pk, event_type="identity.user.created"
    ).exists()
    event = OutboxEvent.objects.get(
        aggregate_id=user.pk, event_type="identity.activation.requested"
    )
    key = mail_secret(event)["key"]
    assert key not in json.dumps(event.data)
    assert (
        EmailConfirmation.objects.get(email_address__user=user).key
        == hashlib.sha256(key.encode()).hexdigest()
    )
    assert (
        client.post(f"{base}/activate", json={"key": key}, timeout=10).status_code
        == 200
    )
    assert (
        client.post(f"{base}/activate", json={"key": key}, timeout=10).status_code
        == 404
    )
    user.refresh_from_db()
    assert user.is_active and user.is_email_verified

    response = http_login(client, base, user)
    access = UntypedToken(response.json()["data"]["access"])
    assert access["sub"] == str(user.pk)
    assert access["exp"] - access["iat"] <= 900
    session = UserSession.objects.get(user=user)
    cookie = next(cookie for cookie in response.cookies if cookie.name == "refresh_token")
    assert cookie.secure and cookie.has_nonstandard_attr("HttpOnly")
    assert cookie.get_nonstandard_attr("SameSite") == "Lax"
    original = cookie.value
    me = client.get(f"{base}/users/me", timeout=10)
    assert me.status_code == 200 and me.json()["data"]["id"] == str(user.pk)
    assert {"display_name", "roles", "student_id", "preferences"} <= me.json()["data"].keys()
    client.cookies.clear()
    refreshed = client.post(f"{base}/refresh", json={"refresh": original}, timeout=10)
    assert refreshed.status_code == 200, refreshed.json()
    new_refresh = refreshed.cookies["refresh_token"]
    assert new_refresh != original
    assert UntypedToken(new_refresh)["exp"] == UntypedToken(original)["exp"]
    session.refresh_from_db()
    assert UserSession.objects.filter(user=user).count() == 1
    assert session.refresh_token_hash == hashlib.sha256(new_refresh.encode()).hexdigest()
    assert session.refresh_jti == UntypedToken(new_refresh)["jti"]
    client.headers["Authorization"] = "Bearer " + refreshed.json()["data"]["access"]
    client.cookies.clear()
    logout = client.post(f"{base}/logout", json={"refresh": new_refresh}, timeout=10)
    assert logout.status_code == 200 and logout.json()["data"] is None
    assert "Max-Age=0" in logout.headers["Set-Cookie"]
    session.refresh_from_db()
    assert session.is_revoked
    revoked = client.get(f"{base}/users/me", timeout=10)
    assert revoked.status_code == 401 and revoked.headers["WWW-Authenticate"].startswith("Bearer")
    client.headers.pop("Authorization")
    assert (
        client.post(
            f"{base}/refresh", json={"refresh": new_refresh}, timeout=10
        ).status_code
        == 401
    )


@pytest.mark.http
@pytest.mark.django_db(transaction=True)
@pytest.mark.case_id("TC_PWD_001", "TC_PWD_003", "TC_PWD_005")
def test_forgot_reset_login_and_old_credentials_revoked(http_client, live_server, active_account):
    user, client, base = active_account, http_client, live_server.url
    response = http_login(client, base, user)
    old_refresh = response.cookies["refresh_token"]
    client.cookies.clear()
    forgot = client.post(
        f"{base}/password-reset/request", json={"email": user.email}, timeout=10
    )
    assert forgot.status_code == 200, forgot.json()
    event = OutboxEvent.objects.get(
        aggregate_id=user.pk, event_type="identity.password_reset.requested"
    )
    secret = mail_secret(event)
    assert forgot.json()["data"] is None
    assert secret["token"] not in json.dumps(forgot.json())
    reset_data = {**secret, "new_password1": NEW_PASSWORD, "new_password2": NEW_PASSWORD}
    reset = client.post(f"{base}/password-reset/confirm", json=reset_data, timeout=10)
    assert reset.status_code == 200, reset.json()
    assert client.get(f"{base}/users/me", timeout=10).status_code == 401
    client.headers.pop("Authorization")
    assert (
        client.post(
            f"{base}/refresh", json={"refresh": old_refresh}, timeout=10
        ).status_code
        == 401
    )
    assert (
        client.post(
            f"{base}/password-reset/confirm", json=reset_data, timeout=10
        ).status_code
        == 400
    )
    assert (
        client.post(
            f"{base}/login",
            json={"email": user.email, "password": PASSWORD},
            timeout=10,
        ).status_code
        == 401
    )
    http_login(client, base, user, NEW_PASSWORD, field="username")


@pytest.mark.parametrize(
    "state", ["unknown", AccountStatus.SUSPENDED, AccountStatus.PENDING_ACTIVATION, "deleted"]
)
def test_forgot_is_neutral_and_does_not_enqueue_ineligible_accounts(state):
    user = create_user()
    if state == "deleted":
        user.deleted_at = timezone.now()
    elif state not in {"unknown"}:
        user.account_status = state
    user.save()
    email = "unknown@example.edu.vn" if state == "unknown" else user.email
    response = APIClient().post(
        "/password-reset/request", {"email": email}, format="json"
    )
    assert response.status_code == 200
    assert not OutboxEvent.objects.filter(event_type="identity.password_reset.requested").exists()


@pytest.mark.http
@pytest.mark.django_db(transaction=True)
@pytest.mark.case_id("TC_PWD_006")
def test_change_password_revokes_current_and_other_devices(
    http_client, live_server, active_account
):
    user, first, base = active_account, http_client, live_server.url
    with requests.Session() as second:
        second.trust_env = False
        first_login = http_login(first, base, user)
        second_login = http_login(second, base, user)
        first.cookies.clear()
        response = first.post(
            f"{base}/password-change",
            json={
                "old_password": PASSWORD,
                "new_password1": NEW_PASSWORD,
                "new_password2": NEW_PASSWORD,
            },
            timeout=10,
        )
        assert response.status_code == 200, response.json()
        for client, logged_in in [(first, first_login), (second, second_login)]:
            assert client.get(f"{base}/users/me", timeout=10).status_code == 401
            client.headers.pop("Authorization")
            client.cookies.clear()
            assert (
                client.post(
                    f"{base}/refresh",
                    json={"refresh": logged_in.cookies["refresh_token"]},
                    timeout=10,
                ).status_code
                == 401
            )
        assert (
            first.post(
                f"{base}/login",
                json={"email": user.email, "password": PASSWORD},
                timeout=10,
            ).status_code
            == 401
        )
        http_login(first, base, user, NEW_PASSWORD)


@pytest.mark.parametrize(
    "updates",
    [
        {"student_id": "OTHER-123"},
        {"roles": ["SYSTEM_ADMIN"]},
        {"password1": "weak", "password2": "weak"},
    ],
)
def test_register_rejects_identity_privilege_or_weak_password(updates, signup_data):
    data = {**signup_data, **updates}
    response = APIClient().post("/register", data, format="json")
    assert response.status_code == 400
    assert not User.objects.filter(email=data["email"]).exists()


def test_resend_invalidates_old_activation_and_imported_user_sets_password():
    user = User.objects.create_user(
        email="imported@example.edu.vn",
        username="imported",
        password=None,
        account_status=AccountStatus.PENDING_ACTIVATION,
    )
    EmailAddress.objects.create(user=user, email=user.email, verified=False, primary=True)
    client = APIClient()
    client.post("/activation/resend", {"email": user.email}, format="json")
    old_key = mail_secret(OutboxEvent.objects.latest("created_at"))["key"]
    client.post("/activation/resend", {"email": user.email}, format="json")
    new_key = mail_secret(OutboxEvent.objects.latest("created_at"))["key"]
    assert old_key != new_key
    assert (
        client.post(
            "/activate",
            {"key": old_key, "new_password1": PASSWORD, "new_password2": PASSWORD},
            format="json",
        ).status_code
        == 404
    )
    response = client.post(
        "/activate",
        {"key": new_key, "new_password1": PASSWORD, "new_password2": PASSWORD},
        format="json",
    )
    assert response.status_code == 200, response.json()
    login(client, user)


def test_missing_mail_key_rolls_back_signup_equally_for_recovery(settings, signup_data):
    settings.IDENTITY_MAIL_KEY = None
    client = APIClient()
    response = client.post("/register", signup_data, format="json")
    assert response.status_code == 503
    assert not User.objects.filter(email=signup_data["email"]).exists()
    assert (
        client.post(
            "/password-reset/request",
            {"email": "unknown@example.edu.vn"},
            format="json",
        ).status_code
        == 503
    )
