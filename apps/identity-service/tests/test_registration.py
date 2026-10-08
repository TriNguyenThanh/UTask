"""Registration input contracts and failure atomicity through the public endpoint."""

from uuid import uuid4

import pytest
from rest_framework.test import APIClient

from accounts.models import AuditLog, OutboxEvent, User, UserProfile, UserSession

pytestmark = [pytest.mark.integration, pytest.mark.django_db, pytest.mark.postgres]
URL = "/api/v1/auth/register"


@pytest.mark.parametrize("field", ["email", "username"])
def test_registration_rejects_duplicate_identity_without_partial_writes(signup_data, field):
    client = APIClient()
    first = client.post(URL, signup_data, format="json")
    assert first.status_code == 201, first.json()
    counts = [model.objects.count() for model in (User, UserProfile, OutboxEvent, AuditLog)]
    other = {**signup_data, "email": f"{uuid4().hex}@example.edu.vn", "username": uuid4().hex}
    other[field] = " " + signup_data[field].upper() + " "

    response = client.post(URL, other, format="json")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert [model.objects.count() for model in (User, UserProfile, OutboxEvent, AuditLog)] == counts
    assert not UserSession.objects.exists()


def test_registration_rejects_unsupported_idempotency_key(signup_data):
    response = APIClient().post(URL, signup_data, format="json", HTTP_IDEMPOTENCY_KEY=str(uuid4()))

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert not User.objects.exists()
    assert not OutboxEvent.objects.exists()
    assert not AuditLog.objects.exists()


@pytest.mark.parametrize(
    "field", ["email", "username", "password1", "password2", "first_name", "last_name"]
)
def test_registration_requires_contract_fields(signup_data, field):
    payload = dict(signup_data)
    payload.pop(field)
    response = APIClient().post(URL, payload, format="json")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert not User.objects.exists()


def test_registration_rejects_password_mismatch_without_creating_account(signup_data):
    response = APIClient().post(
        URL, {**signup_data, "password2": "DifferentStrong123!"}, format="json"
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert not User.objects.exists()
