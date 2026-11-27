"""Wave 6.2: linked_providers, has_usable_password, POST /password-set, and DG8 activation flag."""

from uuid import uuid4

import pytest
from allauth.account.models import EmailAddress
from allauth.socialaccount.models import SocialAccount
from django.test import RequestFactory
from rest_framework.test import APIClient

from accounts.models import AccountStatus, AuditLog, OutboxEvent, User, UserSession
from accounts.services.oauth_accounts import OAuthAccountService
from authentication.serializers.auth import SessionTokenSerializer
from tests.helpers import NEW_PASSWORD, PASSWORD, create_user, login, mail_secret, run_concurrent

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True),
    pytest.mark.postgres,
]


def _issue_oauth_session(user):
    fake_req = RequestFactory().post("/oauth/google")
    fake_req._request = fake_req
    user._identity_request = fake_req
    user._identity_device = "Google OAuth Browser"
    token = SessionTokenSerializer.get_token(user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION="Bearer " + str(token.access_token))
    return client, token


def test_me_exposes_linked_providers_and_has_usable_password():
    user = create_user()
    client = APIClient()
    login(client, user)
    data = client.get("/users/me").json()["data"]
    assert data["has_usable_password"] is True
    assert data["linked_providers"] == []

    SocialAccount.objects.create(user=user, provider="google", uid=f"g-{uuid4().hex}")
    SocialAccount.objects.create(user=user, provider="github", uid=f"gh-{uuid4().hex}")
    refreshed = client.get("/users/me").json()["data"]
    assert refreshed["linked_providers"] == ["github", "google"]
    patched = client.patch("/users/me", {"bio": "OAuth profile"}, format="json").json()["data"]
    assert patched["linked_providers"] == ["github", "google"]
    assert patched["has_usable_password"] is True


def test_password_set_solves_google_only_lockout_and_blocks_existing_password():
    # 1. User who already has a password receives 400 PASSWORD_ALREADY_SET.
    existing = create_user()
    existing_client = APIClient()
    login(existing_client, existing)
    denied = existing_client.post(
        "/password-set",
        {"new_password1": NEW_PASSWORD, "new_password2": NEW_PASSWORD},
        format="json",
    )
    assert denied.status_code == 400
    assert denied.json()["error"]["code"] == "PASSWORD_ALREADY_SET"
    assert existing_client.get("/users/me").status_code == 200

    # 2. Passwordless Google-only user: cannot unlink Google before setting password.
    google_user = create_user()
    google_user.set_unusable_password()
    google_user.save(update_fields=("password",))
    SocialAccount.objects.create(user=google_user, provider="google", uid=f"g-{uuid4().hex}")
    g_client, _ = _issue_oauth_session(google_user)

    me = g_client.get("/users/me").json()["data"]
    assert me["has_usable_password"] is False
    assert me["linked_providers"] == ["google"]

    # Mismatch & weak password rejected cleanly in Vietnamese.
    mismatch = g_client.post(
        "/password-set",
        {"new_password1": NEW_PASSWORD, "new_password2": "OtherStrong123!"},
        format="json",
    )
    assert mismatch.status_code == 400 and mismatch.json()["error"]["code"] == "VALIDATION_ERROR"
    weak = g_client.post(
        "/password-set",
        {"new_password1": "123", "new_password2": "123"},
        format="json",
    )
    assert weak.status_code == 400 and weak.json()["error"]["code"] == "VALIDATION_ERROR"

    # Valid POST /password-set sets password, revokes old session, writes PASSWORD_SET audit.
    ok = g_client.post(
        "/password-set",
        {"new_password1": NEW_PASSWORD, "new_password2": NEW_PASSWORD},
        format="json",
    )
    assert ok.status_code == 200, ok.json()
    assert ok.json()["data"] is None
    google_user.refresh_from_db()
    assert google_user.has_usable_password() is True
    assert google_user.check_password(NEW_PASSWORD)
    assert not UserSession.objects.filter(user=google_user, is_revoked=False).exists()
    assert g_client.get("/users/me").status_code == 401
    assert AuditLog.objects.filter(
        target_user_id=str(google_user.pk), action="PASSWORD_SET"
    ).exists()

    # Re-login with the newly set password -> now can unlink Google cleanly!
    fresh_client = APIClient()
    login(fresh_client, google_user, password=NEW_PASSWORD)
    assert fresh_client.get("/users/me").json()["data"]["has_usable_password"] is True
    # Confirm OAuthAccountService unlink guard now passes!
    unlinked = []
    req = RequestFactory().delete("/oauth/google")
    req.user = google_user
    req.auth = {
        "session_id": str(UserSession.objects.get(user=google_user, is_revoked=False).pk),
        "token_family": str(
            UserSession.objects.get(user=google_user, is_revoked=False).token_family
        ),
    }
    OAuthAccountService.unlink_account(req, "google", lambda pk: unlinked.append(pk))
    assert len(unlinked) == 1


