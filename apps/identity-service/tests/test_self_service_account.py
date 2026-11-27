"""Wave 6.2.4: self-service account deletion (DELETE /users/me) and verified email change."""

from datetime import timedelta
from uuid import uuid4

import pytest
from allauth.account.models import EmailAddress
from django.test import RequestFactory
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import (
    AccountStatus,
    AuditLog,
    EmailChangeRequest,
    OutboxEvent,
    User,
    UserSession,
)
from authentication.serializers.auth import SessionTokenSerializer
from messaging.maintenance import cleanup_identity_data
from tests.helpers import PASSWORD, create_user, login, mail_secret, run_concurrent

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True),
    pytest.mark.postgres,
]


def _issue_oauth_session(user, *, created_offset: timedelta = timedelta(0)):
    fake_req = RequestFactory().post("/oauth/google")
    fake_req._request = fake_req
    user._identity_request = fake_req
    user._identity_device = "Google OAuth Browser"
    token = SessionTokenSerializer.get_token(user)
    if created_offset:
        UserSession.objects.filter(pk=token["session_id"]).update(
            created_at=timezone.now() + created_offset
        )
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION="Bearer " + str(token.access_token))
    return client, token


def test_self_delete_requires_valid_password_and_revokes_all_sessions():
    user = create_user()
    c1, c2 = APIClient(), APIClient()
    login(c1, user)
    login(c2, user)

    # Missing or wrong password -> 400 INCORRECT_CURRENT_PASSWORD, stays active.
    missing = c1.delete("/users/me", {}, format="json")
    assert missing.status_code == 400
    assert missing.json()["error"]["code"] == "INCORRECT_CURRENT_PASSWORD"
    wrong = c1.delete("/users/me", {"current_password": "WrongPassword!99"}, format="json")
    assert wrong.status_code == 400
    assert wrong.json()["error"]["code"] == "INCORRECT_CURRENT_PASSWORD"
    assert c1.get("/users/me").status_code == 200

    # Valid current_password -> soft-deleted, all sessions revoked, status_changed emitted.
    ok = c1.delete(
        "/users/me",
        {"current_password": PASSWORD, "reason": "Không còn sử dụng tài khoản"},
        format="json",
    )
    assert ok.status_code == 200, ok.json()
    data = ok.json()["data"]
    assert data["user_id"] == str(user.pk)
    assert data["deleted_at"] is not None

    user.refresh_from_db()
    assert user.deleted_at is not None
    assert not UserSession.objects.filter(user=user, is_revoked=False).exists()
    assert c1.get("/users/me").status_code == 401
    assert c2.get("/users/me").status_code == 401
    assert (
        APIClient()
        .post("/login", {"email": user.email, "password": PASSWORD}, format="json")
        .status_code
        == 401
    )
    assert AuditLog.objects.filter(
        actor_id=str(user.pk), target_user_id=str(user.pk), action="ACCOUNT_SELF_DELETED"
    ).exists()
    ev = OutboxEvent.objects.get(aggregate_id=user.pk, event_type="identity.user.status_changed")
    assert ev.data["data"]["deleted_at"] is not None


def test_self_delete_oauth_only_enforces_recent_login_window():
    # Stale session (> 15 minutes) rejected with 403 RECENT_LOGIN_REQUIRED.
    user = create_user()
    user.set_unusable_password()
    user.save(update_fields=("password",))
    stale_client, _ = _issue_oauth_session(user, created_offset=-timedelta(minutes=20))
    denied = stale_client.delete("/users/me", {}, format="json")
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "RECENT_LOGIN_REQUIRED"
    user.refresh_from_db()
    assert user.deleted_at is None

    # Passing current_password on passwordless account -> 400 INCORRECT_CURRENT_PASSWORD.
    bad_pw = stale_client.delete("/users/me", {"current_password": PASSWORD}, format="json")
    assert bad_pw.status_code == 400
    assert bad_pw.json()["error"]["code"] == "INCORRECT_CURRENT_PASSWORD"

    # Fresh OAuth login (< 15 minutes) succeeds without password (including explicit null).
    fresh_client, _ = _issue_oauth_session(user)
    ok = fresh_client.delete("/users/me", {"current_password": None}, format="json")
    assert ok.status_code == 200, ok.json()
    user.refresh_from_db()
    assert user.deleted_at is not None


