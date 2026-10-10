from unittest.mock import patch

import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
from rest_framework_simplejwt.tokens import UntypedToken

from accounts.models import AuditLog, UserSession
from tests.helpers import create_user, login, refresh_from_body, run_concurrent

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db,
    pytest.mark.postgres,
]


def test_replay_commits_family_revocation_and_blocks_child_access():
    user = create_user()
    client = APIClient()
    old = login(client, user).cookies["refresh_token"].value
    rotated = refresh_from_body(client, old)
    assert rotated.status_code == 200
    child = rotated.cookies["refresh_token"].value
    assert child != old
    assert UserSession.objects.filter(user=user).count() == 1
    assert BlacklistedToken.objects.filter(token__user=user).count() == 1
    replay = refresh_from_body(client, old)
    assert replay.status_code == 401
    assert replay.json()["error"]["code"] == "TOKEN_REPLAY_ATTACK_DETECTED"
    assert UserSession.objects.get(user=user).revoked_reason == "REPLAY_ATTACK"
    assert AuditLog.objects.filter(
        action="SECURITY_TOKEN_REPLAY_DETECTED", target_user_id=str(user.pk)
    ).exists()
    client.credentials(HTTP_AUTHORIZATION="Bearer " + rotated.json()["data"]["access"])
    blocked_access = client.get("/users/me")
    assert blocked_access.status_code == 401
    assert blocked_access.json()["error"]["code"] == "TOKEN_REVOKED"
    # No Bearer/cookie: a 401 must come from refresh validation, not access authentication.
    blocked_refresh = refresh_from_body(APIClient(), child)
    assert blocked_refresh.status_code == 401
    assert blocked_refresh.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"


@pytest.mark.django_db(transaction=True)
def test_two_refresh_connections_produce_one_success_then_revoke_family():
    user = create_user()
    raw = login(APIClient(), user).cookies["refresh_token"].value
    results = run_concurrent(
        lambda: refresh_from_body(APIClient(), raw), lambda: refresh_from_body(APIClient(), raw)
    )
    assert sorted(response.status_code for response in results) == [200, 401]
    rejected = next(response for response in results if response.status_code == 401)
    assert rejected.json()["error"]["code"] == "TOKEN_REPLAY_ATTACK_DETECTED"
    assert not UserSession.objects.filter(user=user, is_revoked=False).exists()
    accepted = next(response for response in results if response.status_code == 200)
    child = accepted.cookies["refresh_token"].value
    assert set(
        BlacklistedToken.objects.filter(token__user=user).values_list("token__jti", flat=True)
    ) == {
        UntypedToken(raw)["jti"],
        UntypedToken(child)["jti"],
    }
    assert AuditLog.objects.filter(action="SECURITY_TOKEN_REPLAY_DETECTED").count() == 1


def test_refresh_failure_rolls_back_blacklist_and_session_change():
    user = create_user()
    client = APIClient()
    raw = login(client, user).cookies["refresh_token"].value
    before = UserSession.objects.get(user=user).refresh_token_hash
    with patch(
        "authentication.services.session_service.UserSession.save",
        side_effect=RuntimeError("injected DB write failure"),
    ):
        response = refresh_from_body(client, raw)
        assert response.status_code == 500
    assert UserSession.objects.get(user=user).refresh_token_hash == before
    assert not BlacklistedToken.objects.filter(token__user=user).exists()
    assert refresh_from_body(client, raw).status_code == 200


def test_rotated_parent_can_logout_current_family_with_old_access():
    user = create_user()
    client = APIClient()
    raw = login(client, user).cookies["refresh_token"].value
    assert refresh_from_body(client, raw).status_code == 200
    client.cookies.clear()
    assert client.post("/logout", {"refresh": raw}, format="json").status_code == 200
    assert not UserSession.objects.filter(user=user, is_revoked=False).exists()


@pytest.mark.parametrize(
    "case,status,code",
    [("csrf", 403, "PERMISSION_DENIED"), ("conflicting-sources", 400, "VALIDATION_ERROR")],
)
def test_cookie_refresh_rejects_csrf_and_conflicting_sources(case, status, code):
    user = create_user()
    client = APIClient(enforce_csrf_checks=True)
    raw = login(client, user).cookies["refresh_token"].value
    before = UserSession.objects.get(user=user).refresh_token_hash
    body = {} if case == "csrf" else {"refresh": raw + "x"}
    response = client.post("/refresh", body, format="json")
    assert response.status_code == status
    assert response.json()["error"]["code"] == code
    assert UserSession.objects.get(user=user).refresh_token_hash == before
    assert not BlacklistedToken.objects.filter(token__user=user).exists()
    assert UserSession.objects.filter(user=user, is_revoked=False).exists()
