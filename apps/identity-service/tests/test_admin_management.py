"""Wave 6.1 SYSTEM_ADMIN user management, Axes unlock, audit logs, and session revocation."""

from datetime import timedelta
from uuid import uuid4

import pytest
from allauth.socialaccount.models import SocialAccount
from axes.models import AccessAttempt
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import AccountStatus, AuditLog, OutboxEvent, User, UserSession
from tests.helpers import NEW_PASSWORD, PASSWORD, create_user, login, mail_secret, run_concurrent

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True),
    pytest.mark.postgres,
]


def _admin_client():
    admin = create_user(global_role_code="SYSTEM_ADMIN")
    client = APIClient()
    login(client, admin)
    return admin, client


def test_admin_create_user_with_password_and_multi_roles():
    admin, client = _admin_client()
    email = f"Admin.Created.{uuid4().hex[:8]}@example.edu.vn"
    response = client.post(
        "/admin/users",
        {
            "email": f"  {email}  ",
            "first_name": "Minh",
            "last_name": "Trần",
            "student_id": " sv-2026-888 ",
            "roles": ["TEACHER", "STUDENT", "TEACHER"],
            "password": PASSWORD,
        },
        format="json",
    )
    assert response.status_code == 201, response.json()
    data = response.json()["data"]
    assert data["email"] == email.lower()
    assert data["student_id"] == "SV-2026-888"
    assert data["display_name"] == "Trần Minh"
    assert data["account_status"] == "ACTIVE"
    assert data["is_email_verified"] is True
    assert data["has_usable_password"] is True
    assert data["roles"] == ["STUDENT", "TEACHER"]
    assert data["deleted_at"] is None
    assert "password" not in data

    created = User.objects.get(pk=data["id"])
    assert AuditLog.objects.filter(
        actor_id=str(admin.pk), target_user_id=str(created.pk), action="ADMIN_USER_CREATED"
    ).exists()
    assert OutboxEvent.objects.filter(
        aggregate_id=created.pk, event_type="identity.user.created"
    ).exists()

    # Created account can immediately log in.
    user_client = APIClient()
    assert login(user_client, created, password=PASSWORD).status_code == 200


def test_admin_create_user_with_activation_email_and_validation_guards(settings):
    _, client = _admin_client()
    email = f"pending.{uuid4().hex[:8]}@example.edu.vn"

    # Both password and send_activation_email -> 400.
    both = client.post(
        "/admin/users",
        {"email": email, "password": PASSWORD, "send_activation_email": True},
        format="json",
    )
    assert both.status_code == 400 and both.json()["error"]["code"] == "VALIDATION_ERROR"

    # Neither password nor send_activation_email -> 400.
    neither = client.post("/admin/users", {"email": email}, format="json")
    assert neither.status_code == 400 and neither.json()["error"]["code"] == "VALIDATION_ERROR"

    # Missing mail key fails closed 503 with zero orphan users.
    old_key = settings.IDENTITY_MAIL_KEY
    settings.IDENTITY_MAIL_KEY = None
    unavailable = client.post(
        "/admin/users",
        {"email": email, "send_activation_email": True},
        format="json",
    )
    assert unavailable.status_code == 503
    assert not User.objects.filter(email=email).exists()
    settings.IDENTITY_MAIL_KEY = old_key

    # Valid send_activation_email=True creates PENDING_ACTIVATION + encrypted mail event.
    created_res = client.post(
        "/admin/users",
        {
            "email": email,
            "first_name": "Lan",
            "last_name": "Phạm",
            "roles": ["TEACHER"],
            "send_activation_email": True,
        },
        format="json",
    )
    assert created_res.status_code == 201, created_res.json()
    data = created_res.json()["data"]
    assert data["account_status"] == "PENDING_ACTIVATION"
    assert data["is_email_verified"] is False
    assert data["has_usable_password"] is False
    assert data["roles"] == ["TEACHER"]

    mail_event = OutboxEvent.objects.get(
        aggregate_id=data["id"], event_type="identity.activation.requested"
    )
    secret = mail_secret(mail_event)
    act = APIClient().post(
        "/activate",
        {"key": secret["key"], "new_password1": NEW_PASSWORD, "new_password2": NEW_PASSWORD},
        format="json",
    )
    assert act.status_code == 200, act.json()
    activated_user = User.objects.get(pk=data["id"])
    assert activated_user.account_status == AccountStatus.ACTIVE
    assert login(APIClient(), activated_user, password=NEW_PASSWORD).status_code == 200

    # Duplicate email/student_id rejected with clean Vietnamese issues.
    dup = client.post(
        "/admin/users",
        {"email": email.upper(), "password": PASSWORD},
        format="json",
    )
    assert dup.status_code == 400
    assert dup.json()["error"]["details"][0]["field"] == "email"

    # Non-admin denied.
    student_client = APIClient()
    login(student_client, create_user())
    assert (
        student_client.post(
            "/admin/users",
            {"email": f"x.{uuid4().hex[:6]}@example.edu.vn", "password": PASSWORD},
            format="json",
        ).status_code
        == 403
    )


