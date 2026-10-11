"""Bad credential changes must preserve passwords and every existing session."""

from datetime import timedelta

import pytest
from allauth.account.forms import default_token_generator
from allauth.account.models import EmailConfirmation
from allauth.account.utils import user_pk_to_url_str
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import AuditLog, OutboxEvent, User, UserSession
from tests.helpers import NEW_PASSWORD, PASSWORD, create_user, login, mail_secret

pytestmark = [pytest.mark.integration, pytest.mark.django_db, pytest.mark.postgres]


@pytest.mark.parametrize(
    "fault", ["wrong-old-password", "same-password", "mismatch", "weak-password"]
)
def test_password_change_rejects_invalid_credentials_without_revocation(fault):
    user = create_user()
    client = APIClient()
    login(client, user)
    body = {"old_password": PASSWORD, "new_password1": NEW_PASSWORD, "new_password2": NEW_PASSWORD}
    if fault == "wrong-old-password":
        body["old_password"] = "WrongPassword123!"
    elif fault == "same-password":
        body["new_password1"] = body["new_password2"] = PASSWORD
    elif fault == "mismatch":
        body["new_password2"] = "OtherPassword123!"
    else:
        body["new_password1"] = body["new_password2"] = "weak"
    original = user.password

    response = client.post("/password-change", body, format="json")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    user.refresh_from_db()
    assert user.password == original
    assert UserSession.objects.filter(user=user, is_revoked=False).count() == 1
    assert not AuditLog.objects.filter(action="PASSWORD_CHANGED").exists()
    assert client.get("/users/me").status_code == 200


@pytest.mark.parametrize("fault", ["wrong-token", "malformed-uid", "mismatch", "weak-password"])
def test_reset_confirm_rejects_invalid_input_without_password_or_session_change(fault):
    user = create_user()
    login(APIClient(), user)
    user.refresh_from_db()
    original = user.password
    body = {
        "uid": user_pk_to_url_str(user),
        "token": default_token_generator.make_token(user),
        "new_password1": NEW_PASSWORD,
        "new_password2": NEW_PASSWORD,
    }
    if fault == "wrong-token":
        body["token"] = "invalid-token"
    elif fault == "malformed-uid":
        body["uid"] = "invalid-uid"
    elif fault == "mismatch":
        body["new_password2"] = "OtherPassword123!"
    else:
        body["new_password1"] = body["new_password2"] = "weak"

    response = APIClient().post("/password-reset/confirm", body, format="json")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    user.refresh_from_db()
    assert user.password == original
    assert UserSession.objects.filter(user=user, is_revoked=False).count() == 1
    assert not AuditLog.objects.filter(action="PASSWORD_RESET").exists()


@pytest.mark.parametrize("fault", ["unknown-key", "expired", "suspended", "deleted"])
def test_activation_rejects_ineligible_account_or_key(signup_data, fault):
    client = APIClient()
    assert client.post("/register", signup_data, format="json").status_code == 201
    user = User.objects.get(email=signup_data["email"])
    key = mail_secret(OutboxEvent.objects.get(event_type="identity.activation.requested"))["key"]
    status, code = 404, "RESOURCE_NOT_FOUND"
    if fault == "unknown-key":
        key = "invalid-key"
    elif fault == "expired":
        EmailConfirmation.objects.update(sent=timezone.now() - timedelta(days=8))
    else:
        status, code = 400, "INVALID_ACTIVATION_TOKEN"
        if fault == "suspended":
            user.account_status = "SUSPENDED"
        else:
            user.deleted_at = timezone.now()
        user.save()
    old_status = user.account_status

    response = client.post("/activate", {"key": key}, format="json")

    assert response.status_code == status
    assert response.json()["error"]["code"] == code
    user.refresh_from_db()
    assert user.account_status == old_status
    assert not user.is_email_verified
    assert not UserSession.objects.exists()
    assert not AuditLog.objects.filter(action="ACCOUNT_ACTIVATED").exists()