def test_password_set_concurrent_requests_succeed_at_most_once():
    google_user = create_user()
    google_user.set_unusable_password()
    google_user.save(update_fields=("password",))
    client1, _ = _issue_oauth_session(google_user)
    client2, _ = _issue_oauth_session(google_user)

    def send(c):
        return c.post(
            "/password-set",
            {"new_password1": NEW_PASSWORD, "new_password2": NEW_PASSWORD},
            format="json",
        ).status_code

    statuses = sorted(run_concurrent(lambda: send(client1), lambda: send(client2)))
    assert statuses[0] == 200 and statuses[1] in {400, 401}
    assert (
        AuditLog.objects.filter(target_user_id=str(google_user.pk), action="PASSWORD_SET").count()
        == 1
    )


def test_dg8_email_activation_flag_on_register_and_login_error(settings, signup_data):
    settings.IDENTITY_REQUIRE_EMAIL_ACTIVATION = True
    public = APIClient()

    reg = public.post("/register", signup_data, format="json")
    assert reg.status_code == 201, reg.json()
    assert reg.json()["data"]["account_status"] == "PENDING_ACTIVATION"
    user = User.objects.get(email=signup_data["email"])
    assert user.account_status == AccountStatus.PENDING_ACTIVATION
    assert user.is_email_verified is False

    mail_event = OutboxEvent.objects.get(
        aggregate_id=user.pk, event_type="identity.activation.requested"
    )
    secret = mail_secret(mail_event)

    # Login before activation returns 403 ACCOUNT_PENDING_ACTIVATION (not 400 VALIDATION_ERROR).
    blocked = public.post("/login", {"email": user.email, "password": PASSWORD}, format="json")
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "ACCOUNT_PENDING_ACTIVATION"

    # Activate -> ACTIVE -> login succeeds.
    act = public.post("/activate", {"key": secret["key"]}, format="json")
    assert act.status_code == 200, act.json()
    user.refresh_from_db()
    assert user.account_status == AccountStatus.ACTIVE and user.is_email_verified is True
    assert login(public, user).status_code == 200


def test_dg8_email_activation_flag_on_student_provisioning(settings):
    settings.IDENTITY_REQUIRE_EMAIL_ACTIVATION = True
    settings.IDENTITY_SERVICE_KEYS = {"classroom": "dg8-classroom-key"}
    teacher = create_user(global_role_code="TEACHER")
    t_client = APIClient()
    login(t_client, teacher)

    student_email = f"imported.{uuid4().hex[:8]}@example.edu.vn"
    res = t_client.post(
        "/api/v1/internal/users/provision-students",
        {
            "students": [
                {
                    "row_number": 1,
                    "email": student_email,
                    "student_id": "SV-DG8-01",
                    "first_name": "Bình",
                    "last_name": "Võ",
                }
            ]
        },
        format="json",
        HTTP_X_SERVICE_KEY="dg8-classroom-key",
        HTTP_IDEMPOTENCY_KEY=str(uuid4()),
    )
    assert res.status_code == 201, res.json()
    row_data = res.json()["data"]["results"][0]
    assert row_data["account_result"] == "CREATED"
    assert row_data["account_status"] == "PENDING_ACTIVATION"

    student = User.objects.get(pk=row_data["user_id"])
    assert student.has_usable_password() is False
    assert student.is_email_verified is False
    assert OutboxEvent.objects.filter(
        aggregate_id=student.pk, event_type="identity.user.created"
    ).exists()
    mail_event = OutboxEvent.objects.get(
        aggregate_id=student.pk, event_type="identity.student.imported"
    )
    assert mail_event.data["data"]["student_id"] == "SV-DG8-01"
    secret = mail_secret(mail_event)

    # Cannot log in with email-as-password anymore.
    assert (
        APIClient()
        .post("/login", {"email": student.email, "password": student.email}, format="json")
        .status_code
        == 401
    )

    # Activate with new password -> ACTIVE -> login succeeds.
    act = APIClient().post(
        "/activate",
        {"key": secret["key"], "new_password1": NEW_PASSWORD, "new_password2": NEW_PASSWORD},
        format="json",
    )
    assert act.status_code == 200, act.json()
    assert login(APIClient(), student, password=NEW_PASSWORD).status_code == 200


def test_login_with_active_status_but_unverified_email_returns_account_pending_activation():
    user = create_user(account_status=AccountStatus.ACTIVE)
    EmailAddress.objects.filter(user=user).update(verified=False)

    res = APIClient().post("/login", {"email": user.email, "password": PASSWORD}, format="json")
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "ACCOUNT_PENDING_ACTIVATION"
    assert any("À" <= ch <= "ỹ" for ch in res.json()["message"])
    assert not UserSession.objects.filter(user=user).exists()
