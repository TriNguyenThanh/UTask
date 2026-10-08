"""Shared test configuration for the Identity Service."""

from uuid import uuid4

import pytest
from django.core.cache import cache
from django.core.management import call_command
from rest_framework.test import APIClient

from tests.helpers import PASSWORD, create_user, login


@pytest.fixture
def signup_data():
    uid = uuid4().hex
    return {
        "email": f"{uid}@example.edu.vn",
        "username": uid,
        "password1": PASSWORD,
        "password2": PASSWORD,
        "first_name": "An",
        "last_name": "Nguyen",
    }


@pytest.fixture(autouse=True)
def seed_global_roles_for_database_tests(request):
    if request.node.get_closest_marker("django_db") is not None:
        request.getfixturevalue("db")
        call_command("seed_global_roles", verbosity=0)


@pytest.fixture(autouse=True)
def clear_throttle_cache():
    cache.clear()


@pytest.fixture
def authenticated_account(db):
    """Factory returning a user/client pair authenticated through the public login API."""

    def create(**attributes):
        user = create_user(**attributes)
        client = APIClient()
        login(client, user)
        return user, client

    return create