def test_admin_detail_patch_soft_delete_and_deleted_filter():
    admin, client = _admin_client()
    taken = create_user(student_id="TAKEN-99")
    target = create_user(first_name="Cũ", last_name="Nguyễn")
    SocialAccount.objects.create(user=target, provider="google", uid=f"g-{uuid4().hex}")
    victim = APIClient()
    login(victim, target)

    # Detail view includes linked_providers, has_usable_password, active_sessions_count, lockout.
    detail = client.get(f"/admin/users/{target.pk}")
    assert detail.status_code == 200, detail.json()
    d = detail.json()["data"]
    assert d["linked_providers"] == ["google"]
    assert d["has_usable_password"] is True
    assert d["active_sessions_count"] == 1
    assert d["is_login_locked"] is False
    assert d["failed_login_attempts"] == 0
    assert d["locked_until"] is None

    # Empty PATCH rejected.
    assert client.patch(f"/admin/users/{target.pk}", {}, format="json").status_code == 400

    # Duplicate student_id rejected.
    dup_sid = client.patch(
        f"/admin/users/{target.pk}", {"student_id": f" {taken.student_id.lower()} "}, format="json"
    )
    assert dup_sid.status_code == 400
    assert dup_sid.json()["error"]["details"] == [
        {"field": "student_id", "issue": "MSSV này đã được gán cho tài khoản khác."}
    ]

    # Valid PATCH updates profile + student_id + trigger display_name + audit + outbox.
    patched = client.patch(
        f"/admin/users/{target.pk}",
        {"first_name": "Mới", "last_name": "Lê", "student_id": " sv-2026-777 ", "bio": "Updated"},
        format="json",
    )
    assert patched.status_code == 200, patched.json()
    pd = patched.json()["data"]
    assert pd["display_name"] == "Lê Mới"
    assert pd["student_id"] == "SV-2026-777"
    assert pd["bio"] == "Updated"
    assert AuditLog.objects.filter(
        target_user_id=str(target.pk), action="ADMIN_PROFILE_UPDATED"
    ).exists()
    assert OutboxEvent.objects.filter(
        aggregate_id=target.pk, event_type="identity.user.updated"
    ).exists()

    # Admin cannot self-delete.
    self_del = client.delete(f"/admin/users/{admin.pk}")
    assert self_del.status_code == 400
    assert self_del.json()["error"]["code"] == "CANNOT_DELETE_SELF"

    # Soft delete revokes victim sessions immediately and hides from ?deleted=active.
    deleted = client.delete(f"/admin/users/{target.pk}")
    assert deleted.status_code == 200, deleted.json()
    assert deleted.json()["data"]["deleted_at"] is not None
    assert victim.get("/users/me").status_code == 401
    assert not UserSession.objects.filter(user=target, is_revoked=False).exists()
    assert AuditLog.objects.filter(
        target_user_id=str(target.pk), action="ACCOUNT_SOFT_DELETED"
    ).exists()

    # Soft-deleted user cannot be patched until restored, but can be inspected via GET detail.
    assert client.get(f"/admin/users/{target.pk}").json()["data"]["deleted_at"] is not None
    blocked_patch = client.patch(f"/admin/users/{target.pk}", {"bio": "Should fail"}, format="json")
    assert blocked_patch.status_code == 400
    assert blocked_patch.json()["error"]["code"] == "ACCOUNT_UNAVAILABLE"

    # ?deleted=active / deleted / all filtering.
    active_ids = {u["id"] for u in client.get("/admin/users", {"deleted": "active"}).json()["data"]}
    deleted_ids = {
        u["id"] for u in client.get("/admin/users", {"deleted": "deleted"}).json()["data"]
    }
    all_ids = {u["id"] for u in client.get("/admin/users", {"deleted": "all"}).json()["data"]}
    assert str(target.pk) not in active_ids
    assert str(target.pk) in deleted_ids
    assert str(target.pk) in all_ids and str(admin.pk) in all_ids

    # Restore via PATCH /status {restore_deleted: true} puts user back in active list.
    restored = client.patch(
        f"/admin/users/{target.pk}/status",
        {"restore_deleted": True, "reason": "Khôi phục tài khoản"},
        format="json",
    )
    assert restored.status_code == 200 and restored.json()["data"]["deleted_at"] is None
    active_after = {u["id"] for u in client.get("/admin/users").json()["data"]}
    assert str(target.pk) in active_after


