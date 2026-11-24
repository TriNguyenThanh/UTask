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


@pytest.mark.parametrize("invalid_id", ["not-a-uuid", "", "00000000-0000-0000-0000-00000000000z"])
def test_batch_invalid_uuid_has_vietnamese_issue_and_preserves_item_path(
    authenticated_account, invalid_id
):
    user, client = authenticated_account()

    response = client.post("/users/batch", {"user_ids": [str(user.pk), invalid_id]}, format="json")

    assert response.status_code == 400
    assert response.json()["error"] == {
        "code": "VALIDATION_ERROR",
        "details": [{"field": "user_ids.1", "issue": "Mã định danh không hợp lệ."}],
    }


def test_profile_update_trigger_event_and_noop(authenticated_account):
    user, client = authenticated_account()
    create_user(student_id="TAKEN-1")
    changes = {
        "first_name": "An",
        "last_name": "Nguyễn",
        "student_id": " sv-2026-001 ",
        "academic_year": "K2026",
        "faculty": "CNTT",
        "timezone": "Asia/Ho_Chi_Minh",
        "bio": "Django",
        "preferences": {"theme": "system"},
    }
    response = client.patch("/users/me", changes, format="json")
    assert response.status_code == 200
    patch_data = response.json()["data"]
    assert patch_data["display_name"] == "Nguyễn An"
    assert patch_data["student_id"] == "SV-2026-001"
    assert patch_data["first_name"] == "An"
    assert patch_data["last_name"] == "Nguyễn"
    assert patch_data["academic_year"] == "K2026"
    assert patch_data["faculty"] == "CNTT"
    assert patch_data["timezone"] == "Asia/Ho_Chi_Minh"
    assert patch_data == client.get("/users/me").json()["data"]
    user.refresh_from_db()
    assert user.student_id == "SV-2026-001"
    event = OutboxEvent.objects.get(event_type="identity.user.updated")
    assert event.data["data"]["display_name"] == "Nguyễn An"
    assert event.data["data"]["student_id"] == "SV-2026-001"
    assert "github_username" in event.data["data"]
    assert client.patch("/users/me", changes, format="json").status_code == 200
    assert OutboxEvent.objects.filter(event_type="identity.user.updated").count() == 1
    assert AuditLog.objects.filter(action="PROFILE_UPDATED").count() == 1
    conflict = client.patch("/users/me", {"student_id": " taken-1 "}, format="json")
    assert conflict.status_code == 400
    assert conflict.json()["error"]["details"] == [
        {"field": "student_id", "issue": "MSSV này đã được gán cho tài khoản khác."}
    ]
    cleared = client.patch("/users/me", {"student_id": " "}, format="json")
    assert cleared.status_code == 200
    assert cleared.json()["data"]["student_id"] is None
    assert OutboxEvent.objects.filter(event_type="identity.user.updated").count() == 2
    assert AuditLog.objects.filter(action="PROFILE_UPDATED").count() == 2


@pytest.mark.parametrize(
    "field,status,code",
    [
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
        "account_status",
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


def test_admin_cannot_suspend_own_account(authenticated_account):
    admin, client = authenticated_account(global_role_code="SYSTEM_ADMIN")

    response = client.patch(
        f"/admin/users/{admin.pk}/status",
        {"status": "SUSPENDED", "reason": "self-suspend attempt"},
        format="json",
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "CANNOT_SUSPEND_SELF"
    admin.refresh_from_db()
    assert admin.account_status == "ACTIVE"
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


def test_user_search_permissions_filtering_privacy_and_validation(authenticated_account):
    from django.core.cache import cache
    from django.utils import timezone

    from accounts.models import AccountStatus, User
    from tests.helpers import PASSWORD, create_user

    cache.clear()
    _, student_client = authenticated_account(global_role_code="STUDENT")
    denied = student_client.get("/users/search", {"q": "teacher"})
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "FORBIDDEN_TEACHER_OR_ADMIN"

    _, teacher_client = authenticated_account(global_role_code="TEACHER")
    target_teacher = create_user(global_role_code="TEACHER")
    User.objects.filter(pk=target_teacher.pk).update(
        email="gv.nguyen@utask.edu.vn", username="gvnguyen"
    )
    target_teacher.profile.first_name = "Nguyễn"
    target_teacher.profile.last_name = "An"
    target_teacher.profile.display_name = "Nguyễn Văn An"
    target_teacher.profile.save(update_fields=("first_name", "last_name", "display_name"))

    target_student = create_user(student_id="SV202601", global_role_code="STUDENT")
    User.objects.filter(pk=target_student.pk).update(
        email="sv.nguyen@utask.edu.vn", username="svnguyen"
    )
    suspended = create_user(
        account_status=AccountStatus.SUSPENDED,
        global_role_code="TEACHER",
    )
    User.objects.filter(pk=suspended.pk).update(
        email="suspended.nguyen@utask.edu.vn", username="susnguyen"
    )
    deleted = create_user(global_role_code="TEACHER")
    User.objects.filter(pk=deleted.pk).update(
        email="deleted.nguyen@utask.edu.vn",
        username="delnguyen",
        deleted_at=timezone.now(),
    )
    assert PASSWORD  # noqa: S101

    # Validation: short query, invalid role, limit > 20
    assert teacher_client.get("/users/search", {"q": "a"}).status_code == 400
    assert teacher_client.get("/users/search", {"q": "nguyen", "role": "HACKER"}).status_code == 400
    assert teacher_client.get("/users/search", {"q": "nguyen", "limit": 25}).status_code == 400

    # Role-filtered search returns only ACTIVE non-deleted TEACHER
    resp = teacher_client.get("/users/search", {"q": "nguyen", "role": "TEACHER", "limit": 5})
    assert resp.status_code == 200
    data = resp.json()["data"]["users"]
    ids = {row["id"] for row in data}
    assert str(target_teacher.pk) in ids
    assert str(target_student.pk) not in ids
    assert str(suspended.pk) not in ids
    assert str(deleted.pk) not in ids
    assert set(data[0].keys()) == {
        "id",
        "display_name",
        "email",
        "student_id",
        "avatar_url",
        "roles",
    }
    assert resp.json()["meta"] == {"total": len(data), "limit": 5}

    # Search by student_id works for SYSTEM_ADMIN too
    _, admin_client = authenticated_account(global_role_code="SYSTEM_ADMIN")
    by_sid = admin_client.get("/users/search", {"q": "SV202601"})
    assert by_sid.status_code == 200
    assert [row["id"] for row in by_sid.json()["data"]["users"]] == [str(target_student.pk)]


def test_user_search_throttle_enforces_limit(authenticated_account, monkeypatch):
    from django.core.cache import cache
    from rest_framework.throttling import ScopedRateThrottle

    cache.clear()
    assert ScopedRateThrottle.THROTTLE_RATES["user_search"] == "30/min"
    monkeypatch.setitem(ScopedRateThrottle.THROTTLE_RATES, "user_search", "2/min")
    try:
        _, teacher_client = authenticated_account(global_role_code="TEACHER")
        assert teacher_client.get("/users/search", {"q": "test"}).status_code == 200
        assert teacher_client.get("/users/search", {"q": "test"}).status_code == 200
        throttled = teacher_client.get("/users/search", {"q": "test"})
        assert throttled.status_code == 429
    finally:
        cache.clear()