def test_self_delete_blocks_last_system_admin_even_under_concurrency():
    sole_admin = create_user(global_role_code="SYSTEM_ADMIN")
    sole_client = APIClient()
    login(sole_client, sole_admin)

    # Inactive/suspended/deleted second admin does NOT satisfy active-admin invariant.
    create_user(global_role_code="SYSTEM_ADMIN", account_status=AccountStatus.SUSPENDED)
    create_user(global_role_code="SYSTEM_ADMIN", deleted_at=timezone.now())

    blocked = sole_client.delete("/users/me", {"current_password": PASSWORD}, format="json")
    assert blocked.status_code == 400
    assert blocked.json()["error"]["code"] == "CANNOT_DELETE_LAST_ADMIN"
    sole_admin.refresh_from_db()
    assert sole_admin.deleted_at is None

    # Add a second active SYSTEM_ADMIN, then race BOTH self-deletes concurrently!
    second_admin = create_user(global_role_code="SYSTEM_ADMIN")
    second_client = APIClient()
    login(second_client, second_admin)

    def delete_as(client):
        return client.delete("/users/me", {"current_password": PASSWORD}, format="json").status_code

    statuses = sorted(
        run_concurrent(lambda: delete_as(sole_client), lambda: delete_as(second_client))
    )
    assert statuses == [200, 400]
    remaining_active_admins = User.objects.filter(
        global_role_assignments__role__code="SYSTEM_ADMIN",
        account_status=AccountStatus.ACTIVE,
        deleted_at__isnull=True,
    ).count()
    assert remaining_active_admins == 1


def test_email_change_full_verified_flow_and_security_guards(settings):
    user = create_user()
    other = create_user()
    deleted_user = create_user(deleted_at=timezone.now())
    client = APIClient()
    login(client, user)

    # Wrong password rejected.
    bad_pw = client.post(
        "/users/me/email-change/request",
        {"new_email": f"next.{uuid4().hex[:8]}@example.edu.vn", "current_password": "Bad!12345"},
        format="json",
    )
    assert (
        bad_pw.status_code == 400 and bad_pw.json()["error"]["code"] == "INCORRECT_CURRENT_PASSWORD"
    )

    # Same email rejected.
    same = client.post(
        "/users/me/email-change/request",
        {"new_email": user.email.upper(), "current_password": PASSWORD},
        format="json",
    )
    assert same.status_code == 400 and same.json()["error"]["details"][0]["field"] == "new_email"

    # Taken active or soft-deleted email rejected.
    for taken_email in (other.email, deleted_user.email):
        taken = client.post(
            "/users/me/email-change/request",
            {"new_email": taken_email, "current_password": PASSWORD},
            format="json",
        )
        assert taken.status_code == 400
        assert taken.json()["error"]["details"][0]["field"] == "new_email"

    # Missing mail key fails closed 503 with zero EmailChangeRequest rows.
    old_key = settings.IDENTITY_MAIL_KEY
    settings.IDENTITY_MAIL_KEY = None
    unavail = client.post(
        "/users/me/email-change/request",
        {"new_email": f"fail.{uuid4().hex[:8]}@example.edu.vn", "current_password": PASSWORD},
        format="json",
    )
    assert unavail.status_code == 503
    assert not EmailChangeRequest.objects.filter(user=user).exists()
    settings.IDENTITY_MAIL_KEY = old_key

    # First request creates encrypted mail event to new_email_1; second request supersedes first.
    email_1 = f"first.{uuid4().hex[:8]}@example.edu.vn"
    email_2 = f"Second.{uuid4().hex[:8]}@example.edu.vn"
    r1 = client.post(
        "/users/me/email-change/request",
        {"new_email": email_1, "current_password": PASSWORD},
        format="json",
    )
    assert r1.status_code == 200 and r1.json()["data"]["new_email"] == email_1
    ev1 = OutboxEvent.objects.get(
        aggregate_id=user.pk, event_type="identity.email_change.requested"
    )
    assert ev1.data["data"]["email"] == email_1
    token_1 = mail_secret(ev1)["token"]

    r2 = client.post(
        "/users/me/email-change/request",
        {"new_email": f"  {email_2}  ", "current_password": PASSWORD},
        format="json",
    )
    assert r2.status_code == 200 and r2.json()["data"]["new_email"] == email_2.lower()
    ev2 = (
        OutboxEvent.objects.filter(
            aggregate_id=user.pk, event_type="identity.email_change.requested"
        )
        .order_by("-created_at")
        .first()
    )
    assert ev2.data["data"]["email"] == email_2.lower()
    token_2 = mail_secret(ev2)["token"]
    # Raw token is never stored in DB or audit logs.
    assert not EmailChangeRequest.objects.filter(token_hash=token_2).exists()
    assert token_2 not in str(list(AuditLog.objects.filter(target_user_id=str(user.pk)).values()))

    # Superseded token_1 rejected.
    stale_confirm = client.post("/users/me/email-change/confirm", {"token": token_1}, format="json")
    assert stale_confirm.status_code == 400
    assert stale_confirm.json()["error"]["code"] == "INVALID_EMAIL_CHANGE_TOKEN"

    # Cross-user confirmation attempt with token_2 rejected.
    other_client = APIClient()
    login(other_client, other)
    cross = other_client.post("/users/me/email-change/confirm", {"token": token_2}, format="json")
    assert cross.status_code == 400
    assert cross.json()["error"]["code"] == "INVALID_EMAIL_CHANGE_TOKEN"

    # Valid confirmation updates user.email, allauth EmailAddress, audit, outbox, and allows login.
    old_email = user.email
    ok = client.post("/users/me/email-change/confirm", {"token": token_2}, format="json")
    assert ok.status_code == 200, ok.json()
    assert ok.json()["data"]["email"] == email_2.lower()

    user.refresh_from_db()
    assert user.email == email_2.lower()
    assert user.is_email_verified is True
    assert list(
        EmailAddress.objects.filter(user=user).values_list("email", "verified", "primary")
    ) == [(email_2.lower(), True, True)]
    assert AuditLog.objects.filter(target_user_id=str(user.pk), action="EMAIL_CHANGED").exists()
    assert OutboxEvent.objects.filter(
        aggregate_id=user.pk, event_type="identity.user.updated"
    ).exists()

    # Reusing consumed token fails.
    replay = client.post("/users/me/email-change/confirm", {"token": token_2}, format="json")
    assert replay.status_code == 400
    assert replay.json()["error"]["code"] == "INVALID_EMAIL_CHANGE_TOKEN"

    # Can log in with new email; old email no longer works.
    assert login(APIClient(), user, password=PASSWORD).status_code == 200
    assert (
        APIClient()
        .post("/login", {"email": old_email, "password": PASSWORD}, format="json")
        .status_code
        == 401
    )


