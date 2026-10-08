"""Browser refresh/logout exercise Django CSRF, Origin and cookie policy end to end."""

import pytest
from django.middleware.csrf import get_token
from django.test import RequestFactory
from rest_framework.test import APIClient
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
from rest_framework_simplejwt.tokens import UntypedToken

from accounts.models import AuditLog, UserSession
from tests.helpers import create_user, login

pytestmark = [pytest.mark.integration, pytest.mark.django_db, pytest.mark.postgres]
ENDPOINTS = ["refresh", "logout", "logout-all"]


@pytest.fixture
def browser_session(settings):
    settings.CSRF_TRUSTED_ORIGINS = []
    user = create_user()
    client = APIClient(enforce_csrf_checks=True)
    response = login(client, user)
    token = get_token(RequestFactory().get("/"))
    client.cookies[settings.CSRF_COOKIE_NAME] = token
    return user, client, token, response.cookies["refresh_token"].value


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_cookie_mutation_accepts_valid_csrf_and_same_origin(browser_session, endpoint):
    user, client, csrf, raw = browser_session
    before = UserSession.objects.get(user=user)
    response = client.post(
        f"/api/v1/auth/{endpoint}",
        {},
        format="json",
        secure=True,
        HTTP_X_CSRFTOKEN=csrf,
        HTTP_ORIGIN="https://testserver",
    )

    assert response.status_code == 200, response.json()
    before.refresh_from_db()
    cookie = response.cookies["refresh_token"]
    if endpoint == "refresh":
        assert cookie.value != raw
        assert cookie["httponly"] and cookie["secure"] and cookie["samesite"] == "Lax"
        assert cookie["path"] == "/api/v1/auth"
        assert UntypedToken(cookie.value)["family_exp"] == UntypedToken(raw)["family_exp"]
        assert UserSession.objects.filter(user=user).count() == 1
        assert not before.is_revoked
        assert client.get("/api/v1/users/me").status_code == 200
    else:
        assert cookie["max-age"] == 0
        assert before.is_revoked
        assert client.get("/api/v1/users/me").status_code == 401
    assert BlacklistedToken.objects.filter(token__jti=UntypedToken(raw)["jti"]).exists()


@pytest.mark.parametrize("endpoint", ENDPOINTS)
@pytest.mark.parametrize(
    "fault", ["missing-token", "wrong-token", "foreign-origin", "foreign-referer"]
)
def test_cookie_mutation_rejects_csrf_or_origin_without_side_effects(
    browser_session, endpoint, fault
):
    user, client, csrf, _ = browser_session
    before = UserSession.objects.get(user=user)
    original_hash = before.refresh_token_hash
    audit_count = AuditLog.objects.count()
    headers = {"HTTP_X_CSRFTOKEN": csrf, "HTTP_ORIGIN": "https://testserver"}
    if fault == "missing-token":
        headers.pop("HTTP_X_CSRFTOKEN")
    elif fault == "wrong-token":
        headers["HTTP_X_CSRFTOKEN"] = "a" * 32 if csrf != "a" * 32 else "b" * 32
    elif fault == "foreign-origin":
        headers["HTTP_ORIGIN"] = "https://untrusted.example"
    else:
        headers.pop("HTTP_ORIGIN")
        headers["HTTP_REFERER"] = "https://untrusted.example/"

    response = client.post(f"/api/v1/auth/{endpoint}", {}, format="json", secure=True, **headers)

    assert response.status_code == 403
    assert response.json()["error"] == {"code": "PERMISSION_DENIED", "details": []}
    before.refresh_from_db()
    assert not before.is_revoked
    assert before.refresh_token_hash == original_hash
    assert not BlacklistedToken.objects.filter(token__user=user).exists()
    assert AuditLog.objects.count() == audit_count


@pytest.mark.parametrize("endpoint", ["refresh", "logout"])
def test_cookie_and_body_conflict_is_rejected_without_mutation(browser_session, endpoint):
    user, client, csrf, raw = browser_session
    before = UserSession.objects.get(user=user).refresh_token_hash
    response = client.post(
        f"/api/v1/auth/{endpoint}",
        {"refresh": raw + "x"},
        format="json",
        secure=True,
        HTTP_X_CSRFTOKEN=csrf,
        HTTP_ORIGIN="https://testserver",
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert UserSession.objects.get(user=user).refresh_token_hash == before
    assert not BlacklistedToken.objects.filter(token__user=user).exists()
