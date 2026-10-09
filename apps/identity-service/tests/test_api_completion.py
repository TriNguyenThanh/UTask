from datetime import timedelta
from uuid import uuid4

import pytest
from allauth.socialaccount.models import SocialAccount
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from accounts.models import AuditLog, OutboxEvent, UserSession
from tests.helpers import create_user, login

pytestmark = [pytest.mark.integration, pytest.mark.django_db, pytest.mark.postgres]


def test_profile_update_trigger_event_and_noop(authenticated_account):
    user, client = authenticated_account()
    changes = {
        "first_name": "An",
        "last_name": "Nguyễn",
        "bio": "Django",
        "preferences": {"theme": "system"},
    }
    response = client.patch("/users/me", changes, format="json")
    assert response.status_code == 200
    assert response.json()["data"]["display_name"] == "Nguyễn An"
    event = OutboxEvent.objects.get(event_type="identity.user.updated")
    assert event.data["data"]["display_name"] == "Nguyễn An"
    assert "github_username" in event.data["data"]
    assert client.patch("/users/me", changes, format="json").status_code == 200
    assert OutboxEvent.objects.filter(event_type="identity.user.updated").count() == 1
    assert AuditLog.objects.filter(action="PROFILE_UPDATED").count() == 1


@pytest.mark.parametrize(
    "field,status,code",
    [
        ("student_id", 403, "STUDENT_ID_IMMUTABLE"),
        ("email", 400, "VALIDATION_ERROR"),
        ("roles", 400, "VALIDATION_ERROR"),
    ],
)
def test_profile_protected_fields(field, status, code, authenticated_account):
    _, client = authenticated_account()
    result = client.patch("/users/me", {field: "invalid"}, format="json")
    assert result.status_code == status
    assert result.json()["error"]["code"] == code


def test_public_batch_allowlist_dedup_and_deleted(authenticated_account):
    _, client = authenticated_account()
    target, deleted = create_user(), create_user(deleted_at=timezone.now())
    assert client.get(f"/users/{target.pk}").status_code == 200
    assert client.get(f"/users/{deleted.pk}").status_code == 404
    result = client.post(
        "/users/batch",
        {"user_ids": [str(target.pk), str(target.pk), str(deleted.pk), str(uuid4())]},
        format="json",
    )
    assert result.status_code == 200
    assert result.json()["meta"] == {"total": 1}
    users = result.json()["data"]["users"]
    assert len(users) == 1
    assert set(users[0]) == {
        "id",
        "email",
        "student_id",
        "display_name",
        "avatar_url",
        "bio",
        "roles",
    }


@pytest.mark.parametrize("mutation", ["grant-role", "revoke-role", "suspend", "restore-deleted"])
def test_admin_status_role_noop_and_revocation(authenticated_account, mutation):
    _, client = authenticated_account(global_role_code="SYSTEM_ADMIN")
    target, victim = authenticated_account()
    role_url = f"/admin/users/{target.pk}/roles"
    status_url = f"/admin/users/{target.pk}/status"
    if mutation == "revoke-role":
        assert client.post(role_url, {"role_code": "TEACHER"}, format="json").status_code == 200
        login(victim, target)
    elif mutation == "restore-deleted":
        target.deleted_at = timezone.now()
        target.save(update_fields=("deleted_at",))

    events_before = OutboxEvent.objects.filter(aggregate_id=target.pk).count()
    if mutation in {"grant-role", "revoke-role"}:
        method = "post" if mutation == "grant-role" else "delete"
        result = getattr(client, method)(role_url, {"role_code": "TEACHER"}, format="json")
    else:
        action = {"status": "SUSPENDED"} if mutation == "suspend" else {"restore_deleted": True}
        result = client.patch(status_url, {**action, "reason": "test"}, format="json")

    assert result.status_code == 200, result.json()
    target.refresh_from_db()
    assert victim.get("/users/me").status_code == 401
    assert not UserSession.objects.filter(user=target, is_revoked=False).exists()
    assert OutboxEvent.objects.filter(aggregate_id=target.pk).count() == events_before + 1
    if mutation == "suspend":
        assert target.account_status == "SUSPENDED"
    elif mutation == "restore-deleted":
        assert target.deleted_at is None
    else:
        expected_roles = ["STUDENT", "TEACHER"] if mutation == "grant-role" else ["STUDENT"]
        assert result.json()["data"]["roles"] == expected_roles
        login(victim, target)
        noop = getattr(client, method)(role_url, {"role_code": "TEACHER"}, format="json")
        assert noop.status_code == 200
        assert OutboxEvent.objects.filter(aggregate_id=target.pk).count() == events_before + 1
        assert victim.get("/users/me").status_code == 200


