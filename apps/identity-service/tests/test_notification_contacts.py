from uuid import uuid4

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from tests.helpers import create_user

ROUTE = "/api/v1/internal/users/notification-contacts"


def test_notification_contact_token_fail_closed(settings):
    client = APIClient()
    settings.NOTIFICATION_SERVICE_TOKEN = ""
    assert client.post(ROUTE, {}, format="json").status_code == 403
    settings.NOTIFICATION_SERVICE_TOKEN = "secret"
    assert client.post(ROUTE, {}, format="json", HTTP_X_SERVICE_TOKEN="wrong").status_code == 403
    assert client.post(ROUTE, {}, format="json", HTTP_X_SERVICE_TOKEN="secret").status_code == 400


@pytest.mark.django_db
def test_contacts_status_deleted_missing_and_batch_validation(settings):
    settings.NOTIFICATION_SERVICE_TOKEN = "secret"
    active = create_user()
    suspended = create_user(account_status="SUSPENDED")
    deleted = create_user(deleted_at=timezone.now())
    client = APIClient()
    client.credentials(HTTP_X_SERVICE_TOKEN="secret")
    response = client.post(
        ROUTE,
        {"user_ids": [str(user.pk) for user in [active, suspended, deleted]] + [str(uuid4())]},
        format="json",
    )
    assert response.status_code == 200
    users = {item["user_id"]: item for item in response.json()["users"]}
    assert set(users) == {str(active.pk), str(suspended.pk)}
    assert users[str(active.pk)]["email"] == active.email
    assert users[str(suspended.pk)]["account_status"] == "SUSPENDED"
    for values in [[], [str(uuid4())] * 101, ["invalid"]]:
        assert client.post(ROUTE, {"user_ids": values}, format="json").status_code == 400


def test_notification_session_key_allowed(settings):
    settings.IDENTITY_NOTIFICATION_SERVICE_KEY = "notification-key"
    client = APIClient()
    reply = client.post(
        "/api/v1/internal/auth/session-status",
        {},
        format="json",
        HTTP_X_SERVICE_KEY="notification-key",
    )
    assert reply.status_code == 200
    assert reply.json()["data"]["active"] is False
    settings.IDENTITY_NOTIFICATION_SERVICE_KEY = ""
    assert (
        client.post(
            "/api/v1/internal/auth/session-status",
            {},
            format="json",
            HTTP_X_SERVICE_KEY="notification-key",
        ).status_code
        == 403
    )
