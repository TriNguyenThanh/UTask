"""Regression for library-owned lockout and email verification state."""

from datetime import timedelta

import pytest
from allauth.account.models import EmailAddress
from axes.models import AccessAttempt, AccessAttemptExpiration
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.serializers.profiles import AdminUserSerializer
from accounts.services.profiles import public_users
from tests.helpers import PASSWORD, create_user, login

pytestmark = pytest.mark.integration


@pytest.mark.django_db
def test_axes_username_only_attempt_preserves_remaining_lock_and_expires():
    user, other = create_user(), create_user()
    expires_at = timezone.now() + timedelta(minutes=5)
    attempt = AccessAttempt.objects.create(
        username=str(user.pk),
        ip_address=None,
        user_agent="identity-legacy-lockout",
        http_accept="",
        path_info="/api/v1/auth/login",
        get_data="",
        post_data="",
        failures_since_start=5,
    )
    AccessAttempt.objects.filter(pk=attempt.pk).update(
        attempt_time=expires_at - timedelta(minutes=15)
    )
    AccessAttemptExpiration.objects.create(access_attempt=attempt, expires_at=expires_at)
    for field in ("email", "username"):
        response = APIClient().post(
            "/api/v1/auth/login", {field: getattr(user, field), "password": PASSWORD}, format="json"
        )
        assert response.status_code == 429
        assert response["Retry-After"] == "900"
    assert login(APIClient(), other).status_code == 200
    AccessAttempt.objects.filter(pk=attempt.pk).update(
        attempt_time=timezone.now() - timedelta(minutes=16)
    )
    assert login(APIClient(), user).status_code == 200


@pytest.mark.django_db
def test_email_verification_uses_current_allauth_address_and_preserves_api_boolean():
    user = create_user()
    assert user.is_email_verified is True
    EmailAddress.objects.filter(user=user).update(verified=False)
    assert user.is_email_verified is False
    EmailAddress.objects.create(user=user, email="other@example.edu.vn", verified=True)
    assert user.is_email_verified is False
    assert AdminUserSerializer(user).data["is_email_verified"] is False
    EmailAddress.objects.filter(user=user, email=user.email).update(verified=True)
    assert user.is_email_verified is True


@pytest.mark.django_db
def test_admin_verification_flag_uses_prefetch_without_extra_queries(django_assert_num_queries):
    create_user()
    create_user()
    users = list(public_users())
    with django_assert_num_queries(0):
        assert all(row["is_email_verified"] for row in AdminUserSerializer(users, many=True).data)
