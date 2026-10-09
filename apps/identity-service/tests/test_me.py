import pytest
from rest_framework.test import APIClient

from tests.helpers import create_user, login

pytestmark = [pytest.mark.integration, pytest.mark.django_db, pytest.mark.postgres]


def test_me_is_read_only_and_returns_owner():
    user = create_user(first_name="An", last_name="Nguyen")
    other = create_user()
    client = APIClient()
    login(client, user)
    response = client.get("/users/me")
    assert response.json()["data"]["id"] != str(other.pk)
    assert response.json()["data"]["first_name"] == "An"
    assert (
        client.patch("/users/me", {"roles": ["SYSTEM_ADMIN"]}, format="json").status_code
        == 400
    )


def test_me_requires_bearer():
    response = APIClient().get("/users/me")
    assert response.status_code == 401
    assert response["WWW-Authenticate"].startswith("Bearer")
