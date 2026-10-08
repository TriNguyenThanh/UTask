"""Password hashing uses Argon2 for new passwords and upgrades legacy hashes."""

import pytest
from django.contrib.auth.hashers import identify_hasher, make_password
from rest_framework.test import APIClient

from accounts.models import User
from tests.helpers import create_user, login

pytestmark = pytest.mark.integration


@pytest.mark.django_db
def test_user_manager_hashes_new_passwords_with_argon2id():
    user = User.objects.create_user(
        email="argon2-user@example.edu",
        username="argon2-user",
        password="CorrectPassword123!",
    )

    assert identify_hasher(user.password).algorithm == "argon2"
    assert user.check_password("CorrectPassword123!")
    assert not user.check_password("WrongPassword123!")


@pytest.mark.django_db
@pytest.mark.parametrize("field", ["email", "username"])
def test_legacy_pbkdf2_user_can_log_in_and_check_password_upgrades_the_hash(field):
    user = create_user()
    user.password = make_password("LegacyPassword123!", hasher="pbkdf2_sha256")
    user.save(update_fields=("password",))
    assert identify_hasher(user.password).algorithm == "pbkdf2_sha256"

    client = APIClient()
    response = login(client, user, "LegacyPassword123!", field=field)
    assert response.json()["data"]["user"]["id"] == str(user.pk)

    user.refresh_from_db()
    assert identify_hasher(user.password).algorithm == "argon2"
    assert user.check_password("LegacyPassword123!")
    assert client.get("/api/v1/users/me").status_code == 200


@pytest.mark.django_db
def test_wrong_legacy_password_is_rejected_without_rehashing():
    user = User.objects.create_user(
        email="legacy-wrong@example.edu",
        username="legacy-wrong",
        password=None,
    )
    legacy_hash = make_password("LegacyPassword123!", hasher="pbkdf2_sha256")
    user.password = legacy_hash
    user.save(update_fields=("password",))

    assert not user.check_password("WrongPassword123!")

    user.refresh_from_db()
    assert user.password == legacy_hash
