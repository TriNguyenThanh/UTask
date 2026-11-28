"""Integration tests for Identity auth lifecycle, self-service, admin, and PG triggers."""

from __future__ import annotations

import base64
import hashlib
import json
from uuid import uuid4

import pytest
from allauth.account.models import EmailAddress
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.conf import settings as django_settings
from django.db import DatabaseError, connection, transaction
from rest_framework.test import APIClient

from apps.accounts.models import (
    AccountStatus,
    AuditLog,
    GlobalRole,
    GlobalRoleCode,
    User,
    UserGlobalRole,
    UserProfile,
    UserSession,
)
from apps.authentication.adapters.session_tokens import FamilyRefreshToken, token_expiry
from apps.messaging.models import OutboxEvent

pytestmark = [pytest.mark.integration, pytest.mark.django_db]

ENVELOPE_KEYS = {"success", "message", "data", "meta", "error"}
DEFAULT_PASSWORD = "StrongPass123!"
NEW_PASSWORD = "NewStrongPass456!"


def _has_vietnamese_diacritics(text: str) -> bool:
    return any("À" <= ch <= "ỹ" for ch in text)


def _assert_envelope(response, *, status_code: int, success: bool = True) -> dict:
    assert response.status_code == status_code, response.content
    body = response.json()
    assert set(body) == ENVELOPE_KEYS
    assert body["success"] is success
    assert isinstance(body["message"], str) and body["message"].strip()
    assert _has_vietnamese_diacritics(body["message"]), body["message"]
    if success:
        assert body["error"] is None
    else:
        assert body["data"] is None
        assert isinstance(body["error"], dict)
        assert isinstance(body["error"]["code"], str)
        assert isinstance(body["error"]["details"], list)
    return body


def _assert_error(response, *, status_code: int, code: str) -> dict:
    body = _assert_envelope(response, status_code=status_code, success=False)
    assert body["error"]["code"] == code
    for forbidden in ("Traceback", "Exception", "SQL", "uploader", "scope Teacher"):
        assert forbidden not in body["message"]
        for detail in body["error"]["details"]:
            assert forbidden not in detail.get("issue", "")
    return body


def _create_user(
    *,
    email: str | None = None,
    username: str | None = None,
    password: str | None = DEFAULT_PASSWORD,
    roles: tuple[str, ...] = (GlobalRoleCode.STUDENT,),
    status: str = AccountStatus.ACTIVE,
    verified: bool = True,
    first_name: str = "An",
    last_name: str = "Nguyễn",
    student_id: str | None = None,
) -> User:
    suffix = uuid4().hex[:8]
    user = User.objects.create_user(
        email=email or f"user_{suffix}@example.edu.vn",
        username=username or f"user_{suffix}",
        password=password,
        student_id=student_id,
        first_name=first_name,
        last_name=last_name,
        global_role_code=roles[0],
        account_status=status,
    )
    for role_code in roles[1:]:
        role = GlobalRole.objects.get(code=role_code)
        UserGlobalRole.objects.get_or_create(user=user, role=role)
    if verified:
        EmailAddress.objects.create(user=user, email=user.email, primary=True, verified=True)
    user.profile.refresh_from_db()
    return user


def _login_user(
    *,
    email: str | None = None,
    username: str | None = None,
    password: str = DEFAULT_PASSWORD,
    device_name: str = "Chrome Desktop",
    remote_addr: str = "127.0.0.1",
) -> tuple[APIClient, dict, dict]:
    client = APIClient()
    payload: dict[str, str] = {"password": password, "device_name": device_name}
    if email is not None:
        payload["email"] = email
    else:
        assert username is not None
        payload["username"] = username
    response = client.post(
        "/api/auth/login",
        payload,
        format="json",
        secure=True,
        REMOTE_ADDR=remote_addr,
    )
    body = _assert_envelope(response, status_code=200, success=True)
    access = body["data"]["access"]
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    cookies = {
        "refresh_token": response.cookies["refresh_token"],
        "csrftoken": response.cookies["csrftoken"],
    }
    return client, body, cookies


def _issue_direct_session(user: User) -> tuple[APIClient, UserSession]:
    """Issue a real RS256 FamilyRefreshToken + UserSession for OAuth-only accounts."""
    token = FamilyRefreshToken.for_user(user)
    session_id, family = uuid4(), uuid4()
    token["session_id"] = str(session_id)
    token["token_family"] = str(family)
    token["family_exp"] = token["exp"]
    raw_refresh = str(token)
    session = UserSession.objects.create(
        id=session_id,
        user=user,
        token_family=family,
        refresh_token_hash=hashlib.sha256(raw_refresh.encode()).hexdigest(),
        refresh_jti=token["jti"],
        ip_address="127.0.0.1",
        user_agent="pytest",
        device_name="OAuth Device",
        expires_at=token_expiry(token),
    )
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")
    return client, session


