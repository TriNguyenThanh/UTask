"""Two independent PostgreSQL connections verify credential mutation serialization."""

import pytest
from allauth.account.forms import default_token_generator
from allauth.account.utils import user_pk_to_url_str
from rest_framework.test import APIClient

from accounts.models import UserSession
from tests.helpers import NEW_PASSWORD, create_user, login, refresh_from_body, run_concurrent

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True),
    pytest.mark.postgres,
]


def test_refresh_competing_logout_never_leaves_live_child():
    user = create_user()
    browser = APIClient()
    response = login(browser, user)
    refresh = response.cookies["refresh_token"].value
    access = response.json()["data"]["access"]

    def logout():
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION="Bearer " + access)
        return client.post("/logout", {"refresh": refresh}, format="json").status_code

    statuses = run_concurrent(lambda: refresh_from_body(APIClient(), refresh).status_code, logout)
    assert statuses[0] in {200, 401}
    assert statuses[1] == 200
    assert not UserSession.objects.filter(user=user, is_revoked=False).exists()


def test_two_reset_confirms_have_only_one_success():
    user = create_user()
    login(APIClient(), user)
    user.refresh_from_db()
    body = {
        "uid": user_pk_to_url_str(user),
        "token": default_token_generator.make_token(user),
        "new_password1": NEW_PASSWORD,
        "new_password2": NEW_PASSWORD,
    }

    def confirm():
        return APIClient().post("/password-reset/confirm", body, format="json").status_code

    assert sorted(run_concurrent(confirm, confirm)) == [200, 400]
    user.refresh_from_db()
    assert user.check_password(NEW_PASSWORD)
    assert not UserSession.objects.filter(user=user, is_revoked=False).exists()
