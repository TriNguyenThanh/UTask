"""Classroom can verify an assigned teacher without reading Identity's database."""

import pytest
from rest_framework.test import APIClient

from accounts.models import AccountStatus
from tests.helpers import create_user, login


@pytest.mark.django_db
@pytest.mark.integration
@pytest.mark.parametrize("status", AccountStatus.values)
def test_public_teacher_profiles_expose_current_account_status(status):
    client = APIClient()
    login(client, create_user())
    teacher = create_user(global_role_code="TEACHER", account_status=status)

    detail = client.get(f"/users/{teacher.pk}")
    batch = client.post("/users/batch", {"user_ids": [str(teacher.pk)]}, format="json")

    assert detail.status_code == batch.status_code == 200
    for data in (detail.json()["data"], batch.json()["data"]["users"][0]):
        assert data["account_status"] == status
        assert data["roles"] == ["TEACHER"]
        assert {"password", "preferences", "token", "refresh"}.isdisjoint(data)