def test_admin_unlock_login_endpoint_and_status_reset_lockout():
    _, admin_client = _admin_client()
    user = create_user()
    public = APIClient()

    def trigger_lockout():
        for i in range(5):
            r = public.post(
                "/login", {"email": user.email, "password": "WrongPassword!"}, format="json"
            )
            assert r.status_code == (429 if i == 4 else 401)
        assert (
            public.post(
                "/login", {"email": user.email, "password": PASSWORD}, format="json"
            ).status_code
            == 429
        )

    # 1. Unlock via dedicated POST /admin/users/{id}/unlock-login.
    trigger_lockout()
    detail = admin_client.get(f"/admin/users/{user.pk}").json()["data"]
    assert detail["is_login_locked"] is True
    assert detail["failed_login_attempts"] >= 5
    assert detail["locked_until"] is not None

    unlocked = admin_client.post(f"/admin/users/{user.pk}/unlock-login", {}, format="json")
    assert unlocked.status_code == 200, unlocked.json()
    assert unlocked.json()["data"]["is_login_locked"] is False
    assert unlocked.json()["data"]["cleared_attempts"] >= 1
    assert not AccessAttempt.objects.filter(username=str(user.pk)).exists()
    assert AuditLog.objects.filter(target_user_id=str(user.pk), action="LOGIN_UNLOCKED").exists()
    assert login(public, user).status_code == 200

    # 2. Unlock via PATCH /status {status: "ACTIVE", reset_lockout: true} even when already ACTIVE!
    trigger_lockout()
    bad_combo = admin_client.patch(
        f"/admin/users/{user.pk}/status",
        {"status": "SUSPENDED", "reset_lockout": True, "reason": "Invalid"},
        format="json",
    )
    assert bad_combo.status_code == 400

    reset_res = admin_client.patch(
        f"/admin/users/{user.pk}/status",
        {"status": "ACTIVE", "reset_lockout": True, "reason": "Mở khóa đăng nhập"},
        format="json",
    )
    assert reset_res.status_code == 200, reset_res.json()
    assert not AccessAttempt.objects.filter(username=str(user.pk)).exists()
    assert login(public, user).status_code == 200


def test_admin_audit_logs_filtering_and_admin_session_revocation():
    admin, admin_client = _admin_client()
    user_a = create_user()
    user_b = create_user()
    client_a1, client_a2, client_b = APIClient(), APIClient(), APIClient()
    login(client_a1, user_a)
    login(client_a2, user_a)
    login(client_b, user_b)

    # Admin lists user_a sessions (2 active).
    sessions_res = admin_client.get(f"/admin/users/{user_a.pk}/sessions")
    assert sessions_res.status_code == 200, sessions_res.json()
    sessions = sessions_res.json()["data"]
    assert len(sessions) == 2

    # Cross-user IDOR attempt (user_b's session under user_a's path) -> 404.
    b_session = UserSession.objects.get(user=user_b)
    idor = admin_client.delete(f"/admin/users/{user_a.pk}/sessions/{b_session.pk}")
    assert idor.status_code == 404 and idor.json()["error"]["code"] == "SESSION_NOT_FOUND"
    assert client_b.get("/users/me").status_code == 200

    # Revoke single session of user_a -> only 1 remains active.
    rev_one = admin_client.delete(f"/admin/users/{user_a.pk}/sessions/{sessions[0]['id']}")
    assert rev_one.status_code == 200 and rev_one.json()["data"]["revoked"] is True
    assert len(admin_client.get(f"/admin/users/{user_a.pk}/sessions").json()["data"]) == 1
    assert (
        len(
            admin_client.get(
                f"/admin/users/{user_a.pk}/sessions", {"include_revoked": "true"}
            ).json()["data"]
        )
        == 2
    )

    # Revoke all remaining sessions of user_a.
    rev_all = admin_client.post(f"/admin/users/{user_a.pk}/sessions/revoke-all", {}, format="json")
    assert rev_all.status_code == 200
    assert rev_all.json()["data"]["revoked_sessions_count"] == 1
    assert client_a1.get("/users/me").status_code == 401
    assert client_a2.get("/users/me").status_code == 401
    assert client_b.get("/users/me").status_code == 200

    # Audit logs filter by actor_id, target_user_id, action, date range.
    now = timezone.now()
    logs_res = admin_client.get(
        "/admin/audit-logs",
        {
            "actor_id": str(admin.pk),
            "target_user_id": str(user_a.pk),
            "action": "ADMIN_SESSION_REVOKED",
            "created_from": (now - timedelta(minutes=5)).isoformat(),
            "created_to": (now + timedelta(minutes=5)).isoformat(),
        },
    )
    assert logs_res.status_code == 200, logs_res.json()
    assert logs_res.json()["meta"]["total_count"] == 1
    assert logs_res.json()["data"][0]["action"] == "ADMIN_SESSION_REVOKED"

    # Invalid date range rejected.
    bad_range = admin_client.get(
        "/admin/audit-logs",
        {
            "created_from": (now + timedelta(minutes=5)).isoformat(),
            "created_to": (now - timedelta(minutes=5)).isoformat(),
        },
    )
    assert bad_range.status_code == 400
    assert client_b.get("/admin/audit-logs").status_code == 403


def test_admin_create_user_concurrent_duplicate_email_is_atomic():
    admin = create_user(global_role_code="SYSTEM_ADMIN")
    shared_email = f"race.{uuid4().hex[:8]}@example.edu.vn"

    def attempt():
        c = APIClient()
        login(c, admin)
        return c.post(
            "/admin/users",
            {"email": shared_email, "password": PASSWORD, "roles": ["STUDENT"]},
            format="json",
        ).status_code

    statuses = sorted(run_concurrent(attempt, attempt))
    assert statuses == [201, 400]
    assert User.objects.filter(email=shared_email).count() == 1