def _decrypt_mail_secret(event: OutboxEvent) -> dict:
    envelope = event.data
    payload = envelope["data"]
    secret = payload["secret"]
    key = base64.b64decode(django_settings.IDENTITY_MAIL_KEY)
    aad = json.dumps(
        [
            envelope["event_id"],
            envelope["event_type"],
            payload["user_id"],
            secret["expires_at"],
        ],
        separators=(",", ":"),
    ).encode()
    plaintext = AESGCM(key).decrypt(
        base64.b64decode(secret["nonce"]),
        base64.b64decode(secret["ciphertext"]),
        aad,
    )
    return json.loads(plaintext)


# ---------------------------------------------------------------------------
# 1. Public auth lifecycle (/api/auth/*)
# ---------------------------------------------------------------------------


def test_csrf_endpoint_sets_cookie_and_no_store_header():
    client = APIClient()
    response = client.get("/api/auth/csrf", secure=True)

    body = _assert_envelope(response, status_code=200)
    assert body["data"]["csrf_token"]
    assert "csrftoken" in response.cookies
    assert response.headers["Cache-Control"] == "no-store"


def test_register_auto_active_when_email_activation_disabled(settings):
    settings.IDENTITY_REQUIRE_EMAIL_ACTIVATION = False
    client = APIClient()
    email = f"student_{uuid4().hex[:8]}@utask.edu.vn"
    username = f"sv_{uuid4().hex[:8]}"

    response = client.post(
        "/api/auth/register",
        {
            "email": email.upper(),
            "username": username.upper(),
            "password1": DEFAULT_PASSWORD,
            "password2": DEFAULT_PASSWORD,
            "first_name": "Minh",
            "last_name": "Trần",
        },
        format="json",
        secure=True,
    )
    body = _assert_envelope(response, status_code=201)
    assert body["data"]["account_status"] == AccountStatus.ACTIVE
    assert body["data"]["user"]["email"] == email
    assert body["data"]["user"]["username"] == username
    assert body["data"]["user"]["display_name"] == "Trần Minh"
    assert body["data"]["user"]["roles"] == [GlobalRoleCode.STUDENT]

    outbox = OutboxEvent.objects.filter(
        aggregate_id=body["data"]["user"]["id"],
        event_type="identity.user.created",
    ).first()
    assert outbox is not None
    assert outbox.topic == "utask.identity.events"
    assert outbox.data["producer"] == "identity-service"

    # Immediately usable for login without manual activation.
    _, login_body, _ = _login_user(email=email)
    assert login_body["data"]["user"]["email"] == email

    # Duplicate email returns Vietnamese validation error.
    dup = client.post(
        "/api/auth/register",
        {
            "email": email,
            "username": f"other_{uuid4().hex[:8]}",
            "password1": DEFAULT_PASSWORD,
            "password2": DEFAULT_PASSWORD,
            "first_name": "An",
            "last_name": "Lê",
        },
        format="json",
        secure=True,
    )
    dup_body = _assert_error(dup, status_code=400, code="VALIDATION_ERROR")
    assert any(d.get("field") == "email" for d in dup_body["error"]["details"])

    # Idempotency-Key header is rejected cleanly on register.
    with_idem = client.post(
        "/api/auth/register",
        {
            "email": f"idem_{uuid4().hex[:8]}@utask.edu.vn",
            "username": f"idem_{uuid4().hex[:8]}",
            "password1": DEFAULT_PASSWORD,
            "password2": DEFAULT_PASSWORD,
            "first_name": "An",
            "last_name": "Lê",
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="idem-not-allowed",
        secure=True,
    )
    _assert_error(with_idem, status_code=400, code="VALIDATION_ERROR")


def test_register_and_activate_flow_when_email_activation_enabled(settings):
    settings.IDENTITY_REQUIRE_EMAIL_ACTIVATION = True
    client = APIClient()
    email = f"pending_{uuid4().hex[:8]}@utask.edu.vn"
    username = f"pending_{uuid4().hex[:8]}"

    reg = client.post(
        "/api/auth/register",
        {
            "email": email,
            "username": username,
            "password1": DEFAULT_PASSWORD,
            "password2": DEFAULT_PASSWORD,
            "first_name": "Hải",
            "last_name": "Phạm",
        },
        format="json",
        secure=True,
    )
    reg_body = _assert_envelope(reg, status_code=201)
    user_id = reg_body["data"]["user"]["id"]
    assert reg_body["data"]["account_status"] == AccountStatus.PENDING_ACTIVATION

    # Login before activation is rejected with 403 ACCOUNT_PENDING_ACTIVATION.
    blocked_login = client.post(
        "/api/auth/login",
        {"email": email, "password": DEFAULT_PASSWORD},
        format="json",
        secure=True,
    )
    _assert_error(blocked_login, status_code=403, code="ACCOUNT_PENDING_ACTIVATION")

    # Resend activation rotates the key and emits a fresh encrypted mail outbox event.
    resend = client.post(
        "/api/auth/activation/resend",
        {"email": email},
        format="json",
        secure=True,
    )
    _assert_envelope(resend, status_code=200)

    mail_events = list(
        OutboxEvent.objects.filter(
            aggregate_id=user_id,
            event_type="identity.activation.requested",
        ).order_by("created_at")
    )
    assert len(mail_events) == 2
    old_secret = _decrypt_mail_secret(mail_events[0])
    new_secret = _decrypt_mail_secret(mail_events[1])
    assert old_secret["key"] != new_secret["key"]

    # Superseded key no longer activates the account.
    stale_act = client.post(
        "/api/auth/activate",
        {"key": old_secret["key"]},
        format="json",
        secure=True,
    )
    _assert_error(stale_act, status_code=404, code="RESOURCE_NOT_FOUND")

    # Latest key activates account and enables login.
    activated = client.post(
        "/api/auth/activate",
        {"key": new_secret["key"]},
        format="json",
        secure=True,
    )
    _assert_envelope(activated, status_code=200)

    user = User.objects.get(pk=user_id)
    assert user.account_status == AccountStatus.ACTIVE
    assert user.is_email_verified is True
    assert OutboxEvent.objects.filter(
        aggregate_id=user_id,
        event_type="identity.user.activated",
    ).exists()

    _, login_body, _ = _login_user(username=username)
    assert login_body["data"]["user"]["id"] == user_id


def test_login_cookie_refresh_rotation_and_replay_revokes_family():
    user = _create_user()
    client, login_body, cookies = _login_user(email=user.email, device_name="Laptop Chrome")

    refresh_cookie = cookies["refresh_token"]
    assert refresh_cookie["httponly"] is True
    assert refresh_cookie["secure"] is True
    assert refresh_cookie["samesite"] == "Lax"
    assert refresh_cookie["path"] == "/api/auth"
    original_refresh = refresh_cookie.value

    # Cookie-based refresh without X-CSRFToken header is rejected by CSRF enforcement.
    no_csrf_client = APIClient(enforce_csrf_checks=True)
    no_csrf_client.cookies["refresh_token"] = original_refresh
    no_csrf_client.cookies["csrftoken"] = cookies["csrftoken"].value
    csrf_rejected = no_csrf_client.post(
        "/api/auth/refresh",
        {},
        format="json",
        HTTP_ORIGIN="https://localhost",
        secure=True,
    )
    _assert_error(csrf_rejected, status_code=403, code="PERMISSION_DENIED")

    # Valid refresh rotates refresh token and keeps cookie attributes intact.
    refresh_client = APIClient(enforce_csrf_checks=True)
    refresh_client.cookies["refresh_token"] = original_refresh
    refresh_client.cookies["csrftoken"] = cookies["csrftoken"].value
    refreshed = refresh_client.post(
        "/api/auth/refresh",
        {},
        format="json",
        HTTP_ORIGIN="https://localhost",
        HTTP_X_CSRFTOKEN=cookies["csrftoken"].value,
        secure=True,
    )
    refreshed_body = _assert_envelope(refreshed, status_code=200)
    rotated_access = refreshed_body["data"]["access"]
    rotated_cookie = refreshed.cookies["refresh_token"]
    assert rotated_cookie["path"] == "/api/auth"
    assert rotated_cookie["httponly"] is True
    assert rotated_cookie.value != original_refresh

    # Reusing the superseded refresh token triggers replay detection & revokes the session family.
    replay_client = APIClient(enforce_csrf_checks=True)
    replay_client.cookies["refresh_token"] = original_refresh
    replay_client.cookies["csrftoken"] = cookies["csrftoken"].value
    replay = replay_client.post(
        "/api/auth/refresh",
        {},
        format="json",
        HTTP_ORIGIN="https://localhost",
        HTTP_X_CSRFTOKEN=cookies["csrftoken"].value,
        secure=True,
    )
    _assert_error(replay, status_code=401, code="TOKEN_REPLAY_ATTACK_DETECTED")

    session = UserSession.objects.get(user=user)
    assert session.is_revoked is True
    assert session.revoked_reason == "REPLAY_ATTACK"
    assert AuditLog.objects.filter(
        target_user_id=str(user.pk),
        action="SECURITY_TOKEN_REPLAY_DETECTED",
    ).exists()

    # Access tokens issued for that revoked family are rejected immediately.
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {rotated_access}")
    me_after_replay = client.get("/api/auth/users/me", secure=True)
    _assert_error(me_after_replay, status_code=401, code="TOKEN_REVOKED")
    assert login_body["data"]["access"] != rotated_access


def test_logout_logout_all_and_device_management():
    user = _create_user()
    client_one, _, cookies_one = _login_user(email=user.email, device_name="Workstation")
    client_two, _, _ = _login_user(email=user.email, device_name="Mobile")
    client_three, _, _ = _login_user(email=user.email, device_name="Tablet")

    # List active sessions/devices.
    listed = client_one.get("/api/auth/sessions", secure=True)
    listed_body = _assert_envelope(listed, status_code=200)
    devices = listed_body["data"]
    assert len(devices) == 3
    by_name = {item["device_name"]: item for item in devices}
    assert {"Workstation", "Mobile", "Tablet"} == set(by_name)

    # Revoke a single remote device (Tablet) while Workstation remains active.
    revoke_tablet = client_one.delete(
        f"/api/auth/sessions/{by_name['Tablet']['id']}",
        secure=True,
    )
    _assert_envelope(revoke_tablet, status_code=200)
    _assert_error(
        client_three.get("/api/auth/users/me", secure=True),
        status_code=401,
        code="TOKEN_REVOKED",
    )
    _assert_envelope(client_one.get("/api/auth/users/me", secure=True), status_code=200)

    # Unknown session ID returns 404 SESSION_NOT_FOUND.
    missing = client_one.delete(f"/api/auth/sessions/{uuid4()}", secure=True)
    _assert_error(missing, status_code=404, code="SESSION_NOT_FOUND")

    # Logout current session (Workstation) using its refresh cookie + CSRF token.
    client_one.cookies["refresh_token"] = cookies_one["refresh_token"].value
    client_one.cookies["csrftoken"] = cookies_one["csrftoken"].value
    logged_out = client_one.post(
        "/api/auth/logout",
        {},
        format="json",
        HTTP_X_CSRFTOKEN=cookies_one["csrftoken"].value,
        secure=True,
    )
    _assert_envelope(logged_out, status_code=200)
    _assert_error(
        client_one.get("/api/auth/users/me", secure=True),
        status_code=401,
        code="TOKEN_REVOKED",
    )

    # Mobile is still active; open one more device then invoke logout-all.
    client_four, _, _ = _login_user(email=user.email, device_name="Browser 4")
    logout_all = client_two.post("/api/auth/logout-all", {}, format="json", secure=True)
    logout_all_body = _assert_envelope(logout_all, status_code=200)
    assert logout_all_body["data"]["revoked_sessions_count"] == 2
    _assert_error(
        client_two.get("/api/auth/users/me", secure=True),
        status_code=401,
        code="TOKEN_REVOKED",
    )
    _assert_error(
        client_four.get("/api/auth/users/me", secure=True),
        status_code=401,
        code="TOKEN_REVOKED",
    )


def test_password_change_reset_and_initial_set_flows():
    # 1. Password change
    user = _create_user()
    client, _, _ = _login_user(email=user.email)

    same_pwd = client.post(
        "/api/auth/password-change",
        {
            "old_password": DEFAULT_PASSWORD,
            "new_password1": DEFAULT_PASSWORD,
            "new_password2": DEFAULT_PASSWORD,
        },
        format="json",
        secure=True,
    )
    _assert_error(same_pwd, status_code=400, code="VALIDATION_ERROR")

    changed = client.post(
        "/api/auth/password-change",
        {
            "old_password": DEFAULT_PASSWORD,
            "new_password1": NEW_PASSWORD,
            "new_password2": NEW_PASSWORD,
        },
        format="json",
        secure=True,
    )
    _assert_envelope(changed, status_code=200)
    # Changing password revokes active sessions.
    _assert_error(
        client.get("/api/auth/users/me", secure=True),
        status_code=401,
        code="TOKEN_REVOKED",
    )

    # 2. Password reset request & confirm via encrypted outbox event
    anon = APIClient()
    reset_req = anon.post(
        "/api/auth/password-reset/request",
        {"email": user.email},
        format="json",
        secure=True,
    )
    _assert_envelope(reset_req, status_code=200)

    # Unknown email returns identical 200 to prevent account enumeration.
    unknown_req = anon.post(
        "/api/auth/password-reset/request",
        {"email": "nonexistent@utask.edu.vn"},
        format="json",
        secure=True,
    )
    _assert_envelope(unknown_req, status_code=200)

    reset_event = (
        OutboxEvent.objects.filter(
            aggregate_id=str(user.pk),
            event_type="identity.password_reset.requested",
        )
        .order_by("-created_at")
        .first()
    )
    assert reset_event is not None
    reset_secret = _decrypt_mail_secret(reset_event)
    final_password = "ResetStrongPass789!"

    confirm = anon.post(
        "/api/auth/password-reset/confirm",
        {
            "uid": reset_secret["uid"],
            "token": reset_secret["token"],
            "new_password1": final_password,
            "new_password2": final_password,
        },
        format="json",
        secure=True,
    )
    _assert_envelope(confirm, status_code=200)

    # Login with reset password succeeds; replaying reset token fails.
    _login_user(email=user.email, password=final_password)
    replay_confirm = anon.post(
        "/api/auth/password-reset/confirm",
        {
            "uid": reset_secret["uid"],
            "token": reset_secret["token"],
            "new_password1": "AnotherPass999!",
            "new_password2": "AnotherPass999!",
        },
        format="json",
        secure=True,
    )
    _assert_error(replay_confirm, status_code=400, code="VALIDATION_ERROR")

    # 3. Initial password-set for OAuth-only account without usable password
    oauth_user = _create_user(password=None)
    assert oauth_user.has_usable_password() is False
    oauth_client, _ = _issue_direct_session(oauth_user)

    set_resp = oauth_client.post(
        "/api/auth/password-set",
        {"new_password1": DEFAULT_PASSWORD, "new_password2": DEFAULT_PASSWORD},
        format="json",
        secure=True,
    )
    _assert_envelope(set_resp, status_code=200)
    oauth_user.refresh_from_db()
    assert oauth_user.has_usable_password() is True

    # Calling password-set once a password already exists fails with PASSWORD_ALREADY_SET.
    logged_in_oauth, _, _ = _login_user(email=oauth_user.email, password=DEFAULT_PASSWORD)
    second_set = logged_in_oauth.post(
        "/api/auth/password-set",
        {"new_password1": NEW_PASSWORD, "new_password2": NEW_PASSWORD},
        format="json",
        secure=True,
    )
    _assert_error(second_set, status_code=400, code="PASSWORD_ALREADY_SET")


def test_axes_login_lockout_returns_429_and_admin_can_unlock(settings):
    user = _create_user()
    admin = _create_user(roles=(GlobalRoleCode.SYSTEM_ADMIN,))
    admin_client, _, _ = _login_user(email=admin.email, remote_addr="10.0.0.2")

    anon = APIClient()
    limit = settings.AXES_FAILURE_LIMIT
    for _ in range(limit - 1):
        fail = anon.post(
            "/api/auth/login",
            {"email": user.email, "password": "WrongPassword1!"},
            format="json",
            secure=True,
            REMOTE_ADDR="10.0.0.10",
        )
        _assert_error(fail, status_code=401, code="INVALID_CREDENTIALS")

    locked = anon.post(
        "/api/auth/login",
        {"email": user.email, "password": "WrongPassword1!"},
        format="json",
        secure=True,
        REMOTE_ADDR="10.0.0.10",
    )
    _assert_error(locked, status_code=429, code="RATE_LIMIT_EXCEEDED")

    # Even correct credentials stay locked until cooloff or admin unlock.
    still_locked = anon.post(
        "/api/auth/login",
        {"email": user.email, "password": DEFAULT_PASSWORD},
        format="json",
        secure=True,
        REMOTE_ADDR="10.0.0.10",
    )
    _assert_error(still_locked, status_code=429, code="RATE_LIMIT_EXCEEDED")

    # Admin inspects lockout status and unlocks the account.
    detail = admin_client.get(f"/api/auth/admin/users/{user.pk}", secure=True)
    detail_body = _assert_envelope(detail, status_code=200)
    assert detail_body["data"]["is_login_locked"] is True
    assert detail_body["data"]["failed_login_attempts"] >= limit

    unlock = admin_client.post(
        f"/api/auth/admin/users/{user.pk}/unlock-login",
        {},
        format="json",
        secure=True,
    )
    unlock_body = _assert_envelope(unlock, status_code=200)
    assert unlock_body["data"]["is_login_locked"] is False
    assert unlock_body["data"]["cleared_attempts"] >= 1

    # Login now succeeds from the previously locked IP.
    _login_user(email=user.email, password=DEFAULT_PASSWORD, remote_addr="10.0.0.10")


# ---------------------------------------------------------------------------
# 2. Account self-service (/api/auth/users/*)
# ---------------------------------------------------------------------------


def test_account_self_service_profile_email_change_search_batch_and_public():
    student = _create_user(first_name="Lan", last_name="Lê", student_id="sv20260001")
    peer = _create_user(first_name="Khang", last_name="Võ", student_id="SV20260002")
    teacher = _create_user(
        first_name="Hùng",
        last_name="Đỗ",
        roles=(GlobalRoleCode.TEACHER,),
    )
    student_client, _, _ = _login_user(email=student.email)
    teacher_client, _, _ = _login_user(email=teacher.email)

    # GET /api/auth/users/me
    me = student_client.get("/api/auth/users/me", secure=True)
    me_body = _assert_envelope(me, status_code=200)
    assert me_body["data"]["student_id"] == "SV20260001"
    assert me_body["data"]["display_name"] == "Lê Lan"

    # PATCH /api/auth/users/me updates profile & triggers display_name sync + outbox event.
    patched = student_client.patch(
        "/api/auth/users/me",
        {
            "first_name": "Mai",
            "last_name": "Hoàng",
            "bio": "Backend engineer",
            "timezone": "Asia/Ho_Chi_Minh",
            "preferences": {"theme": "dark"},
        },
        format="json",
        secure=True,
    )
    patched_body = _assert_envelope(patched, status_code=200)
    assert patched_body["data"]["display_name"] == "Hoàng Mai"
    assert patched_body["data"]["bio"] == "Backend engineer"
    assert patched_body["data"]["preferences"] == {"theme": "dark"}
    assert OutboxEvent.objects.filter(
        aggregate_id=str(student.pk),
        event_type="identity.user.updated",
    ).exists()

    # Invalid timezone returns Vietnamese validation error.
    bad_tz = student_client.patch(
        "/api/auth/users/me",
        {"timezone": "Invalid/Zone"},
        format="json",
        secure=True,
    )
    _assert_error(bad_tz, status_code=400, code="VALIDATION_ERROR")

    # Email change: wrong password rejected, valid request emits encrypted token & confirm updates.
    new_email = f"updated_{uuid4().hex[:8]}@utask.edu.vn"
    bad_req = student_client.post(
        "/api/auth/users/me/email-change/request",
        {"new_email": new_email, "current_password": "WrongPassword1!"},
        format="json",
        secure=True,
    )
    _assert_error(bad_req, status_code=400, code="INCORRECT_CURRENT_PASSWORD")

    ok_req = student_client.post(
        "/api/auth/users/me/email-change/request",
        {"new_email": new_email, "current_password": DEFAULT_PASSWORD},
        format="json",
        secure=True,
    )
    ok_req_body = _assert_envelope(ok_req, status_code=200)
    assert ok_req_body["data"]["new_email"] == new_email

    change_event = (
        OutboxEvent.objects.filter(
            aggregate_id=str(student.pk),
            event_type="identity.email_change.requested",
        )
        .order_by("-created_at")
        .first()
    )
    assert change_event is not None
    change_secret = _decrypt_mail_secret(change_event)

    confirmed = student_client.post(
        "/api/auth/users/me/email-change/confirm",
        {"token": change_secret["token"]},
        format="json",
        secure=True,
    )
    confirmed_body = _assert_envelope(confirmed, status_code=200)
    assert confirmed_body["data"]["email"] == new_email

    # Consumed email-change token cannot be replayed.
    replay_confirm = student_client.post(
        "/api/auth/users/me/email-change/confirm",
        {"token": change_secret["token"]},
        format="json",
        secure=True,
    )
    _assert_error(replay_confirm, status_code=400, code="INVALID_EMAIL_CHANGE_TOKEN")

    # User search: forbidden for STUDENT, allowed for TEACHER.
    student_search = student_client.get("/api/auth/users/search?q=SV2026", secure=True)
    _assert_error(student_search, status_code=403, code="FORBIDDEN_TEACHER_OR_ADMIN")

    teacher_search = teacher_client.get(
        "/api/auth/users/search?q=SV20260002&role=STUDENT&limit=5",
        secure=True,
    )
    search_body = _assert_envelope(teacher_search, status_code=200)
    assert [u["id"] for u in search_body["data"]["users"]] == [str(peer.pk)]
    assert search_body["meta"] == {"total": 1, "limit": 5}

    # Short query rejected with Vietnamese validation detail.
    short_q = teacher_client.get("/api/auth/users/search?q=a", secure=True)
    short_body = _assert_error(short_q, status_code=400, code="VALIDATION_ERROR")
    assert any("2 ký tự" in detail["issue"] for detail in short_body["error"]["details"])

    # Batch users preserves request order and omits unknown IDs.
    batch = student_client.post(
        "/api/auth/users/batch",
        {"user_ids": [str(peer.pk), str(uuid4()), str(student.pk)]},
        format="json",
        secure=True,
    )
    batch_body = _assert_envelope(batch, status_code=200)
    assert [u["id"] for u in batch_body["data"]["users"]] == [str(peer.pk), str(student.pk)]
    assert batch_body["meta"] == {"total": 2}

    # Public user profile endpoint.
    pub = student_client.get(f"/api/auth/users/{peer.pk}", secure=True)
    pub_body = _assert_envelope(pub, status_code=200)
    assert pub_body["data"]["id"] == str(peer.pk)
    assert pub_body["data"]["display_name"] == "Võ Khang"
    _assert_error(
        student_client.get(f"/api/auth/users/{uuid4()}", secure=True),
        status_code=404,
        code="RESOURCE_NOT_FOUND",
    )


# ---------------------------------------------------------------------------
# 3. Admin management (/api/auth/admin/*)
# ---------------------------------------------------------------------------


def test_admin_management_lifecycle_status_roles_sessions_and_audit_logs():
    admin = _create_user(roles=(GlobalRoleCode.SYSTEM_ADMIN,), first_name="Quản", last_name="Trị")
    target = _create_user(roles=(GlobalRoleCode.STUDENT,), first_name="Nam", last_name="Bùi")
    admin_client, _, _ = _login_user(email=admin.email)
    target_client_1, _, _ = _login_user(email=target.email, device_name="Target PC")
    target_client_2, _, _ = _login_user(email=target.email, device_name="Target Phone")

    # Non-admin receives 403 FORBIDDEN_ADMIN_ONLY with Vietnamese message.
    _assert_error(
        target_client_1.get("/api/auth/admin/users", secure=True),
        status_code=403,
        code="FORBIDDEN_ADMIN_ONLY",
    )

    # List & detail users.
    users_list = admin_client.get(f"/api/auth/admin/users?search={target.email}", secure=True)
    list_body = _assert_envelope(users_list, status_code=200)
    assert any(item["id"] == str(target.pk) for item in list_body["data"])

    detail = admin_client.get(f"/api/auth/admin/users/{target.pk}", secure=True)
    detail_body = _assert_envelope(detail, status_code=200)
    assert detail_body["data"]["active_sessions_count"] == 2

    # Admin session list, single revoke, and revoke-all.
    sessions_resp = admin_client.get(f"/api/auth/admin/users/{target.pk}/sessions", secure=True)
    sessions_body = _assert_envelope(sessions_resp, status_code=200)
    assert len(sessions_body["data"]) == 2
    first_session_id = sessions_body["data"][0]["id"]

    revoke_one = admin_client.delete(
        f"/api/auth/admin/users/{target.pk}/sessions/{first_session_id}",
        secure=True,
    )
    revoke_one_body = _assert_envelope(revoke_one, status_code=200)
    assert revoke_one_body["data"]["revoked"] is True

    revoke_all = admin_client.post(
        f"/api/auth/admin/users/{target.pk}/sessions/revoke-all",
        {},
        format="json",
        secure=True,
    )
    revoke_all_body = _assert_envelope(revoke_all, status_code=200)
    assert revoke_all_body["data"]["revoked_sessions_count"] == 1
    _assert_error(
        target_client_1.get("/api/auth/users/me", secure=True),
        status_code=401,
        code="TOKEN_REVOKED",
    )
    _assert_error(
        target_client_2.get("/api/auth/users/me", secure=True),
        status_code=401,
        code="TOKEN_REVOKED",
    )

    # Role grant (POST) and revoke (DELETE with JSON body).
    grant = admin_client.post(
        f"/api/auth/admin/users/{target.pk}/roles",
        {"role_code": GlobalRoleCode.TEACHER},
        format="json",
        secure=True,
    )
    grant_body = _assert_envelope(grant, status_code=200)
    assert sorted(grant_body["data"]["roles"]) == [GlobalRoleCode.STUDENT, GlobalRoleCode.TEACHER]

    revoke_role = admin_client.delete(
        f"/api/auth/admin/users/{target.pk}/roles",
        {"role_code": GlobalRoleCode.TEACHER},
        format="json",
        secure=True,
    )
    revoke_role_body = _assert_envelope(revoke_role, status_code=200)
    assert revoke_role_body["data"]["roles"] == [GlobalRoleCode.STUDENT]

    # Admin cannot revoke own SYSTEM_ADMIN role.
    self_revoke = admin_client.delete(
        f"/api/auth/admin/users/{admin.pk}/roles",
        {"role_code": GlobalRoleCode.SYSTEM_ADMIN},
        format="json",
        secure=True,
    )
    _assert_error(self_revoke, status_code=400, code="CANNOT_REVOKE_OWN_ADMIN_ROLE")

    # Suspend & reactivate target user; admin cannot suspend self.
    self_suspend = admin_client.patch(
        f"/api/auth/admin/users/{admin.pk}/status",
        {"status": AccountStatus.SUSPENDED, "reason": "Tự đình chỉ"},
        format="json",
        secure=True,
    )
    _assert_error(self_suspend, status_code=400, code="CANNOT_SUSPEND_SELF")

    suspended = admin_client.patch(
        f"/api/auth/admin/users/{target.pk}/status",
        {"status": AccountStatus.SUSPENDED, "reason": "Vi phạm nội quy"},
        format="json",
        secure=True,
    )
    suspended_body = _assert_envelope(suspended, status_code=200)
    assert suspended_body["data"]["account_status"] == AccountStatus.SUSPENDED

    blocked_login = APIClient().post(
        "/api/auth/login",
        {"email": target.email, "password": DEFAULT_PASSWORD},
        format="json",
        secure=True,
    )
    _assert_error(blocked_login, status_code=403, code="ACCOUNT_SUSPENDED")

    reactivated = admin_client.patch(
        f"/api/auth/admin/users/{target.pk}/status",
        {"status": AccountStatus.ACTIVE, "reason": "Đã khôi phục quyền truy cập"},
        format="json",
        secure=True,
    )
    reactivated_body = _assert_envelope(reactivated, status_code=200)
    assert reactivated_body["data"]["account_status"] == AccountStatus.ACTIVE
    _login_user(email=target.email)

    # Admin audit logs list & filtering.
    audit_resp = admin_client.get(
        f"/api/auth/admin/audit-logs?target_user_id={target.pk}&action=ROLE_REVOKED",
        secure=True,
    )
    audit_body = _assert_envelope(audit_resp, status_code=200)
    assert len(audit_body["data"]) == 1
    assert audit_body["data"][0]["action"] == "ROLE_REVOKED"
    assert audit_body["data"][0]["actor_id"] == str(admin.pk)


# ---------------------------------------------------------------------------
# 4. PostgreSQL write guards (live Postgres 16 triggers)
# ---------------------------------------------------------------------------


def test_postgres_display_name_trigger_syncs_on_insert_and_update():
    user = _create_user(first_name="Bình", last_name="Trần")
    profile = UserProfile.objects.get(user=user)
    assert profile.display_name == "Trần Bình"

    # Updating first_name / last_name recalculates display_name inside PostgreSQL.
    profile.first_name = "Khánh"
    profile.last_name = "Lý"
    profile.save(update_fields=("first_name", "last_name"))
    profile.refresh_from_db()
    assert profile.display_name == "Lý Khánh"

    # Blank names fall back to canonical Vietnamese placeholder.
    empty_user = _create_user(first_name="", last_name="")
    empty_profile = UserProfile.objects.get(user=empty_user)
    assert empty_profile.display_name == "Thành viên UTask"


def test_postgres_audit_logs_immutable_trigger_rejects_update_and_delete():
    entry = AuditLog.objects.create(
        actor_id=str(uuid4()),
        action="LOGIN_SUCCESS",
        target_user_id=str(uuid4()),
        ip_address="127.0.0.1",
        user_agent="pytest",
        details={"source": "trigger-test"},
    )

    with pytest.raises(DatabaseError, match="Audit logs are immutable"):
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE audit_logs SET action = %s WHERE id = %s",
                    ["TAMPERED", str(entry.pk)],
                )

    with pytest.raises(DatabaseError, match="Audit logs are immutable"):
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM audit_logs WHERE id = %s", [str(entry.pk)])

    assert AuditLog.objects.filter(pk=entry.pk, action="LOGIN_SUCCESS").exists()