def test_admin_cannot_revoke_own_admin_role(authenticated_account):
    admin, client = authenticated_account(global_role_code="SYSTEM_ADMIN")

    response = client.delete(
        f"/admin/users/{admin.pk}/roles", {"role_code": "SYSTEM_ADMIN"}, format="json"
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "CANNOT_REVOKE_OWN_ADMIN_ROLE"
    assert admin.global_role_assignments.filter(role__code="SYSTEM_ADMIN").exists()
    assert not OutboxEvent.objects.filter(aggregate_id=admin.pk).exists()
    assert client.get("/users/me").status_code == 200


def test_admin_reactivation_does_not_restore_revoked_session(authenticated_account):
    _, client = authenticated_account(global_role_code="SYSTEM_ADMIN")
    target, victim = authenticated_account()
    url = f"/admin/users/{target.pk}/status"
    assert (
        client.patch(url, {"status": "SUSPENDED", "reason": "test"}, format="json").status_code
        == 200
    )
    assert victim.get("/users/me").status_code == 401

    response = client.patch(url, {"status": "ACTIVE", "reason": "test"}, format="json")

    assert response.status_code == 200
    target.refresh_from_db()
    assert target.is_active
    assert victim.get("/users/me").status_code == 401
    assert not UserSession.objects.filter(user=target, is_revoked=False).exists()
    login(victim, target)
    assert victim.get("/users/me").status_code == 200


def test_admin_filter_pagination_and_student_denied(authenticated_account):
    _, client = authenticated_account(global_role_code="SYSTEM_ADMIN")
    student, student_client = authenticated_account()
    assert student_client.get("/admin/users").status_code == 403
    result = client.get("/admin/users", {"role": "STUDENT", "limit": 1})
    assert result.status_code == 200
    assert result.json()["data"][0]["id"] == str(student.pk)
    assert result.json()["meta"]["total_count"] == 1
    assert client.get("/admin/users", {"limit": 101}).status_code == 400


def test_session_status_live_revoked_invalid_and_caller_keys(settings, authenticated_account):
    settings.IDENTITY_SERVICE_KEYS = {
        "work": "local-work-key",
        "integration": "local-integration-key",
    }
    user, client = authenticated_account()
    url = "/api/v1/internal/auth/session-status"
    assert client.post(url, {}, format="json").status_code == 403
    assert (
        client.post(url, {}, format="json", HTTP_X_SERVICE_KEY="local-integration-key").status_code
        == 403
    )
    assert client.post(url, {}, format="json", HTTP_X_SERVICE_KEY="local-work-key").json()[
        "data"
    ] == {"active": True}
    client.cookies.clear()
    assert client.post("/logout-all", {}, format="json").status_code == 200
    assert client.post(url, {}, format="json", HTTP_X_SERVICE_KEY="local-work-key").json()[
        "data"
    ] == {"active": False}
    login(client, user)
    assert client.post(url, {}, format="json", HTTP_X_SERVICE_KEY="local-work-key").json()[
        "data"
    ] == {"active": True}
    client.credentials(HTTP_AUTHORIZATION="Bearer malformed")
    assert client.post(url, {}, format="json", HTTP_X_SERVICE_KEY="local-work-key").json()[
        "data"
    ] == {"active": False}


def test_github_reconcile_backend_only_allowlist(settings):
    settings.IDENTITY_SERVICE_KEYS = {
        "integration": "local-integration-key",
        "classroom": "local-class-key",
    }
    user = create_user()
    SocialAccount.objects.create(
        user=user, provider="github", uid="123", extra_data={"access_token": "must-not-leak"}
    )
    user.profile.github_username = "octocat"
    user.profile.save()
    client = APIClient()
    url = f"/api/v1/internal/users/{user.pk}/oauth/GITHUB"
    assert client.get(url).status_code == 403
    assert client.get(url, HTTP_X_SERVICE_KEY="local-class-key").status_code == 403
    result = client.get(url, HTTP_X_SERVICE_KEY="local-integration-key")
    assert result.status_code == 200
    assert result.json()["data"] == {
        "user_id": str(user.pk),
        "mapping": {"provider_user_id": "123", "github_username": "octocat"},
    }
    user.deleted_at = timezone.now()
    user.save(update_fields=("deleted_at",))
    assert (
        client.get(url, HTTP_X_SERVICE_KEY="local-integration-key").json()["data"]["mapping"]
        is None
    )
    assert (
        client.get(
            "/api/v1/internal/users/bad/oauth/GITHUB", HTTP_X_SERVICE_KEY="local-integration-key"
        ).status_code
        == 400
    )


@pytest.mark.parametrize(
    "kind,code", [("expired", "TOKEN_EXPIRED"), ("malformed", "INVALID_TOKEN")]
)
def test_jwt_errors_headers_and_resolver_envelope(kind, code, authenticated_account):
    # Resolver errors are independent contracts in test_http_errors.py.
    user, client = authenticated_account()
    raw = "malformed"
    if kind == "expired":
        logged_in = login(client, user)
        token = AccessToken(logged_in.json()["data"]["access"])
        token.set_exp(lifetime=timedelta(seconds=-1))
        raw = str(token)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {raw}")
    response = client.get("/users/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == code
    assert response.headers["WWW-Authenticate"].startswith("Bearer")
    assert isinstance(response.json()["error"]["details"], list)


def test_profile_transaction_rollback_on_outbox_failure(monkeypatch, authenticated_account):
    user, client = authenticated_account()

    def fail(*args):
        raise RuntimeError("test infrastructure failure")

    monkeypatch.setattr("accounts.services.profiles.emit_user", fail)
    result = client.patch("/users/me", {"bio": "not committed"}, format="json")
    assert result.status_code == 500
    user.profile.refresh_from_db()
    assert user.profile.bio is None
    assert not AuditLog.objects.filter(action="PROFILE_UPDATED").exists()
    assert UserSession.objects.filter(user=user, is_revoked=False).exists()


@pytest.mark.parametrize(
    "user_ids", [["bad-uuid"], [str(uuid4()) for _ in range(101)]], ids=["bad-id", "over-limit"]
)
def test_batch_rejects_invalid_identifiers_and_size(user_ids, authenticated_account):
    _, client = authenticated_account()
    response = client.post("/users/batch", {"user_ids": user_ids}, format="json")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