def test_email_change_expired_conflict_concurrency_and_cleanup():
    user = create_user()
    client = APIClient()
    login(client, user)

    # 1. Expired token -> 400 EMAIL_CHANGE_TOKEN_EXPIRED.
    exp_email = f"exp.{uuid4().hex[:8]}@example.edu.vn"
    assert (
        client.post(
            "/users/me/email-change/request",
            {"new_email": exp_email, "current_password": PASSWORD},
            format="json",
        ).status_code
        == 200
    )
    ev_exp = OutboxEvent.objects.get(
        aggregate_id=user.pk, event_type="identity.email_change.requested"
    )
    tok_exp = mail_secret(ev_exp)["token"]
    now = timezone.now()
    EmailChangeRequest.objects.filter(user=user, consumed_at__isnull=True).update(
        created_at=now - timedelta(hours=2),
        expires_at=now - timedelta(hours=1),
    )
    expired_res = client.post("/users/me/email-change/confirm", {"token": tok_exp}, format="json")
    assert expired_res.status_code == 400
    assert expired_res.json()["error"]["code"] == "EMAIL_CHANGE_TOKEN_EXPIRED"

    # Mark outbox event expired and verify cleanup_identity_data purges row & redacts mail secret.
    ev_data = ev_exp.data
    ev_data["data"]["expires_at"] = (now - timedelta(hours=1)).isoformat()
    ev_data["data"]["secret"]["expires_at"] = (now - timedelta(hours=1)).isoformat()
    ev_exp.data = ev_data
    ev_exp.save(update_fields=("data",))
    cleaned = cleanup_identity_data(apply=True)
    assert cleaned["email_change_requests"] >= 1
    assert cleaned["expired_mail_secrets"] >= 1
    ev_exp.refresh_from_db()
    assert ev_exp.data["data"]["secret"] is None

    # 2. Email taken between request and confirm -> 409 EMAIL_ALREADY_EXISTS.
    race_email = f"raced.{uuid4().hex[:8]}@example.edu.vn"
    assert (
        client.post(
            "/users/me/email-change/request",
            {"new_email": race_email, "current_password": PASSWORD},
            format="json",
        ).status_code
        == 200
    )
    ev_race = (
        OutboxEvent.objects.filter(
            aggregate_id=user.pk, event_type="identity.email_change.requested"
        )
        .order_by("-created_at")
        .first()
    )
    tok_race = mail_secret(ev_race)["token"]
    User.objects.create_user(email=race_email, username=f"sq_{uuid4().hex[:8]}", password=PASSWORD)
    conflict = client.post("/users/me/email-change/confirm", {"token": tok_race}, format="json")
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "EMAIL_ALREADY_EXISTS"

    # 3. Concurrent double-confirm of same token succeeds exactly once.
    final_email = f"final.{uuid4().hex[:8]}@example.edu.vn"
    assert (
        client.post(
            "/users/me/email-change/request",
            {"new_email": final_email, "current_password": PASSWORD},
            format="json",
        ).status_code
        == 200
    )
    ev_final = (
        OutboxEvent.objects.filter(
            aggregate_id=user.pk, event_type="identity.email_change.requested"
        )
        .order_by("-created_at")
        .first()
    )
    tok_final = mail_secret(ev_final)["token"]
    c1, c2 = APIClient(), APIClient()
    login(c1, user)
    login(c2, user)

    def confirm(c):
        return c.post(
            "/users/me/email-change/confirm", {"token": tok_final}, format="json"
        ).status_code

    statuses = sorted(run_concurrent(lambda: confirm(c1), lambda: confirm(c2)))
    assert statuses == [200, 400]
    user.refresh_from_db()
    assert user.email == final_email
    assert AuditLog.objects.filter(target_user_id=str(user.pk), action="EMAIL_CHANGED").count() == 1
