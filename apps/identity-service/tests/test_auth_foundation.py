from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import AccountStatus, UserSession
from tests.helpers import create_user, login

pytestmark = [pytest.mark.integration, pytest.mark.django_db, pytest.mark.postgres]


@pytest.mark.parametrize(
    "change", ["revoked", "expired", "owner", "suspended", "deleted", "pending"]
)
def test_current_db_state_blocks_old_access(change):
    user = create_user()
    other = create_user()
    client = APIClient()
    login(client, user)
    session = UserSession.objects.get(user=user)
    if change == "revoked":
        session.is_revoked = True
        session.revoked_at = timezone.now()
        session.revoked_reason = "LOGOUT"
    elif change == "expired":
        session.created_at = timezone.now() - timedelta(days=8)
        session.expires_at = timezone.now() - timedelta(seconds=1)
    elif change == "owner":
        session.user = other
    elif change == "deleted":
        user.deleted_at = timezone.now()
    else:
        user.account_status = (
            AccountStatus.SUSPENDED if change == "suspended" else AccountStatus.PENDING_ACTIVATION
        )
    user.save()
    session.save()
    assert client.get("/users/me").status_code == 401
