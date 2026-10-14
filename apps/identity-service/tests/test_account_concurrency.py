"""Real PostgreSQL locks prove actor role rechecks and admin/refresh serialization."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import uuid4

import pytest
from django.db import connections, transaction
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from accounts.models import AccountStatus, User, UserGlobalRole, UserSession
from accounts.services import administration
from authentication.services.session_service import require_current_session
from tests.helpers import create_user, login, refresh_from_body, run_concurrent

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True),
    pytest.mark.postgres,
]


def test_transaction_recheck_rejects_wrong_token_family():
    user = create_user()
    token = AccessToken(login(APIClient(), user).json()["data"]["access"])
    token["token_family"] = str(uuid4())
    with pytest.raises(AuthenticationFailed) as error:
        require_current_session(user, token)
    assert error.value.detail["code"] == "TOKEN_REVOKED"


def test_admin_actor_role_is_rechecked_after_waiting_for_lock(monkeypatch):
    actor = create_user(global_role_code="SYSTEM_ADMIN")
    target = create_user()
    token = login(APIClient(), actor).json()["data"]["access"]
    entered = Event()
    original = administration.lock_accounts

    def observed_lock(*args, **kwargs):
        entered.set()  # Request passed its HTTP permission; it now needs the DB lock.
        return original(*args, **kwargs)

    monkeypatch.setattr(administration, "lock_accounts", observed_lock)

    def worker():
        try:
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION="Bearer " + token)
            return client.patch(
                f"/admin/users/{target.pk}/status",
                {"status": "SUSPENDED", "reason": "race"},
                format="json",
            )
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=1) as pool:
        with transaction.atomic():
            User.objects.select_for_update().get(pk=actor.pk)
            future = pool.submit(worker)
            assert entered.wait(timeout=10)
            UserGlobalRole.objects.filter(user=actor, role__code="SYSTEM_ADMIN").delete()
        response = future.result(timeout=15)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN_ADMIN_ONLY"
    target.refresh_from_db()
    assert target.account_status == AccountStatus.ACTIVE


def test_refresh_competing_admin_suspend_never_leaves_live_session():
    admin = create_user(global_role_code="SYSTEM_ADMIN")
    target = create_user()
    admin_token = login(APIClient(), admin).json()["data"]["access"]
    raw = login(APIClient(), target).cookies["refresh_token"].value

    def suspend():
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION="Bearer " + admin_token)
        return client.patch(
            f"/admin/users/{target.pk}/status",
            {"status": "SUSPENDED", "reason": "race"},
            format="json",
        ).status_code

    results = run_concurrent(lambda: refresh_from_body(APIClient(), raw).status_code, suspend)
    assert results[0] in {200, 401}
    assert results[1] == 200
    assert not UserSession.objects.filter(user=target, is_revoked=False).exists()
