import pytest
from rest_framework.test import APIClient

from tests.helpers import create_user, login

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db,
    pytest.mark.postgres,
]


def test_device_scope_remote_revoke_and_logout_all():
    user, other = create_user(), create_user()
    first, second, stranger = APIClient(), APIClient(), APIClient()
    login(first, user)
    login(second, user)
    login(stranger, other)
    first.cookies.clear()
    devices = first.get("/sessions").json()["data"]
    assert len(devices) == 2
    assert sum(device["is_current"] for device in devices) == 1
    target = next(device for device in devices if not device["is_current"])
    response = stranger.delete("/sessions/" + target["id"])
    assert response.status_code == 404
    assert first.delete("/sessions/" + target["id"]).status_code == 200
    assert second.get("/users/me").status_code == 401
    assert first.get("/users/me").status_code == 200
    assert first.post("/logout-all", {}, format="json").status_code == 200
    assert first.get("/users/me").status_code == 401
    assert stranger.get("/users/me").status_code == 200
    login(first, user)
    assert first.get("/users/me").status_code == 200
