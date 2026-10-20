import re
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.utils import timezone

from .errors import InvalidGitHubIdentity

GITHUB_ID_PATTERN = r"[1-9][0-9]{0,99}"
GITHUB_USERNAME_PATTERN = r"[a-zA-Z0-9]+(?:-[a-zA-Z0-9]+)*"


@dataclass(frozen=True)
class VerifiedAccountIdentity:
    user_id: UUID
    github_user_id: str
    github_username: str
    verified_at: datetime


def validate_user_id(user_id):
    if not isinstance(user_id, (str, UUID)):
        raise InvalidGitHubIdentity("user_id must be a nonzero UUID")
    try:
        parsed = UUID(user_id) if isinstance(user_id, str) else user_id
    except ValueError as exc:
        raise InvalidGitHubIdentity("user_id must be a nonzero UUID") from exc
    if parsed.int == 0:
        raise InvalidGitHubIdentity("user_id must be a nonzero UUID")
    return parsed


def validate_verified_identity(*, user_id, github_user_id, github_username, verified_at, now):
    """Validate an identity already verified by an internal provider adapter."""
    parsed_user_id = validate_user_id(user_id)
    if not isinstance(github_user_id, str) or not re.fullmatch(GITHUB_ID_PATTERN, github_user_id):
        raise InvalidGitHubIdentity("github_user_id must be a canonical positive ASCII integer")
    if (
        not isinstance(github_username, str)
        or not 1 <= len(github_username) <= 39
        or not re.fullmatch(GITHUB_USERNAME_PATTERN, github_username)
    ):
        raise InvalidGitHubIdentity(
            "github_username must be a GitHub login of at most 39 characters"
        )
    if (
        not isinstance(verified_at, datetime)
        or timezone.is_naive(verified_at)
        or not isinstance(now, datetime)
        or timezone.is_naive(now)
        or verified_at > now
    ):
        raise InvalidGitHubIdentity("verified_at must be timezone-aware and not in the future")
    return VerifiedAccountIdentity(
        user_id=parsed_user_id,
        github_user_id=github_user_id,
        github_username=github_username,
        verified_at=verified_at,
    )
