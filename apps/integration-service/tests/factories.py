from datetime import timedelta

from django.utils import timezone

from infrastructure.github_app import TokenIdentity


def token_identity(
    github_user_id="123", github_username="Octo", access_token="ghu_test", refresh_token="ghr_test"
):
    return TokenIdentity(
        access_token,
        refresh_token,
        timezone.now() + timedelta(hours=8),
        timezone.now() + timedelta(days=180),
        github_user_id,
        github_username,
    )
