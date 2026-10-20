from unittest.mock import patch
from uuid import uuid4

import pytest
from django.utils import timezone

from apps.github_accounts.models import GitHubAccount
from apps.github_accounts.services import link_verified_account
from common.api_errors import IdentityUnavailable
from infrastructure.identity import Principal

pytestmark = [pytest.mark.integration, pytest.mark.django_db]
URL = "/api/v1/github/account"


@pytest.fixture
def actor(client):
    user_id = uuid4()
    with patch(
        "common.authentication.IdentityUserClient.current_user", return_value=Principal(user_id)
    ) as verify:
        client.defaults["HTTP_AUTHORIZATION"] = "Bearer actor-token"
        yield user_id, verify


def test_account_get_returns_only_current_user_link(client, actor):
    user_id, verify = actor
    own = link_verified_account(
        user_id=user_id,
        github_user_id="12345",
        github_username="My-Login",
        verified_at=timezone.now(),
    )
    link_verified_account(
        user_id=uuid4(),
        github_user_id="67890",
        github_username="Other-Login",
        verified_at=timezone.now(),
    )
    response = client.get(URL)
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["user_id"] == str(user_id)
    assert data["github_user_id"] == own.github_user_id
    assert data["github_username"] == "My-Login"
    assert data["source_version"] == 1
    assert "67890" not in response.content.decode()
    assert response["Cache-Control"] == "private, no-store"
    verify.assert_called_once_with("actor-token")


def test_missing_link_is_unlinked_instead_of_using_identity_profile(client, actor):
    user_id, _ = actor
    response = client.get(URL)
    assert response.status_code == 200
    assert response.json()["data"] == {
        "user_id": str(user_id),
        "status": "UNLINKED",
        "authorization_status": "NOT_AUTHORIZED",
        "github_user_id": None,
        "github_username": None,
        "verified_at": None,
        "linked_at": None,
        "revoked_at": None,
        "source_version": 0,
    }
    assert not GitHubAccount.objects.exists()


def test_delete_revokes_own_link_once_and_leaves_other_user_untouched(client, actor):
    user_id, verify = actor
    own = link_verified_account(
        user_id=user_id,
        github_user_id="12345",
        github_username="My-Login",
        verified_at=timezone.now(),
    )
    other = link_verified_account(
        user_id=uuid4(),
        github_user_id="67890",
        github_username="Other-Login",
        verified_at=timezone.now(),
    )
    for _ in range(2):
        response = client.delete(URL)
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["status"] == "REVOKED"
        assert data["source_version"] == 2
        assert data["github_user_id"] is None
        assert data["revoked_at"] is not None
    own.refresh_from_db()
    other.refresh_from_db()
    assert own.status == "REVOKED"
    assert own.source_version == 2
    assert other.status == "LINKED"
    assert verify.call_count == 2


def test_delete_missing_link_is_idempotent_without_creating_account(client, actor):
    response = client.delete(URL)
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "UNLINKED"
    assert not GitHubAccount.objects.exists()


@pytest.mark.parametrize("method", ["get", "delete"])
def test_user_query_cannot_change_owner_or_mutate_state(client, actor, method):
    user_id, _ = actor
    record = link_verified_account(
        user_id=user_id,
        github_user_id="12345",
        github_username="My-Login",
        verified_at=timezone.now(),
    )
    response = getattr(client, method)(URL + f"?user_id={uuid4()}")
    assert response.status_code == 400
    record.refresh_from_db()
    assert record.status == "LINKED"


def test_delete_rejects_forged_actor_body(client, actor):
    response = client.delete(URL, data='{"user_id":"forged"}', content_type="application/json")
    assert response.status_code == 400


@pytest.mark.parametrize("method", ["get", "delete"])
def test_missing_user_bearer_or_service_key_alone_is_denied(client, method):
    with patch("common.authentication.IdentityUserClient.current_user") as verify:
        response = getattr(client, method)(URL, HTTP_X_SERVICE_KEY="service-key")
    assert response.status_code == 401
    assert response["WWW-Authenticate"] == "Bearer"
    verify.assert_not_called()


def test_identity_unavailable_prevents_unlink(client, actor):
    user_id, verify = actor
    record = link_verified_account(
        user_id=user_id,
        github_user_id="12345",
        github_username="My-Login",
        verified_at=timezone.now(),
    )
    verify.side_effect = IdentityUnavailable()
    response = client.delete(URL)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "IDENTITY_UNAVAILABLE"
    record.refresh_from_db()
    assert record.status == "LINKED"


def test_browser_cannot_link_unverified_github_identity(client, actor):
    response = client.post(URL, data={"github_user_id": "12345"}, content_type="application/json")
    assert response.status_code == 405
    assert not GitHubAccount.objects.exists()
